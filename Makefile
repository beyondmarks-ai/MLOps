COMPOSE = docker compose --env-file .env -f deploy/compose.azure.yml
.PHONY: up down build train ingest retrain monitor logs test lint format deploy backup
up:
	$(COMPOSE) up -d --build

down:
	$(COMPOSE) down

build:
	$(COMPOSE) build

train:
	$(COMPOSE) exec scheduler airflow dags trigger training_pipeline

ingest:
	$(COMPOSE) exec scheduler airflow dags trigger data_ingestion

retrain:
	$(COMPOSE) exec scheduler python -c "from src.data.store import enqueue; print(enqueue('manual'))"

monitor:
	$(COMPOSE) exec scheduler airflow dags trigger model_monitoring

logs:
	$(COMPOSE) logs -f --tail=100

test:
	python -m pytest tests/ --cov=src --cov-fail-under=80

lint:
	ruff check src/ dags/ tests/
	ruff format --check src/ dags/ tests/

format:
	ruff format src/ dags/ tests/

deploy:
	powershell -File scripts/deploy.ps1

backup:
	bash deploy/backup.sh
