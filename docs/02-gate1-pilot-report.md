# Gate 1 Pilot — First Read on "Does Any Signal Beat Baseline?"

Status: PILOT RESULT, not a Gate 1 verdict — 2026-09-01
**Superseded by docs/03-gate1-full-run-report.md** (representative city-wide
sample, confidence intervals). Kept here for history — the pilot's clustered
sample and one of its findings (activity correlating with lower sale
likelihood) did NOT replicate at full scale. See docs/03 for the current
Gate 1 status.
Ref: docs/00-gate0-and-first-milestone.md §17 (Gate 1), Section F/G

## What this is and isn't

This is a **methodology pilot**, run against the data already ingested in
Phase 1/1b (`services/research/gate1_pilot.py`), not the full Gate 1 required
by docs/00. Two honesty-relevant limits, stated up front:

1. **Sample is small and geographically clustered.** 861 parcels, all sharing
   low block numbers — an artifact of how the Phase 1b backfill was
   paginated (sorted by `parcel_number` ascending with a row limit), not a
   representative citywide sample. Whatever this pilot finds is evidence
   about this cluster of blocks, not about San Francisco as a whole.
2. **Task A only**, per docs/00 Section F: no price label exists, so only
   sale-likelihood (not discount) is tested.

Treat this as "does the harness work and what does it say on a small slice,"
not "Gate 1 passed/failed for the product."

## Method

- T0 = 2023 closed roll. Features frozen to what was on record as of that
  roll (no data from 2024+ used as a feature - the label, not a feature).
- Label = a new `current_sales_date` appearing in the 2024 closed roll that
  wasn't present as of the 2023 roll (i.e., a sale recorded in the ~1 year
  after T0).
- Pulled real permits/violations data for the *actual historical window*
  (2022-2023, not the 2026 data used in Phase 1's freshness proof) scoped to
  the same 49 blocks, via a targeted Socrata query — 300 permit records, 119
  violation records.
- 809 parcels had both a 2023 and 2024 roll row (49 excluded for missing
  2023, 3 for missing 2024 — genuinely missing, not assumed negative).

## Results (n=809, 119 positive labels, base rate 14.71%)

| Ranking method | Precision@20 | Lift@20 | Precision@50 | Lift@50 |
|---|---|---|---|---|
| Random (analytic) | 0.147 | 1.00 | 0.147 | 1.00 |
| Long-hold-alone (years since last sale, ranked desc) | 0.15 | **1.02** | 0.08 | **0.54** |

| Heuristic filter | n | Precision | Lift |
|---|---|---|---|
| long-hold > median (11yr) AND recent permit/violation activity | 17 | 0.118 | **0.80** |

| Conditional check | n | P(sale within ~1yr) |
|---|---|---|
| Any recent permit or violation activity | 76 | **0.079** |
| No recent activity | 733 | **0.154** |

## Honest read

**No edge was found in this pilot.** Long-hold-alone is statistically
indistinguishable from random at K=20 (lift 1.02) and *worse* than random at
K=50 (lift 0.54). The distress-heuristic (long hold + recent permit/violation
activity) also underperforms random (lift 0.80).

The one finding worth flagging as a real signal, not noise: **recent
permit/violation activity correlates with a *lower* probability of near-term
sale in this sample** (7.9% vs 15.4%), the opposite of the master prompt's
assumed direction (§16 lists code violations as a distress-indicating,
sale-predicting signal). A plausible explanation — not verified, `HYPOTHESIS`
— is that owners actively pulling permits or getting violations cleared are
investing in the property, which is more consistent with staying than
selling. This deserves investigation before code-violation activity is
treated as a positive feature for sale prediction, let alone distress.

## Gate 1 decision

Per docs/00 §17, the options are `CONTINUE`, `NARROW`, `MORE DATA NEEDED`,
`STOP`. Given the sample-size and representativeness caveats above, this
pilot cannot license a full `STOP` on the product thesis — but it also found
**no positive evidence** for the two most obvious baseline signals the
master prompt itself proposes (long-hold, distress-heuristic).

**Decision: MORE DATA NEEDED**, specifically:
- A representative (not block-clustered) parcel sample, city-wide or a
  proper random sample, before any lift claim can be trusted.
- More positive-label volume — 119 events is thin for K=20/K=50 precision
  estimates; confidence intervals on these numbers would be wide (not
  computed here — flagging the gap rather than presenting false precision).
- The counter-intuitive activity/sale relationship should be re-tested on a
  larger sample before being treated as either a real feature or a modeling
  artifact.

**What this does NOT prove**: that the product thesis is wrong. It proves
this pilot, on this small non-representative slice, did not find the
obvious baseline signals working in the assumed direction. That is exactly
the kind of result the master prompt asks to be reported plainly rather than
buried under a better-looking architecture.
