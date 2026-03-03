"""Main ETL orchestrator — coordinates file discovery, parsing, and loading."""

from __future__ import annotations

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from etl.config import AppConfig, load_config
from etl.focus_parser import parse_focus_csv
from etl.loader import bulk_load, get_connection, refresh_materialized_views, run_migrations
from etl.oci_client import OciObjectStorageClient
from etl.watermark import get_loaded_files, get_watermark_summary, mark_failed, mark_loaded

logger = logging.getLogger(__name__)


def run_etl(config: AppConfig, dry_run: bool = False, backfill: bool = False) -> dict:
    """Run the ETL pipeline.

    Args:
        config: Application configuration.
        dry_run: If True, list files to load but don't actually load them.
        backfill: If True, load all historical data. If False, only load new files.

    Returns:
        Summary dict with files_found, files_loaded, rows_loaded, errors.
    """
    summary = {"files_found": 0, "files_skipped": 0, "files_loaded": 0, "rows_loaded": 0, "errors": []}

    # Connect to PostgreSQL
    conn = get_connection(config.pg)

    try:
        # Get already-loaded files
        loaded_files = get_loaded_files(conn) if not backfill else set()
        logger.info("Watermark: %d files previously loaded", len(loaded_files))

        # List available FOCUS report files from OCI Object Storage
        oci_client = OciObjectStorageClient(config.oci)
        report_files = oci_client.list_focus_reports(year=config.etl.focus_report_year)
        summary["files_found"] = len(report_files)

        # Filter out already-loaded files
        new_files = [f for f in report_files if f.name not in loaded_files]
        summary["files_skipped"] = len(report_files) - len(new_files)
        logger.info("New files to load: %d (skipping %d already loaded)", len(new_files), summary["files_skipped"])

        if dry_run:
            logger.info("=== DRY RUN — would load these files: ===")
            for f in new_files:
                logger.info("  %s (%d bytes)", f.name, f.size)
            return summary

        # Process each file
        for report_file in new_files:
            try:
                logger.info("Processing: %s", report_file.name)

                # Download to temp directory
                local_path = oci_client.download_file(report_file.name, config.etl.temp_dir)

                # Parse the CSV
                rows = list(parse_focus_csv(local_path, source_file=report_file.name))
                row_count = len(rows)

                if row_count == 0:
                    logger.warning("No rows parsed from %s, skipping", report_file.name)
                    mark_loaded(conn, report_file.name, report_file.size, 0, status="empty")
                    continue

                # Bulk load into PostgreSQL
                loaded = bulk_load(conn, rows, batch_size=config.etl.batch_size)
                mark_loaded(conn, report_file.name, report_file.size, loaded)

                summary["files_loaded"] += 1
                summary["rows_loaded"] += loaded
                logger.info("Loaded %d rows from %s", loaded, report_file.name)

                # Clean up temp file
                local_path.unlink(missing_ok=True)

            except Exception as e:
                logger.error("Failed to process %s: %s", report_file.name, e, exc_info=True)
                summary["errors"].append({"file": report_file.name, "error": str(e)})
                conn.rollback()
                mark_failed(conn, report_file.name, report_file.size)

        # Refresh materialized views after loading
        if summary["files_loaded"] > 0:
            try:
                refresh_materialized_views(conn)
            except Exception as e:
                logger.error("Failed to refresh materialized views: %s", e, exc_info=True)
                summary["errors"].append({"file": "materialized_views", "error": str(e)})

    finally:
        conn.close()

    # Log summary
    logger.info("=== ETL Summary ===")
    logger.info("  Files found:   %d", summary["files_found"])
    logger.info("  Files skipped: %d", summary["files_skipped"])
    logger.info("  Files loaded:  %d", summary["files_loaded"])
    logger.info("  Rows loaded:   %d", summary["rows_loaded"])
    if summary["errors"]:
        logger.warning("  Errors:        %d", len(summary["errors"]))
        for err in summary["errors"]:
            logger.warning("    %s: %s", err["file"], err["error"])

    return summary


def init_database(config: AppConfig) -> None:
    """Run database migrations to initialize the schema."""
    conn = get_connection(config.pg)
    try:
        run_migrations(conn)
    finally:
        conn.close()


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="OCI FinOps ETL Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="List files to load without loading them")
    parser.add_argument("--backfill", action="store_true", help="Re-load all files (ignore watermark)")
    parser.add_argument("--init-db", action="store_true", help="Run database migrations")
    parser.add_argument("--year", type=str, help="Filter reports by year (overrides FOCUS_REPORT_YEAR)")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    config = load_config()

    if args.year:
        # Override the year filter
        config = AppConfig(
            oci=config.oci,
            pg=config.pg,
            etl=type(config.etl)(
                batch_size=config.etl.batch_size,
                temp_dir=config.etl.temp_dir,
                focus_report_year=args.year,
            ),
            notification=config.notification,
        )

    if args.init_db:
        logger.info("Initializing database...")
        init_database(config)
        logger.info("Database initialized")
        return

    summary = run_etl(config, dry_run=args.dry_run, backfill=args.backfill)

    if summary["errors"] and not args.dry_run:
        sys.exit(1)


if __name__ == "__main__":
    main()
