.PHONY: help build up down logs shell test clean

help:
	@echo "Taxi Backend - Available commands:"
	@echo "  make build    - Build Docker containers"
	@echo "  make up       - Start all services"
	@echo "  make down     - Stop all services"
	@echo "  make logs     - View application logs"
	@echo "  make shell    - Open app container shell"
	@echo "  make db-shell - Open PostgreSQL shell"
	@echo "  make test     - Run tests"
	@echo "  make clean    - Clean up containers and volumes"
	@echo "  make migrate  - Run database migrations"

build:
	docker-compose build

up:
	docker-compose up -d
	@echo "Services started!"
	@echo "API: http://localhost:8000"
	@echo "Docs: http://localhost:8000/docs"

down:
	docker-compose down

logs:
	docker-compose logs -f app

shell:
	docker-compose exec app /bin/bash

db-shell:
	docker-compose exec db psql -U postgres -d taxi_db

test:
	docker-compose exec app pytest

clean:
	docker-compose down -v
	docker system prune -f

migrate:
	docker-compose exec app alembic upgrade head

migrate-create:
	@read -p "Enter migration message: " msg; \
	docker-compose exec app alembic revision --autogenerate -m "$$msg"
