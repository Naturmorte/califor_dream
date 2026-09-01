# Phase 1b — Assessor Roll Ingestion + Gate 1 Label Source

Status: DONE, with a corrected scope for Gate 1 — 2026-09-01
Ref: docs/00-gate0-and-first-milestone.md (Risk #1), docs/01-phase1-ingestion-report.md

## What was built

Added a third source, `assessor_roll` (DataSF `wv5m-vpq2`), to the same
ingestion pipeline used for Phase 1. This source has a materially different
shape than Building Permits / Notices of Violation — it's an **annual full
snapshot per parcel**, not a transactional log — which required two generic
(config-driven, not hardcoded) additions to `pipeline.py` rather than a
separate pipeline:

1. `extra_hash_excludes` — fields to drop before computing `content_hash`,
   beyond the always-excluded Socrata freshness metadata. `closed_roll_year`
   and `row_id` mechanically differ every year even when nothing about the
   property changed; without excluding them, every parcel would generate a
   spurious "new version" every year forever.
2. `order_by` — multi-field Socrata `$order` (`parcel_number,closed_roll_year`),
   so that for a given parcel, older roll years are always inserted before
   newer ones. This is required for the pipeline's "diff against the most
   recently inserted version" logic to actually mean "diff against the prior
   year," not an artifact of fetch order.
3. `snapshot_year_field` — when a changed field isn't itself a date (e.g.
   `assessed_land_value`), anchor `effective_at` to the roll year
   (`YYYY-01-01`, confidence 0.7) instead of falling back to "now." Without
   this, backfilling five years of history would have produced events that
   all claim to be effective today — actively misleading for any future
   backtest.

## Correction to Gate 0 (docs/00), found by testing against real data

The original Gate 0 table assumed this dataset gave "sale price + sale date."
Live verification against the dataset's own column metadata
(`data.sfgov.org/api/views/wv5m-vpq2.json`) shows: **no sale price field, no
owner name field exist at all.** Only `current_sales_date` does. docs/00 has
been corrected in place (Section B, F, J) rather than left stale.

Practical effect: Task A (sale likelihood, needs only a date) is fully
supported. Task C/D (discount prediction, needs a price) has **no free/legal
price label source identified in this Gate 0 result.** Gate 1, when it runs,
should be scoped to Task A only unless a price source is found first.

## Prop-13 assessed-value-jump hypothesis — first real data point

California Prop 13 reassesses a parcel to full cash value on change of
ownership, which raised the question: could the assessed-value jump around a
recorded sale approximate price, as a workaround for the missing price field?

One real example from the live backfill (parcel `0024007`, San Francisco):

```
2022-06-27  sale recorded (current_sales_date changes)
2023 roll:  assessed_land_value        1,261,413 -> 1,856,400  (+47%)
            assessed_improvement_value   887,935 ->   795,600  (-10%)
```

The land value jumped consistent with a reassessment; the improvement value
*fell* in the same year. This is one data point, not a validated pattern —
it's evidence the hypothesis is worth testing at scale in Gate 1, and equally
evidence that it should not be assumed to work cleanly. Recorded as
`HYPOTHESIS`, not `FACT`.

## Verification (same rigor as Phase 1)

- Live backfill, `closed_roll_year >= 2020`, 5,000-row bounded sample:
  4,847 new versions, 153 rows correctly recognized as unchanged year-over-year
  (proves `extra_hash_excludes` works), 8,930 events derived.
- Re-running the identical command: 0 new versions, 0 events, all 5,000 rows
  recognized as unchanged — idempotency confirmed live, same as Phase 1.
- Event type breakdown in this sample: `ASSESSED_VALUE_CHANGED` 7,813,
  `ASSESSOR_ROLL_FIRST_SEEN` 861, `PROPERTY_SALE_RECORDED` 198,
  `USE_CODE_CHANGED` 46, `UNIT_COUNT_CHANGED` 12.
- `PROPERTY_SALE_RECORDED` events correctly carry the real sale date as
  `effective_at` (not a fallback) — this is the field Gate 1's Task A label
  will be built from.
- All three sources now share the same `entity_id` scheme (`block+lot`), so a
  single parcel's permit, violation, and assessor-roll history join
  automatically without any entity-resolution step — confirmed by inspecting
  cross-source event timelines for real parcels in the ingested sample.

## What's still open before Gate 1 can actually run

- Full historical backfill (not the bounded 5,000-row sample used here) —
  straightforward given the pipeline already works, just needs to actually be
  run across the full 2007-present range.
- A defined T0 cutoff methodology and train/test split (Gate 1's leakage-
  prevention requirements, docs/00 §17) — not implemented yet, this milestone
  only proves the data pipeline underneath it.
- A price label source is still an open gap for Task C/D, not solved here.
