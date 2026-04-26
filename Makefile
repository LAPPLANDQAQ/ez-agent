PYTHON ?= python
COMPOSE ?= docker compose -f deploy/docker-compose.yml

.PHONY: dev api frontend cli test lint eval check-env check-ports docker-up docker-down

dev:
	$(PYTHON) scripts/start_dev.py

api:
	$(PYTHON) -m app.main

frontend:
	streamlit run frontend/app.py

check-env:
	$(PYTHON) scripts/check_env.py

check-ports:
	$(PYTHON) scripts/check_ports.py

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
