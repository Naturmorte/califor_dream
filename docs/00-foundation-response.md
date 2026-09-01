# 00 — Foundation Response (Gate 0 / First Response per §50)

Status: DRAFT — depends on user confirmation of critical ASSUMPTIONs marked below.
Date: 2026-09-01

This is the constitution-mandated "first response" (§50 of MASTER PROMPT v4). It is analysis and
scoping, not implementation. Per §44/§47, no production code is written until Gate 0 sources are
verified and Phase 1 (ingestion) is scoped.

---

## A. Constraints Interpretation

None of §5's reality constraints were supplied by the user. Per §1 ("не вигадуй"), the numeric
values below are NOT invented — they are marked ASSUMPTION and must be confirmed before Gate 0 is
finalized. Where I had to pick a working default to keep moving (per §0 autonomous-mode rule), I
did, and flagged it.

```text
Developers:                  ASSUMPTION — solo developer (no team mentioned)
Monthly data budget:         UNKNOWN — treat as bootstrap-tier (<$500/mo) until confirmed
Infrastructure budget:       UNKNOWN — treat as single small VM / managed Postgres until confirmed
MLS access:                  ASSUMPTION — none (no broker/MLS affiliation mentioned)
Historical datasets:         UNKNOWN — none currently licensed
Labeled outcomes:            FACT — none exist yet (no prior product/users mentioned)
Existing users:               FACT — none
Target market:               ASSUMPTION — California, inferred ONLY from working-dir name
                              "califor_dream". Not confirmed by user. HIGH-IMPORTANCE gap — see §L.
Target county:                NOT YET DECIDED — see section C
ICP:                         HYPOTHESIS — independent/small real-estate investors (flip or buy-
                              and-hold) operating in a single county, not institutional funds
Time until first usable demo:        ASSUMPTION — weeks, not days (solo dev, real ingestion work)
Time until first statistical validation (Gate 1): UNKNOWN — depends on how much historical
                              transaction history the chosen county's source actually exposes
```

**This is the single biggest open gap in this response.** Everything in sections C, D, H below is
downstream of "solo dev, bootstrap budget, California." If any of those are wrong, re-run Gate 0.

---

## B. Gate 0 — Candidate Data Sources

Assessment based on general public knowledge of how US county real-estate data is typically
published, NOT on live verification of any specific county's current portal/API/ToS. Treat
cost/access/difficulty as HYPOTHESIS until someone actually pulls from the live source — this
table itself is not Gate 0 completion, it's Gate 0 scoping.

| Source | Data | Event Date | Historical Data | Access | Legal/ToS | Cost | Freshness | Difficulty |
|---|---|---|---|---|---|---|---|---|
| County Assessor (parcel/characteristics) | ownership snapshot, land use, building chars, assessed value | mostly PRESENT_ONLY (snapshot, not event-dated) | usually current-only unless county publishes annual rolls | often open (CSV/API/GIS) | open data, typically fine | free–low | quarterly/annual | low–medium |
| County Recorder (deeds, liens, judgments) | transactions, transfers, deed type, financing docs | real effective_at (recording date) | varies — some counties index back decades, some don't | **CA counties typically do NOT offer free bulk deed data** — usually per-document fee or requires a paid vendor (ATTOM/DataTree/CoreLogic/PropertyRadar-class reseller) | public record but access-gated | low (per-doc) to moderate/high (bulk via vendor) | daily–weekly at vendor, days at county | medium–high |
| County Treasurer / Tax Collector | tax delinquency, lien sales | real effective_at | usually current-only public view | often open | open | free–low | monthly | low |
| City/County Building Permits | permit filed/issued/withdrawn | real effective_at | often several years via Socrata/ArcGIS open data portals | open in most CA cities (LA, SF, San Diego, Sacramento all run open-data portals) | open data | free | daily–weekly | low |
| Code Violations | violation events | real effective_at | patchy — depends on city | open in some cities, absent in others | open where present | free | weekly | medium |
| Probate Court Filings | probate case events | real effective_at | rarely digitized/open | mostly in-person/PACER-equivalent, county-specific | public record, access-gated | low–moderate (per lookup) | slow | high |
| Bankruptcy (PACER) | filings | real effective_at | yes, federal system | official API, paid per page | official, licensed | low (~$0.10/page-class fee, needs verification) | daily | medium |
| Foreclosure notices (NOD/NOS) | distress events | real effective_at | patchy at county level; commercial aggregators much better | county recorder or paid vendor (ATTOM/RealtyTrac-class) | public record / licensed | free (county) to moderate (vendor) | daily (vendor) | medium–high |
| Secretary of State (CA SOS) business filings | LLC/corp officers, registered agent | real effective_at (filing date) | yes, bulk data available | open, some bulk downloads, some paid | open/licensed | free–low | days–weeks | low–medium |
| MLS listing data | listing/DOM/price reductions | real effective_at | requires broker/vendor relationship (RESO Web API) | restricted — needs board membership or paid feed reseller | licensed, ToS-restricted | moderate–high | real-time at source | high (access, not technical) |
| Zillow/Redfin/Realtor.com scraping | listing signal | n/a | n/a | **prohibited by ToS** | prohibited | n/a | n/a | REJECT |
| Skip tracing (BatchSkipTracing/TLOxp/IDI-class) | owner phone/email | n/a (enrichment, not event) | n/a | commercial API | licensed, TCPA/DNC implications on use, not on acquisition | per-lookup fee (commonly cited industry range ~$0.05–$0.30/lookup — UNVERIFIED, do not treat as fact) | on-demand | low (integration), high (compliance) |
| US Census / TIGER / OSM geocoding | geometry, demographics | n/a | yes | open | open | free | static/annual | low |

