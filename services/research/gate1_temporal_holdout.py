"""Gate 1, the real validation step flagged in docs/04: a genuine temporal
holdout, not cross-validation within one T0 vintage.

Train: T0=2022 (features from 2021 vs 2022 roll), label = sale recorded in
       the 2023 roll.
Test:  T0=2023 (features from 2022 vs 2023 roll), label = sale recorded in
       the 2024 roll. This is the exact T0=2023/label=2024 pairing used in
       docs/03 and docs/04 - reused here as a genuinely unseen test vintage
       relative to a model trained one year earlier.

Originally attempted with TEST = T0=2024/label=2025, but the 2025 roll
turned out to be too fresh to trust: its data_as_of is only ~2 months old
at the time of this run, vs ~12-15 months for the other rolls used here,
and the measured base rate on that pairing collapsed to 0.1% (vs 4.25%
elsewhere) - almost certainly a label-immaturity artifact (current_sales_date
not yet fully updated for the most recent roll), not a real 40x drop in
sales. Documented in docs/05, not silently discarded. Shifted the whole
train/test window back one year to stay clear of the freshest, unsettled
roll.
"""

import json
import sqlite3

import numpy as np

from services.ingestion import db
from services.ingestion.pipeline import ingest_source
from services.research.gate1_pilot import count_events
from services.research.gate1_full import wilson_ci
from services.research.gate1_signals_v2 import logistic_regression_np, predict_proba

FEATURE_KEYS = ["long_hold_years", "value_jump_pct", "use_code_changed",
                 "unit_count_changed", "recent_permits", "recent_violations"]

ASSESSOR_WHERE = "parcel_number like '%1' AND closed_roll_year in ('2021','2022','2023','2024')"


def load_assessor_rows_by_parcel(conn: sqlite3.Connection) -> dict:
    rows = conn.execute(
        "SELECT raw_payload FROM raw_record WHERE source_id='datasf_assessor_secured_roll'"
    ).fetchall()
    by_parcel = {}
    for (payload,) in rows:
        d = json.loads(payload)
        by_parcel.setdefault(d["parcel_number"], {})[d["closed_roll_year"]] = d
    return by_parcel


def total_value(row):
    try:
        return float(row.get("assessed_land_value", 0) or 0) + \
               float(row.get("assessed_improvement_value", 0) or 0)
    except (TypeError, ValueError):
        return None


def build_dataset(conn, by_parcel, t0_year, t0_prev_year, label_year):
    records = []
    excluded = {"no_t0": 0, "no_t0_prev": 0, "no_label": 0}
    for apn, years in by_parcel.items():
        t0 = years.get(t0_year)
        t0_prev = years.get(t0_prev_year)
        label_row = years.get(label_year)
        if t0 is None:
            excluded["no_t0"] += 1
            continue
        if t0_prev is None:
            excluded["no_t0_prev"] += 1
            continue
        if label_row is None:
            excluded["no_label"] += 1
            continue

        sale_at_t0 = t0.get("current_sales_date")
        sale_at_label = label_row.get("current_sales_date")
        label = 1 if (sale_at_label and sale_at_label != sale_at_t0) else 0

        long_hold_years = None
        if sale_at_t0:
            try:
                long_hold_years = int(t0_year) - int(sale_at_t0[:4])
            except ValueError:
                pass

        v0, v1 = total_value(t0_prev), total_value(t0)
        value_jump_pct = (v1 - v0) / v0 if (v0 and v0 > 0 and v1 is not None) else None

        use_code_changed = 1 if t0.get("use_code") != t0_prev.get("use_code") else 0
        unit_count_changed = 1 if t0.get("number_of_units") != t0_prev.get("number_of_units") else 0

        recent_permits = count_events(conn, apn, "PERMIT_", f"{int(t0_year)-1}-01-01", f"{t0_year}-01-01")
        recent_violations = count_events(conn, apn, "VIOLATION_", f"{int(t0_year)-1}-01-01", f"{t0_year}-01-01")

        records.append({
            "apn": apn, "label": label,
            "long_hold_years": long_hold_years,
            "value_jump_pct": value_jump_pct,
            "use_code_changed": use_code_changed,
            "unit_count_changed": unit_count_changed,
            "recent_permits": recent_permits,
            "recent_violations": recent_violations,
        })
    return records, excluded


