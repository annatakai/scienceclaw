.PHONY: install data score demo compare test run
install:   ## pandas is the only dependency (the team's scoring.py needs it)
	python3 -m pip install -r requirements.txt
data:      ## export the synthetic city as CSVs in the team's schema
	python3 -m sim.export_city
score:     ## run the team's pipe scoring CLI and the road rating CLI on the synthetic data
	python3 agents/pipe_agent/scoring.py data/synthetic_pipes.csv outputs/scored_pipes.csv --year 2026
	python3 -m agents.road_agent.scoring data/synthetic_roads.csv outputs/scored_roads.csv --year 2026
demo:      ## build demo/demo.html and open it in your browser
	python3 -m demo.build_demo
compare:   ## 30-seed comparison table
	python3 -m experiments.compare 30
test:
	python3 -m unittest discover -s tests -v
run:
	python3 -m sim.runner
