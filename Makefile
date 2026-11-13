.PHONY: dev test migrate seed db-up db-down db-reset ml-baseline

dev:
	uvicorn app.main:app --reload

test:
	python -m pytest -q

migrate:
	alembic upgrade head

seed:
	python scripts/seed_demo.py

db-up:
	docker compose up -d db

db-down:
	docker compose down

db-reset:
	docker compose down -v
	docker compose up -d db

ml-baseline:
	python scripts/train_ml_baseline.py
