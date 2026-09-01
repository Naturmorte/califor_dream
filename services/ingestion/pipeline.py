"""Ingestion + event-derivation pipeline.

Core discipline (docs/00-gate0-and-first-milestone.md Section E/H):
  - never rewrite an unchanged raw record (append-only, content_hash keyed)
  - effective_at (when the fact became true, per the source) is always kept
    separate from detected_at (when our pipeline noticed it)
  - idempotent: re-running against unchanged upstream data produces zero
    new raw_record rows and zero new events
"""

import hashlib
import json
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Iterable, Optional

from services.ingestion import socrata
from services.ingestion.config import SOCRATA_DOMAIN, SOURCES

SCHEMA_VERSION = "1"
PARSER_VERSION = "1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# Socrata system/freshness metadata that changes on every platform refresh
# even when the underlying record is substantively unchanged. Excluded from
# content_hash so a nightly Socrata reload doesn't masquerade as a real
# change (would otherwise defeat idempotency and spam false events).
VOLATILE_FIELDS = {"data_as_of", "data_loaded_at"}


def _substantive_row(row: dict, extra_excludes: frozenset = frozenset()) -> dict:
    excludes = VOLATILE_FIELDS | extra_excludes
    return {
        k: v for k, v in row.items()
        if k not in excludes and not k.startswith(":")
    }


def _content_hash(row: dict, config: dict) -> str:
    extra = frozenset(config.get("extra_hash_excludes", []))
    canonical = json.dumps(
        _substantive_row(row, extra), sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _record_id(row: dict, config: dict) -> tuple:
    """Returns (id, was_fallback). Falls back to a composite key derived
    from other fields when the dataset's nominal id_field is null on this
    row - a real, observed condition (not hypothetical), see config.py."""
    val = row.get(config["id_field"])
    if val not in (None, ""):
        return str(val), False
    fallback_fields = config.get("fallback_id_fields") or []
    if not fallback_fields:
        raise ValueError(
            f"Row missing {config['id_field']} and no fallback_id_fields configured: {row}"
        )
    basis = "|".join(str(row.get(f, "")) for f in fallback_fields)
    digest = hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]
    return f"composite:{digest}", True


def _apn(row: dict, apn_fields: tuple) -> Optional[str]:
    parts = [row.get(f) for f in apn_fields]
    if any(p is None for p in parts):
        return None
    return "".join(str(p) for p in parts)


def _pick_effective_at(row: dict, config: dict) -> Optional[str]:
    """Best-known 'this happened' timestamp for a full record snapshot:
    the most recent non-null value among the configured date fields."""
    candidates = [row.get(f) for f in config["date_fields"] if row.get(f)]
    if not candidates:
        return None
    return max(candidates)


def _build_where(config: dict, since: Optional[str]) -> Optional[str]:
    if not since:
        return None
    watermark = config.get("watermark_field") or config["primary_date_field"]
    return f"{watermark} >= '{since}'"


