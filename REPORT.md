# REPORT: Dig Once capital plan analysis

ALL ASSET DATA IS SIMULATED. Street geometry, names, lengths, classes and neighborhoods are real (Analyze Boston SAM, MassDOT Road Inventory; `data/SOURCES.md`). Every pipe, pavement, break and cost value is simulated. Results are model outputs under stated assumptions, not predictions about real Boston streets. Per-item status is in [AUDIT.md](AUDIT.md); every number shown in the demo or report is in [docs/claims_ledger.csv](docs/claims_ledger.csv).

> **Update after calibration (read this first).** The break rate is now Calibrated to BWSC (35 failures a year over about 1,018 miles of pipe = 0.0344 per mile, versus the earlier ASSUMPTION of 0.30). That removes the shared-dig result: with the calibrated rate **no pipe work is funded at all** (the full-network plan is 1,404 repaves and 6 preservations, 0 replacements or relines), there are **0 shared digs and $0 dig savings in every one of the 30 seeds**, and the "coordination" advantage is entirely road work. Sections 3 to 5 below were rewritten with the new numbers; the older numbers (break rate 0.30, dig savings $0.22M) are kept only where marked "earlier".

## 1. What changed

- **Return formula (`sim/costs.py`)** now implements `docs/return_formula.md`: wait-a-year option, preserve and reconstruct road options, bundle cost (one dig plus both works) with a marginal check on each add-on, choice by NPV, tier 1 first up to a cap, ranking by return only when the budget binds, `return_lo` and `return_hi`, and a "needs engineering review" flag. All dollar arithmetic is in this file. A test reproduces the section 8 example (2.88, 1.04, 2.74) using the document's benefit figures.
- **Funding:** four sources (bonds, rate revenue, interest-free loan, state revolving loan) with BWSC Table 11 shares, eligibility, cheapest-first assignment, net cost after financing and debt service. Relining is rate-revenue eligible (BWSC p.17); `interfaces.md` listed only replace and repave.
- **Reserve:** sized from the simulation (95th percentile of yearly emergency repair cost over pilot seeds) instead of a fixed 15%, with the balance reported by year. See section 5 for why the result is a cap.
- **CIP report (`cip/`, `make cip`):** executive summary, ranked decision list, funding by year and source with debt service, program pace, engineering review section, not-funded section with what would change the answer, reserve table, methodology page. Outputs in `outputs/cip/` (report.json, decision_list.csv, funding_table.csv, capital_plan.html, capital_plan.pdf).
- **Demo:** a Decision list tab beside the map: row click selects and zooms, the year slider filters, funded segments are coloured by tier, CSV and PDF download, comparison with isolated.
- **Evidence:** a source, status and date for every config value (`sim/config_meta.py`), a config snapshot written beside every results file, and the claims ledger.
- **Experiments:** 30-seed paired comparison with t-based 95% intervals (`make compare`), zero-benefit control, sensitivity sweep with tornado charts (`make sensitivity`), and baselines including an exact knapsack central benchmark (`make baselines`).
- **Fixes found on the way:** the rubric cache grew past 1 GB on full-menu runs and made process pools hang; pools now use `spawn` and the cache is cleared per run.

## 2. Which numbers are Sourced, Calibrated, or ASSUMPTION

**Calibrated (one number):** break rate 0.0344 per mile per year = 35 failures a year / 1,018 miles of pipe.
- 1,018 miles: bwsc.org water system page, "approximately 1,018 linear miles of pipe" (4 to 48 inches), read 2026-10-31 by fetching the page. The page has no date in its body.
- 35 failures a year: "just over 35" from the BWSC CIP, as quoted in `docs/budget_agent_reference.md`; I did not re-read the CIP.
- Caveats: 35 is an average over past years; BWSC's miles of pipe are applied to our 839 miles of city-owned street (one mile of main per mile of street assumed); one count, not a fitted model. This is "calibrated" in the evidence-plan sense (divide the reported failures by miles of main), not a statistical fit.

**Sourced** (as recorded in `docs/assumptions_register.md`; originals not re-read): street network (Analyze Boston SAM, MassDOT Road Inventory); cost inflation 7% (MassDOT FY27-31 CIP p.58); funding mix 29.3 / 30.3 / 21.1 / 19.3 percent (BWSC CIP Table 11); interest-free loan 10 years (BWSC CIP p.18); rate revenue for renewal and replacement (BWSC CIP p.17, relining added by decision); net-cost factors 0.811 / 0.800 / 1.0 (computed, tested).

