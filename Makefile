PYTHON ?= python

.PHONY: run test

run:
	$(PYTHON) -m app.main

test:
	pytest

