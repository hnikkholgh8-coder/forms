#!/usr/bin/env makefile
# Makefile for Exir Pooyan Development & Deployment

.PHONY: help install dev test lint format clean docker-up docker-down db-init

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE := \033[0;34m
GREEN := \033[0;32m
RED := \033[0;31m
NC := \033[0m # No Color

help: ## Display this help message
	@echo "$(BLUE)Exir Pooyan Smart Management System$(NC)"
	@echo "$(BLUE)Available Make Commands:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(NC) %s\n", $$1, $$2}'

install: ## Install Python dependencies
	@echo "$(BLUE)Installing dependencies...$(NC)"
	pip install -r requirements.txt
	@echo "$(GREEN)✅ Dependencies installed$(NC)"

dev: ## Run development server
	@echo "$(BLUE)Starting development server...$(NC)"
	python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

test: ## Run all tests with coverage
	@echo "$(BLUE)Running test suite...$(NC)"
	pytest tests/ -v --cov=. --cov-report=html --asyncio-mode=auto
	@echo "$(GREEN)✅ Tests complete$(NC)"

test-orchestrator: ## Run orchestrator tests
	@echo "$(BLUE)Running orchestrator tests...$(NC)"
	pytest tests/test_orchestrator_adversarial.py -v -s --asyncio-mode=auto

test-domain: ## Run domain tests
	@echo "$(BLUE)Running domain tests...$(NC)"
	pytest tests/test_domain_adversarial.py -v -s --asyncio-mode=auto

test-integration: ## Run integration tests
	@echo "$(BLUE)Running integration tests...$(NC)"
	pytest tests/test_integration_resilience.py -v -s --asyncio-mode=auto

lint: ## Run code linting
	@echo "$(BLUE)Running linter...$(NC)"
	flake8 . --exclude=venv,__pycache__,build,dist
	mypy . --ignore-missing-imports
	@echo "$(GREEN)✅ Linting complete$(NC)"

format: ## Auto-format code with Black
	@echo "$(BLUE)Formatting code...$(NC)"
	black .
	@echo "$(GREEN)✅ Code formatted$(NC)"

clean: ## Clean temporary files and caches
	@echo "$(BLUE)Cleaning up...$(NC)"
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	find . -type d -name "*.egg-info" -exec rm -rf {} +
	rm -rf .pytest_cache .coverage htmlcov build dist .tox
	@echo "$(GREEN)✅ Cleanup complete$(NC)"

docker-build: ## Build Docker image
	@echo "$(BLUE)Building Docker image...$(NC)"
	docker build -t exir-pooyan:latest .
	@echo "$(GREEN)✅ Docker image built$(NC)"

docker-up: ## Start Docker Compose services
	@echo "$(BLUE)Starting Docker services...$(NC)"
	docker-compose up -d
	@echo "$(GREEN)✅ Services started$(NC)"
	@echo "Services ready at:"
	@echo "  - Backend: http://localhost:8000"
	@echo "  - Directus: http://localhost:8055"
	@echo "  - Keycloak: http://localhost:8080"
	@echo "  - PostgreSQL: localhost:5432"
	@echo "  - pgAdmin: http://localhost:5050"

docker-down: ## Stop Docker Compose services
	@echo "$(BLUE)Stopping Docker services...$(NC)"
	docker-compose down
	@echo "$(GREEN)✅ Services stopped$(NC)"

docker-logs: ## View Docker logs
	@echo "$(BLUE)Docker logs:$(NC)"
	docker-compose logs -f

db-init: ## Initialize PostgreSQL database with schema
	@echo "$(BLUE)Initializing database...$(NC)"
	psql -h localhost -U postgres -d exir_pooyan -f sql_schemas.txt
	@echo "$(GREEN)✅ Database initialized$(NC)"

db-migrate: ## Run database migrations
	@echo "$(BLUE)Running migrations...$(NC)"
	alembic upgrade head
	@echo "$(GREEN)✅ Migrations complete$(NC)"

db-shell: ## Open PostgreSQL shell
	@echo "$(BLUE)Opening PostgreSQL shell...$(NC)"
	psql -h localhost -U postgres -d exir_pooyan

seed-data: ## Seed database with sample data
	@echo "$(BLUE)Seeding database...$(NC)"
	python scripts/seed_data.py
	@echo "$(GREEN)✅ Data seeded$(NC)"

docs: ## Generate API documentation
	@echo "$(BLUE)Generating documentation...$(NC)"
	@echo "API docs available at: http://localhost:8000/api/docs"

requirements-update: ## Update requirements from current environment
	@echo "$(BLUE)Updating requirements...$(NC)"
	pip freeze > requirements.txt
	@echo "$(GREEN)✅ Requirements updated$(NC)"

audit-logger-test: ## Test audit logging with sample function
	@echo "$(BLUE)Testing audit logger...$(NC)"
	python -c "from security.audit_logger import exir_boundary_tracer; print('✅ Audit logger working')"

auth-bootstrap-test: ## Test Keycloak role bootstrap
	@echo "$(BLUE)Testing auth bootstrap...$(NC)"
	python -c "from security.auth_manager import auth_manager; print('✅ Auth manager ready')"

lookup-test: ## Test fuzzy lookup engine
	@echo "$(BLUE)Testing lookup engine...$(NC)"
	python -c "from lookup.engine_lookup import hub_lookup; print('✅ Lookup engine ready')"

all: clean install lint test ## Run complete development cycle
	@echo "$(GREEN)✅ All checks passed$(NC)"

.PHONY: help install dev test lint format clean docker-build docker-up docker-down db-init db-shell seed-data docs requirements-update audit-logger-test auth-bootstrap-test lookup-test all
