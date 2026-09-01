"""Gate 1, round 2: new candidate signals from data already ingested in
gate1_full.py's run (docs/03) - no new ingestion needed, just new feature
engineering on the 2022/2023/2024 assessor roll + permits/violations already
in data/ingestion.db.

New features, all computable for free from DataSF, none requiring owner or
foreclosure data (still unavailable per docs/00 Gate 0):
  - value_jump_pct: % change in assessed land+improvement value, T0-1 -> T0
    (a same-year reassessment can indicate an ownership change or major
    permit-driven improvement that didn't register as a "sale" in
    current_sales_date - e.g. inherited/gifted transfers, which are common
    in SF and don't always show as arm's-length sales)
  - use_code_changed_recent: use_code differs T0-1 vs T0
  - unit_count_changed_recent: number_of_units differs T0-1 vs T0

Per docs/00 §32 (ML Stage progression), Stage 0 rules must be tried before
Stage 2 (logistic regression) - each new feature is checked individually
first. A combined logistic regression is then fit ONLY because the master
prompt explicitly allows combining several individually-weak signals to
check for interaction effects, evaluated on a held-out test split to avoid
the overfitting-looks-like-lift trap.
"""

import json
import math
import random
import sqlite3

import numpy as np

from services.ingestion import db
from services.research.gate1_pilot import count_events
from services.research.gate1_full import wilson_ci

T0_YEAR = "2023"
T0_PREV_YEAR = "2022"
LABEL_YEAR = "2024"
SEED = 42


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
    excluded = {"no_t0": 0, "no_t0_prev": 0, "no_label": 0}
    for apn, years in by_parcel.items():
        t0 = years.get(T0_YEAR)
        t0_prev = years.get(T0_PREV_YEAR)
        label_row = years.get(LABEL_YEAR)
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
                long_hold_years = int(T0_YEAR) - int(sale_at_t0[:4])
            except ValueError:
                pass

        def total_value(row):
            try:
                return float(row.get("assessed_land_value", 0) or 0) + \
                       float(row.get("assessed_improvement_value", 0) or 0)
            except (TypeError, ValueError):
                return None

        v0, v1 = total_value(t0_prev), total_value(t0)
        value_jump_pct = None
        if v0 and v0 > 0 and v1 is not None:
            value_jump_pct = (v1 - v0) / v0

        use_code_changed = 1 if t0.get("use_code") != t0_prev.get("use_code") else 0
        unit_count_changed = 1 if t0.get("number_of_units") != t0_prev.get("number_of_units") else 0

        recent_permits = count_events(conn, apn, "PERMIT_", f"{int(T0_YEAR)-1}-01-01", f"{T0_YEAR}-01-01")
        recent_violations = count_events(conn, apn, "VIOLATION_", f"{int(T0_YEAR)-1}-01-01", f"{T0_YEAR}-01-01")

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


def report_binary_feature(records, key, label_key="label"):
    yes = [r for r in records if r[key] == 1]
    no = [r for r in records if r[key] == 0]
    for name, group in (("=1", yes), ("=0", no)):
        if not group:
            continue
        s = sum(r[label_key] for r in group)
        p = s / len(group)
        lo, hi = wilson_ci(s, len(group))
        print(f"  {key}{name}: n={len(group)} P(sale)={p:.4f} 95%CI[{lo:.4f},{hi:.4f}]")


def logistic_regression_np(X: np.ndarray, y: np.ndarray, lr=0.1, iters=2000, l2=1e-3):
    n, d = X.shape
    mu, sigma = X.mean(axis=0), X.std(axis=0)
    sigma[sigma == 0] = 1
    Xn = (X - mu) / sigma
    Xn = np.hstack([np.ones((n, 1)), Xn])
    w = np.zeros(d + 1)
    for _ in range(iters):
        z = Xn @ w
        p = 1 / (1 + np.exp(-np.clip(z, -30, 30)))
        grad = Xn.T @ (p - y) / n
        grad[1:] += l2 * w[1:]
        w -= lr * grad
    return w, mu, sigma


def predict_proba(X: np.ndarray, w, mu, sigma):
    Xn = (X - mu) / sigma
    Xn = np.hstack([np.ones((Xn.shape[0], 1)), Xn])
    z = Xn @ w
    return 1 / (1 + np.exp(-np.clip(z, -30, 30)))


