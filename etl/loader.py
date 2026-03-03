"""PostgreSQL bulk loader using COPY FROM STDIN."""

from __future__ import annotations

import logging
from typing import Any

import psycopg2

from etl.config import PgConfig
from etl.focus_parser import FOCUS_COLUMNS, rows_to_copy_buffer

logger = logging.getLogger(__name__)

# Columns for COPY (all FOCUS columns + source_file; id and loaded_at are auto-generated)
COPY_COLUMNS = FOCUS_COLUMNS + ["source_file"]


def get_connection(config: PgConfig):
    """Create a new PostgreSQL connection."""
    return psycopg2.connect(config.dsn)


def bulk_load(conn, rows: list[list[Any]], batch_size: int = 10000) -> int:
    """Load rows into oci_finops_reports using COPY FROM STDIN.

    Returns the number of rows loaded.
    """
    if not rows:
        return 0

    total_loaded = 0
    columns_str = ", ".join(COPY_COLUMNS)
    copy_sql = f"COPY oci_finops_reports ({columns_str}) FROM STDIN WITH (FORMAT text, NULL '\\N')"

    # Process in batches
    for i in range(0, len(rows), batch_size):
        batch = rows[i : i + batch_size]
        buf = rows_to_copy_buffer(batch)

        with conn.cursor() as cur:
            cur.copy_expert(copy_sql, buf)

        total_loaded += len(batch)
        logger.debug("Loaded batch: %d rows (total: %d)", len(batch), total_loaded)

    conn.commit()
    logger.info("Bulk loaded %d rows into oci_finops_reports", total_loaded)
    return total_loaded


def refresh_materialized_views(conn) -> None:
    """Refresh all FOCUS materialized views after data load."""
    logger.info("Refreshing materialized views...")
    with conn.cursor() as cur:
        cur.execute("SELECT refresh_finops_views()")
    conn.commit()
    logger.info("Materialized views refreshed")


def run_migrations(conn, migrations_dir: str = "db/migrations") -> None:
    """Run all SQL migration files in order."""
    from pathlib import Path

    mig_path = Path(migrations_dir)
    if not mig_path.exists():
        logger.error("Migrations directory not found: %s", migrations_dir)
        return

    sql_files = sorted(mig_path.glob("*.sql"))
    for sql_file in sql_files:
        logger.info("Running migration: %s", sql_file.name)
        with open(sql_file) as f:
            sql = f.read()
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    logger.info("All %d migrations applied", len(sql_files))