### Rejected outright
- **MLS scraping or unlicensed MLS data reseller feeds** — ToS/legal risk, REJECT until a licensed feed is budgeted.
- **Zillow/Redfin scraping** — explicit ToS prohibition, REJECT.

### Gate 0 result (preliminary, pending live verification)

- **Viable without paid vendor:** Assessor parcels, building permits, tax delinquency, CA SOS business filings, geocoding.
- **Requires a paid vendor or per-document fee to be usable at scale:** Recorder deed/transaction history, foreclosure notices, probate. This is the crux — Task A/C/D labels (§3) depend on transaction history, which in California is the least-open layer.
- **Estimated monthly data cost:** UNKNOWN — cannot be stated as a number without either (a) confirmed budget or (b) a live quote from a recorder-data vendor. Do not treat any figure here as fact.
- **Major legal risk:** none of the free-tier sources above carry material legal risk. Risk concentrates entirely in (1) MLS access and (2) skip-tracing/contact use under TCPA — both deferred past Gate 1.

**Decision: CONTINUE, with REDUCE SCOPE on transaction data** — start with what's free (assessor + permits + tax + business filings) to prove the entity-resolution/temporal/event-detection pipeline (Phase 1–3) works at all, before paying for recorder/transaction data needed for Gate 1 labeling.

---

## C. Recommended Market

HYPOTHESIS, pending confirmation of the California assumption in §A.

Within California, LA County is the largest and most obvious choice but is high-competition
(most existing wholesaler/investor tooling already targets it) and its Recorder data is
gated like every CA county's. A mid-size county with a working open-data culture reduces
both cost and time-to-first-signal without giving up a real investor market.

**Recommended starting county: Sacramento County, CA**
- City of Sacramento + Sacramento County both run active open-data portals (permits, code enforcement).
- Assessor parcel data is accessible.
- Smaller/less saturated than LA/SF/San Diego for real-estate-investing tooling — more room to
  validate an edge before worrying about competitive obviousness (§28).
- Still large enough (>1.5M county population) to generate enough monthly transaction volume for
  eventual statistical testing.

**Alternative: San Diego County, CA** — comparable open-data maturity, larger/more expensive
market, more competition.

This is a starting hypothesis for Phase 0 verification, not a committed decision — confirm with
user before spending budget on a recorder-data vendor scoped to this county.

---

## D. Tech Stack (minimal, per §14)

No component added without a stated reason. Default to boring.

