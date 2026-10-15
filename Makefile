.PHONY: setup setup-backend setup-frontend dev api start-api frontend test lint format db-upgrade clean

setup: setup-backend setup-frontend

setup-backend:
	uv sync --locked --group dev

setup-frontend:
	cd frontend && npm ci

dev:
	./scripts/dev.sh

api:
	uv run uvicorn backend.app.main:app --reload --host 127.0.0.1 --port 8000

start-api:
	uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1

frontend:
	cd frontend && npm run dev

test:
	uv run pytest
	cd frontend && npm test -- --run

lint:
	uv run ruff check backend
	cd frontend && npm run lint && npm run typecheck

format:
	uv run ruff format backend
	cd frontend && npm run format

db-upgrade:
	uv run alembic upgrade head

clean:
	rm -rf .venv frontend/node_modules frontend/dist var
