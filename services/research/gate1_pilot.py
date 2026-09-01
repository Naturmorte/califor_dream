"""Gate 1 pilot: does anything in the ingested signal set predict a property
sale better than a naive baseline?

Scope, stated plainly (see docs/02-gate1-pilot-report.md for the full writeup):
  - PILOT, not a full Gate 1 run. Universe is the ~861 parcels already
    ingested in Phase 1b (docs/01b), which are geographically clustered
    (lowest block/lot numbers first, an artifact of how that backfill was
    paginated) - not a representative citywide sample. Results here say
    something about methodology and about this specific cluster of parcels,
    not about San Francisco in general.
  - Task A only (sale within ~365 days of T0), per docs/00 Section F - no
    price label exists in the free source set, so no discount task is
    attempted.
  - T0 = the 2023 closed roll. Label = a new current_sales_date appearing in
    the 2024 closed roll that wasn't present as of the 2023 roll.
"""

import json
import sqlite3
from datetime import date

from services.ingestion import db
from services.ingestion.pipeline import ingest_source

T0_YEAR = "2023"
LABEL_YEAR = "2024"
LOOKBACK_WHERE_START = "2022-01-01T00:00:00"
LOOKBACK_WHERE_END = "2024-01-01T00:00:00"


def load_assessor_rows_by_parcel(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT raw_payload FROM raw_record WHERE source_id='datasf_assessor_secured_roll'"
    ).fetchall()
    by_parcel = {}
    for (payload,) in rows:
        d = json.loads(payload)
        by_parcel.setdefault(d["parcel_number"], {})[d["closed_roll_year"]] = d
    return by_parcel


def get_blocks(by_parcel: dict) -> list:
    blocks = sorted({v["block"] for years in by_parcel.values() for v in years.values()})
    return blocks


def pull_historical_permits_and_violations(conn: sqlite3.Connection, blocks: list):
    block_list = ",".join(f"'{b}'" for b in blocks)
    permits_where = (
        f"filed_date >= '{LOOKBACK_WHERE_START}' AND filed_date < '{LOOKBACK_WHERE_END}' "
        f"AND block in ({block_list})"
    )
    violations_where = (
        f"date_filed >= '{LOOKBACK_WHERE_START}' AND date_filed < '{LOOKBACK_WHERE_END}' "
        f"AND block in ({block_list})"
    )
    r1 = ingest_source(conn, "building_permits", where_override=permits_where)
    r2 = ingest_source(conn, "code_violations", where_override=violations_where)
    return r1, r2


def count_events(conn: sqlite3.Connection, apn: str, event_type_prefix: str, start: str, end: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM event WHERE entity_id=? AND event_type LIKE ? "
        "AND effective_at >= ? AND effective_at < ?",
        (apn, f"{event_type_prefix}%", start, end),
    ).fetchone()[0]


def build_dataset(conn: sqlite3.Connection, by_parcel: dict) -> list:
    records = []
    excluded_no_t0 = 0
    excluded_no_label_year = 0
    for apn, years in by_parcel.items():
        t0_row = years.get(T0_YEAR)
        label_row = years.get(LABEL_YEAR)
        if t0_row is None:
            excluded_no_t0 += 1
            continue
        if label_row is None:
            excluded_no_label_year += 1
            continue

        sale_at_t0 = t0_row.get("current_sales_date")
        sale_at_label = label_row.get("current_sales_date")
        label = 1 if (sale_at_label and sale_at_label != sale_at_t0) else 0

        long_hold_years = None
        if sale_at_t0:
            try:
                sold_year = int(sale_at_t0[:4])
                long_hold_years = int(T0_YEAR) - sold_year
            except ValueError:
                pass

        recent_permits = count_events(
            conn, apn, "PERMIT_", f"{int(T0_YEAR)-1}-01-01", f"{T0_YEAR}-01-01"
        )
        recent_violations = count_events(
            conn, apn, "VIOLATION_", f"{int(T0_YEAR)-1}-01-01", f"{T0_YEAR}-01-01"
        )

        records.append({
            "apn": apn,
            "label": label,
            "long_hold_years": long_hold_years,
            "recent_permits": recent_permits,
            "recent_violations": recent_violations,
        })
    return records, excluded_no_t0, excluded_no_label_year


