# Gate 0 + First Milestone — Real Estate Opportunity Intelligence Platform

Status: DRAFT v1 — 2026-09-01
Scope: Research stage, Phase 0-1 only. Not a build spec for the full platform.

---

## A. Constraints Interpretation

Reality constraints (from user, 2026-09-01):

```text
Developers: 1 (solo, + Claude Code)
Monthly data budget: <$300/mo
Infrastructure budget: assumed same envelope (<$300/mo combined) — ASSUMPTION, not stated separately
MLS access: none
Historical datasets: none
Labeled outcomes: none
Existing users: none
Target market: California — county TBD by Gate 0 (this document)
ICP: not yet defined — ASSUMPTION: individual/small investor or wholesaler, deferred to post-Gate 3
Time until first usable demo: not specified — ASSUMPTION: not a hard constraint yet
Time until first statistical validation: not specified — ASSUMPTION: not a hard constraint yet
```

**Implication for architecture:** everything in this document is scoped for one person, zero paid data contracts, public/legal sources only. No microservices, no graph DB, no ML, no multi-tenant auth, no message queue beyond what a single Postgres-backed worker needs. Anything in the master prompt's "DO NOT BUILD YET" list (§44) is explicitly out of scope until Gate 1/2/3 pass.

---

## B. Gate 0 — Candidate Source Table

Researched 2026-09-01 via live web search (not training-data recall — availability/pricing/ToS drift, so these were checked, not assumed). Labels: **FACT** (verified via official docs/portal), **ASSUMPTION** (plausible but unverified), **HYPOTHESIS** (third-party claim, unverified against primary source).

