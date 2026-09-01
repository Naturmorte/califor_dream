"""Deterministic, network-free tests for the ingestion/event-derivation
pipeline. These prove the acceptance criteria in
docs/00-gate0-and-first-milestone.md Section I that don't require live data:
idempotency (#2), effective_at != detected_at (#3), event derivation on
change (#4)."""

import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from services.ingestion import db, pipeline  # noqa: E402


def make_conn():
    conn = sqlite3.connect(":memory:")
    db.init_schema(conn)
    return conn


PERMIT_V1 = {
    "permit_number": "TEST0001",
    "status": "filed",
    "filed_date": "2026-01-01T00:00:00.000",
    "issued_date": None,
    "completed_date": None,
    "last_permit_activity_date": "2026-01-01T00:00:00.000",
    "block": "1234",
    "lot": "001",
}

PERMIT_V2_ISSUED = {
    **PERMIT_V1,
    "status": "issued",
    "issued_date": "2026-01-15T00:00:00.000",
    "last_permit_activity_date": "2026-01-15T00:00:00.000",
}


def test_first_ingest_creates_raw_record_and_creation_event(monkeypatch):
    conn = make_conn()
    monkeypatch.setattr(
        pipeline.socrata, "fetch_records", lambda *a, **k: iter([PERMIT_V1])
    )

    result = pipeline.ingest_source(conn, "building_permits")

    assert result["fetched_count"] == 1
    assert result["new_version_count"] == 1
    assert result["unchanged_count"] == 0
    assert result["event_count"] == 1

    raw = conn.execute("SELECT effective_at, fetched_at FROM raw_record").fetchone()
    effective_at, fetched_at = raw
    assert effective_at == "2026-01-01T00:00:00.000"
    assert effective_at != fetched_at  # source date vs pipeline-run time, kept distinct

    ev = conn.execute("SELECT event_type, effective_at FROM event").fetchone()
    assert ev[0] == "PERMIT_FILED"
    assert ev[1] == "2026-01-01T00:00:00.000"


def test_rerun_with_unchanged_data_is_idempotent(monkeypatch):
    conn = make_conn()
    monkeypatch.setattr(
        pipeline.socrata, "fetch_records", lambda *a, **k: iter([PERMIT_V1])
    )
    pipeline.ingest_source(conn, "building_permits")
    result2 = pipeline.ingest_source(conn, "building_permits")

    assert result2["new_version_count"] == 0
    assert result2["unchanged_count"] == 1
    assert result2["event_count"] == 0

    raw_count = conn.execute("SELECT COUNT(*) FROM raw_record").fetchone()[0]
    assert raw_count == 1  # no duplicate row written


def test_status_change_produces_specific_event_with_new_effective_at(monkeypatch):
    conn = make_conn()
    monkeypatch.setattr(
        pipeline.socrata, "fetch_records", lambda *a, **k: iter([PERMIT_V1])
    )
    pipeline.ingest_source(conn, "building_permits")

    monkeypatch.setattr(
        pipeline.socrata, "fetch_records", lambda *a, **k: iter([PERMIT_V2_ISSUED])
    )
    result2 = pipeline.ingest_source(conn, "building_permits")

    assert result2["new_version_count"] == 1
    # issued_date changed AND status changed -> two distinct real facts
    assert result2["event_count"] == 2

    raw_count = conn.execute("SELECT COUNT(*) FROM raw_record").fetchone()[0]
    assert raw_count == 2  # append-only: old version kept, new version added

    event_types = {
        r[0] for r in conn.execute("SELECT event_type FROM event").fetchall()
    }
    assert "PERMIT_ISSUED" in event_types
    assert "PERMIT_STATUS_CHANGED" in event_types

    issued_event = conn.execute(
        "SELECT effective_at, detected_at FROM event WHERE event_type='PERMIT_ISSUED'"
    ).fetchone()
    assert issued_event[0] == "2026-01-15T00:00:00.000"
    assert issued_event[0] != issued_event[1]  # effective_at != detected_at


def test_apn_used_as_entity_id():
    row = PERMIT_V1
    apn = pipeline._apn(row, ("block", "lot"))
    assert apn == "1234001"
