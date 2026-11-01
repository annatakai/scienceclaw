# Zhora: Agentic CIP (Capital Improvement Plan)
Problem: Lack of holistic data analysis to help cities determine infrastructure repair prioritization (including high cost, high labor, and slow process). 
Solution: Create an agentic CIP using a decentralized AI agent system. 3 AI agents: Road Agent, Pipe Agent, and Budget Agent.  

## Visual Overview
    ```mermaid
flowchart LR
    A["Pipe Agent"] --> D["Shared Board"]
    B["Road Agent"] --> D
    D --> C["Budget Agent"]
    C --> E["Coordinated Repair Plan"]
    E --> F["MapLibre Dashboard"]
```

## Strategies
- isolated: separate departments, fixed 60/40 budget split, no board
- pooled: one shared budget, no board (ablation: isolates the budget agent's value)
- coordinated: agents negotiate on the board, pooled budget (the proposal)
- central: one planner with full data. A heuristic benchmark, NOT yet a proven upper bound.

## Results (simulated; break rate calibrated to BWSC: 35 failures / 1,018 miles = 0.0344 per mile per year)
`make compare`: 30 seeds, paired by seed, 95% CI by Student t, compact 800-segment area. Total cost $M: isolated 94.4, pooled 81.8, coordinated 81.4, central heuristic 75.4.
- coordinated minus isolated: -12.95 (+-0.47), lower in 30 of 30; the board alone: -0.32 (+-0.17), lower in 21 of 30.
- **No pipe work clears the hurdle at the calibrated break rate, so there are no shared digs: dig savings are $0 in every seed** (the full-network plan is all road work). The earlier uncalibrated rate (0.30) gave $0.22M.
- Baselines (`make baselines`): age-first 112.7, risk-first 94.5, single agent 81.8, central full menu greedy 69.5, exact knapsack benchmark 61.1: a planner with all the data beats the agents.
- Sensitivity (`make sensitivity`): coordinated cheaper than isolated in 25 of 26 settings; depends mainly on road user cost u0 (unsourced) and menu size.
- Real break records (Springfield MA, no inventory) by age and material: `python3 -m experiments.break_cohorts`.
See REPORT.md for the full account and what could not be verified.

## CIP report (`make cip`)
`python3 -m cip.build` runs isolated and coordinated on one seed and writes `outputs/cip/`: `report.json`, `decision_list.csv`, `funding_table.csv`,
`capital_plan.html` (self-contained, printable), `capital_plan.pdf` (Playwright), and a config snapshot. The demo has a Decision list tab beside the map
(row click zooms and selects, year slider filters, tier colours, CSV and PDF download, comparison with isolated). Every config value has a source, status
and date in `sim/config_meta.py`; `docs/claims_ledger.csv` lists every number shown (regenerate: `python3 -m cip.ledger`).
Money: all dollars come from `sim/costs.py` (docs/return_formula.md). Funding: four sources, cheapest first within BWSC Table 11 shares; reserve sized by `sim/reserve.py`.

## Claude-driven agents (strategy `coordinated_llm`, optional)
The rule-based agents stay the default. `agents/*/llm_agent.py` swap in Claude for the choices and the written rationale;
every number comes from tools (`agents/*/tools.py`) that call scoring.py / sim/costs.py. Only `agents/llm.py` imports the SDK.
- Needs `pip install anthropic` and `ANTHROPIC_API_KEY`; model, effort and prices are in `sim/config.py`.
- Pipe tools read only the pipe view, road tools only the road view, both read the board; only the budget agent has `fund`/`reject`, and `fund` refuses over the spendable amount.
- At most 8 tool calls per agent per year; rationales at most 280 chars; invalid output is rejected, retried once, then the rule-based decision is used and logged.
- Traces: `traces/<strategy>_seed<seed>.jsonl` (git-ignored). Tests use a mocked client: `make test`.
- `python3 -m experiments.compare_llm [seeds] [years] [max_usd]` runs the small live comparison and records seed 0 for `python3 -m demo.build_demo --llm 0`.

## Caveats
- The simulated world uses the same rubric the pipe agent uses, so there is no model mismatch. Real data would add one.
- condition_grade is a proxy from age and break count; observation_years is fixed at 20.
- n_target (breaks per year), costs and the budget are ASSUMPTIONS, so absolute dollars mean nothing.
- Street geometry, names, length, road class and neighborhood are REAL; all pipe, pavement, break and cost data is SIMULATED. ALL ASSET DATA SIMULATED.

## All-Boston street network (real) and scale
Source: Analyze Boston Street Segments (SAM), class and jurisdiction from the MassDOT Road Inventory, neighborhoods from Analyze Boston
(details, dates, terms in `data/SOURCES.md`). Result: 15,176 segments, 839.2 miles (arterial 223.1, collector 63.1, local 553.0).
MassDOT class matched 96.8% of kept SAM segments within 15 m (unmatched ones use the SAM CFCC class; list in `data/unmatched_segments.csv`).
Dropped from 19,440 SAM segments: 1,397 not Public Works (state, DCR, Massport, parks, housing), 1,290 private, 842 ramps/service/special,
621 alleys/walkways/private roads, 245 limited-access highways, 237 likely paper streets, 78 non-city per MassDOT, 27 freeway class,
77 no CFCC, 19 unknown owner, 13 other municipality, 4 tiny, 2 bike/ped or private facility; 589 extra pieces from cutting segments over 250 m.
The osmnx fallback (`--osm`) exists but is untested because both downloads worked.
Scaling assumptions (sim/config.py, tagged ASSUMPTION): $48k per mile per year budget (about $40M for the city), 0.30 breaks per mile per
year, proposals per agent at most 3% of segments (floor 15, cap 600), central planner scans 20% of segments (bounded for run time, so it
is NOT like-for-like with the 3% menus). Older pipes are assumed in older neighborhoods. Options: `--neighborhood "South End"`, `--max-segments N`.
Run time: one strategy, 10 years, full network is 9 to 28 s; `make demo` (4 strategies in parallel) about 25 s, plus a one-time reserve pilot (cached in `outputs/reserve_cache.json`).
Full-network results from before the return formula was completed (8 seeds) are no longer valid; rerun `make compare-full` for new ones.

## Merging into the team repo
Everything except `agents/pipe_agent/adapter.py` and `agent.py` is new; `scoring.py` is identical to the team's, so
copying this tree over the repo adds files without changing existing ones. Run from the repo root.
