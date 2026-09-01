"""Storage layer for Phase 1.

Uses SQLite, not the PostgreSQL named in docs/00-gate0-and-first-milestone.md
Section D. Deviation reason: no verified credentials for the local Postgres
17.6 instance found running on this machine, and no time budget in an
autonomous run to chase that down. SQLite satisfies every Phase 1 acceptance
criterion (idempotency, effective_at vs detected_at separation, event
derivation) with zero setup friction. The schema below is plain SQL with no
SQLite-only extensions (JSON stored as TEXT, no JSONB), so migrating to
Postgres later is a schema+driver swap, not a redesign. Recorded as an
assumption/deviation, not hidden.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "ingestion.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS raw_record (
    source_id           TEXT NOT NULL,
    source_name          TEXT NOT NULL,
    original_record_id  TEXT NOT NULL,
    fetched_at           TEXT NOT NULL,
    effective_at          TEXT,
    published_at          TEXT,
    raw_payload            TEXT NOT NULL,
    content_hash           TEXT NOT NULL,
    schema_version          TEXT NOT NULL,
    parser_version           TEXT NOT NULL,
    jurisdiction              TEXT NOT NULL,
    record_type                TEXT NOT NULL,
    ingestion_job_id            TEXT NOT NULL,
    PRIMARY KEY (source_id, original_record_id, content_hash)
);

CREATE INDEX IF NOT EXISTS idx_raw_record_lookup
    ON raw_record (source_id, original_record_id, fetched_at);

CREATE TABLE IF NOT EXISTS event (
    event_id           TEXT PRIMARY KEY,
    entity_id            TEXT NOT NULL,
    source_id             TEXT NOT NULL,
    original_record_id   TEXT NOT NULL,
    event_type             TEXT NOT NULL,
    previous_value          TEXT,
    new_value                 TEXT NOT NULL,
    effective_at              TEXT,
    detected_at                TEXT NOT NULL,
    source                      TEXT NOT NULL,
    confidence                   REAL NOT NULL,
    ingestion_job_id              TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_event_entity ON event (entity_id, effective_at);

CREATE TABLE IF NOT EXISTS ingestion_job (
    job_id       TEXT PRIMARY KEY,
    source_key   TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    fetched_count       INTEGER,
    new_version_count   INTEGER,
    unchanged_count      INTEGER,
    event_count            INTEGER,
    status                   TEXT NOT NULL,
    notes                     TEXT
);
"""


def connect(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()
