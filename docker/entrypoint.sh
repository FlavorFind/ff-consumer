#!/bin/sh
set -e

echo "Waiting for PostgreSQL..."
until pg_isready -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER"; do
  sleep 1
done
echo "PostgreSQL is ready."

echo "Waiting for Redis..."
until redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping | grep -q PONG; do
  sleep 1
done
echo "Redis is ready."

echo "Running migrations..."
python manage.py migrate --noinput

echo "Starting server..."
exec "$@"