**Checked but left ASSUMPTION (could not verify):**
- Road user cost `u0` ($0.30 per vehicle-mile at worst condition): the National Academies report "Estimating the Effects of Pavement Condition on Vehicle Operating Costs" (2012) exists, but the chapter I could read had no per-mile figures and the other chapters were not fetched. A web search summary quoted per-driver annual costs from an advocacy group (TRIP); I did not use it. `u0` is the parameter the headline depends on most and remains the top item to source.
- Trench cost, dig penalty `lam`: the City of Davis report (403 Forbidden) and the Nashville appendix (404) could not be fetched. Search summaries mention life reductions from utility cuts of about 6% to 64% in different studies, which would bracket the tested `lam` range of 0.06 to 0.6, but I did not read any of them, so `lam` stays ASSUMPTION with that tested range.
- Discount rate: the USDOT benefit-cost guidance returned 403; no MassDOT or City of Boston rate was found. Stays 4% with 3 to 7% tested.
- Emergency cost per failure, budget per mile: cross-check only. BWSC's 2026 repair and maintenance ($16.3M) plus overtime ($2.65M) lines divided by 35 give about $541,000 per failure as an upper bound (those lines cover far more than main breaks); the model's all-in failure cost is about $527,000 (documented in the register; not re-read). BWSC's water program ($99.3M over three years, from the docs) over 1,018 miles is about $32,500 per mile per year, against the model's $48,000 for pipes and roads together. BWSC's page states a minimum of 8 miles of pipe in each year's capital program (0.79% of the system); the calibrated model funds none (see section 5). Neither figure changed a model value.

**Simulated assumption, everything else:** trench cost $50,000, `lam` 0.3, cycle 15 years, pipe and repave cost per foot, reline share, emergency multiplier 3, worst-case social cost $500,000, `u0`, discount rate 4%, budget $48,000 per mile, return hurdle 1.0, urgency thresholds, treatment lives, preserve and reconstruct parameters, PoF bounds, road benefit band, the state revolving loan rate (2%) and bond terms, the reserve cap (0.25), and the pipe and road simulation itself.

## 3. Results: 30 seeds with confidence intervals (calibrated break rate)

`make compare`: 30 seeds, paired by seed, compact 800-segment area (42 miles), Student t 95% intervals. Total cost = capital + emergency repairs + road user cost over ten years, $M.

| Strategy | Total | Capital | Emergency | Road user |
|---|---|---|---|---|
| isolated | 94.38 ±1.66 | 2.74 ±0.03 | 7.28 ±0.73 | 84.36 ±1.93 |
| pooled | 81.76 ±1.49 | 7.11 ±0.04 | 7.28 ±0.73 | 67.38 ±1.70 |
| coordinated | 81.44 ±1.50 | 7.58 ±0.10 | 7.28 ±0.73 | 66.58 ±1.71 |
| central (20% scan heuristic) | 75.42 ±1.47 | 7.37 ±0.03 | 7.28 ±0.73 | 60.77 ±1.66 |

Paired, coordinated minus comparator:
- vs isolated: total −12.95 ±0.47 (lower in 30 of 30); road user −17.78 ±0.51; capital +4.84 ±0.10; emergency and failures identical (0.00).
- vs pooled (the board alone): total −0.32 ±0.17, lower in 21 of 30; road user −0.80 ±0.25 (28 of 30).
- Dig savings: **$0.00M in all strategies and all 30 seeds.**
- Shares of coordinated total cost: capital 9.3%, emergency repairs 8.9%, road user 81.8%.

`make baselines` (same seeds and area), total $M: age-first 112.7, isolated 94.4, risk-first 94.5, pooled 81.8, single agent 81.8, coordinated 81.4, central heuristic 75.4, central full menu greedy 69.5, central full menu exact knapsack 61.1. Coordinated minus age-first −31.3 ±1.0 and minus risk-first −13.0 ±0.4 (30 of 30 each); minus the exact central benchmark +20.3 ±0.8 (never lower).

Full network, seed 42 (`make cip`, one seed, no interval): coordinated total $1,612M against $1,844M isolated; 1,410 funded projects ($155.0M), 1,410 openings, 0 shared digs; 1,404 repaves, 6 preservations, no pipe work. Isolated funds 526 projects ($60.2M).

Not run: 30 seeds on the full network (`make compare-full`) and the full-menu benchmark on the full network.

**Earlier results (break rate 0.30, uncalibrated, kept for comparison only):** coordinated minus isolated −13.4M, board alone −0.76M, dig savings $0.22M per run, emergency repairs 48% of cost. They differ because that rate was about nine times BWSC's.

## 4. Where coordination wins and where it does not

**Wins.** Against isolated departments, age-first and risk-first: lower total cost in 30 of 30 seeds. The advantage comes from funding more road work (road user cost −$17.8M against isolated): the isolated 60/40 split with no pooling leaves most of the budget unspent (capital $2.7M of about $15M available).

