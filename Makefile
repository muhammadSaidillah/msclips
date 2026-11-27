.PHONY: infra backend-install migrate api worker web-install web test e2e

infra:            ## start postgres, redis, minio
	docker compose -f infra/docker-compose.yml up -d

backend-install:
	cd backend && uv venv .venv && uv pip install --python .venv/bin/python -e ".[dev]"

migrate:
	cd backend && .venv/bin/alembic upgrade head

api:
	cd backend && .venv/bin/uvicorn clipforge.api.main:app --reload --port 8000

worker:
	cd backend && .venv/bin/arq clipforge.workers.worker.WorkerSettings

web-install:
	cd apps/web && npm ci

web:
	cd apps/web && npm run dev

test:             ## backend tests (needs postgres with a clipforge_test database) + frontend checks
	cd backend && .venv/bin/pytest -q
	cd apps/web && npm run lint && npm run typecheck

e2e:              ## browser smoke test; api, worker and web must be running
	cd apps/web && node e2e/smoke.mjs $(VIDEO)
