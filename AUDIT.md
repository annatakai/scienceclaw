# AUDIT: Dig Once repo vs. the CIP plan

Audit date 2026-10-31. No code was changed. ALL ASSET DATA IS SIMULATED. Repo root is `/Users/hualala/Documents/SC2026/dig_once`
(branch `feat/real-boston-streets`, last commit `5265a05`).

## Blockers found while auditing

1. **The `docs/` folder does not exist in this repo.** None of these were found in the repo or under `~/Documents`, `~/Downloads`, `~/Desktop`:
   `docs/interfaces.md`, `docs/return_formula.md`, `docs/assumptions_register.md`, `docs/evidence_plan.md`,
   `docs/budget_agent_reference.md`, `docs/cip_report.py`. Also missing: `data/processed_water_breaks.csv`.
   Consequences: I could not check `sim/costs.py` against `return_formula.md`, could not check the section 8 numbers
   (2.88 / 1.04 / 2.74), the Table 11 shares, the loan terms, or the seven assumptions in `evidence_plan.md`. Items 1, 2, 4, 7 and 8 below are
   judged from the code and its comments only. Phase 1d (move `docs/cip_report.py` to `cip/report.py`) cannot start without that file.
   I will not reconstruct these documents from memory, because that would invent sources and numbers.
2. **Uncommitted work.** The Claude-driven agents (item 16) are untracked or modified in the working tree: `agents/llm.py`, `agents/llm_support.py`,
   `agents/trace.py`, `agents/*/llm_agent.py`, `agents/*/tools.py`, `experiments/compare_llm.py`, `tests/test_llm.py`, plus edits to
   `agents/board.py` and `agents/budget_agent/agent.py`. They should be committed before further work.
3. **Dollar arithmetic outside `sim/costs.py`** (ground rule breach): `agents/budget_agent/agent.py` (`_cands`, `_decisions`) computes bundle cost,
   the marginal check, per-proposal amounts and the rate-revenue cap; `agents/pipe_agent/adapter.py::_args` computes the emergency cost passed to the
   team rubric; `sim/city.py::apply` sums spend. Needs to move into `sim/costs.py` as part of item 1.
4. **Stale README results.** README "Results so far (30 seeds, ... $1.2M per year, $3.3M lower)" describes the old 260-segment demo. The current code
   cannot reproduce it. The only full-network record is `outputs/compare_full.txt` (8 seeds; `outputs/` is git-ignored).

## Commands run

| Command | Result |
|---|---|
| `make test` | 23 tests, all pass (7.8 s): 12 in `tests/test_basic.py`, 11 in `tests/test_llm.py` (mock model only) |
| `make cip` | **fails: no such target** |
| `make compare` | Full run is 8 seeds, about 16 min; not repeated. Ran the same code as `python3 -m experiments.compare 3 --neighborhood "South End"`: works, 1 s. The recorded full-network output is in `outputs/compare_full.txt`. |
| `make demo` | Ran `python3 -m demo.build_demo --no-open --no-serve` (the target also serves on :8000): works, 4 strategies in 29 s, wrote `demo/site/` (15,176 segments, 839 miles). I did not open the page in a browser. |

## Status per item

