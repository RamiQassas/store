#!/bin/bash
set -e

# Verify that .env exists
if [ ! -f .env ]; then
    echo "Error: .env file is missing. Please create .env with environment variables."
    exit 1
fi

docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec web python manage.py migrate
docker compose -f docker-compose.prod.yml ps

