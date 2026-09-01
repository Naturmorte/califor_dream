# Gate 1 — Full Representative Run

Status: **Gate 1 CLOSED for the two tested signals** — 2026-09-01
Ref: docs/00-gate0-and-first-milestone.md §17, docs/02-gate1-pilot-report.md

## What changed from the pilot

docs/02 flagged the pilot's sample (861 parcels) as geographically clustered
— an artifact of pagination order, not a real sample. This run replaces it
with a **systematic city-wide sample**: `parcel_number LIKE '%1'`, i.e. every
parcel whose block+lot concatenation ends in the digit 1, spread across every
block in San Francisco. This is disclosed as a systematic sample, not true
simple random sampling (Socrata's API has no random-order primitive) — but
it is not geographically biased the way the pilot was.

Same task and methodology as the pilot (docs/02): Task A only (sale within
~1 year), T0 = 2023 closed roll, label = new `current_sales_date` appearing
in the 2024 closed roll.

## Scale

- Assessor sample: 62,762 rows ingested (2022-2024 roll years), 21,779
  distinct parcels total.
- Historical permits, citywide, 2022-2023: 50,458 records.
- Historical violations, citywide, 2022-2023: 28,550 records.
- Eligible dataset (had both a 2023 and 2024 roll row): **20,792 parcels**,
  **984 positive labels**.

## Result: base rate corrected, and it matters

**Base rate: 4.73%** (95% CI [4.45%, 5.03%]) — a plausible annual turnover
rate for a dense urban housing stock. The pilot's 14.71% base rate was
itself an artifact of the clustered sample (likely condo-heavy blocks near
Russian Hill/North Beach with higher unit-level turnover) — a useful
reminder that an unrepresentative sample distorts not just the lift
estimate but the label distribution itself.

## Results with confidence intervals (Wilson score, 95%)

| Ranking | n | Precision | 95% CI | Lift |
|---|---|---|---|---|
| Random (analytic) | - | 0.0473 | [0.0445, 0.0503] | 1.00 |
| Long-hold-alone @20 | 20 | 0.0000 | [0.00, 0.161] | 0.00 |
| Long-hold-alone @100 | 100 | 0.0400 | [0.0157, 0.0984] | 0.85 |
| Long-hold-alone @300 | 300 | 0.0367 | [0.0206, 0.0645] | 0.77 |
| Heuristic (long-hold>median AND recent activity) | 473 | 0.0444 | [0.0292, 0.0669] | 0.94 |

**Every confidence interval above contains the base rate (4.73%).** None of
these results are statistically distinguishable from random at this sample
size. This is a more precise and more defensible statement than the pilot's
raw point estimates allowed — the pilot's small n (809/119) had confidence
intervals wide enough that "worse than random" point estimates couldn't be
trusted either way. At full scale, the honest statement is: **no evidence
of edge, positive or negative**, for either tested signal.

## The pilot's "activity is bad for sale odds" finding did not replicate

The pilot showed 7.9% vs 15.4% (a 2x gap) for recent-activity vs no-activity.
At full scale:

| Group | n | P(sale) | 95% CI |
|---|---|---|---|
| Any recent permit/violation activity | 1,872 | 4.17% | [3.35%, 5.17%] |
| No recent activity | 18,920 | 4.79% | [4.49%, 5.10%] |

The gap shrank from a factor of ~2 to a few tenths of a percentage point,
and the confidence intervals now overlap substantially. **The pilot's
"activity correlates with lower sale likelihood" finding does not hold up
at scale** — it was very likely a small-sample artifact of the clustered
811-parcel pilot, not a real effect. This is exactly why docs/02 labeled it
`HYPOTHESIS` and flagged it as needing a larger sample before being trusted
either way — that caution turned out to be warranted.

## Gate 1 decision

Per docs/00 §17 options (`CONTINUE` / `NARROW` / `MORE DATA NEEDED` / `STOP`):

**Decision: NARROW.**

Not a full product `STOP` — but a real, statistically grounded finding that
the two most obvious baseline signals available from **free San Francisco
public data** (long property hold time, and permit/code-violation activity
as a distress proxy) show **no measurable lift** over random ranking for
predicting a sale within ~1 year, on a representative 20,792-parcel sample.

This narrows the plan in a specific, actionable way: it does not disprove
the master prompt's product thesis, but it does mean **the free-data-only
signal set tested so far is not sufficient**. The higher-value signal
categories the constitution names (§16: absentee ownership, tax
delinquency, foreclosure/NOD, ownership-portfolio behavior) were never
tested here because docs/00 Gate 0 already found no free/legal bulk source
for foreclosure data, and the Assessor roll has no owner-name field at all
— so "absentee" isn't even computable from what's been ingested. This
result sharpens why that gap matters: it's not just a missing nice-to-have,
it may be load-bearing for whether this product has an edge at all under
the $300/mo, public-data-only constraint set at the start of this project.

## What this does not prove

- It does not prove no signal exists anywhere in the data — only that these
  two specific, simple constructions of long-hold and permit/violation
  activity don't show one.
- It does not test Task B/C/D (off-market, discount, composite opportunity)
  — no price or owner data exists to test them.
- The systematic `LIKE '%1'` sample, while not geographically clustered, is
  still not proven equivalent to true random sampling — a legitimate,
  disclosed limitation, not hidden.
- Combinations beyond the two tested (e.g. a proper weighted multi-signal
  score, or interaction effects) were not tried — this Gate 1 run tested
  the constitution's own suggested baselines, not an exhaustive signal
  search.