| # | Item | Status | Evidence and what is missing |
|---|---|---|---|
| 1 | `sim/costs.py` implements all of `return_formula.md` | **PARTIAL** | Has: pipe benefit from PoF trajectories, replace and reline options (`costs.price`, `agents/pipe_agent/agent.py::_proposal`), road user-cost benefit, dig penalty, cost inflation (`config.infl`), bundle cost = one dig + both works and the road-side marginal check (`BudgetAgent._cands`), NPV choice per segment (`allocate`, `select="npv"`), tier-1 first up to `urgent_cap_fraction` (`_fund`), `return_lo`/`return_hi` (`price`). Missing: "wait a year" option (pipe and road); menu items `preserve_road`, `reconstruct_road` (road agent proposes only `repave`); "needs engineering review" flag (`return_lo < hurdle <= return_hi`; the values are computed but never used); marginal check on the pipe side; `return_lo/hi` for roads is a fixed plus or minus 15%, not from PoF bounds; pipe PoF bounds are a made-up x0.85 / x1.15+5 (labelled ASSUMPTION in `agent.py`); "rank by return only when budget binds" is not explicit (always ranks by return); money logic is spread over three files (blocker 3). No test reproduces `return_formula.md` section 8 (file missing). |
| 2 | Four funding sources, eligibility, financing, debt service | **PARTIAL (barely)** | Only `bonds` and `rate_revenue` exist (`BudgetAgent._decisions`). Rate revenue takes any eligible work in proposal-id order until it hits `rate_revenue_share` x spendable (0.5; the config comment says BWSC is about 30%, so the two disagree). Eligibility is hard-coded `[replace_pipe, repave]`, so relining is excluded and the BWSC discrepancy is undecided and undocumented. Missing: interest-free loan, state revolving loan, shares and loan terms, "cheapest source with room first", present value of repayments, net cost after financing, loan interest in cost of ownership, debt service, eligibility in config. Source is assigned after the funding decision and does not affect it. |
| 3 | Simulated reserve instead of fixed 15% | **NOT STARTED** | `reserve_fraction=0.15` in `sim/config.py`, used in `BudgetAgent.allocate` (spendable = budget x 0.85). The reserve is never spent on emergency repairs, and emergency repair cost is not drawn from any budget. No 95th-percentile calculation, no balance by year. |
| 4 | CIP report module, adapter, `outputs/cip`, PDF | **NOT STARTED** | No `cip/` package, no `docs/cip_report.py`, no `make cip`, no `outputs/cip/`. Runner (`sim/runner.py::simulate`) returns only counts, plus per-year decisions (without `funding_source`, without priced proposals) when `record=True`; nothing is persisted per run. Playwright imports, but I did not check that a browser is installed. |
| 5 | Decision list tab, row-click, year filter | **NOT STARTED** | `demo/src/index.html` tabs are Activity, Compare, Table, About. No Decision list; no `cip:select` or `map:year` events. Related pieces exist: year slider (`app.js`, `#slider`), Table tab with filter, Table CSV button. |
| 6 | Config with source/status/date; snapshot per run; claims ledger | **PARTIAL (minimal)** | `sim/config.py` tags most values `ASSUMPTION` in comments; one cites a source (`cost_inflation`: "MassDOT FY27-31 CIP p.58", not verified by me). Street-data download dates are in `data/build_info.json`, `data/SOURCES.md`. Missing: per-value source / status (Sourced, Calibrated, Simulated assumption) / date-checked structure, config snapshot beside results (`outputs/compare_full.txt` has none), `docs/claims_ledger.csv`. |
| 7 | Numbers calibrated from documents | **NOT STARTED** | Break rate 0.30 per mile per year, $48k per mile budget, `emergency_multiplier=3`, `dig_fixed=50,000`, `pipe_per_ft=300`, `repave_per_ft=120`, penalty `lam`/`L`, `u0=0.30`, `discount_rate=0.04` are all ASSUMPTION. Scale check: 0.30 x 839 miles = about 252 breaks per year, versus the plan's "about 35 BWSC failures a year" (about 7x higher; BWSC miles of main not looked up, and street miles are not main miles). Nothing verified; no documents in the repo to calibrate from. |
| 8 | Backtest on real break data | **NOT STARTED** | `data/processed_water_breaks.csv` is not in this repo. No backtest, lift curve or calibration plot. |
| 9 | 30+ seed paired comparison with CIs | **PARTIAL** | `experiments/compare.py` runs paired differences vs isolated and coordinated vs pooled, with mean and 95% CI. Gaps: `make compare` default is 8 seeds; 30 seeds only suggested on one neighborhood; CI uses z=1.96 (too narrow at n=8, needs t); only total cost is paired, not each component; no saved output with a config snapshot (`outputs/` ignored). Recorded 8-seed full-network result (`outputs/compare_full.txt`): total $M isolated 3031.7, pooled 2730.6, coordinated 2689.7, central 2561.1; coordinated minus isolated -341.9 +/-5.0; board alone (coordinated minus pooled) -40.9 +/-3.7. The README's 30-seed numbers are stale (blocker 4). |
| 10 | Sensitivity sweep and tornado chart | **NOT STARTED** | No `experiments/sensitivity.py`. |
| 11 | Zero-benefit control run | **NOT STARTED** | No `experiments/control_no_benefit.py`. Note: `dig_savings` comes from the shared dig cost, so zeroing `dig_fixed` and the penalty should drive it to 0, but the pooled-versus-isolated gap also comes from the budget pooling and the 60/40 split, so a gap that does not vanish is plausible and must be investigated, not assumed a bug. |
| 12 | Central planner benchmark and other baselines | **PARTIAL** | `central` strategy exists (`runner.py`), but it is a heuristic: it ranks only the top 20% of segments by the same rules, greedy by return, same menu type, no knapsack or ILP, no full data across all options. It currently beats coordinated (2561 vs 2690 $M), which README already flags as a flawed benchmark. Missing: real knapsack/ILP benchmark, single-agent, age-first and risk-first baselines. |
| 13 | Emergency share of total cost checked | **PARTIAL** | The emergency column is printed, but share is not computed or checked. From `outputs/compare_full.txt` (coordinated): emergency 50.4%, road user cost 42.1%, capital 7.4% of total; isolated emergency 45.1%. Average failure about $527k ($1,356.6M over 2,574.9 failures). Failure counts are about equal across strategies, so most of the "savings" are road user cost, not avoided failures. Calibration of failure cost and scale is not done (item 7). |
| 14 | Real Boston streets | **DONE** | `sim/fetch_streets.py`, `data/boston_streets.geojson` (15,176 segments, 839.2 miles), `data/SOURCES.md` (sources, licenses, dates), per-mile scaling in `sim/config.py::resolve`, test `test_real_street_loader` and `test_subset_options_and_stable_attributes` pass. Caveats: osmnx fallback untested; MassDOT Road Inventory feature service used instead of the MassGIS shapefile (documented). |
| 15 | GIS UI | **PARTIAL (looks complete, not tested)** | `demo/src/app.js`: MapLibre GL (WebGL) map, layer panel with legend, scale bars, north arrow, cursor lat/lon, click-to-inspect panel, year slider with replay, street search, basemap choice, PNG and CSV export. Screenshots in `demo/shots/`. No automated UI test, and I did not open the built page in this audit. |
| 16 | Claude-driven agents | **PARTIAL** | `agents/llm.py`, `agents/llm_support.py`, `agents/*/llm_agent.py`, `agents/*/tools.py`; strategy `coordinated_llm`; tool-call cap, validation, fallback to rule-based, dollar cap (default $5) all covered by mock-model tests (11 pass). No live run (needs `ANTHROPIC_API_KEY`), no recorded run, no results. All of it is uncommitted (blocker 2). |

