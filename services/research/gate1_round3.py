"""Gate 1, round 3: untried permit/violation attributes, not just event
counts. Still Task A only - Task B (off-market classification) needs a
deed-type field that doesn't exist in any source ingested so far (see
docs/00 Gate 0 - no free bulk deed/recorder data), so it isn't attempted;
noted here rather than silently skipped.

New candidate features, each checked individually first (docs/00 §32):
  - open_violations_at_t0: count of violations with status='active' (not
    just any violation ever filed) in the trailing 12 months before T0
  - total_permit_cost_recent: sum of estimated_cost across permits filed in
    the trailing 12 months before T0 (investment magnitude, not just count)
  - major_construction_recent: any permit in the trailing window whose
    permit_type_definition indicates new construction/demolition, vs the
    much more common minor "otc alterations" permits
  - adu_permit_recent: any ADU-flagged permit in the trailing window

Learned the hard way in docs/05: a combined model must be validated with a
genuine temporal holdout (train on one vintage, test on a later one) before
being trusted, not just cross-validation within one vintage. Applied that
methodology from the start here instead of repeating the docs/04 mistake.
"""

import json
import sqlite3

import numpy as np

from services.ingestion import db
from services.ingestion.pipeline import ingest_source
from services.research.gate1_full import wilson_ci
from services.research.gate1_signals_v2 import logistic_regression_np, predict_proba
from services.research.gate1_temporal_holdout import (
    build_dataset as build_base_dataset,
    load_assessor_rows_by_parcel,
)

MAJOR_TYPES = {"new construction wood frame", "new construction", "demolitions"}


def build_permit_violation_index(conn: sqlite3.Connection):
    """apn -> list of (effective_date_str, record_type, payload-subset)"""
    idx = {}

    for (payload,) in conn.execute(
        "SELECT raw_payload FROM raw_record WHERE source_id='datasf_building_permits'"
    ).fetchall():
        d = json.loads(payload)
        block, lot = d.get("block"), d.get("lot")
        if not block or not lot:
            continue
        apn = block + lot
        filed = d.get("filed_date")
        if not filed:
            continue
        idx.setdefault(apn, []).append({
            "type": "permit", "date": filed[:10],
            "permit_number": d.get("permit_number"),
            "estimated_cost": d.get("estimated_cost"),
            "permit_type_definition": d.get("permit_type_definition"),
            "adu": d.get("adu"),
        })

    for (payload,) in conn.execute(
        "SELECT raw_payload FROM raw_record WHERE source_id='datasf_notices_of_violation'"
    ).fetchall():
        d = json.loads(payload)
        block, lot = d.get("block"), d.get("lot")
        if not block or not lot:
            continue
        apn = block + lot
        filed = d.get("date_filed")
        if not filed:
            continue
        idx.setdefault(apn, []).append({
            "type": "violation", "date": filed[:10],
            "complaint_number": d.get("complaint_number"),
            "status": d.get("status"),
        })
    return idx


def window_records(records, start, end):
    return [r for r in records if start <= r["date"] < end]


def add_round3_features(records, apn_index, t0_year):
    start, end = f"{int(t0_year)-1}-01-01", f"{t0_year}-01-01"
    for r in records:
        apn_records = apn_index.get(r["apn"], [])
        win = window_records(apn_records, start, end)

        open_violations = len({
            w["complaint_number"] for w in win
            if w["type"] == "violation" and w.get("status") == "active"
        })

        seen_permits = {}
        for w in win:
            if w["type"] != "permit":
                continue
            seen_permits[w["permit_number"]] = w  # dedupe multiple raw_record versions, keep latest seen
        total_cost = 0.0
        major_construction = 0
        adu_permit = 0
        for p in seen_permits.values():
            try:
                total_cost += float(p.get("estimated_cost") or 0)
            except (TypeError, ValueError):
                pass
            if p.get("permit_type_definition") in MAJOR_TYPES:
                major_construction = 1
            if p.get("adu") == "Y":
                adu_permit = 1

        r["open_violations_at_t0"] = open_violations
        r["total_permit_cost_recent"] = total_cost
        r["major_construction_recent"] = major_construction
        r["adu_permit_recent"] = adu_permit
    return records


def report_binary(records, key):
    yes = [r for r in records if r[key] == 1]
    no = [r for r in records if r[key] == 0]
    for name, group in (("=1", yes), ("=0", no)):
        if not group:
            continue
        s = sum(r["label"] for r in group)
        p = s / len(group)
        lo, hi = wilson_ci(s, len(group))
        print(f"  {key}{name}: n={len(group)} P(sale)={p:.4f} 95%CI[{lo:.4f},{hi:.4f}]")


