# Gate 1 — Temporal Holdout: the Round 2 Signal Does Not Generalize

Status: Gate 1 REOPENED to `NARROW` — 2026-09-01
Ref: docs/04-gate1-round2-signals-report.md (the finding being tested here)

## What this tests

docs/04 flagged its own biggest weakness explicitly: "cross-validation
within one T0 vintage is not a true temporal out-of-sample test... the real
test is whether this exact fitted approach still shows lift on a fresh T0."
This is that test.

**Method:** fit the same logistic regression (same 6 features) on one
vintage (T0=2022, features from 2021→2022 roll, label=2023 roll), then
apply that fitted model, unchanged, to a *later, unseen* vintage (T0=2023,
label=2024 — the same pairing docs/03/04 already used). No retraining, no
peeking at the test vintage during fitting.

## A data trap found and avoided along the way

The first attempt used TEST = T0=2024/label=2025 (the freshest available
roll pair). That run measured a **0.1% base rate** (vs 4.25% and 3.51% in
every other vintage tested) — a red flag, not a finding. Investigation: the
2025 roll's `data_as_of` is only ~2 months old at the time of this run,
versus 12-15+ months for every other roll used here. Comparing
year-over-year `current_sales_date` counts, the 2025 roll's values for
recent years look frozen/carried-over rather than updated (e.g. parcels
with `current_sales_date` in 2024 stayed at exactly 410 between the 2024
and 2025 rolls, and the 2023-dated count *decreased*, which shouldn't
happen with a stable or growing backfill). Conclusion: the most recent
roll year is not yet mature enough to trust as a label source — real,
practical confirmation of the "Time-to-Signal" risk flagged all the way
back in docs/00 §J risk #5. **Whole train/test window shifted back one
year to avoid the freshest, unsettled roll**, rather than reporting the
0.1%-base-rate run as if it meant something.

## Result: the model trained on one year fails on the next

| K | Precision (test) | 95% CI | Lift |
|---|---|---|---|
| 20 | 0.00% | [0, 16.1%] | 0.00 |
| 50 | 0.00% | [0, 7.1%] | 0.00 |
| 100 | 2.00% | [0.55%, 7.00%] | **0.47** |
| 300 | 1.67% | [0.71%, 3.84%] | **0.39** |

The same model that showed Lift@50 ≈ 2.8x under 5-fold cross-validation
*within* the T0=2023 vintage (docs/04) produces **Lift@100 = 0.47 and
Lift@300 = 0.39 — worse than random — when applied to a genuinely different
year without retraining.** For comparison, the long-hold-alone baseline on
this same test vintage scores Lift@100 = 0.94 (≈random), i.e. even the
"boring" baseline beats the "sophisticated" combined model here.

## Honest read

**docs/04's finding does not survive a real temporal holdout.** The most
likely explanation is exactly what docs/04's own caveats predicted: 5-fold
CV within one T0 vintage shares that vintage's specific macro conditions
and specific parcel quirks, and the model picked up on patterns that were
true of 2023→2024 sales specifically, not a transferable relationship.
This is the textbook failure mode the master prompt's ML staging discipline
(§32: "don't move to stage N+1 until stage N beats baseline") exists to
catch — and it caught it.

## Gate 1 status, final for this data cycle

Every method tried against San Francisco's free public data now points the
same direction:
- Simple baselines (long-hold, distress heuristic) on a representative
  20,792-parcel sample: no edge (docs/03).
- New engineered features individually: no edge (docs/04).
- Combined logistic regression, validated properly with a temporal holdout
  (not just CV): **no edge — actively worse than random on unseen data**
  (this document).

**Decision: NARROW**, confirming docs/03's original call rather than
docs/04's more optimistic interim read. The free-data-only signal set
tested across three rounds of analysis does not show a validated edge for
Task A (sale likelihood) in San Francisco. Per docs/00's own Gate 0
findings, the harder-to-get, likely-higher-value signal categories
(absentee ownership, tax delinquency, foreclosure/NOD) were never testable
here at all — no free bulk source exists for them. That gap remains the
most plausible path to a real edge, and it requires either a paid data
source or a different jurisdiction with more open recorder/foreclosure
data — a real strategic decision, not a modeling one.
