# ---- EcoTwin AI ------------------------------------------------------------
.DEFAULT_GOAL := help
PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
	 | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: setup
setup: ## Create the venv and install backend + frontend dependencies
	python3 -m venv .venv
	$(PIP) install -q --upgrade pip
	$(PIP) install -r requirements-dev.txt
	cd apps/web && npm install --no-audit --no-fund

.PHONY: data
data: ## Download the public source datasets (~1.4 GB)
	bash scripts/download_data.sh

.PHONY: inspect
inspect: ## Emit the raw-data schema report
	$(PY) scripts/inspect_data.py

.PHONY: prepare
prepare: ## Normalise raw data and choose the demo window
	$(PY) scripts/prepare_data.py

.PHONY: train
train: ## Train the per-asset forecasters
	$(PY) scripts/train_models.py

.PHONY: cache
cache: ## Precompute the demo cache used by the hosted deployment
	$(PY) scripts/build_demo_cache.py

.PHONY: pipeline
pipeline: data inspect prepare train cache ## Everything, from download to demo cache

.PHONY: api
api: ## Run the backend on :8000
	PYTHONPATH=. $(PY) -m uvicorn apps.api.main:app --reload --port 8000

.PHONY: web
web: ## Run the frontend on :3000
	cd apps/web && npm run dev

.PHONY: test
test: ## Run the Python test suite
	$(PY) -m pytest

.PHONY: lint
lint: ## Ruff + Black + ESLint + strict TypeScript
	.venv/bin/ruff check .
	.venv/bin/black --check .
	cd apps/web && npm run lint && npm run typecheck

.PHONY: format
format: ## Auto-format Python and TypeScript
	.venv/bin/ruff check --fix .
	.venv/bin/black .
	cd apps/web && npm run format

.PHONY: check
check: lint test ## Lint and test

.PHONY: up
up: ## Local engineering mode (web + api)
	docker compose up --build

.PHONY: up-boptest
up-boptest: ## Local engineering mode with a live BOPTEST instance
	ECOTWIN_BOPTEST_URL=http://boptest:5000 docker compose --profile boptest up --build

.PHONY: down
down: ## Stop the stack
	docker compose down