def precision_lift_at_k(ranked_apns_desc: list, labels_by_apn: dict, k: int, base_rate: float):
    top_k = ranked_apns_desc[:k]
    if not top_k:
        return None, None
    positives = sum(labels_by_apn[a] for a in top_k)
    precision = positives / len(top_k)
    lift = (precision / base_rate) if base_rate > 0 else None
    return precision, lift


def main():
    conn = db.connect()
    db.init_schema(conn)

    by_parcel = load_assessor_rows_by_parcel(conn)
    print(f"Distinct parcels in assessor sample: {len(by_parcel)}")

    blocks = get_blocks(by_parcel)
    print(f"Distinct blocks: {len(blocks)}")

    r1, r2 = pull_historical_permits_and_violations(conn, blocks)
    print("Historical permits pull:", json.dumps(r1, indent=2))
    print("Historical violations pull:", json.dumps(r2, indent=2))

    records, excl_t0, excl_label = build_dataset(conn, by_parcel)
    print(f"Excluded (no {T0_YEAR} roll row): {excl_t0}")
    print(f"Excluded (no {LABEL_YEAR} roll row): {excl_label}")
    print(f"Eligible dataset size: {len(records)}")

    labels_by_apn = {r["apn"]: r["label"] for r in records}
    base_rate = sum(r["label"] for r in records) / len(records) if records else 0
    print(f"Base rate (P(sale within ~1yr of T0)): {base_rate:.4f} "
          f"({sum(r['label'] for r in records)}/{len(records)})")

    print()
    print("=== Baseline 2: LONG_HOLD alone (rank by years-since-sale desc) ===")
    ranked = [r for r in records if r["long_hold_years"] is not None]
    ranked.sort(key=lambda r: r["long_hold_years"], reverse=True)
    excluded_no_hold = len(records) - len(ranked)
    print(f"(excluded {excluded_no_hold} parcels with no on-record prior sale date)")
    for k in (20, 50):
        p, lift = precision_lift_at_k([r["apn"] for r in ranked], labels_by_apn, k, base_rate)
        print(f"Precision@{k}: {p}  Lift@{k}: {lift}")

    print()
    print("=== Baseline 3: heuristic filter (long_hold > median AND recent permit/violation activity) ===")
    hold_values = sorted(r["long_hold_years"] for r in ranked)
    median_hold = hold_values[len(hold_values) // 2] if hold_values else 0
    heuristic_hits = [
        r for r in records
        if r["long_hold_years"] is not None and r["long_hold_years"] > median_hold
        and (r["recent_permits"] > 0 or r["recent_violations"] > 0)
    ]
    print(f"median hold (years): {median_hold}")
    print(f"heuristic-positive parcels: {len(heuristic_hits)}")
    if heuristic_hits:
        precision = sum(r["label"] for r in heuristic_hits) / len(heuristic_hits)
        lift = precision / base_rate if base_rate > 0 else None
        print(f"Precision on heuristic set: {precision:.4f}  Lift: {lift}")
    else:
        print("Precision on heuristic set: N/A (empty set)")

    print()
    print("=== Baseline 1: random (analytic, not simulated) ===")
    print(f"Expected Precision@K == base_rate == {base_rate:.4f} for any K, Lift@K == 1.0 by definition")

    print()
    print("=== Signal-count sanity: does recent activity alone correlate with label? ===")
    any_activity = [r for r in records if r["recent_permits"] > 0 or r["recent_violations"] > 0]
    no_activity = [r for r in records if r["recent_permits"] == 0 and r["recent_violations"] == 0]
    if any_activity:
        p_activity = sum(r["label"] for r in any_activity) / len(any_activity)
        print(f"P(sale | any recent permit/violation activity), n={len(any_activity)}: {p_activity:.4f}")
    if no_activity:
        p_no_activity = sum(r["label"] for r in no_activity) / len(no_activity)
        print(f"P(sale | no recent activity), n={len(no_activity)}: {p_no_activity:.4f}")


if __name__ == "__main__":
    main()
