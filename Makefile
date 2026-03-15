# ─────────────────────────────────────────────────────────────────────────────
# SDE-3 Mentor Agent — Developer Workflow
# ─────────────────────────────────────────────────────────────────────────────
.PHONY: help up down logs dev migrate migrate-down migrate-status \
        smoke-test mock-start mock-answer install clean

PYTHON   := python3
PIP      := $(PYTHON) -m pip
BASE_URL := http://localhost:8000

help:   ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-20s\033[0m %s\n",$$1,$$2}'

# ── Docker ────────────────────────────────────────────────────────────────────

up:     ## Start Postgres with pgvector (DB only — use 'make dev' for the app)
	docker compose up -d postgres
	@echo "⏳ Waiting for Postgres to be healthy…"
	@docker compose exec postgres sh -c \
	  'until pg_isready -U $${POSTGRES_USER:-postgres} -d $${POSTGRES_DB:-ai_guide}; do sleep 1; done'
	@echo "✅ Postgres is ready on localhost:5432"

up-full:    ## Start Postgres + FastAPI app container
	docker compose --profile full up -d
	@echo "✅ Stack running — API at $(BASE_URL)"

down:   ## Stop and remove all containers (data volume is preserved)
	docker compose down

down-v: ## Stop containers AND delete the Postgres data volume
	docker compose down -v

logs:   ## Tail Postgres logs
	docker compose logs -f postgres

logs-app:   ## Tail app container logs (only when using up-full)
	docker compose logs -f app

# ── Python environment ────────────────────────────────────────────────────────

install:    ## Install Python dependencies into current venv
	$(PIP) install -r requirements.txt

# ── Database migrations (Alembic) ────────────────────────────────────────────

migrate:    ## Run all pending Alembic migrations
	@set -a; . ./.env; set +a; \
	  alembic upgrade head
	@echo "✅ Migrations applied"

migrate-down:   ## Rollback the last migration
	@set -a; . ./.env; set +a; \
	  alembic downgrade -1

migrate-status: ## Show current migration revision
	@set -a; . ./.env; set +a; \
	  alembic current

migrate-history:    ## Show full migration history
	@set -a; . ./.env; set +a; \
	  alembic history --verbose

# ── Local development server ──────────────────────────────────────────────────

dev:    ## Start FastAPI with hot-reload (requires Postgres running via 'make up')
	@if [ ! -f .env ]; then \
	  echo "⚠️  .env not found — copy .env.example first:"; \
	  echo "    cp .env.example .env && vi .env"; \
	  exit 1; \
	fi
	$(PYTHON) main.py

# ── Testing ───────────────────────────────────────────────────────────────────

smoke-test: ## Run full end-to-end smoke test (server must be running)
	$(PYTHON) scripts/smoke_test.py --base-url $(BASE_URL)

mock-start: ## Send 'start' to the mock WhatsApp webhook
	@curl -s -X POST $(BASE_URL)/webhook/mock \
	  -H 'Content-Type: application/json' \
	  -d '{"from": "+10000000001", "body": "start"}' | python3 -m json.tool

mock-answer: ## Submit a sample answer to the mock webhook
	@read -p "Paste your answer (one line, Ctrl+D to finish): " ans; \
	curl -s -X POST $(BASE_URL)/webhook/mock \
	  -H 'Content-Type: application/json' \
	  -d "{\"from\": \"+10000000001\", \"body\": \"$$ans\"}" | python3 -m json.tool

mock-hint:  ## Request a hint via mock webhook
	@curl -s -X POST $(BASE_URL)/webhook/mock \
	  -H 'Content-Type: application/json' \
	  -d '{"from": "+10000000001", "body": "hint"}' | python3 -m json.tool

health:     ## Check server health
	@curl -s $(BASE_URL)/health | python3 -m json.tool

# ── Housekeeping ──────────────────────────────────────────────────────────────

clean:  ## Remove Python cache files
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete 2>/dev/null || true
	rm -f /tmp/ai_guide_checkpoints.db

# ── One-shot full setup ───────────────────────────────────────────────────────

setup: ## Complete first-time setup: copy .env, install deps, start DB, migrate
	@if [ ! -f .env ]; then \
	  cp .env.example .env; \
	  echo "📝 Created .env from .env.example — fill in your API keys before running 'make dev'"; \
	fi
	$(MAKE) install
	$(MAKE) up
	$(MAKE) migrate
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo "  Setup complete!"
	@echo ""
	@echo "  Next steps:"
	@echo "    1. Edit .env — add your ANTHROPIC_API_KEY,"
	@echo "                   GOOGLE_API_KEY, TAVILY_API_KEY"
	@echo "    2. make dev        — start the server"
	@echo "    3. make mock-start — fire your first challenge"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
