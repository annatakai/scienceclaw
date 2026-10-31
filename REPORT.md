# REPORT: Dig Once capital plan analysis

ALL ASSET DATA IS SIMULATED. Street geometry, names, lengths, classes and neighborhoods are real (Analyze Boston SAM, MassDOT Road Inventory; `data/SOURCES.md`). Every pipe, pavement, break and cost value is simulated. Results are model outputs under stated assumptions, not predictions about real Boston streets. Per-item status is in [AUDIT.md](AUDIT.md); every number shown in the demo or report is in [docs/claims_ledger.csv](docs/claims_ledger.csv).

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

**Calibrated: none.** Nothing is fit to real data yet.

**Sourced** (as recorded in `docs/assumptions_register.md`; I did not re-read the BWSC or MassDOT originals):
- Street network: Analyze Boston SAM and MassDOT Road Inventory (downloaded 2026-10-31, `data/build_info.json`).
- Cost inflation 7% a year: MassDOT FY27-31 CIP p.58 (asphalt +40% over five years).
- Funding mix 29.3 / 30.3 / 21.1 / 19.3 percent: BWSC 2024-2026 CIP Table 11 (p.19).
- Interest-free loan, 10 years: BWSC CIP p.18.
- Rate revenue pays for renewal and replacement: BWSC CIP p.17 (relining added by decision).
- Net-cost factors 0.811, 0.800, 1.0: computed from the loan terms at a 4% discount rate; tested.

**Simulated assumption, everything else**, including: trench cost $50,000 per opening, dig penalty parameter `lam` 0.3 (range 0.06 to 0.6 quoted by the team from the literature, not verified), cycle `L` 15 years, pipe and repave cost per foot, reline share, emergency multiplier 3, worst-case social cost $500,000, road user cost `u0` $0.30 per vehicle-mile, discount rate 4%, break rate 0.30 per mile per year, budget $48,000 per mile, return hurdle 1.0, urgency thresholds, treatment lives, the preserve and reconstruct parameters, pipe PoF bounds (x0.85, x1.15 + 5), road benefit band (±15%), state revolving loan rate (2%; the 20 to 30 year term is sourced) and bond terms (4%, 20 years), the reserve cap (0.25), and the pipe and road simulation itself (install years, materials, breaks, pavement age, traffic).

## 3. Results: 30 seeds with confidence intervals

`make compare`: 30 seeds, paired by seed (same city and failure luck across strategies), compact 800-segment area (42 miles), Student t 95% intervals. Total cost = capital + emergency repairs + road user cost over ten years, $M.

| Strategy | Total | Capital | Emergency | Road user |
|---|---|---|---|---|
| isolated | 154.89 ±2.86 | 2.74 ±0.03 | 67.79 ±2.27 | 84.36 ±1.93 |
| pooled | 142.27 ±2.76 | 7.11 ±0.04 | 67.79 ±2.27 | 67.38 ±1.70 |
| coordinated | 141.51 ±2.74 | 7.91 ±0.14 | 67.59 ±2.30 | 66.01 ±1.69 |
| central (20% scan heuristic) | 135.59 ±2.69 | 7.52 ±0.05 | 67.71 ±2.28 | 60.36 ±1.68 |

Paired differences, coordinated minus comparator:
- vs isolated: total −13.38 ±0.59, lower in 30 of 30 seeds; road user −18.35 ±0.63 (30 of 30); capital +5.16 ±0.14; emergency −0.20 ±0.11; failures −0.43 ±0.25 (lower in 10 of 30).
- vs pooled (the board alone): total −0.76 ±0.27, lower in 27 of 30; dig savings +0.22 ±0.05 per run.
- vs central heuristic: total +5.92 ±0.49, never lower.
- Shares of total cost (coordinated): capital 5.6%, emergency repairs 47.8%, road user cost 46.6%.

`make baselines` (same 30 seeds and area), total $M: age-first 171.3, risk-first 152.2, isolated 154.9, single agent 142.3, pooled 142.3, coordinated 141.5, central 20% heuristic 135.6, central full menu greedy 129.8, central full menu exact knapsack 121.7. Coordinated minus age-first −29.8 ±1.0, minus risk-first −10.7 ±0.7 (both 30 of 30); coordinated minus the exact central benchmark +19.9 ±0.8 (never lower).

Not run: 30 seeds on the full network (`make compare-full`, about an hour) and the full-menu central benchmark on the full network. One full-network seed (42) feeds `make cip` and the demo: coordinated total cost $2,786M against $3,025M isolated, and 1,570 funded projects, 1,453 street openings, 117 shared digs, $6.9M dig savings, $163.8M funded.

## 4. Where coordination wins and where it does not

**Wins.**
- Against isolated departments, age-first and risk-first: lower total cost in 30 of 30 seeds, and the mean difference is negative in all 26 sensitivity settings.
- Dig savings are real but small: $0.22M of a $141M total at base. They vanish exactly when trench cost and penalty are set to zero.