def ingest_source(
    conn: sqlite3.Connection,
    source_key: str,
    since: Optional[str] = None,
    max_records: Optional[int] = None,
    job_id: Optional[str] = None,
    where_override: Optional[str] = None,
) -> dict:
    config = SOURCES[source_key]
    job_id = job_id or str(uuid.uuid4())
    started_at = _now_iso()

    conn.execute(
        "INSERT INTO ingestion_job (job_id, source_key, started_at, status) "
        "VALUES (?, ?, ?, 'running')",
        (job_id, source_key, started_at),
    )
    conn.commit()

    fetched_count = 0
    new_version_count = 0
    unchanged_count = 0
    event_count = 0
    fallback_id_count = 0

    where = where_override if where_override is not None else _build_where(config, since)
    # explicit $order is required for stable offset pagination - without it
    # Socrata can re-serve/skip rows across pages (confirmed live, 2026-09-01:
    # caused 2842 fetched rows for 983 distinct code_violations records).
    # order matters beyond pagination stability for snapshot-style sources
    # (e.g. Assessor roll): rows must arrive oldest-version-first per entity
    # so "most recently inserted" == "most recent real version" when diffing.
    order_by = config.get("order_by", config["id_field"])
    rows = socrata.fetch_records(
        SOCRATA_DOMAIN,
        config["dataset_id"],
        where=where,
        order=order_by,
        max_records=max_records,
    )

    cur = conn.cursor()
    for row in rows:
        fetched_count += 1
        original_record_id, was_fallback = _record_id(row, config)
        if was_fallback:
            fallback_id_count += 1
        content_hash = _content_hash(row, config)

        cur.execute(
            "SELECT 1 FROM raw_record WHERE source_id=? AND original_record_id=? "
            "AND content_hash=?",
            (config["source_id"], original_record_id, content_hash),
        )
        if cur.fetchone():
            unchanged_count += 1
            continue

        cur.execute(
            "SELECT raw_payload FROM raw_record WHERE source_id=? AND "
            "original_record_id=? ORDER BY fetched_at DESC LIMIT 1",
            (config["source_id"], original_record_id),
        )
        prev_row = cur.fetchone()
        previous_payload = json.loads(prev_row[0]) if prev_row else None

        fetched_at = _now_iso()
        effective_at = _pick_effective_at(row, config)
        raw_payload = json.dumps(row, sort_keys=True)

        cur.execute(
            """INSERT INTO raw_record
               (source_id, source_name, original_record_id, fetched_at,
                effective_at, published_at, raw_payload, content_hash,
                schema_version, parser_version, jurisdiction, record_type,
                ingestion_job_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                config["source_id"],
                config["source_name"],
                original_record_id,
                fetched_at,
                effective_at,
                row.get("data_as_of"),
                raw_payload,
                content_hash,
                SCHEMA_VERSION,
                PARSER_VERSION,
                config["jurisdiction"],
                config["record_type"],
                job_id,
            ),
        )
        new_version_count += 1

        events = _derive_events(
            row=row,
            previous_row=previous_payload,
            config=config,
            source_key=source_key,
            original_record_id=original_record_id,
            detected_at=fetched_at,
            job_id=job_id,
        )
        for ev in events:
            cur.execute(
                """INSERT INTO event
                   (event_id, entity_id, source_id, original_record_id,
                    event_type, previous_value, new_value, effective_at,
                    detected_at, source, confidence, ingestion_job_id)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    ev["event_id"],
                    ev["entity_id"],
                    config["source_id"],
                    original_record_id,
                    ev["event_type"],
                    ev["previous_value"],
                    ev["new_value"],
                    ev["effective_at"],
                    ev["detected_at"],
                    config["source_name"],
                    ev["confidence"],
                    job_id,
                ),
            )
            event_count += 1

    finished_at = _now_iso()
    conn.execute(
        """UPDATE ingestion_job SET finished_at=?, fetched_count=?,
           new_version_count=?, unchanged_count=?, event_count=?, status='done'
           WHERE job_id=?""",
        (finished_at, fetched_count, new_version_count, unchanged_count, event_count, job_id),
    )
    conn.commit()

    return {
        "job_id": job_id,
        "source_key": source_key,
        "fetched_count": fetched_count,
        "new_version_count": new_version_count,
        "unchanged_count": unchanged_count,
        "event_count": event_count,
        "fallback_id_count": fallback_id_count,
        "started_at": started_at,
        "finished_at": finished_at,
    }


def _derive_events(
    row: dict,
    previous_row: Optional[dict],
    config: dict,
    source_key: str,
    original_record_id: str,
    detected_at: str,
    job_id: str,
) -> Iterable[dict]:
    apn = _apn(row, config["apn_fields"])
    entity_id = apn or f"{source_key}:{original_record_id}"

    if previous_row is None:
        primary_date = row.get(config["primary_date_field"])
        yield {
            "event_id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "event_type": config["creation_event_type"],
            "previous_value": None,
            "new_value": json.dumps(row, sort_keys=True),
            "effective_at": primary_date,
            "detected_at": detected_at,
            "confidence": 1.0 if primary_date else 0.5,
        }
        return

    for field, event_type in config["event_rules"]:
        old_val = previous_row.get(field)
        new_val = row.get(field)
        if old_val == new_val:
            continue
        is_date_field = field in config["date_fields"]
        effective_at = new_val if (is_date_field and new_val) else None
        confidence = 1.0 if effective_at else None
        if effective_at is None:
            # non-date field changed on a snapshot-style source (e.g. assessor
            # roll assessed value): anchor to the snapshot's own year rather
            # than "today", or every historical backfill year would otherwise
            # collapse to today's ingestion timestamp - misleading for any
            # future backtest that reads effective_at as "when this was true".
            year_field = config.get("snapshot_year_field")
            if year_field and row.get(year_field):
                effective_at = f"{row[year_field]}-01-01T00:00:00"
                confidence = 0.7  # approximate: roll year, not exact day
            else:
                effective_at = detected_at  # only proof we have: we saw it now
                confidence = 0.5
        yield {
            "event_id": str(uuid.uuid4()),
            "entity_id": entity_id,
            "event_type": event_type,
            "previous_value": json.dumps(old_val),
            "new_value": json.dumps(new_val),
            "effective_at": effective_at,
            "detected_at": detected_at,
            "confidence": confidence,
        }