- **Storage:** PostgreSQL + PostGIS (parcel geometry). Single instance, no read replicas, no
  sharding — county-scale data (low millions of rows including full temporal history) does not
  need it. Graph DB / Elasticsearch / ClickHouse / Redis: NOT added — no query has been shown yet
  that Postgres + recursive CTEs can't serve (§14 gate).
- **Raw snapshot storage:** flat files (JSON/Parquet) on local disk or a single low-cost object
  store (e.g., Cloudflare R2/S3-compatible) — needed for `raw_payload` preservation (§7), not a
  database concern.
- **Ingestion/ETL:** Python, plain scripts + a lightweight scheduler (cron, or Prefect if retries/
  DAG visibility earn their keep — not decided yet, cron is the honest MVP default for a solo dev).
- **API layer:** none yet. Not needed until Phase 9 (feed/property intelligence). Building it now
  would violate §44.
- **Frontend:** none yet. Same reasoning.
- **ML:** none yet — Stage 0 is rules + descriptive stats (§32).

---

## E. Data Model (Phase 1–3 subset only)

Full canonical model is §9 of the constitution; only the tables actually needed for Milestone 1
are listed here — building the rest now would be premature.

- `raw_records` — per §7 fields (source_id, fetched_at, effective_at, published_at, raw_payload,
  content_hash, schema_version, parser_version, ingestion_job_id, jurisdiction, record_type)
- `properties` — internal_id, apn, address, normalized_address, geometry, zoning, land_use,
  building characteristics, assessed values
- `ownership` — property_id, owner_ref (person/company/trust), start, end, evidence, confidence
- `persons`, `companies`, `trusts` — minimal fields from §9, expand only when a source populates them
- `events` — event_type, entity_id, previous_value, new_value, effective_at, detected_at, source,
  confidence (§15)
- `ingestion_jobs` — job_id, source_id, status, started_at, completed_at, records_processed,
  records_failed (observability, §40)

Transaction, Loan, Permit, LegalEvent, Listing, Contact tables are deferred until their source is
actually connected (permits table arrives with the permits ingestor, etc.) — no empty tables for
future features.

---

## F. First Prediction Target

**Task A — Sale Likelihood, 180-day horizon**, on a single segment (single-family + small
multifamily, 2–4 units) in the recommended county.

Reasoning: it's the only task in §3 whose label doesn't require solving something else first.
- Task B (off-market) needs a reliable arm's-length-and-off-market classifier, which needs deed-type/MLS cross-referencing not yet available.
- Task C (discount) needs a working valuation engine (Phase 5, after Gate 1).
- Task D (economic opportunity) is the actual product goal but is a composite of A+C+contact+economics — not a first-milestone label.
- Task E (response/close) needs proprietary outcome data that doesn't exist yet.

This is explicitly the easiest-to-label starting point, not the end goal — flagged in §L as a risk that easiest-to-label ≠ most monetizable.

---

## G. Baseline

- **Baseline 1:** random ranking (statistical floor).
- **Baseline 2:** strongest single signal alone (e.g., tax delinquency alone, or long-hold alone).
- **Baseline 3 (primary comparison):** simple realistic investor heuristic — `absentee owner AND hold >10yr AND ≥1 distress/legal event in trailing 12mo`. This is the one the system has to beat to mean anything.
- **Baseline 4 (deferred):** a paid commercial list/filter product (e.g., PropStream-class). Deferred because it requires its own subscription budget to even generate a comparison — not affordable at bootstrap tier per §A. Flagged as a real gap: without Baseline 4, "we beat baseline" only proves we beat a heuristic we invented ourselves, not that we beat what a real investor could already buy.

---

## H. First Milestone

Per §47 — not a UI demo. Concrete deliverable:

> Reliably ingest, normalize, and temporally-version real property records from **one** source
> (recommended: county Assessor parcel data for the chosen county) into `raw_records` +
> `properties`, with idempotent incremental sync and raw snapshot preservation.

Scope explicitly excludes: entity resolution beyond exact-match dedup, any signal/event logic,
any ranking, any UI.

---

## I. Acceptance Criteria

- Ingestion job successfully pulls ≥95% of the target county's published parcel records without
  unhandled failure (remainder logged to dead-letter, not silently dropped).
