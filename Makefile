# Common dev tasks for opkomst. ``make help`` lists the targets.

.PHONY: help db-up db-down db-reset db-shell test test-fast lint typecheck e2e openapi

help:
	@echo "make db-up        Start postgres in docker (port 5433)."
	@echo "make db-down      Stop postgres."
	@echo "make db-reset     Drop and recreate the postgres volume."
	@echo "make db-shell     Open a psql shell against the dev database."
	@echo "make test         Run backend pytest with coverage gate."
	@echo "make test-fast    Run pytest without coverage."
	@echo "make lint         ruff + pyright."
	@echo "make typecheck    pyright + vue-tsc."
	@echo "make e2e          Playwright critical-path on a fresh stack."
	@echo "make openapi      Regenerate openapi.json + frontend/src/api/schema.ts."

db-up:
	docker compose up -d postgres
	@echo "Waiting for postgres to be ready…"
	@for i in $$(seq 1 30); do \
		docker compose exec -T postgres pg_isready -U opkomst -d opkomst >/dev/null 2>&1 && break; \
		sleep 1; \
	done

db-down:
	docker compose stop postgres

db-reset:
	docker compose down -v postgres
	$(MAKE) db-up

db-shell:
	docker compose exec postgres psql -U opkomst -d opkomst

test:
	uv run pytest

test-fast:
	uv run pytest --no-cov

lint:
	uv run ruff check backend tests
	uv run pyright backend

typecheck:
	uv run pyright backend
	cd frontend && npx vue-tsc --noEmit

e2e:
	cd frontend && CI=1 npx playwright test

openapi:
	uv run python scripts/generate_openapi.py
	cd frontend && npx openapi-typescript ../openapi.json -o src/api/schema.ts