**Does not win, or not for the claimed reason.**
- **There are no shared digs.** With the calibrated break rate no pipe job clears the return hurdle, so there is nothing to bundle: 0 shared digs and $0 dig savings in all 30 seeds, on the full network as well. The project's premise (open a street once for pipe and road work) is not supported by this model at BWSC's failure rate. It re-appears only at much higher break rates (the earlier 0.10 to 0.60 sweep gave $0.01M to $2.97M).
- **The board alone** is $0.32M ±0.17M (0.4%), lower in 21 of 30 seeds, and it comes from the board's join requests roughly doubling the proposals each year (about 880 against 480), not from digs. The zero-benefit control confirms it: with trench and penalty at zero the gap does not vanish (−1.07M ±0.50M, 10 seeds), because dig savings were already zero.
- **Central planners beat coordinated at every scale tried:** the exact full-menu benchmark is $20.3M (25%) cheaper; about $11.9M of that is menu size and about $8.4M is optimisation. The case for agents is private data and scale, not lower cost.
- **A single agent equals pooled.**
- **The result is road work.** Failures and emergency cost are identical across strategies (same city and failure luck), so total cost differences are capital and road user cost only.

**Sensitivity** (`make sensitivity`, 10 paired seeds per setting, calibrated base, break rate swept 0.017 to 0.069): the mean of coordinated minus isolated is negative in 25 of 26 settings. It is +$0.69M ±0.34M (coordination worse) with road user cost 0.1, the small menu and trench cost $100,000 together. The headline depends on `u0` (−1.4M at 0.10 to −31.3M at 0.60), menu size (−6.5M to −16.5M), trench cost (−12.2M to −9.5M) and the reserve cap (−12.4M to −13.2M). It does not move with break rate, social cost, emergency multiplier, `lam` or discount rate within the tested ranges. The board alone is distinguishable from zero in only 10 of 26 settings.

## 5. What could not be verified, and known weaknesses

- **Only the break rate is calibrated**, and only by one division of two figures, one of them quoted second-hand (see section 2). Everything else that drives results (`u0`, trench cost, penalty, failure cost, budget per mile, discount rate) is still ASSUMPTION; I tried to source them and could not read a primary document (list in section 2).
- **The calibrated model conflicts with BWSC practice:** BWSC schedules at least 8 miles of pipe renewal a year; the model funds none, because pipe benefit (the removed loss from 29 breaks a year over the whole simulated city at about $500,000 each) never reaches the cost of work plus a $50,000 trench at the 1.0 hurdle. Either the model undervalues pipe renewal (BWSC also renews for water quality, capacity, regulatory and risk reasons the model ignores) or the cost assumptions are too high. This is the most important open modelling issue; it cannot be resolved without real unit costs.
- **Reserve:** the 95th percentile of yearly emergency cost is now about 0.55 of the capital budget (full network; 1.17 on the 800-segment area), still above my 0.25 cap, so the share is the cap. The reserve covers the typical year but not the 95th percentile year (shortfalls in some years).
- **Roads:** 97% of funded projects are tier 1 Urgent because simulated pavement deteriorates to failed quickly; tier colours carry little information. Road user cost is 82% of total cost and rests on the unverified `u0`.
- **Backtest not done.** `data/processed_water_breaks.csv` has 114 break records (97 Springfield, 15 Ludlow, 2 others; 2025-01 to 2026-09) and no main inventory, so there is no break rate, lift curve or calibration plot. What it can show is on its own page, `outputs/results/break_cohorts.html` (real data, not Boston): 108 of 114 breaks are on cast iron; 85 of 113 with a usable install year occurred on mains aged 50 to 99; 75 of 114 occurred in January and February. A dataset with an inventory is still needed.
- **Section 8 benefits:** `return_example.py` is not in the repo, so the PoF-to-dollar step is tested for structure only.
- **Smaller points:** wait-a-year defers only replacement and repaving; "cheapest source" is by present value (state revolving loan before interest-free); debt service is reported but not deducted from the budget; sensitivity uses 10 seeds; the pipe rubric weights (team's `scoring.py`) were not swept; Claude-driven agents have only mock-model tests; the PDF is long (every funded project) and only page 1 was inspected; 30-seed results are on an 800-segment area.

## 6. How to reproduce

```
make test            # 55 tests
python3 -m experiments.break_cohorts   # real break records by age and material
make cip             # outputs/cip/ (full network, seed 42)
make demo            # demo/site/, serves http://localhost:8000
make compare         # 30 seeds, 800-segment area
make baselines       # baselines and exact central benchmark
make sensitivity     # sweeps and tornado charts in outputs/results/
python3 -m experiments.control_no_benefit
python3 -m cip.ledger   # regenerate docs/claims_ledger.csv
```

Results land in `outputs/results/` with a `.config.json` snapshot beside each file (`outputs/` is git-ignored except `outputs/cip/`).