def to_matrix(rows):
    X = np.array([[r[k] for k in FEATURE_KEYS] for r in rows], dtype=float)
    y = np.array([r["label"] for r in rows], dtype=float)
    return X, y


def main():
    conn = db.connect()
    db.init_schema(conn)

    print("=== Ensuring 2021 roll data is ingested (2022-2024 already present) ===")
    r = ingest_source(conn, "assessor_roll", where_override=ASSESSOR_WHERE)
    print(json.dumps(r, indent=2))

    by_parcel = load_assessor_rows_by_parcel(conn)

    print("\n=== TRAIN vintage: T0=2022, label=2023 (one year earlier than docs/04) ===")
    train_records, train_excl = build_dataset(conn, by_parcel, "2022", "2021", "2023")
    print(f"excluded: {train_excl}, eligible: {len(train_records)}")
    train_usable = [r for r in train_records if r["long_hold_years"] is not None and r["value_jump_pct"] is not None]
    print(f"usable (complete features): {len(train_usable)}")
    X_train, y_train = to_matrix(train_usable)
    train_base_rate = y_train.mean()
    print(f"train base rate: {train_base_rate:.4f}")

    w, mu, sigma = logistic_regression_np(X_train, y_train)
    print("weights:", dict(zip(["intercept"] + FEATURE_KEYS, np.round(w, 4))))

    print("\n=== TEST vintage: T0=2023, label=2024 (same pairing as docs/03 and docs/04) ===")
    test_records, test_excl = build_dataset(conn, by_parcel, "2023", "2022", "2024")
    print(f"excluded: {test_excl}, eligible: {len(test_records)}")
    test_usable = [r for r in test_records if r["long_hold_years"] is not None and r["value_jump_pct"] is not None]
    print(f"usable (complete features): {len(test_usable)}")
    X_test, y_test = to_matrix(test_usable)
    test_base_rate = y_test.mean()
    print(f"test base rate: {test_base_rate:.4f}")

    p_test = predict_proba(X_test, w, mu, sigma)
    order = np.argsort(-p_test)
    test_labels_sorted = y_test[order]

    print(f"\n=== Applying TRAIN-fitted model to TEST vintage, no retraining ===")
    for k in (20, 50, 100, 300):
        if k > len(test_labels_sorted):
            continue
        top_k = test_labels_sorted[:k]
        precision = top_k.mean()
        lift = precision / test_base_rate if test_base_rate > 0 else None
        lo, hi = wilson_ci(int(top_k.sum()), k)
        print(f"Precision@{k}: {precision:.4f} (95%CI[{lo:.4f},{hi:.4f}])  Lift@{k}: {lift:.4f}")

    print("\n=== Baseline on TEST vintage: long-hold-alone, for comparison ===")
    ranked = [r for r in test_usable if r["long_hold_years"] is not None]
    ranked.sort(key=lambda r: r["long_hold_years"], reverse=True)
    labels_by_apn = {r["apn"]: r["label"] for r in test_usable}
    for k in (20, 50, 100):
        top = ranked[:k]
        if not top:
            continue
        s = sum(labels_by_apn[r["apn"]] for r in top)
        p = s / len(top)
        lift = p / test_base_rate if test_base_rate else None
        lo, hi = wilson_ci(s, len(top))
        print(f"Precision@{k}: {p:.4f} (95%CI[{lo:.4f},{hi:.4f}])  Lift@{k}: {lift:.4f}")


if __name__ == "__main__":
    main()
