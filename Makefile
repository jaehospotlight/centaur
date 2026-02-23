.PHONY: install lint test migrate sync api sandbox-build sandbox-update-repos fmt clean

install:
	uv sync --all-packages

lint:
	uv run ruff check .
	uv run ruff format --check .

fmt:
	uv run ruff check --fix .
	uv run ruff format .

test:
	uv run pytest

migrate:
	uv run alembic upgrade head

sync:
	uv run python -m dataplane.cli sync

api:
	uv run uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload

sandbox-build:
	docker build -t tempo-ai-sandbox:latest sandbox/

sandbox-update-repos:
	uv run python -m sandbox.update_repos

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .mypy_cache -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .ruff_cache -exec rm -rf {} + 2>/dev/null || true
