.PHONY: install data score demo compare compare-full test run cip control
install:   ## pandas is the only dependency (the team's scoring.py needs it)
	python3 -m pip install -r requirements.txt
data:      ## export the synthetic city as CSVs in the team's schema
	python3 -m sim.export_city
score:     ## run the team's pipe scoring CLI and the road rating CLI on the synthetic data
	python3 agents/pipe_agent/scoring.py data/synthetic_pipes.csv outputs/scored_pipes.csv --year 2026
	python3 -m agents.road_agent.scoring data/synthetic_roads.csv outputs/scored_roads.csv --year 2026
demo:      ## run the strategies, write demo/site/ and serve it at http://localhost:8000 (full network, about 30 s)
	python3 -m demo.build_demo
compare:   ## 30 seeds, paired, 95% CI (t), on a compact 800-segment area (about 2 minutes). Results and config snapshot in outputs/results/
	python3 -m experiments.compare 30 --max-segments 800
compare-full:  ## 30 seeds on the full network (about an hour on 8 cores)
	python3 -m experiments.compare 30
cip:       ## capital plan: report.json, decision_list.csv, funding_table.csv, capital_plan.html and .pdf in outputs/cip/
	python3 -m cip.build
test:
	python3 -m unittest discover -s tests -v
run:
	python3 -m sim.runner