**Does not win, or not for the claimed reason.**
- **The board alone** (coordinated minus pooled) is $0.76M (about 0.5%). In the sensitivity sweep it is distinguishable from zero in 19 of 26 settings, and not when road user cost is 0.1, the break rate is 0.1 per mile, the social cost is $100,000, or in any corner with road user cost 0.1.
- **Zero-benefit control fails.** With trench and penalty at zero, dig savings are exactly $0 but coordinated is still $1.43M ±0.53M cheaper than pooled, more than with the mechanism on. Cause: the board's join requests roughly double the proposals each year (about 860 against 480), and the capital budget does not bind, so more work clears the hurdle. This is a menu-size effect. A pooled run with a 3x larger menu costs less than coordinated at the normal menu. Treat the board's value as menu size plus shared digs, not shared digs alone.
- **Central planners beat coordinated at every scale tried.** The exact full-menu benchmark is $19.9M (14%) cheaper; about $11.7M of that is menu size and about $8.1M is optimisation. The case for agents is private data and scalability across owners, not lower cost than a planner with all the data.
- **A single agent equals pooled** (menus are small, so picks rarely overlap), so negotiation, not a single point of view, is what produces any shared digs.
- **Most of the saving is road user cost, not fewer failures.** Failure counts differ by under 0.5 per run across strategies. The headline therefore depends on `u0`: the difference against isolated runs from −1.5M at `u0` 0.10 to −32.4M at 0.60.

**Sensitivity ranges** (10 paired seeds per setting): the difference against isolated swings most with `u0` (−1.5M to −32.4M) and menu size (−6.6M to −17.7M), then break rate (−13.3M to −15.6M), trench cost (−12.4M to −10.4M), emergency multiplier, social cost and reserve cap (each within about 1.5M of base), and not at all with discount rate (3% to 7%) or `lam`. `lam` has no visible effect because the repaving penalty averages $0.6k to $5.8k per pipe replacement against a $50k trench. Dig savings run from $0.01M to $2.97M, driven by the break rate, emergency multiplier and social cost, and move little with trench cost (0.17M to 0.28M over a 4x range). With low `u0`, a small menu and a low break rate together, coordinated is $0.16M cheaper than isolated with an interval that includes zero.

## 5. What could not be verified, and known weaknesses

- **Nothing is calibrated.** The break rate of 0.30 per mile gives about 252 breaks a year over 839 street miles, against BWSC's "just over 35 failures a year" (about 7 times higher). I did not look up BWSC miles of main, and street miles are not main miles. The average failure costs about $527,000 in the model; no repair-cost, bid-tab, user-cost or discount-rate source has been found and checked.
- **Sourced entries rest on the team's register.** I did not re-read the BWSC CIP, the BWSC 2026 budget or the MassDOT CIP.
- **Section 8 benefits:** `return_example.py` is not in the repo, so the step from PoF trajectories to dollars is tested for structure, not against the example's trajectories.
- **Reserve:** the 95th percentile of yearly emergency cost is 4.4 times the whole capital budget (full network), so the share is the cap I set (0.25), and the reserve covers about 9% of emergency repairs. This is a consequence of the uncalibrated break rate and failure cost, and it is why item 13 (is emergency share realistic) cannot be closed.
- **Emergency repairs are about half of total cost** and rest on uncalibrated numbers. The conclusions above depend on them.
- **Roads:** 90% of funded projects are tier 1 Urgent because simulated pavement deteriorates to "failed" quickly, so tier colours carry little information until roads are calibrated.
- **Slack budget:** under the agents' menus, capital is hurdle-limited, not money-limited. The headline result holds in that regime; with full menus the budget binds.
- **Backtest not done.** `data/processed_water_breaks.csv` has 114 break records (97 Springfield, 15 Ludlow, 2 others; 2025-01 to 2026-09) and no main inventory, so a lift curve against age-only ranking cannot be built from it. A dataset with an inventory and break dates is still needed; licenses and fields were not checked. The pipe model is therefore unvalidated against real failures.
- **Wait a year** defers only replacement (pipe) and repaving (road), and its benefit horizon is capped at the proposal's arrays, so waiting loses its last year.
- **Source order:** "cheapest" is by present value of repayments (state revolving loan before interest-free loan), which differs from the order listed in `interfaces.md`. Debt service is reported but not taken out of the capital budget.
- **Sensitivity** uses 10 seeds, not 30, per setting; the pipe failure-model weights (the team's `scoring.py`) were not swept.
- **Claude-driven agents** are committed and tested with a mock model only. No live run, no results, no cost figure.
- **The PDF** is 74 pages on the full network because every funded project is listed; only its first page was inspected.
- **Scope:** all 30-seed results are on an 800-segment area, not the whole city.

## 6. How to reproduce

```
make test            # 55 tests
make cip             # outputs/cip/ (full network, seed 42)
make demo            # demo/site/, serves http://localhost:8000
make compare         # 30 seeds, 800-segment area
make baselines       # baselines and exact central benchmark
make sensitivity     # sweeps and tornado charts in outputs/results/
python3 -m experiments.control_no_benefit
python3 -m cip.ledger   # regenerate docs/claims_ledger.csv
```

Results land in `outputs/results/` with a `.config.json` snapshot beside each file (`outputs/` is git-ignored except `outputs/cip/`).
