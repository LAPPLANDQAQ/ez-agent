PYTHON ?= python
COMPOSE ?= docker compose -f deploy/docker-compose.yml

.PHONY: api frontend cli test lint eval docker-up docker-down

api:
	$(PYTHON) -m app.main

frontend:
	streamlit run frontend/app.py

cli:
	$(PYTHON) scripts/run_cli.py "$(QUERY)"

test:
	pytest

lint:
	ruff check app scripts tests frontend

eval:
	$(PYTHON) scripts/eval.py "$(QUERY)"

docker-up:
	$(COMPOSE) up --build

docker-down:
	$(COMPOSE) down
