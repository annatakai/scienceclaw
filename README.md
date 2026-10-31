# Dig Once: multi-agent infrastructure repair coordination (prototype, ALL DATA SIMULATED)

Pipe, road and budget agents coordinate repairs on a shared board so a street is opened once, not several times.
Layout mirrors the team repo (`agents/pipe_agent/scoring.py` is the team's file, unchanged).

    pip install -r requirements.txt   # pandas; geopandas, pyproj, shapely, pyogrio only to rebuild the street data
    make demo                         # runs 4 strategies on all of Boston (about 30 s), writes demo/site/, serves http://localhost:8000
    make compare                      # 30 seeds, paired, on a compact 800-segment area (about 20 s); make compare-full: full network (about an hour)
    make cip                          # capital plan report and PDF in outputs/cip/
    make score                        # team pipe rubric + road ratings on data/synthetic_*.csv
    make test

## Layout
    agents/
      board.py                  shared board (the only channel between agents)
      pipe_agent/
        scoring.py              TEAM FILE: heuristic pipe risk rubric v2.0 (PoF x CoF -> Critical/High/Moderate/Low)
        adapter.py              simulated pipe -> team CSV schema -> score_pipe(); future-year and after-repair scores
        agent.py                PipeAgent: menu of replace/reline proposals, round-2 negotiation
      road_agent/
        scoring.py              road condition rating: Good/Fair/Poor/Failed, urgency, recommended action
        agent.py                RoadAgent: repave proposals, offers to share digs
      budget_agent/
        scoring.py              return rating (Strong/Acceptable/Below hurdle) and urgency tiers (1 Urgent .. 4 Monitor)
        agent.py                BudgetAgent: funds by return, bundles shared digs, explains every decision
    sim/
      fetch_streets.py          builds data/boston_streets.geojson from Analyze Boston SAM + MassDOT (see data/SOURCES.md)
      config.py                 every number, each sourced or tagged ASSUMPTION (per-mile scaling)
      city.py                   simulated assets on the real street network, failures, applying work
      costs.py                  the ONLY place dollars are computed (benefit, cost, urgency, return)
      runner.py                 yearly loop and the four strategies
      export_city.py            writes data/synthetic_pipes.csv and synthetic_roads.csv
    experiments/compare.py      multi-seed comparison
    demo/                       build_demo.py + src/ (MapLibre GL JS GIS-style UI) -> demo/site/ (index.html + typed-array data); screenshots.py checks it
    data/                       synthetic CSVs in the team's schema
    tests/

## Strategies
- isolated: separate departments, fixed 60/40 budget split, no board
- pooled: one shared budget, no board (ablation: isolates the budget agent's value)
- coordinated: agents negotiate on the board, pooled budget (the proposal)
- central: one planner with full data. A heuristic benchmark, NOT yet a proven upper bound.

## Results (simulated; one config, see `outputs/results/*.config.json` for every value used)
`make compare`: 30 seeds, paired by seed, 95% CI by Student t, compact 800-segment area (42 miles). Total cost = capital + emergency repairs + road user cost, ten years.
- total $M: isolated 154.9, pooled 142.3, coordinated 141.5, central (heuristic) 135.6
- coordinated minus isolated: -13.4 (+-0.6) in 30 of 30 seeds; coordinated minus pooled (the board alone): -0.76 (+-0.27), lower in 27 of 30
- dig savings from shared digs: $0.22M (+-0.05) per run; the central heuristic beats coordinated by $5.9M (+-0.5), so we make no claim against a central planner
- Emergency repairs are about 48% of total cost and road user cost about 47%; capital is about 6%. Failure counts are about equal across strategies,
  so the gain is road user cost (more work clears the hurdle), not fewer failures. The capital budget does not bind (isolated spends under a fifth of it).
- The zero-benefit control (`experiments/control_no_benefit.py`) removes the dig savings but NOT the coordinated-pooled gap: the board's join requests
  roughly double the proposals each year, and with a slack budget more work clears the hurdle. Treat the board's value as menu size plus shared digs, not shared digs alone.
- The old 30-seed figures in earlier versions of this file described a 260-segment demo and the pre-formula model; they are gone.

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
