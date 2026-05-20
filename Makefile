.PHONY: help up down api web scorer test lint typecheck migrate seed clean

help:
	@echo "Targets:"
	@echo "  up         docker compose up --build"
	@echo "  down       docker compose down -v"
	@echo "  api        uvicorn with reload (local, not in docker)"
	@echo "  web        next dev (local)"
	@echo "  scorer     run the scoring worker (local)"
	@echo "  test       pytest + tsc"
	@echo "  lint       ruff + eslint"
	@echo "  typecheck  mypy + tsc"
	@echo "  migrate    alembic upgrade head"
	@echo "  seed       populate demo data"

up:
	docker compose up --build

down:
	docker compose down -v

api:
	cd apps/api && uvicorn cellbench_api.main:app --reload

web:
	cd apps/web && npm run dev

scorer:
	cd apps/scorer && python -m cellbench_scorer.worker

test:
	cd apps/api && pytest -q
	cd apps/scorer && pytest -q
	cd apps/web && npm run typecheck

lint:
	cd apps/api && ruff check .
	cd apps/scorer && ruff check .
	cd apps/web && npm run lint

typecheck:
	cd apps/api && mypy cellbench_api
	cd apps/web && npm run typecheck

migrate:
	cd apps/api && alembic upgrade head

seed:
	cd apps/api && python -m scripts.seed
