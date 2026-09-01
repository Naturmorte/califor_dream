# Gate 1, Round 2 — New Signals + Combined Model

Status: FIRST POSITIVE (QUALIFIED) RESULT — 2026-09-01
Ref: docs/03-gate1-full-run-report.md, docs/00 §32 (ML stage discipline)

## What was tested

Reused the data already ingested for docs/03 (no new pulls needed) and added
three new features, computable for free from the Assessor roll alone:

- `value_jump_pct` — % change in assessed land+improvement value, T0-1 → T0
  (a same-period reassessment jump; a possible proxy for an ownership change
  that didn't register as a same-year `current_sales_date`, e.g. inherited
  or gifted transfers, which are common and not always "arm's-length")
- `use_code_changed` — property use code differs T0-1 vs T0
- `unit_count_changed` — unit count differs T0-1 vs T0

Per docs/00 §32, individual (Stage 0) checks came first.

## Individual signals: no clean win, one caution flag

| Feature | n (flag=1) | P(sale) | 95% CI | vs base rate 4.59% |
|---|---|---|---|---|
| value_jump > 10% | 806 | 3.85% | [2.72%, 5.41%] | overlaps, not significant |
| use_code_changed | 30 | 13.33% | [5.31%, 29.68%] | borderline — n=30 is too small to trust; flagged, not claimed |
| unit_count_changed | 34 | 2.94% | [0.52%, 14.92%] | overlaps, not significant |

None of these three individually clear the bar on their own. `use_code_changed`
is the one worth watching (point estimate 3x base rate) but n=30 is far too
small for the CI to mean much — noted as a lead for a larger sample, not a
finding.

## Combined logistic regression: a real, qualified signal

Fit a plain logistic regression (numpy, no sklearn dependency, standardized
features) on all 6 features (`long_hold_years`, `value_jump_pct`,
`use_code_changed`, `unit_count_changed`, `recent_permits`,
`recent_violations`). A single 70/30 split looked strong (Lift@20 = 3.27x)
but n=20 in a small test set isn't trustworthy on its own — replaced with
**5-fold cross-validation, pooled out-of-fold predictions across all 14,100
usable rows** (rows with complete data on all 6 features; 6,605 of 20,705
excluded for missing `long_hold_years` or `value_jump_pct` — see caveats).

| K | Precision | 95% CI | Lift | Statistically significant vs random? |
|---|---|---|---|---|
| 20 | 10.00% | [2.79%, 30.10%] | 2.35x | No — CI too wide at this n |
| **50** | **12.00%** | **[5.62%, 23.81%]** | **2.82x** | **Yes — CI excludes the 4.25% base rate** |
| 100 | 8.00% | [4.11%, 15.00%] | 1.88x | Borderline (lower bound 4.11% vs base 4.25%) |
| 300 | 4.00% | [2.30%, 6.86%] | 0.94x | No — signal has decayed to random by here |

**This is the first result in this whole exercise where a confidence
interval clears the random baseline** — at K=50, cleanly; at K=100,
borderline. The shape (strong at the top, decaying to nothing by K=300) is
what a real, modest ranking signal is supposed to look like, structurally
different from docs/03's flat-to-negative results.

## A genuinely surprising direction: recency, not staleness

The fitted weight on `long_hold_years` is **negative** (-0.27, standardized):
shorter hold time predicts a *higher* near-term sale probability in this
model — the opposite of the "long-held property is overdue for a sale"
intuition tested (and rejected) in docs/03. A plausible read, `HYPOTHESIS`
not fact: recently-sold units (investor flips, condo churn) are more likely
to sell again soon than long-held stable ownership. Worth testing directly
as its own feature before trusting this interpretation.

## Why this is not a Gate 1 pass yet — real caveats, not hedging

1. **Multiple comparisons.** Three new individual features, four K values, one
   combined model — some chance any single "hit" here is noise from testing
   several things. K=50's result is the strongest single number and should
   be treated as one candidate finding to confirm, not a proven result.
2. **32% of the sample was excluded** (missing `long_hold_years` or
   `value_jump_pct`) to build this feature set — parcels with no on-record
   prior sale, or a zero/missing prior-year assessed value, are
   systematically different from the rest. This could bias the result in
   either direction and hasn't been characterized.
3. **Cross-validation within one T0 vintage is not a true temporal
   out-of-sample test.** All 5 folds share the same T0=2023/label=2024
   macro conditions (interest rates, market conditions that year). The real
   test is whether this exact fitted approach still shows lift on a fresh
   T0 (e.g. T0=2024, label=2025) once that data exists — not yet possible,
   2025 roll data availability wasn't confirmed.
4. Still Task A only (sale likelihood) — no discount/price capability, same
   Gate 0 gap as before.

## Gate 1 status update

Previous decision (docs/03): `NARROW`. This round changes it to:

**Decision: CONTINUE, narrowly** — specifically for a combined-signal
ranking model targeting a small top-K working set (K≈50, matching where the
CI actually clears random), not for any single hand-picked heuristic. The
next required step before trusting this further is an actual **temporal**
holdout (a later T0, not cross-validation within one T0) — flagged as the
next validation gate, not yet run.
