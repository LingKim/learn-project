.PHONY: init-env bootstrap-db bootstrap-storage preflight install dev practice-worker knowledge-worker down logs contract format check test compose-config

init-env:
	./scripts/init-env.sh

bootstrap-db:
	./scripts/bootstrap-db.sh

bootstrap-storage:
	cd backend && uv run xuemian-ai-init-storage

preflight:
	./scripts/preflight.sh

install:
	cd backend && uv sync --frozen
	cd frontend && pnpm install --frozen-lockfile

dev: preflight
	docker compose up

practice-worker:
	cd backend && uv run xuemian-ai-practice-worker

knowledge-worker:
	cd backend && uv run python -m xuemian_ai.learning_assets.worker

down:
	docker compose down

logs:
	docker compose logs --follow

contract:
	cd backend && uv run python -m xuemian_ai.openapi ../openapi/openapi.json
	cd frontend && pnpm openapi:check

format:
	cd backend && uv run ruff format .
	cd frontend && pnpm format

check: contract
	cd backend && uv run ruff format --check .
	cd backend && uv run ruff check .
	cd backend && uv run mypy
	cd frontend && pnpm format:check
	cd frontend && pnpm lint
	cd frontend && pnpm typecheck
	$(MAKE) compose-config

test:
	cd backend && uv run pytest
	cd frontend && pnpm test

compose-config:
	docker compose --env-file .env.example config --quiet
