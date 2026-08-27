# Common dev tasks for opkomst. ``make help`` lists the targets.

.PHONY: help db-up db-down db-reset db-shell test test-fast lint typecheck e2e openapi \
	pre-push-checks pp-backend pp-frontend-build pp-frontend-tests pp-schema-drift

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
	@echo "make pre-push-checks  Everything git push runs except e2e (use -j4)."

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

# --- What ``git push`` runs (see lefthook.yml) ------------------------
#
# Everything that has no deadline, run concurrently with ``make -j``.
# The e2e job is deliberately NOT in here: it boots two servers and
# holds per-test timeouts, so it runs on its own afterwards rather than
# fighting these four for cores.
pre-push-checks: pp-backend pp-frontend-build pp-frontend-tests pp-schema-drift

pp-backend:
	uv run pytest --no-cov -q

# Built to ``dist-check`` rather than ``dist``: ``routers/spa.py``
# serves the app shell out of ``dist`` on every request, so the backend
# suite reads it while a build here would be emptying it.
pp-frontend-build:
	cd frontend && npm run build -- --outDir dist-check

pp-frontend-tests:
	cd frontend && npx vitest run

pp-schema-drift:
	$(MAKE) openapi
	@if ! git diff --quiet openapi.json frontend/src/api/schema.ts; then \
		echo "openapi.json or frontend/src/api/schema.ts is out of date — 'make openapi' refreshed them, please commit"; \
		exit 1; \
	fi
