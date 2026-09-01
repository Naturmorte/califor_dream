"""Gate 1, full run: a representative (systematic, city-wide) sample instead
of the geographically-clustered pilot in gate1_pilot.py.

Sampling method: parcel_number LIKE '%1' (last digit of the concatenated
block+lot = 1). This is a systematic ~1-in-10 sample spread across every
block in San Francisco, not a geographic cluster and not true simple random
sampling (documented as such - it's a disclosed method, not claimed to be
a perfect random sample). Socrata's SODA API has no native random-order
primitive, so this is the honest alternative to "first N rows returned by
pagination," which is what produced the biased pilot sample.

Same task, same T0/label methodology as gate1_pilot.py (see docs/02):
Task A only, T0 = 2023 closed roll, label = new current_sales_date appearing
in the 2024 closed roll.
"""

import json
import math
import sqlite3

from services.ingestion import db
from services.ingestion.pipeline import ingest_source
from services.research.gate1_pilot import count_events, precision_lift_at_k

SAMPLE_PREDICATE = "parcel_number like '%1'"
ASSESSOR_WHERE = f"{SAMPLE_PREDICATE} AND closed_roll_year in ('2022','2023','2024')"
PERMITS_WHERE = "filed_date >= '2022-01-01T00:00:00' AND filed_date < '2024-01-01T00:00:00'"
VIOLATIONS_WHERE = "date_filed >= '2022-01-01T00:00:00' AND date_filed < '2024-01-01T00:00:00'"

T0_YEAR = "2023"
LABEL_YEAR = "2024"


def wilson_ci(successes: int, n: int, z: float = 1.96):
    if n == 0:
        return None, None
    phat = successes / n
    denom = 1 + z * z / n
    center = phat + z * z / (2 * n)
    margin = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n))
    return (center - margin) / denom, (center + margin) / denom


def load_assessor_rows_by_parcel(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT raw_payload FROM raw_record WHERE source_id='datasf_assessor_secured_roll'"
    ).fetchall()
    by_parcel = {}
    for (payload,) in rows:
        d = json.loads(payload)
        by_parcel.setdefault(d["parcel_number"], {})[d["closed_roll_year"]] = d
    return by_parcel


def build_dataset(conn: sqlite3.Connection, by_parcel: dict):
    records = []
    excl_no_t0 = excl_no_label = 0
    for apn, years in by_parcel.items():
        t0_row = years.get(T0_YEAR)
        label_row = years.get(LABEL_YEAR)
        if t0_row is None:
            excl_no_t0 += 1
            continue
        if label_row is None:
            excl_no_label += 1
            continue
        sale_at_t0 = t0_row.get("current_sales_date")
        sale_at_label = label_row.get("current_sales_date")
        label = 1 if (sale_at_label and sale_at_label != sale_at_t0) else 0

        long_hold_years = None
        if sale_at_t0:
            try:
                long_hold_years = int(T0_YEAR) - int(sale_at_t0[:4])
            except ValueError:
                pass

        recent_permits = count_events(conn, apn, "PERMIT_", f"{int(T0_YEAR)-1}-01-01", f"{T0_YEAR}-01-01")
        recent_violations = count_events(conn, apn, "VIOLATION_", f"{int(T0_YEAR)-1}-01-01", f"{T0_YEAR}-01-01")

        records.append({
            "apn": apn, "label": label, "long_hold_years": long_hold_years,
            "recent_permits": recent_permits, "recent_violations": recent_violations,
        })
    return records, excl_no_t0, excl_no_label


def main():
    conn = db.connect()
    db.init_schema(conn)

    print("=== Ingesting representative assessor sample (parcel_number LIKE '%1') ===")
    r_assessor = ingest_source(conn, "assessor_roll", where_override=ASSESSOR_WHERE)
    print(json.dumps(r_assessor, indent=2))

    print("=== Ingesting citywide historical permits (2022-2023) ===")
    r_permits = ingest_source(conn, "building_permits", where_override=PERMITS_WHERE)
    print(json.dumps(r_permits, indent=2))

    print("=== Ingesting citywide historical violations (2022-2023) ===")
    r_violations = ingest_source(conn, "code_violations", where_override=VIOLATIONS_WHERE)
    print(json.dumps(r_violations, indent=2))

    by_parcel = load_assessor_rows_by_parcel(conn)
    print(f"\nDistinct sampled parcels total (any year): {len(by_parcel)}")

    records, excl_t0, excl_label = build_dataset(conn, by_parcel)
    print(f"Excluded (no {T0_YEAR} roll row): {excl_t0}")
    print(f"Excluded (no {LABEL_YEAR} roll row): {excl_label}")
    n = len(records)
    print(f"Eligible dataset size: {n}")

    labels_by_apn = {r["apn"]: r["label"] for r in records}
    positives = sum(r["label"] for r in records)
    base_rate = positives / n if n else 0
    lo, hi = wilson_ci(positives, n)
    print(f"Base rate: {base_rate:.4f} ({positives}/{n})  95% CI [{lo:.4f}, {hi:.4f}]")

    print("\n=== Baseline 2: LONG_HOLD alone ===")
    ranked = [r for r in records if r["long_hold_years"] is not None]
    ranked.sort(key=lambda r: r["long_hold_years"], reverse=True)
    print(f"(excluded {n - len(ranked)} with no on-record prior sale)")
    for k in (20, 100, 300):
        p, lift = precision_lift_at_k([r["apn"] for r in ranked], labels_by_apn, k, base_rate)
        if p is None:
            continue
        successes = round(p * k)
        clo, chi = wilson_ci(successes, k)
        print(f"Precision@{k}: {p:.4f} (95% CI [{clo:.4f},{chi:.4f}])  Lift@{k}: {lift:.4f}")

    print("\n=== Baseline 3: heuristic filter (long_hold > median AND recent permit/violation activity) ===")
    hold_values = sorted(r["long_hold_years"] for r in ranked)
    median_hold = hold_values[len(hold_values) // 2] if hold_values else 0
    heuristic_hits = [
        r for r in records
        if r["long_hold_years"] is not None and r["long_hold_years"] > median_hold
        and (r["recent_permits"] > 0 or r["recent_violations"] > 0)
    ]
    print(f"median hold: {median_hold} years, heuristic-positive n={len(heuristic_hits)}")
    if heuristic_hits:
        hp = sum(r["label"] for r in heuristic_hits) / len(heuristic_hits)
        hlo, hhi = wilson_ci(sum(r["label"] for r in heuristic_hits), len(heuristic_hits))
        lift = hp / base_rate if base_rate else None
        print(f"Precision: {hp:.4f} (95% CI [{hlo:.4f},{hhi:.4f}])  Lift: {lift:.4f}")

    print("\n=== Baseline 1: random (analytic) ===")
    print(f"Precision@K == base_rate == {base_rate:.4f} for any K, Lift == 1.0 by definition")

    print("\n=== Activity correlation check ===")
    any_activity = [r for r in records if r["recent_permits"] > 0 or r["recent_violations"] > 0]
    no_activity = [r for r in records if r["recent_permits"] == 0 and r["recent_violations"] == 0]
    for label_txt, group in (("any recent activity", any_activity), ("no recent activity", no_activity)):
        if not group:
            continue
        s = sum(r["label"] for r in group)
        p = s / len(group)
        clo, chi = wilson_ci(s, len(group))
        print(f"P(sale | {label_txt}), n={len(group)}: {p:.4f} (95% CI [{clo:.4f},{chi:.4f}])")


if __name__ == "__main__":
    main()
