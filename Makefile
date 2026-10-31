# -------------------------------------------------------
# Flavor Find — ff-consumer Makefile
# Usage: make <target>
# -------------------------------------------------------

COMPOSE = docker compose -f docker/docker-compose.yml

.PHONY: help up up-d down down-v restart logs logs-web shell bash \
        test test-v test-cov lint format typecheck migrate \
        makemigrations createsuperuser collectstatic build ps db-shell

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Start all services (web + db + redis + worker + beat)
	$(COMPOSE) up --build

up-d: ## Start all services in the background
	$(COMPOSE) up --build -d

down: ## Stop all services
	$(COMPOSE) down

down-v: ## Stop all services and remove volumes (WARNING: deletes data)
	$(COMPOSE) down -v

restart: ## Restart all services
	$(COMPOSE) restart

logs: ## Tail logs for all services
	$(COMPOSE) logs -f

logs-web: ## Tail logs for the web service only
	$(COMPOSE) logs -f web

shell: ## Open a Django shell
	$(COMPOSE) exec web python manage.py shell

bash: ## Open a bash shell in the web container
	$(COMPOSE) exec web bash

test: ## Run the full test suite
	$(COMPOSE) exec web pytest --tb=short -q

test-v: ## Run tests with verbose output
	$(COMPOSE) exec web pytest --tb=short -v

test-cov: ## Run tests with coverage report
	$(COMPOSE) exec web pytest --cov=apps --cov-report=term-missing --tb=short

lint: ## Run ruff linter
	$(COMPOSE) exec web ruff check .

format: ## Auto-format code with ruff
	$(COMPOSE) exec web ruff format .

typecheck: ## Run mypy type checks
	$(COMPOSE) exec web mypy apps/

migrate: ## Run Django migrations
	$(COMPOSE) exec web python manage.py migrate

makemigrations: ## Create new migrations
	$(COMPOSE) exec web python manage.py makemigrations

createsuperuser: ## Create a Django superuser
	$(COMPOSE) exec web python manage.py createsuperuser

collectstatic: ## Collect static files
	$(COMPOSE) exec web python manage.py collectstatic --noinput

build: ## Rebuild Docker images
	$(COMPOSE) build

ps: ## Show running containers
	$(COMPOSE) ps

db-shell: ## Open a psql shell
	$(COMPOSE) exec db psql -U ff_consumer -d ff_consumer
