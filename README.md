# Dig Once: multi-agent infrastructure repair coordination (prototype, ALL DATA SIMULATED)

Pipe, road and budget agents coordinate repairs on a shared board so a street is opened once, not several times.
Layout mirrors the team repo (`agents/pipe_agent/scoring.py` is the team's file, unchanged).

    pip install -r requirements.txt   # pandas only
    make demo                         # runs 4 strategies, writes demo/demo.html, opens the map replay
    make compare                      # 30-seed table with paired differences
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
      config.py                 every number, each sourced or tagged ASSUMPTION
      city.py                   synthetic city (generated grid over Boston coordinates), failures, applying work
      costs.py                  the ONLY place dollars are computed (benefit, cost, urgency, return)
      runner.py                 yearly loop and the four strategies
      export_city.py            writes data/synthetic_pipes.csv and synthetic_roads.csv
    experiments/compare.py      multi-seed comparison
    demo/                       build_demo.py + template.html -> self-contained replay (SVG map, board feed, scoreboard)
    data/                       synthetic CSVs in the team's schema
    tests/

## Strategies
- isolated: separate departments, fixed 60/40 budget split, no board
- pooled: one shared budget, no board (ablation: isolates the budget agent's value)
- coordinated: agents negotiate on the board, pooled budget (the proposal)
- central: one planner with full data. A heuristic benchmark, NOT yet a proven upper bound.

## Results so far (30 seeds, paired, simulated; budget $1.2M per year)
Total cost = capital + emergency repairs + road user cost, over 10 years.
- coordinated vs isolated: about $3.3M lower (+-0.9M)
- pooled vs isolated: about $1.7M lower (+-0.7M); the board adds about $1.6M on top of pooling (+-0.8M)
- Failure counts are about equal across strategies; the gain is road cost and spending efficiency.
- Do NOT claim decentralized beats central: the central benchmark is currently worse than coordinated, which means the
  benchmark is flawed, not that coordination beats an ideal planner.

## Caveats
- The simulated world uses the same rubric the pipe agent uses, so there is no model mismatch. Real data would add one.
- condition_grade is a proxy from age and break count; observation_years is fixed at 20.
- n_target (breaks per year), costs and the budget are ASSUMPTIONS, so absolute dollars mean nothing.
- Street geometry is a generated grid. Next step: real Boston main streets from OpenStreetMap.

## Merging into the team repo
Everything except `agents/pipe_agent/adapter.py` and `agent.py` is new; `scoring.py` is identical to the team's, so
copying this tree over the repo adds files without changing existing ones. Run from the repo root.