## Running list of what is finished

- Items 14 (DONE) at audit time. Nothing else is complete.
- No code changed during this audit.

## Prioritized list of what is missing

Order requested: 1-6, 9-12, 7-8, 13, then 14-16.

**Needs the missing docs first**
- 1. Finish `sim/costs.py`: wait-a-year, `preserve_road`/`reconstruct_road`, engineering-review flag, pipe-side marginal check; move all dollar logic out of the budget agent and adapter into `sim/costs.py`; add the section 8 test (needs `return_formula.md`).
- 2. Four funding sources with shares, loan terms, eligibility (decide relining), cheapest-first assignment, debt service, net cost after financing (needs `interfaces.md`, `budget_agent_reference.md`).
- 3. Reserve sized from simulated 95th-percentile yearly emergency cost; balance by year (needs register section 7).
- 4. `cip/` package: report, adapter, runner persistence, `outputs/cip/*`, `make cip`, PDF (needs `docs/cip_report.py`).
- 5. Decision list tab with row click, year filter, tier colors, CSV/PDF, coordinated-vs-isolated toggle.
- 6. Config with source/status/date per value, snapshot per run, `docs/claims_ledger.csv`.

**Credibility of the comparison**
- 9. 30+ seeds on the full network with t-based CIs, paired components, saved with a config snapshot.
- 10. `experiments/sensitivity.py` and a tornado chart; report where the sign flips.
- 11. `experiments/control_no_benefit.py`.
- 12. Real benchmark (knapsack or ILP) or keep the "heuristic" label; add single-agent, age-first, risk-first baselines.

**Evidence**
- 7. Calibrate break rate, budget per mile, emergency cost, trench cost, penalty, road user cost, discount rate from verified documents; the rest stay ASSUMPTION with a tested range.
- 8. Backtest (needs the break data; if no main inventory, report break rates by age cohort and material only).
- 13. Report emergency share after calibration.

**Already built, needs hardening**
- 14. Done.
- 15. Add a UI smoke test.
- 16. Commit, then run the capped live comparison.
