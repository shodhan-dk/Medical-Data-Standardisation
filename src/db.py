"""
Database loader (FR-4.1). SQLite for the take-home; schema and upsert
pattern translate directly to Postgres/BigQuery (see /docs/architecture.md
'Storage layer' for the production choice and why).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .schema import LAB_RESULTS_COLUMNS, MEDICATIONS_COLUMNS, RECORDS_COLUMNS

DB_PATH = Path(__file__).resolve().parent.parent / "veritas_claims.db"


def _cols_sql(columns: list[str]) -> str:
    return ", ".join(f'"{c}" TEXT' for c in columns)


def get_connection(db_path: str | Path = DB_PATH) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute(f'CREATE TABLE IF NOT EXISTS records ('
                 f'"record_id" TEXT PRIMARY KEY, {_cols_sql([c for c in RECORDS_COLUMNS if c != "record_id"])})')
    conn.execute(f'CREATE TABLE IF NOT EXISTS lab_results ('
                 f'"result_id" TEXT PRIMARY KEY, {_cols_sql([c for c in LAB_RESULTS_COLUMNS if c != "result_id"])})')
    conn.execute(f'CREATE TABLE IF NOT EXISTS medications ('
                 f'"medication_id" TEXT PRIMARY KEY, {_cols_sql([c for c in MEDICATIONS_COLUMNS if c != "medication_id"])})')
    conn.execute('CREATE TABLE IF NOT EXISTS dead_letters ('
                 '"id" INTEGER PRIMARY KEY AUTOINCREMENT, "source_file" TEXT, '
                 '"reason" TEXT, "raised_at" TEXT, "detail" TEXT)')
    conn.execute('CREATE TABLE IF NOT EXISTS pipeline_runs ('
                 '"run_id" TEXT PRIMARY KEY, "started_at" TEXT, "finished_at" TEXT, '
                 '"files_total" INTEGER, "files_success" INTEGER, "files_failed" INTEGER, '
                 '"records_total" INTEGER, "records_flagged" INTEGER, "duplicates_suppressed" INTEGER)')
    conn.commit()


def _upsert(conn: sqlite3.Connection, table: str, pk: str, columns: list[str], row: dict) -> None:
    """INSERT ... ON CONFLICT(pk) DO UPDATE — re-running the pipeline on
    the same input never creates a duplicate row (NFR-3.2 Idempotency);
    it just refreshes the record with the latest processed values."""
    cols = columns  # includes pk
    quoted_cols = ", ".join(f'"{c}"' for c in cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    updates = ", ".join(f'"{c}"=excluded."{c}"' for c in cols if c != pk)
    sql = (f'INSERT INTO {table} ({quoted_cols}) '
           f'VALUES ({placeholders}) '
           f'ON CONFLICT("{pk}") DO UPDATE SET {updates}')
    safe_row = {c: row.get(c) for c in cols}
    conn.execute(sql, safe_row)


def upsert_record(conn: sqlite3.Connection, row: dict) -> None:
    _upsert(conn, "records", "record_id", RECORDS_COLUMNS, row)


def upsert_lab_result(conn: sqlite3.Connection, row: dict) -> None:
    _upsert(conn, "lab_results", "result_id", LAB_RESULTS_COLUMNS, row)


def upsert_medication(conn: sqlite3.Connection, row: dict) -> None:
    _upsert(conn, "medications", "medication_id", MEDICATIONS_COLUMNS, row)


def insert_dead_letter(conn: sqlite3.Connection, dl) -> None:
    conn.execute(
        "INSERT INTO dead_letters (source_file, reason, raised_at, detail) VALUES (?, ?, ?, ?)",
        (dl.source_file, dl.reason, dl.raised_at, dl.detail),
    )


def record_run(conn: sqlite3.Connection, stats: dict) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO pipeline_runs "
        "(run_id, started_at, finished_at, files_total, files_success, files_failed, "
        "records_total, records_flagged, duplicates_suppressed) VALUES "
        "(:run_id, :started_at, :finished_at, :files_total, :files_success, :files_failed, "
        ":records_total, :records_flagged, :duplicates_suppressed)",
        stats,
    )