def report_continuous_by_quartile(records, key):
    vals = sorted(r[key] for r in records if r[key] > 0)
    if len(vals) < 20:
        print(f"  {key}: too few nonzero values ({len(vals)}) to bucket")
        return
    zero_group = [r for r in records if r[key] == 0]
    nonzero_group = [r for r in records if r[key] > 0]
    for name, group in (("=0", zero_group), (">0", nonzero_group)):
        s = sum(r["label"] for r in group)
        p = s / len(group)
        lo, hi = wilson_ci(s, len(group))
        print(f"  {key}{name}: n={len(group)} P(sale)={p:.4f} 95%CI[{lo:.4f},{hi:.4f}]")


def main():
    conn = db.connect()
    db.init_schema(conn)

    print("=== Extending permits/violations back to 2021 (needed for T0=2022 trailing window) ===")
    r1 = ingest_source(conn, "building_permits", where_override=(
        "filed_date >= '2021-01-01T00:00:00' AND filed_date < '2024-01-01T00:00:00'"
    ))
    print(json.dumps(r1, indent=2))
    r2 = ingest_source(conn, "code_violations", where_override=(
        "date_filed >= '2021-01-01T00:00:00' AND date_filed < '2024-01-01T00:00:00'"
    ))
    print(json.dumps(r2, indent=2))

    print("Building permit/violation index by APN...")
    apn_index = build_permit_violation_index(conn)
    print(f"parcels with any permit/violation history: {len(apn_index)}")

    by_parcel = load_assessor_rows_by_parcel(conn)

    print("\n=== Building TRAIN (T0=2022, label=2023) with round-3 features ===")
    train_records, _ = build_base_dataset(conn, by_parcel, "2022", "2021", "2023")
    add_round3_features(train_records, apn_index, "2022")

    print("=== Individual signal checks (TRAIN vintage only, as exploration) ===")
    print("open_violations_at_t0:")
    report_binary(
        [{**r, "open_violations_at_t0_flag": 1 if r["open_violations_at_t0"] > 0 else 0}
         for r in train_records],
        "open_violations_at_t0_flag",
    )
    print("total_permit_cost_recent:")
    report_continuous_by_quartile(train_records, "total_permit_cost_recent")
    print("major_construction_recent:")
    report_binary(train_records, "major_construction_recent")
    print("adu_permit_recent:")
    report_binary(train_records, "adu_permit_recent")

    # --- combined model, validated with a real temporal holdout from the start ---
    print("\n=== Combined model (all round-2 + round-3 features), TRAIN=2022->2023 ===")
    feature_keys = ["long_hold_years", "value_jump_pct", "use_code_changed", "unit_count_changed",
                     "recent_permits", "recent_violations", "open_violations_at_t0",
                     "total_permit_cost_recent", "major_construction_recent", "adu_permit_recent"]

    train_usable = [r for r in train_records if r["long_hold_years"] is not None and r["value_jump_pct"] is not None]
    print(f"train usable: {len(train_usable)}")

    def to_matrix(rows):
        X = np.array([[r[k] for k in feature_keys] for r in rows], dtype=float)
        y = np.array([r["label"] for r in rows], dtype=float)
        return X, y

    X_train, y_train = to_matrix(train_usable)
    print(f"train base rate: {y_train.mean():.4f}")
    w, mu, sigma = logistic_regression_np(X_train, y_train)
    print("weights:", dict(zip(["intercept"] + feature_keys, np.round(w, 4))))

    print("\n=== TEST vintage: T0=2023, label=2024 (genuinely unseen, same as docs/05) ===")
    test_records, _ = build_base_dataset(conn, by_parcel, "2023", "2022", "2024")
    add_round3_features(test_records, apn_index, "2023")
    test_usable = [r for r in test_records if r["long_hold_years"] is not None and r["value_jump_pct"] is not None]
    print(f"test usable: {len(test_usable)}")
    X_test, y_test = to_matrix(test_usable)
    test_base_rate = y_test.mean()
    print(f"test base rate: {test_base_rate:.4f}")

    p_test = predict_proba(X_test, w, mu, sigma)
    order = np.argsort(-p_test)
    test_labels_sorted = y_test[order]
    for k in (20, 50, 100, 300):
        top_k = test_labels_sorted[:k]
        precision = top_k.mean()
        lift = precision / test_base_rate if test_base_rate > 0 else None
        lo, hi = wilson_ci(int(top_k.sum()), k)
        print(f"Precision@{k}: {precision:.4f} (95%CI[{lo:.4f},{hi:.4f}])  Lift@{k}: {lift:.4f}")


if __name__ == "__main__":
    main()
