PYTHON ?= python3

.PHONY: test run spice
test:
	$(PYTHON) -m unittest discover -s tests -v

run:
	$(PYTHON) src/front_end.py --out results

spice:
	$(PYTHON) src/front_end.py --out results --spice