- Every stored record has `content_hash`, `fetched_at`, and either a real `effective_at` or an
  explicit `PRESENT_ONLY` flag (§6.1) — no field is silently left null where the source is
  actually PRESENT_ONLY.
- Re-running the same ingestion run produces zero duplicate rows (idempotency test, automated).
- A deliberately malformed/shifted-schema test record triggers schema-drift detection rather than
  silently corrupting downstream data.
- Gate 0 table (§B) is updated with **live-verified** cost/access/legal status for the chosen
  county's Assessor source (this draft is HYPOTHESIS, not verified).
- Unit + integration tests pass for the ingestion path.

---

## J. Biggest Risks (top 5)

1. **California recorder/transaction data is the hardest part of the whole stack to get cheaply**, and it's exactly the data needed for Gate 1 (sale/discount labels). Budget reality could force either a paid vendor spend earlier than planned, or a pivot to a non-CA county with more open recorder data — which would contradict the "califor_dream" assumption.
2. **Scope-vs-capacity mismatch.** This constitution is a 50-section production system; a solo developer building all of it before validating Gate 1 would violate the document's own §0/§44 rules. Real risk is discipline, not technical difficulty.
3. **No labeled outcomes exist**, so Gate 1 statistical validation is gated entirely on how much historical transaction depth the chosen source actually has — could be months before there's enough history to backtest against, not a solo-dev-controllable timeline.
4. **Baseline 4 is unaffordable at bootstrap budget**, weakening the strength of any "we beat baseline" claim (§G) — the system could clear Gate 1 against a self-defined heuristic and still lose to a $50/mo commercial tool never actually tested against.
5. **Contactability economics (Gate 3) could kill the product even if Gate 1/2 pass** — skip-tracing cost and TCPA-constrained response rates are unverified assumptions (§B) and are the most likely place for "the model works but the business doesn't."

---

## K. What Not To Build Yet

Per §44, plus specific to this response: multi-source ingestion beyond the first source, any
frontend, any ML (Stage 0 rules only, and not until Phase 3+), graph DB, contact/skip-tracing
integration, valuation engine, economics module, entity resolution beyond deterministic exact-match, API layer.

---

## L. Where This Plan Can Be Wrong

1. **The California/Sacramento assumption is inferred from a folder name, nothing else.** If the actual target market is different, sections C, D (vendor choice), and the entire Gate 0 table's legal/cost column need re-doing — this is the single highest-leverage thing to confirm early.
2. **The "solo developer, bootstrap budget" assumption may be wrong** — if there's actually a team or funding, the "reduce scope" posture in §B/§H is overly conservative and slows things down for no reason.
3. **Sacramento may not match the user's actual investor demand** even within California — the choice optimizes for open-data maturity over market size/margin, which is a real tradeoff not validated with the user.
4. **Task A (plain sale-likelihood) may not be the right first target even as a stepping stone** — it's chosen for label-availability, but a model that predicts sale-likelihood well could still be economically useless if it doesn't correlate with discount/off-market opportunity (Task D, the actual product goal). Easiest-to-label ≠ most informative-to-validate.
5. **PostgreSQL-first may hit real limits sooner than assumed** if the constitution's full temporal event history (every observed state change, forever) is kept at full county scale — this is asserted as fine in §D without a load test, which contradicts the document's own rule against unmeasured scalability claims (§1). Needs an actual row-count/query-latency estimate once real data volume is known, not an assumption.
6. **Skip-tracing cost figures cited in §B are industry folklore, not verified numbers** — Gate 3 economics (§26) cannot be trusted until a real vendor quote replaces that placeholder.

---

## Immediate next action (blocking on user)

Before Phase 0 (Gate 0) can be marked complete, need confirmation or correction on:
1. Is California actually the target market? Which county, if known?
2. Rough team size / monthly budget ceiling (even an order-of-magnitude answer is enough — "solo, <$300/mo" vs "small team, $5k/mo" changes the whole plan).
3. Any existing data access already secured (MLS, a licensed vendor, prior scraped datasets)?

Until then, Phase 1 work will proceed against the Sacramento-County/bootstrap-budget assumption
per the autonomous-mode rule in §0, and will be revised if those assumptions are corrected.
