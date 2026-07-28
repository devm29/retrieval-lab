SHELL := /bin/bash
PY := backend/.venv/bin
PYTHON ?= python3.12

.PHONY: help install db db-stop db-reset migrate seed api web dev test test-backend test-web e2e lint typecheck build gate corpus docker-up docker-down clean

help:
	@grep -E '^[a-z-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}'

install: ## Create the Python venv and install web dependencies
	test -d backend/.venv || $(PYTHON) -m venv backend/.venv
	$(PY)/pip install -q --upgrade pip
	$(PY)/pip install -q -c backend/requirements.lock -e "backend[dev]"
	cd web && pnpm install

db: ## Start a project-local Postgres 17 + pgvector on :5502 (no Docker)
	./scripts/local-pg.sh start

db-stop: ## Stop the local Postgres
	./scripts/local-pg.sh stop

db-reset: ## Drop and recreate the local retrieval_lab database (run `make seed` after)
	./scripts/local-pg.sh reset

migrate: ## Apply database migrations
	$(PY)/rlab db upgrade

seed: migrate ## Index the corpus and populate configs, golden set, runs, baselines and calibration
	$(PY)/rlab seed

api: ## Run the FastAPI service on :8102
	cd backend && .venv/bin/uvicorn retrieval_lab.api.app:app --host 127.0.0.1 --port 8102 --reload

web: ## Run the Next.js dashboard on :3102
	cd web && pnpm dev

dev: ## Run API and dashboard together
	@trap 'kill 0' EXIT; $(MAKE) api & $(MAKE) web & wait

test: test-backend test-web ## Run all unit and integration tests

test-backend:
	cd backend && .venv/bin/pytest -q

test-web:
	cd web && pnpm test

e2e: ## Playwright smoke tests against a running, seeded stack
	cd web && pnpm e2e

lint: ## Ruff and ESLint
	cd backend && .venv/bin/ruff check src tests migrations && .venv/bin/ruff format --check src tests migrations
	cd web && pnpm lint

typecheck: ## mypy --strict and tsc
	cd backend && .venv/bin/mypy
	cd web && pnpm typecheck

build: ## Production build of the dashboard
	cd web && pnpm build

gate: ## Evaluate hybrid-rerank and fail if it regressed against its stored baseline
	$(PY)/rlab eval gate --config hybrid-rerank

corpus: ## Rebuild data/corpus from Project Gutenberg
	$(PYTHON) scripts/build_corpus.py

docker-up: ## Full stack in Docker (Postgres, API, web)
	docker compose up --build -d
	docker compose --profile tools run --rm seed

docker-down:
	docker compose down

clean:
	rm -rf web/.next web/test-results backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
