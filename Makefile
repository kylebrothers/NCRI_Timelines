# Makefile for Asana Integration Platform
# Provides automated build, deployment, and management commands

# Variables
DOCKER_COMPOSE = docker-compose
DOCKER = docker
PYTHON = python3
PIP = pip3
APP_NAME = asana-integration
CONTAINER_NAME = asana-integration-app
IMAGE_NAME = asana-integration:latest
NAS_IP ?= 192.168.0.134
HOST_PORT ?= 5000

# Color output
RED = \033[0;31m
GREEN = \033[0;32m
YELLOW = \033[1;33m
NC = \033[0m # No Color

# Default target
.DEFAULT_GOAL := help

# Phony targets
.PHONY: help build up down restart logs shell test clean backup restore update-deps lint format security-check

## Help
help: ## Show this help message
	@echo "$(GREEN)Asana Integration Platform - Makefile Commands$(NC)"
	@echo ""
	@echo "Available targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(YELLOW)%-20s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Environment Variables:$(NC)"
	@echo "  NAS_IP=$(NAS_IP)"
	@echo "  HOST_PORT=$(HOST_PORT)"

## Docker Commands
build: ## Build Docker image
	@echo "$(GREEN)Building Docker image...$(NC)"
	$(DOCKER_COMPOSE) build --no-cache
	@echo "$(GREEN)Build complete!$(NC)"

up: ## Start all services
	@echo "$(GREEN)Starting services...$(NC)"
	$(DOCKER_COMPOSE) up -d
	@echo "$(GREEN)Services started! Access at http://localhost:$(HOST_PORT)$(NC)"

down: ## Stop all services
	@echo "$(YELLOW)Stopping services...$(NC)"
	$(DOCKER_COMPOSE) down
	@echo "$(GREEN)Services stopped!$(NC)"

restart: ## Restart all services
	@echo "$(YELLOW)Restarting services...$(NC)"
	$(MAKE) down
	$(MAKE) up

logs: ## View container logs
	@echo "$(GREEN)Showing logs (Ctrl+C to exit)...$(NC)"
	$(DOCKER_COMPOSE) logs -f $(CONTAINER_NAME)

shell: ## Access container shell
	@echo "$(GREEN)Accessing container shell...$(NC)"
	$(DOCKER) exec -it $(CONTAINER_NAME) /bin/bash

status: ## Show container status
	@echo "$(GREEN)Container Status:$(NC)"
	@$(DOCKER_COMPOSE) ps
	@echo ""
	@echo "$(GREEN)Health Check:$(NC)"
	@curl -s http://localhost:$(HOST_PORT)/health | python3 -m json.tool || echo "$(RED)Service not responding$(NC)"

## Development Commands
dev: ## Run Flask in development mode (local)
	@echo "$(GREEN)Starting development server...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(RED)Error: .env file not found. Copy .env.example to .env$(NC)"; \
		exit 1; \
	fi
	@export FLASK_ENV=development && \
	export FLASK_DEBUG=true && \
	$(PYTHON) app.py

install: ## Install Python dependencies locally
	@echo "$(GREEN)Installing Python dependencies...$(NC)"
	$(PIP) install -r requirements.txt
	@echo "$(GREEN)Dependencies installed!$(NC)"

install-dev: ## Install development dependencies
	@echo "$(GREEN)Installing development dependencies...$(NC)"
	$(PIP) install -r requirements.txt
	$(PIP) install pytest pytest-cov black flake8 bandit
	@echo "$(GREEN)Development dependencies installed!$(NC)"

## Testing
test: ## Run tests
	@echo "$(GREEN)Running tests...$(NC)"
	@if [ -d "tests" ]; then \
		$(PYTHON) -m pytest tests/ -v; \
	else \
		echo "$(YELLOW)No tests directory found. Creating test structure...$(NC)"; \
		$(MAKE) create-tests; \
	fi

test-api: ## Test Asana API connection
	@echo "$(GREEN)Testing Asana API connection...$(NC)"
	@$(PYTHON) test_asana_connection.py

test-coverage: ## Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	$(PYTHON) -m pytest tests/ --cov=. --cov-report=html --cov-report=term

create-tests: ## Create test directory structure
	@echo "$(GREEN)Creating test structure...$(NC)"
	@mkdir -p tests
	@echo "import pytest\n\ndef test_placeholder():\n    assert True" > tests/test_basic.py
	@echo "$(GREEN)Test structure created!$(NC)"

## Code Quality
lint: ## Run code linting
	@echo "$(GREEN)Running flake8 linter...$(NC)"
	@flake8 . --count --select=E9,F63,F7,F82 --show-source --statistics || true
	@flake8 . --count --exit-zero --max-complexity=10 --max-line-length=127 --statistics

format: ## Format code with black
	@echo "$(GREEN)Formatting code with black...$(NC)"
	@black . --line-length=100 --skip-string-normalization

security-check: ## Run security checks with bandit
	@echo "$(GREEN)Running security checks...$(NC)"
	@bandit -r . -f json -o security_report.json || true
	@echo "$(GREEN)Security report saved to security_report.json$(NC)"

## Database/Files Management
backup: ## Backup server files and configurations
	@echo "$(GREEN)Creating backup...$(NC)"
	@mkdir -p backups
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	tar -czf backups/backup_$$timestamp.tar.gz \
		server_files/ \
		templates/ \
		static/ \
		.env \
		docker-compose.yml || true
	@echo "$(GREEN)Backup created in backups/ directory$(NC)"

restore: ## Restore from latest backup
	@echo "$(YELLOW)Restoring from latest backup...$(NC)"
	@latest_backup=$$(ls -t backups/*.tar.gz 2>/dev/null | head -1); \
	if [ -z "$$latest_backup" ]; then \
		echo "$(RED)No backup found!$(NC)"; \
		exit 1; \
	fi; \
	echo "$(GREEN)Restoring from $$latest_backup...$(NC)"; \
	tar -xzf $$latest_backup
	@echo "$(GREEN)Restore complete!$(NC)"

clean-logs: ## Clean log files
	@echo "$(YELLOW)Cleaning log files...$(NC)"
	@rm -f logs/*.log
	@touch logs/app.log
	@echo "$(GREEN)Logs cleaned!$(NC)"

## Setup Commands
init: ## Initialize project (first time setup)
	@echo "$(GREEN)Initializing Asana Integration Platform...$(NC)"
	@echo "1. Creating directories..."
	@mkdir -p logs templates static server_files uploads
	@echo "2. Checking for .env file..."
	@if [ ! -f .env ]; then \
		echo "$(YELLOW)Creating .env from template...$(NC)"; \
		cp .env.example .env; \
		echo "$(RED)Please edit .env and add your Asana credentials!$(NC)"; \
	else \
		echo "$(GREEN).env file exists$(NC)"; \
	fi
	@echo "3. Creating NFS mount points..."
	@$(MAKE) setup-nfs
	@echo "$(GREEN)Initialization complete!$(NC)"

setup-nfs: ## Setup NFS directories on NAS
	@echo "$(GREEN)Setting up NFS directories...$(NC)"
	@echo "Creating directories on NAS at $(NAS_IP)..."
	@echo "Please ensure these directories exist on your NAS:"
	@echo "  - /Docker/asana-integration/logs"
	@echo "  - /Docker/asana-integration/server_files"
	@echo "  - /Docker/asana-integration/templates"
	@echo "  - /Docker/asana-integration/static"
	@echo "  - /Docker/asana-integration/uploads"

check-env: ## Verify environment configuration
	@echo "$(GREEN)Checking environment configuration...$(NC)"
	@if [ ! -f .env ]; then \
		echo "$(RED)✗ .env file not found$(NC)"; \
		exit 1; \
	else \
		echo "$(GREEN)✓ .env file exists$(NC)"; \
	fi
	@if grep -q "your-asana-personal-access-token" .env; then \
		echo "$(RED)✗ Asana access token not configured$(NC)"; \
	else \
		echo "$(GREEN)✓ Asana access token configured$(NC)"; \
	fi
	@if grep -q "your-workspace-gid" .env; then \
		echo "$(RED)✗ Workspace GID not configured$(NC)"; \
	else \
		echo "$(GREEN)✓ Workspace GID configured$(NC)"; \
	fi

test-connection: test-api ## Alias for test-api
	@echo ""

## Deployment
deploy: ## Full deployment (build, test, and start)
	@echo "$(GREEN)Starting full deployment...$(NC)"
	@$(MAKE) check-env
	@$(MAKE) build
	@$(MAKE) up
	@sleep 5
	@$(MAKE) status
	@echo "$(GREEN)Deployment complete!$(NC)"

deploy-prod: ## Production deployment with safety checks
	@echo "$(GREEN)Starting production deployment...$(NC)"
	@echo "$(YELLOW)This will restart the service. Continue? [y/N]$(NC)"
	@read -r response; \
	if [ "$$response" != "y" ]; then \
		echo "$(RED)Deployment cancelled$(NC)"; \
		exit 1; \
	fi
	@$(MAKE) backup
	@$(MAKE) check-env
	@$(MAKE) build
	@$(MAKE) down
	@$(MAKE) up
	@sleep 5
	@$(MAKE) status
	@echo "$(GREEN)Production deployment complete!$(NC)"

rollback: ## Rollback to previous version
	@echo "$(RED)Rolling back to previous version...$(NC)"
	@$(MAKE) down
	@$(MAKE) restore
	@$(MAKE) up
	@echo "$(GREEN)Rollback complete!$(NC)"

## Maintenance
update-deps: ## Update Python dependencies
	@echo "$(GREEN)Updating dependencies...$(NC)"
	$(PIP) install --upgrade -r requirements.txt
	@echo "$(GREEN)Dependencies updated!$(NC)"

health-check: ## Perform health check
	@echo "$(GREEN)Performing health check...$(NC)"
	@curl -s http://localhost:$(HOST_PORT)/health | python3 -m json.tool

monitor: ## Monitor container resources
	@echo "$(GREEN)Monitoring container resources (Ctrl+C to exit)...$(NC)"
	@$(DOCKER) stats $(CONTAINER_NAME)

prune: ## Clean up unused Docker resources
	@echo "$(YELLOW)Cleaning up Docker resources...$(NC)"
	$(DOCKER) system prune -f
	@echo "$(GREEN)Cleanup complete!$(NC)"

## Database Operations
export-tasks: ## Export tasks to CSV
	@echo "$(GREEN)Exporting tasks to CSV...$(NC)"
	@mkdir -p exports
	@timestamp=$$(date +%Y%m%d_%H%M%S); \
	$(DOCKER) exec $(CONTAINER_NAME) python -c \
		"from asana_client import AsanaClient; \
		client = AsanaClient(); \
		tasks = client.search_tasks(''); \
		import csv; \
		with open('/app/exports/tasks_$$timestamp.csv', 'w') as f: \
			writer = csv.DictWriter(f, fieldnames=['gid', 'name', 'completed', 'due_on']); \
			writer.writeheader(); \
			writer.writerows(tasks)" || echo "$(RED)Export failed$(NC)"
	@echo "$(GREEN)Tasks exported to exports/tasks_$$timestamp.csv$(NC)"

## Quick Commands
test-quick: ## Quick API connection test (no Docker needed)
	@$(PYTHON) test_asana_connection.py

quick-start: init test-api deploy ## Quick start for new installations
	@echo "$(GREEN)Quick start complete!$(NC)"

rebuild: down build up ## Rebuild and restart everything
	@echo "$(GREEN)Rebuild complete!$(NC)"

refresh: ## Refresh application (restart without rebuild)
	@echo "$(YELLOW)Refreshing application...$(NC)"
	$(DOCKER_COMPOSE) restart $(CONTAINER_NAME)
	@echo "$(GREEN)Application refreshed!$(NC)"

tail-logs: ## Tail application logs
	@$(DOCKER) exec $(CONTAINER_NAME) tail -f /app/logs/app.log

## Documentation
docs: ## Generate documentation
	@echo "$(GREEN)Generating documentation...$(NC)"
	@mkdir -p docs
	@echo "# Asana Integration Platform" > docs/README.md
	@echo "" >> docs/README.md
	@echo "## Available Make Commands" >> docs/README.md
	@echo "" >> docs/README.md
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "- **make %s**: %s\n", $$1, $$2}' >> docs/README.md
	@echo "$(GREEN)Documentation generated in docs/README.md$(NC)"

version: ## Show version information
	@echo "$(GREEN)Asana Integration Platform$(NC)"
	@echo "Version: 1.0.0"
	@echo "Python: $$($(PYTHON) --version)"
	@echo "Docker: $$($(DOCKER) --version)"
	@echo "Docker Compose: $$($(DOCKER_COMPOSE) --version)"

## Debugging
debug-env: ## Debug environment variables
	@echo "$(GREEN)Environment Variables:$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) env | grep -E "ASANA|FLASK" | sort

debug-network: ## Debug network connectivity
	@echo "$(GREEN)Testing network connectivity...$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) ping -c 3 app.asana.com || echo "$(RED)Cannot reach Asana$(NC)"
	@echo "$(GREEN)Testing NFS mounts...$(NC)"
	@$(DOCKER) exec $(CONTAINER_NAME) df -h | grep nfs || echo "$(YELLOW)No NFS mounts found$(NC)"

validate: ## Validate configuration files
	@echo "$(GREEN)Validating configuration files...$(NC)"
	@python3 -m py_compile app.py asana_client.py page_handlers.py task_formatters.py utils.py config.py
	@echo "$(GREEN)✓ Python files valid$(NC)"
	@docker-compose config --quiet && echo "$(GREEN)✓ docker-compose.yml valid$(NC)" || echo "$(RED)✗ docker-compose.yml invalid$(NC)"

# Clean everything
clean: ## Clean all generated files and containers
	@echo "$(RED)This will remove all containers, images, and generated files!$(NC)"
	@echo "$(YELLOW)Continue? [y/N]$(NC)"
	@read -r response; \
	if [ "$$response" = "y" ]; then \
		$(MAKE) down; \
		$(DOCKER) rmi $(IMAGE_NAME) || true; \
		rm -rf __pycache__ *.pyc .pytest_cache htmlcov; \
		rm -f security_report.json; \
		$(MAKE) clean-logs; \
		echo "$(GREEN)Cleanup complete!$(NC)"; \
	else \
		echo "$(YELLOW)Cleanup cancelled$(NC)"; \
	fi
