# Gate 1, Round 3 — Permit Cost, ADU, Major Construction, Open Violations

Status: THIRD CONSECUTIVE NO-EDGE RESULT — 2026-09-01
Ref: docs/05-gate1-temporal-holdout-report.md (methodology this round follows)

## What was tested

Four new features, none tried before, all free from data already in scope:

- `open_violations_at_t0` — count of violations still `status='active'`
  (not just ever-filed) in the trailing 12 months
- `total_permit_cost_recent` — sum of `estimated_cost` across permits filed
  in the trailing 12 months (investment magnitude, not just count)
- `major_construction_recent` — any permit in the window typed as new
  construction or demolition, vs the much more common minor alteration permits
- `adu_permit_recent` — any ADU-flagged permit in the window

Applied the methodology docs/05 established the hard way: individual checks
first, then a combined model validated with a genuine temporal holdout
(train T0=2022→2023, test on unseen T0=2023→2024) from the start — not
cross-validation within one vintage.

## Individual checks: no signal, and most groups are too small to trust

| Feature | n (flag=1) | P(sale) | 95% CI |
|---|---|---|---|
| open_violations_at_t0 > 0 | 26 | 0.00% | [0%, 12.9%] |
| total_permit_cost_recent > 0 | 1,641 | 3.35% | [2.58%, 4.34%] |
| major_construction_recent | 17 | 0.00% | [0%, 18.4%] |
| adu_permit_recent | 34 | 0.00% | [0%, 10.2%] |

`total_permit_cost_recent` has a large enough sample to read (n=1,641) and
shows no difference from the zero-cost group (3.35% vs 3.07%, overlapping
CIs). The other three have too few positive cases (17-34) in a ~21,000-
parcel sample to say anything — major construction, ADU permits, and active
open violations are all genuinely rare events at this scale, not just
weak signals.

## Combined model (10 features): same failure pattern as docs/05

| K | Precision | Lift |
|---|---|---|
| 20 | 0.00% | 0.00 |
| 50 | 0.00% | 0.00 |
| 100 | 2.00% | **0.47** |
| 300 | 2.00% | **0.47** |

Identical shape to docs/05's result on the same held-out vintage — worse
than random at every K, catching zero positives in the top 50. Adding more
features did not help; if anything the model is now fitting more noise
dimensions on the same ~3.5% base rate with no more real signal to find.

## Conclusion: closing this line of inquiry

Three independent rounds (docs/03 baselines, docs/04 engineered features
validated only by CV, docs/05/06 the same features plus four more validated
by genuine temporal holdout) have now converged on the same answer: **no
signal available in San Francisco's free public data (Assessor roll,
building permits, code violations) shows a validated edge for Task A**,
under any combination or model tried so far.

This isn't a "try one more feature" situation anymore — it's a consistent,
repeated result across meaningfully different signal families (ownership
duration, reassessment magnitude, use/unit changes, permit activity and
cost, violation activity and severity). Per docs/00 §1 ("не приховуй
uncertainty") and §32 (don't add model complexity when the current stage
hasn't beaten baseline), continuing to fish for a free-data signal here
without a new *category* of data (not just a new feature on the same three
sources) is not a good use of further iteration. The Gate 0 finding that
started this thread stands: the higher-value signal categories (absentee
ownership, tax delinquency, foreclosure/NOD) were never available for free
in San Francisco, and that gap - not a missing clever feature - looks like
the real limiting factor.

**Recommendation: do not continue searching for new features on these
three sources.** The next productive step is the strategic one already
flagged in docs/05 - paid data, a different jurisdiction, or accepting this
as the documented research conclusion for the free-data-only constraint set
at the start of this project - not another round of feature engineering.
