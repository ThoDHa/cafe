SERVER_PORT ?= 8000

.PHONY: dev test start export-openapi

dev:
	uv run uvicorn app.main:app --reload --port $(SERVER_PORT)

test:
	uv run pytest

start:
	uv run uvicorn app.main:app --port $(SERVER_PORT)

export-openapi:
	uv run export-openapi --out ../web/openapi.json
