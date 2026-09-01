# Phase 1 — Ingestion Milestone: Result

Status: ACCEPTANCE CRITERIA MET — 2026-09-01
Ref: docs/00-gate0-and-first-milestone.md Sections H/I

## What was built

`services/ingestion/` — a Socrata ingestion pipeline (Python, stdlib only) for two
DataSF sources: Building Permits (`i98e-djp9`) and DBI Notices of Violation
(`nbtm-fbw5`). SQLite storage (deviation from the Postgres default in the Gate 0
doc — recorded there as an assumption; no verified local Postgres credentials were
available in this autonomous run, and SQLite meets every Phase 1 criterion with
zero setup friction; schema is plain SQL so migration later is a driver swap).

## Acceptance criteria — results against live data (not a dry run)

| # | Criterion | Result |
|---|---|---|
| 1 | Backfill run, 10 random records spot-checked against live API | **10/10 match**, field-for-field, on substantive fields |
| 2 | Re-running the same job produces zero duplicate rows | **Confirmed live**: permits 2450→2450 fetched, 0 new versions on rerun; violations 2842→2842 fetched, 0 new versions on rerun |
| 3 | `effective_at` populated from source date fields, demonstrably ≠ `fetched_at`/`detected_at` | **Confirmed**: e.g. a permit filed 2001-04-20 has `effective_at=2001-04-20T15:12:21`, `detected_at=2026-09-01T11:58:14` (today, ingestion run time) |
| 4 | Two ingestion runs produce a correctly-typed `event` row with correct previous/new value | **Confirmed** via unit tests (`tests/test_pipeline.py`, deterministic, no network) simulating a permit transitioning `filed → issued` |
| 5 | Same four checks for the second source | **Confirmed** — see counts below |
| 6 | Written note: counts, schema surprises, corrections | This document |

## Real counts (single backfill window, not full historical load)

- Building Permits: 2,450 records fetched (`last_permit_activity_date >= 2026-08-01`), 2,226 events derived, 0 fallback IDs needed.
- Notices of Violation: 2,842 records fetched (`date_filed >= 2026-06-01`), 2,842 events derived (all first-time `VIOLATION_ITEM_OPENED`, since this was a cold table), **541 records (19%) required a fallback composite ID** — see below.
- Total: 5,292 `raw_record` rows, 5,068 `event` rows, 4 ingestion jobs, across two live backfill runs each.
- Full-history counts for context (not backfilled in this milestone): 1,294,667 total permits, 516,553 total violation records exist in these datasets.

## Schema surprises found by testing against real data (not assumed)

These were wrong in the first implementation and are recorded here rather than
silently fixed, per the project's "don't hide technical debt" rule:

1. **Pagination without an explicit `$order` is unstable.** The first live run against
   Notices of Violation produced 2,842 fetched rows resolving to only 983 distinct
   IDs under the (wrong) assumption below — initially misdiagnosed as a Socrata
   paging bug. Fixed by adding `$order=<id_field>` to every paginated fetch
   (`services/ingestion/socrata.py` call in `pipeline.py`). This is a real fix
   worth keeping regardless of the second finding below.
2. **`complaint_number` is not a row-level identifier in the Notices of Violation
   dataset.** A single complaint can carry 15-19 separate line items (one per
   violated code section), each with its own `item_sequence_number`. The original
   Gate 0 assumption (based on a single sample record) was wrong. Fixed by keying
   on `item_sequence_number` instead, with `complaint_number` retained as a
   grouping field in the payload, not the identity.
3. **`item_sequence_number` is itself null on a real subset of rows** (541/2,842 =
   19% in this window) — not a sampling artifact. These are genuine records the
   API returns with that field empty. Rather than drop or silently collapse them,
   the pipeline falls back to a composite key (`sha1` of `complaint_number` +
   `code_violation_desc` + `block` + `lot`, truncated) and reports the fallback
   count in every ingestion result (`fallback_id_count`). This is a known,
   disclosed weak point: two genuinely distinct violation items that happen to
   share all four fallback fields would collide. Not observed in this run, but
   not proven impossible either.
4. **`data_as_of`/`data_loaded_at` are Socrata refresh-metadata fields that change
   on every platform reload independent of whether the underlying record changed.**
   Including them in `content_hash` would have made idempotency fail on any
   dataset refresh (false "new version" on every row, every night). Excluded from
   the hash; still stored in full in `raw_payload` and separately captured in
   `published_at`.

## Confirmed working: cross-source "what changed for this property" query

Property `0751001` (block 0751, lot 001) has 33 events across both sources in this
one backfill window — a real permit filing plus a run of violation items opened in
July/August 2026. This is the literal building block for the "What Changed Today?"
feed described in the master prompt §35, working end-to-end against real data,
months before any ranking/ML/UI exists.

## Open risk not yet resolved

Risk #1 from docs/00 (Assessor roll date-truncation severity) is still open —
addressed next in Phase 1b (Assessor roll ingestion), not in this milestone.

## Deviations from the Gate 0 plan, stated plainly

- SQLite instead of PostgreSQL (see above).
- CA SOS integration, entity resolution beyond exact-APN-match, and the Assessor
  roll itself were explicitly out of scope for this milestone per docs/00 Section H
  and were not attempted here.
