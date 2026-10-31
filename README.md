# Dig Once: rough prototype (ALL DATA SIMULATED)

    make demo                    # runs the 10-year simulation for 4 strategies, writes demo.html, opens it
    make compare                 # 30-seed comparison with paired differences (no browser)
    make run                     # one-line summary per strategy

Files
- `sim.py`     config (every number tagged ASSUMPTION or source), synthetic city, PoF/PCR methods, `price()` (the only place dollars are computed), failures
- `agents.py`  Board, PipeAgent, RoadAgent, BudgetAgent (rule-based; an LLM would only write the `text`/`rationale` strings)
- `run.py`     yearly loop and strategies: isolated, pooled (ablation), coordinated (board), central
- `template.html` + `build_demo.py`  self-contained replay (SVG map, board feed, scoreboard)

Known simplifications: 144 segments on a generated grid; two work types per asset (replace/reline, repave); two funding
sources; no sewer/gas; no ML; heuristic PoF weights; N_target and costs are ASSUMPTIONS, so absolute dollars mean nothing.

Requirements: Python 3.9+ and nothing else (standard library only). `make test` runs the sanity tests.
The replay page loads an OpenStreetMap basemap when online; it also works offline without it.

Results so far (30 seeds, paired, simulated): agents + board are about $3.5M cheaper than isolated departments over
10 years; the central planner is NOT a valid upper bound yet (heuristic flaw). Do not claim decentralized beats central.
