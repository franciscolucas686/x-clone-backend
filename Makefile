# Vocabulário de comandos do backend.
#
# Os mesmos verbos do frontend (lint, format, typecheck, test), para que os dois
# repositórios sejam operados igual. `lint` nunca corrige — é este que o CI roda;
# `lint-fix` é o opt-in separado.

.DEFAULT_GOAL := help
PY := .venv/bin/python
PIP := .venv/bin/pip

.PHONY: help setup db-up db-down migrate seed run test test-cov lint lint-fix format check clean

help: ## Lista os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

setup: ## Cria o venv e instala as dependências
	python3 -m venv .venv
	$(PIP) install --upgrade pip
	$(PIP) install -r requirements.txt -r requirements-dev.txt
	@test -f .env || (cp .env.example .env && echo "\n.env criado a partir de .env.example")

db-up: ## Sobe o Postgres
	docker compose up -d db

db-down: ## Derruba o Postgres, preservando o volume
	docker compose stop db

migrate: ## Aplica as migrações
	$(PY) manage.py migrate

seed: ## Popula dados de demonstração (exige RUN_SEED=true no .env)
	$(PY) manage.py seed_demo

run: ## Sobe o servidor de desenvolvimento
	$(PY) manage.py runserver

test: ## Roda a suíte
	$(PY) -m pytest

test-cov: ## Roda a suíte com relatório de cobertura
	$(PY) -m pytest --cov=. --cov-report=term-missing

lint: ## Verifica lint e formatação, sem corrigir
	$(PY) -m ruff check .
	$(PY) -m ruff format --check .

lint-fix: ## Corrige o que der e formata
	$(PY) -m ruff check --fix .
	$(PY) -m ruff format .

check: ## Verificações do Django: configuração, deploy e migrações pendentes
	$(PY) manage.py check
	$(PY) manage.py makemigrations --check --dry-run
	DJANGO_SETTINGS_MODULE=backend.settings.production \
	SECRET_KEY=$$($(PY) -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())") \
	ALLOWED_HOSTS=exemplo.com DATABASE_NAME=x DATABASE_USER=x DATABASE_PASSWORD=x DATABASE_HOST=x \
	CLOUDINARY_CLOUD_NAME=x CLOUDINARY_API_KEY=x CLOUDINARY_API_SECRET=x \
	CORS_ALLOWED_ORIGINS=https://exemplo.com \
	$(PY) manage.py check --deploy

clean: ## Remove caches
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache .ruff_cache htmlcov .coverage