def main():
    conn = db.connect()
    db.init_schema(conn)

    by_parcel = load_assessor_rows_by_parcel(conn)
    records, excluded = build_dataset(conn, by_parcel)
    print(f"Excluded: {excluded}")
    n = len(records)
    print(f"Eligible dataset size: {n}")
    base_rate = sum(r["label"] for r in records) / n
    print(f"Base rate: {base_rate:.4f}")

    print("\n=== New signals, individual check ===")
    print("value_jump_pct > 0.10 (10%+ same-period value jump):")
    for r in records:
        r["value_jump_flag"] = 1 if (r["value_jump_pct"] is not None and r["value_jump_pct"] > 0.10) else 0
    report_binary_feature(records, "value_jump_flag")

    print("use_code_changed:")
    report_binary_feature(records, "use_code_changed")

    print("unit_count_changed:")
    report_binary_feature(records, "unit_count_changed")

    # --- Stage 2: combined logistic regression, held-out test split ---
    print("\n=== Combined logistic regression (train/test split, seed=42) ===")
    usable = [r for r in records if r["long_hold_years"] is not None and r["value_jump_pct"] is not None]
    print(f"Usable rows (non-null on all features): {len(usable)} of {n}")

    rnd = random.Random(SEED)
    idx = list(range(len(usable)))
    rnd.shuffle(idx)
    split = int(0.7 * len(idx))
    train_idx, test_idx = idx[:split], idx[split:]

    feature_keys = ["long_hold_years", "value_jump_pct", "use_code_changed",
                     "unit_count_changed", "recent_permits", "recent_violations"]

    def to_matrix(rows):
        X = np.array([[r[k] for k in feature_keys] for r in rows], dtype=float)
        y = np.array([r["label"] for r in rows], dtype=float)
        return X, y

    train_rows = [usable[i] for i in train_idx]
    test_rows = [usable[i] for i in test_idx]
    X_train, y_train = to_matrix(train_rows)
    X_test, y_test = to_matrix(test_rows)

    w, mu, sigma = logistic_regression_np(X_train, y_train)
    print("Learned weights (standardized features):", dict(zip(["intercept"] + feature_keys, np.round(w, 4))))

    p_test = predict_proba(X_test, w, mu, sigma)
    order = np.argsort(-p_test)
    test_labels = y_test[order]
    test_base_rate = y_test.mean()
    print(f"Test set n={len(test_rows)}, base rate={test_base_rate:.4f}")
    for k in (20, 50, 100):
        if k > len(test_labels):
            continue
        top_k = test_labels[:k]
        precision = top_k.mean()
        lift = precision / test_base_rate if test_base_rate > 0 else None
        lo, hi = wilson_ci(int(top_k.sum()), k)
        print(f"Precision@{k}: {precision:.4f} (95%CI[{lo:.4f},{hi:.4f}])  Lift@{k}: {lift:.4f}")

    # --- 5-fold cross-validation: is the single-split result stable, or luck? ---
    print("\n=== 5-fold cross-validation (out-of-fold predictions pooled, seed=42) ===")
    X_all, y_all = to_matrix(usable)
    n_all = len(usable)
    fold_idx = list(range(n_all))
    rnd2 = random.Random(SEED)
    rnd2.shuffle(fold_idx)
    n_folds = 5
    fold_size = n_all // n_folds
    oof_p = np.zeros(n_all)
    for fold in range(n_folds):
        test_i = fold_idx[fold * fold_size: (fold + 1) * fold_size] if fold < n_folds - 1 else fold_idx[fold * fold_size:]
        train_i = [i for i in fold_idx if i not in set(test_i)]
        w_f, mu_f, sigma_f = logistic_regression_np(X_all[train_i], y_all[train_i])
        oof_p[test_i] = predict_proba(X_all[test_i], w_f, mu_f, sigma_f)

    order_all = np.argsort(-oof_p)
    oof_labels_sorted = y_all[order_all]
    oof_base_rate = y_all.mean()
    print(f"Pooled out-of-fold n={n_all}, base rate={oof_base_rate:.4f}")
    for k in (20, 50, 100, 300):
        top_k = oof_labels_sorted[:k]
        precision = top_k.mean()
        lift = precision / oof_base_rate if oof_base_rate > 0 else None
        lo, hi = wilson_ci(int(top_k.sum()), k)
        print(f"Precision@{k}: {precision:.4f} (95%CI[{lo:.4f},{hi:.4f}])  Lift@{k}: {lift:.4f}")


if __name__ == "__main__":
    main()
