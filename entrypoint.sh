#!/bin/sh
set -e

if [ "$1" = "gunicorn" ]; then
    if [ -f "/usr/src/app/app/functions/asset_diagnostics_v4_tables.sql" ]; then
        echo "Ensuring asset diagnostics tables exist..."
        python manage.py shell -c "from pathlib import Path; from django.db import connection; sql = Path('/usr/src/app/app/functions/asset_diagnostics_v4_tables.sql').read_text(); cursor = connection.cursor(); cursor.execute(sql); connection.commit()"
    fi

    echo "Running migrations..."
    python manage.py makemigrations --noinput || { echo "Makemigrations failed"; exit 1; }

    DIAG_MIGRATION="$(find /usr/src/app/app/migrations -maxdepth 1 -type f -name '*alarmqueuemaster_assetdiagnosticreportmaster.py' -print -quit 2>/dev/null || true)"
    if [ -n "$DIAG_MIGRATION" ]; then
        DIAG_MIGRATION_NAME="$(basename "$DIAG_MIGRATION" .py)"
        echo "Faking pre-existing diagnostics migration: $DIAG_MIGRATION_NAME"
        python manage.py migrate app "$DIAG_MIGRATION_NAME" --fake --noinput || true
    fi

    python manage.py migrate --noinput || { echo "Migration failed"; exit 1; }
    echo "Starting Gunicorn..."

    python manage.py crontab add
    service cron start

    echo "Loading Redis data mappings..."
    python manage.py initialize_cache || echo "Redis data loading failed"
fi

exec "$@"