| Source | Data | Event Date | Historical Data | Access | Legal/ToS | Cost | Freshness | Difficulty |
|---|---|---|---|---|---|---|---|---|
| DataSF — Building Permits (`i98e-djp9`) | Permit applications, status, filed/issued/completed | `filed_date`, `issued_date`, `completed_date` — **FACT** | Full history in dataset | Socrata REST API, no key required — **FACT** | Public Domain Dedication (PDDL 1.0) — **FACT** | $0 | Nightly refresh — **FACT** | Low |
| DataSF — Notices of Violation / DBI Complaints / Code Enforcement (`nbtm-fbw5`, `nyek-jaw8`, `av5k-qvh8`) | Building/housing/electrical/plumbing violations, 311 code cases | Explicit dated fields — **FACT** | Since 2008 (311-based set) — **FACT** | Same Socrata platform — **FACT** | PDDL 1.0 — **FACT** | $0 | Nightly — **FACT** | Low |
| DataSF — Assessor Historical Secured Property Tax Rolls (`wv5m-vpq2`) | Parcel characteristics, assessed value, **current sale DATE only** | `current_sales_date` full day-level precision confirmed live via API, 2026-09-01 — **CORRECTED, was wrong below**. **No sale price field and no owner name field exist in this dataset at all** — verified against the dataset's own column metadata (`data.sfgov.org/api/views/wv5m-vpq2.json`), not inferred. This invalidates the original Gate 0 assumption that this source gives "sale price + date" ground truth; it only gives sale date. `assessed_improvement_value`/`assessed_land_value` are Prop-13 assessed values, not transaction price — live data (parcel `0024007`) shows a real but noisy, partial value jump the roll-year after a recorded sale (land value +47%, improvement value *decreased*), so "assessed value at reassessment ≈ price" is a **HYPOTHESIS to test in Gate 1**, not usable as a price label as-is. | 2007–2024 confirmed in docs; live query 2026-09-01 shows data present through closed_roll_year 2025 at least | Socrata REST/bulk CSV, no key | PDDL 1.0 | $0 | Annual, closed ~August — **FACT**. This is the binding constraint on signal timing, not the daily sources. | Low ingestion effort; **Medium** for correct temporal modeling (see docs/01b) |
| DataSF — Eviction Notices (`5cei-gny5`) | Eviction notice filings since 1997, cause codes | Filing date — **FACT** | Since 1997 | Socrata REST/bulk | PDDL 1.0 | $0 | Regular | **Medium** — see limitation below |
| SF Recorder — Official Records Index (deeds, liens, NOD, reconveyances) | Grantor/grantee, doc type, recording date | Recording date, real event | 1990–present searchable online — **FACT** | Web search UI only, **no bulk export or API confirmed** | Free to *view*, but automated bulk scraping ToS/legality of this specific portal is **UNCONFIRMED** | $0 view / $1.81 per doc copy (immaterial) | Real-time filing | **High** — no API means either manual lookup (doesn't scale) or scraping (legal status unverified) |
| SF Treasurer — Delinquent Secured Property Tax List | Parcels 3+ years tax-delinquent | Real event, but **HYPOTHESIS**: exact publication format (PDF list vs downloadable dataset) not confirmed against primary source | Unknown | Described as viewable "through their office" — **bulk/API access NOT CONFIRMED** | Public record | $0 (assumed) | Unknown | **Unconfirmed — do not build against this until verified** |
| Notice of Default / Notice of Trustee Sale (pre-foreclosure) | Foreclosure filing stage | Real event | N/A | **No free bulk source found.** Only paid aggregators (subscription-based, e.g. commercial foreclosure-data resellers) or per-county recorder lookup | Recorder data is public, but free bulk access not found | Paid aggregators exist but were not priced — out of $300/mo scope by category, not by a number I verified | N/A | **REJECTED for MVP** — no free/legal bulk path found |
| CA Secretary of State — Business Entity Search API (`calicodev.sos.ca.gov` / `api.sos.ca.gov`) | LLC/corp registration, status, registered agent, filing dates | Filing date | Full CA registry (17M+ entities) — **FACT** of portal existing, official state resource | Official developer portal, sign-up required | Official state data | Free tier exists per docs — **ASSUMPTION** on exact rate limits/cost at volume, needs confirmation before relying on it in production | Real-time | Medium — **member/officer-level detail may require pulling separate "Statement of Information" documents, not confirmed to be in the base search API response** |
| LA County — Parcel GIS (ArcGIS REST, `LACounty_Parcel/MapServer`) | Parcel boundaries + basic attributes | N/A (spatial, not event data) | Weekly cache — **FACT** | Free REST API, no key | Public | $0 | Weekly | Low (for parcels only) |
| LA County — permits / code enforcement | Same categories as SF | N/A | **Fragmented**: LA County contains ~88 incorporated cities plus unincorporated areas, each often running its own permit/code-enforcement system — no single consolidated feed found comparable to DataSF | Varies per city | Varies | Varies | Varies | **High** — integration cost, not a single Gate 0 line item |

### 6.1–6.4 discussion

- **Event Time (6.1):** Building Permits and Code Enforcement/Violations are the only sources here with reliable, granular, non-`PRESENT_ONLY` event dates. The Assessor roll is real event data but at **annual** cadence — this caps how "early" any sale-related signal can be, regardless of downstream cleverness. Eviction Notices have a real filing date but the *location* is destroyed to block-level for tenant privacy, which breaks property-level joins — usable only as a neighborhood-density feature, not a per-property signal.
- **Historical Availability (6.2):** Permits and violations: full backfill available today via API pagination. Assessor roll: full backfill 2007–2024 (recheck upper bound). NOD/foreclosure: no historical backfill found at all within budget.
- **Legality (6.3):** DataSF sources are the only ones with an explicit, verified open license (PDDL 1.0). CA SOS is an official state API. The Recorder index and Treasurer delinquent list are public record but their *automation* legality is unverified — do not scrape them without a direct ToS read, and prefer not building Phase 1 dependencies on them.
- **Cost (6.4):** Everything usable in Phase 1 is $0. Estimated monthly data cost for Phase 1: **$0**, well inside the $300/mo budget. That budget is effectively unused until enrichment (geocoding, skip tracing) enters in Phase 7 — a real design implication: we have budget headroom for enrichment later, not for data acquisition now.

## Gate 0 Result

- **Viable sources (Phase 1):** DataSF Building Permits, DataSF Code Enforcement/Violations, DataSF Assessor Historical Secured Property Tax Rolls, CA SOS Business Entity API (pending rate-limit confirmation).
- **Deferred, not rejected:** Eviction Notices (neighborhood-level feature only), SF Treasurer delinquent list (needs primary-source confirmation of access format).
- **Rejected for now:** NOD/foreclosure bulk data (no free/legal bulk path found), full LA County rollout (fragmentation cost too high for solo dev at this stage).
- **Estimated monthly data cost:** $0 (Phase 1–3). Budget reserved for Phase 7+ enrichment.
- **Expected update lag:** permits/violations nightly; assessor roll annual (major constraint, documented, not hidden).
- **Major legal risk:** none identified for the viable-source list (all PDDL or official state API). Risk is concentrated entirely in the *rejected/deferred* sources (recorder scraping) — correctly excluded rather than worked around.
- **Recommended starting county: San Francisco.**

**Decision: CONTINUE** — with scope reduced to what Section C below states plainly.

---

## C. Recommended Market — San Francisco (City & County)

**Why, specifically (not because of the project's name):**

1. San Francisco is a *consolidated* city-county — one government, one set of systems. This is a real, verifiable structural advantage over LA County, which fragments permitting/code-enforcement across ~88 separate city governments. For a solo developer, integration cost scales with the number of independent systems, and SF has one.
2. DataSF is the only source found with (a) a confirmed open license, (b) no-auth REST API, (c) genuine sub-daily-refreshed event data with real `effective_at` fields, across *multiple* signal categories (permits, violations) on the *same platform* — lowering ingestion-pipeline variance.
3. The Assessor roll gives an actual, if annual, ground-truth label source (sale price + sale date per parcel) — necessary for Gate 1 backtesting. Most counties don't publish this for free.

**What this recommendation does NOT claim:** it does not claim SF has more transaction volume, better investor economics, or a bigger opportunity space than LA or San Diego — those are separate, unmeasured questions belonging to Gate 3 (economics), not Gate 0 (data feasibility). Gate 0 only answers "can we reliably get real, legal, free data with real dates." San Diego (SanGIS) was not fully evaluated and is a plausible second candidate if SF's foreclosure-data gap turns out to matter more than expected — flagged as an open alternative, not dismissed.

---

## D. Tech Stack (minimal, matches constraints)

```text
Language:        TypeScript (Node) OR Python — pick one; Python recommended for
                  data/ML-heavy ingestion + easy Socrata/pandas ecosystem
Database:        PostgreSQL (single instance) — relational, handles temporal
                  tables + recursive CTEs for relationships. No graph DB:
                  no query has been identified yet that Postgres can't serve
                  (§14 test). Revisit only with a measured, failing query.
Ingestion:       Scheduled worker (cron or simple job runner) hitting Socrata
                  REST endpoints ($where updated_at > checkpoint), no queue
                  needed at this volume (3 datasets, city-scale, not
                  national-scale).
Storage of raw:  raw_payload as JSONB column, content_hash for dedup, no
                  object storage needed yet (single-county JSON volume is
                  small).
Hosting:         Single VM or local dev + scheduled task; no k8s, no
                  microservices. One process, one deploy target.
Frontend:        Deferred. Phase 1 has no UI — a CLI/notebook is sufficient
                  to inspect ingested data and prove the milestone.
```

No Elasticsearch, Redis, Neo4j, message broker, or container orchestration in Phase 1–3. Each would need its own §14-style justification before being added.

---

## E. Data Model (Phase 1–3 subset only)

Only what's needed to ingest and temporally version the four viable sources — not the full canonical model from §9, which is premature before Gate 1.

```text
raw_record
  source_id            text        -- e.g. 'datasf_building_permits'
  source_name           text
  original_record_id   text        -- source's own permit/violation number
  fetched_at            timestamptz
  effective_at          timestamptz -- filed_date / issued_date / event date
  published_at          timestamptz nullable
  raw_payload           jsonb
  content_hash          text
  schema_version        text
  parser_version        text
  jurisdiction           text        -- 'san_francisco_ca'
  record_type            text        -- 'building_permit' | 'code_violation' | 'assessor_roll'
  ingestion_job_id       uuid
  PRIMARY KEY (source_id, original_record_id, content_hash)

property (minimal)
  property_id            uuid
  apn                    text
  normalized_address     text
  jurisdiction            text
  raw_source_ref          -> raw_record

event (temporal, derived)
  event_id                uuid
  entity_id                uuid       -- property_id for now
  event_type               text       -- 'PERMIT_FILED' | 'PERMIT_ISSUED' |
                                          'VIOLATION_OPENED' | ...
  previous_value            jsonb nullable
  new_value                 jsonb
  effective_at              timestamptz
  detected_at               timestamptz  -- when OUR pipeline noticed it
  source                    text
  confidence                 numeric
```

`effective_at` vs `fetched_at`/`detected_at` is enforced from day one — this is the single most important discipline for backtesting later (§8), and it's cheap to get right now and expensive to retrofit.

---

## F. First Prediction Target

The template in §17 suggests horizons of 30/90/180/365 days. **I'm not adopting 30/90/180 as stated — that would be dishonest given the data.** The only ground-truth label source identified (Assessor roll) updates **once a year**, and its sale-date field has confirmed truncated precision. Predicting a 30-day sale event against a label that's only resolved annually, at reduced date precision, is not a supportable claim.

**First target (Task A, single horizon):**

`P(arm's-length sale within 365 days | signals observable at T0)`

using:
- **Label**: year-over-year change in `current_sales_date` in the Assessor roll (`PROPERTY_SALE_RECORDED` event, implemented and verified live 2026-09-01 — 198 such events found in a 5,000-row sample). **Corrected from the original draft**: the roll has no owner-name field at all (verified against the dataset's own column metadata), so "owner-name change" is not an available label signal from this source — sale-date change is the only ground truth this source provides. `PRESENT_ONLY` risk stands: T0 must be set to a prior closed-roll date, not "today".
- **Not available from any free/legal source found so far**: sale *price*, which means **Task C/D (discount prediction) has no price-label source in this Gate 0 result** — see docs/01b. Gate 1 as currently scoped can only address Task A (sale likelihood), not discount magnitude, until a price source is found.
- **Features**: building permit activity, code violation/complaint activity, hold duration (years since last owner change in roll history), property characteristics from the roll itself.

This is stated as a **research target for Gate 1**, not a production commitment. 90/180-day horizons may become viable later *if* a higher-frequency transaction/deed source is found (this is exactly why the Recorder-index gap in Section B matters — it's the thing that would unlock shorter horizons, and it's explicitly flagged as unresolved, not silently dropped).

---

## G. Baseline

Per §17, all four required:

1. **Random ranking** — trivial, computed directly from label base rate.
2. **Strongest individual signal alone** — e.g., "long hold" (years since last transfer) used by itself as the entire ranking function.
3. **Simple realistic investor heuristic** — `absentee-style proxy (mailing address ≠ situs address, derivable from Assessor roll) + long hold + any open code violation`, combined with unweighted AND/OR logic, no ML.
4. **Best affordable comparable product accessible to the eventual ICP** — not yet identified since ICP is undefined (flagged as ASSUMPTION gap in Section A). Deferred until ICP is set; Gate 1 can run with baselines 1–3 in the meantime and add 4 later without invalidating the earlier ones.

---

## H. First Milestone (Phase 1)

**Goal:** prove we can reliably fetch, normalize, and temporally-version real property events from DataSF Building Permits (primary) and DataSF Code Enforcement/Violations (secondary), with correct provenance and idempotent re-ingestion — satisfying §47's requirement literally, using the two sources confirmed in Gate 0 to have real, granular, legally-clean event dates.

**Deliverable:**
- Postgres schema for `raw_record` and `event` (Section E).
- Ingestion job for DataSF Building Permits: paginated Socrata fetch, checkpointed by `updated_at`, writes `raw_record` rows, computes `content_hash`, is idempotent on re-run.
- Same for Code Enforcement/Violations dataset.
- A derivation step that turns new/changed `raw_record` rows into `event` rows, correctly populating `effective_at` (source date) separately from `detected_at` (pipeline run time).
- Basic CLI/script to query: "what changed for property X between two ingestion runs."

**Explicitly not in this milestone:** entity resolution beyond APN-exact-match, ranking, valuation, ML, UI, CA SOS integration, Assessor-roll ingestion (that's a natural Phase 1b, but the *first* milestone should prove the harder daily-cadence case first).

---

## I. Acceptance Criteria

1. A full backfill run against DataSF Building Permits ingests a verifiable count of records; spot-check 10 random records against the live Socrata API confirms field-for-field match.
2. Re-running the same ingestion job twice produces **zero** duplicate `raw_record` rows (idempotency proven, not asserted).
3. `effective_at` is populated from the source's `filed_date`/`issued_date`/`completed_date` and is demonstrably different from `fetched_at`/`detected_at` for at least one real record (i.e., not just copying fetch time into both fields — a bug that would silently defeat all future backtesting).
4. Running the job on two different days against a dataset that has genuinely changed produces at least one correctly-typed `event` row (e.g., `PERMIT_ISSUED`) with correct `previous_value`/`new_value`.
5. Same four checks repeated for the Code Enforcement/Violations source.
6. A short written note records: actual record counts ingested, any schema surprises encountered, and any field that didn't match what Section B assumed (Gate 0 table gets corrected in place if wrong, not left stale).

---

## J. Biggest Risks (top 5)

1. ~~Assessor roll date truncation~~ **RESOLVED, non-issue** — verified live 2026-09-01: `current_sales_date` has full day-level precision via the API. The real, bigger risk found in its place: **the Assessor roll has no sale-price field and no owner field at all** (verified against the dataset's own column metadata, not inferred). Task A (sale likelihood) is unaffected — it only needs the date, which is confirmed and now implemented. Task C/D (discount prediction) has **no price ground-truth source** in the current Gate 0 result; the Prop-13 assessed-value-jump proxy is a live-data-supported but noisy hypothesis (see docs/01b), not a substitute.
2. **No property-level foreclosure/pre-distress signal at all** in the free/legal source set — this removes one of the master prompt's named highest-value signal categories (§16: foreclosure, tax delinquency) from the entire research stage unless the Recorder-index or Treasurer-list access questions get resolved later.
3. **CA SOS API rate limits/cost at volume unconfirmed** — if it turns out to be metered per-call in a way that doesn't fit $300/mo at the volume needed for portfolio/LLC signals (§13), that whole relationship-layer feature category is delayed.
4. **Single-city data may not generalize** — even if Gate 1 shows a real lift in SF, that's evidence about SF's data-generation process, not a general claim about the product across markets. Must be stated plainly if/when Gate 1 results are reported.
5. **Annual label cadence structurally caps this research stage's usefulness** — even a "successful" Gate 1 result on a 365-day horizon says less about product viability than a 30-day result would, because real investor decisions happen faster than a once-a-year label lets us validate. This is a genuine ceiling on what Phase 1-6 can prove, not a wording problem.

---

## K. What Not to Build Yet

Per §44, explicitly deferred: AI assistant/chat, graph visualization, multi-market support, deep learning, custom graph DB, outreach automation, development underwriting, enterprise admin/RBAC beyond a single user, sophisticated CRM, and — specific to this plan — Assessor-roll ingestion, CA SOS integration, entity resolution beyond exact-match, any ranking/scoring, and any UI. All of it waits behind Gate 1.

---

## L. Where This Plan Can Be Wrong

1. **SF may simply lack enough opportunity volume/dollar value** to matter economically, even if the signal detection works — that's a Gate 3 question this plan cannot answer yet, and choosing SF for *data* reasons doesn't guarantee it's right for *economics* reasons.
2. **The Assessor roll's annual cadence may make Task A (365-day sale prediction) too coarse to be a meaningful proxy for the deal economics the product actually needs** (which care about *this week's* new distress, not *this year's*).
3. **"No free bulk foreclosure data" may be wrong** — it may exist and simply wasn't surfaced by this search pass; a follow-up direct check of `sfassessor.org`/`sftreasurer.org` and the actual Recorder ToS page (not just search-result summaries) could change Section B's foreclosure row from REJECTED to DEFERRED.
4. **CA SOS API may not actually expose LLC officer/member names** in the base search response (only registered agent) — if so, the entire "common officers / related LLCs" relationship signal (§13) has no cheap data path in this plan and needs a different source or manual sampling.
5. **Single-jurisdiction simplicity is being weighted heavily against LA's larger opportunity volume** — this is a judgment call under solo-dev/$300-budget constraints, not a proof that SF beats LA in general. A well-resourced team should probably reach a different Gate 0 conclusion.
6. **PDDL license covers DataSF's own datasets, not necessarily every field re-published inside them** (e.g., if a field is sourced from a third party into DataSF) — the "exceptions noted" clause in the terms of use wasn't checked per-dataset, only at the portal level.
