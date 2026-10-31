.PHONY: demo compare test run
demo:      ## build demo.html and open it in your browser
	python3 build_demo.py
compare:   ## 30-seed comparison table
	python3 compare.py 30
test:
	python3 -m unittest discover -s tests -v
run:
	python3 run.py
