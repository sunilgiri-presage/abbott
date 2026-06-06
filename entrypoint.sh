#!/bin/sh
set -e

if [ "$1" = "gunicorn" ]; then
    echo "Running migrations..."
    python manage.py makemigrations --noinput || { echo "Makemigrations failed"; exit 1; }
    python manage.py migrate --noinput || { echo "Migration failed"; exit 1; }
    echo "Starting Gunicorn..."

    python manage.py crontab add
    service cron start

    echo "Loading Redis data mappings..."
    python manage.py initialize_cache || echo "Redis data loading failed"
fi

exec "$@"
