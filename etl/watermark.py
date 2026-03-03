"""ETL watermark tracking — records which files have been loaded."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def get_loaded_files(conn) -> set[str]:
    """Return the set of file paths that have been successfully loaded."""
    with conn.cursor() as cur:
        cur.execute("SELECT file_path FROM etl_watermark WHERE status = 'success'")
        return {row[0] for row in cur.fetchall()}


def mark_loaded(conn, file_path: str, file_size: int, row_count: int, status: str = "success") -> None:
    """Record a file as loaded in the watermark table."""
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO etl_watermark (file_path, file_size, loaded_at, row_count, status)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (file_path) DO UPDATE SET
                file_size = EXCLUDED.file_size,
                loaded_at = EXCLUDED.loaded_at,
                row_count = EXCLUDED.row_count,
                status = EXCLUDED.status
            """,
            (file_path, file_size, datetime.now(timezone.utc), row_count, status),
        )
    conn.commit()
    logger.info("Watermark %s: %s (%d rows, %s)", status, file_path, row_count, _human_size(file_size))


def mark_failed(conn, file_path: str, file_size: int) -> None:
    """Record a file as failed in the watermark table."""
    mark_loaded(conn, file_path, file_size, row_count=0, status="failed")


def get_watermark_summary(conn) -> dict:
    """Return summary statistics from the watermark table."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT
                status,
                COUNT(*) AS file_count,
                COALESCE(SUM(row_count), 0) AS total_rows,
                COALESCE(SUM(file_size), 0) AS total_bytes
            FROM etl_watermark
            GROUP BY status
        """)
        summary = {}
        for row in cur.fetchall():
            summary[row[0]] = {"file_count": row[1], "total_rows": row[2], "total_bytes": row[3]}
        return summary


def _human_size(size_bytes: int) -> str:
    """Format bytes into a human-readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
