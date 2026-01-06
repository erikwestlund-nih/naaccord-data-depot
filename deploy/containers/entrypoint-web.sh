#!/bin/bash
# Flexible entrypoint for web container
# Supports both development (hot reload) and production modes

set -e

# Default values
: ${DJANGO_SETTINGS_MODULE:=depot.settings}
: ${SERVER_ROLE:=web}
: ${PORT:=8000}
: ${WORKERS:=4}
: ${THREADS:=2}
: ${DEV_MODE:=false}
: ${AUTO_RELOAD:=true}

echo "Starting NA-ACCORD Web Server"
echo "Environment: SERVER_ROLE=$SERVER_ROLE, DEV_MODE=$DEV_MODE"

# Read Docker secrets from files into environment variables
if [ -n "$INTERNAL_API_KEY_FILE" ] && [ -f "$INTERNAL_API_KEY_FILE" ]; then
    export INTERNAL_API_KEY=$(cat "$INTERNAL_API_KEY_FILE")
    echo "Loaded INTERNAL_API_KEY from secret file"
fi

if [ -n "$SECRET_KEY_FILE" ] && [ -f "$SECRET_KEY_FILE" ]; then
    export SECRET_KEY=$(cat "$SECRET_KEY_FILE")
    echo "Loaded SECRET_KEY from secret file"
fi

if [ -n "$DB_PASSWORD_FILE" ] && [ -f "$DB_PASSWORD_FILE" ]; then
    export DB_PASSWORD=$(cat "$DB_PASSWORD_FILE")
    echo "Loaded DB_PASSWORD from secret file"
fi

# Read Redis password from secret and construct Celery broker URL
if [ -f "/run/secrets/redis_password" ]; then
    REDIS_PASSWORD=$(cat /run/secrets/redis_password)
    export CELERY_BROKER_URL="redis://:${REDIS_PASSWORD}@10.100.0.11:6379/0"
    export REDIS_URL="redis://:${REDIS_PASSWORD}@10.100.0.11:6379/0"  # For compatibility
    echo "Loaded Redis password from secret file and constructed CELERY_BROKER_URL"
fi

# Install missing dependencies if in dev mode (temporary until images are rebuilt)
if [ "$DEV_MODE" = "true" ] && [ "$INSTALL_MISSING_DEPS" = "true" ]; then
    echo "Installing missing dependencies for development..."
    pip install django-axes --quiet || true
fi

# Wait for database if needed
if [ "$WAIT_FOR_DB" = "true" ]; then
    echo "Waiting for database..."
    python manage.py wait_for_db || true
fi

# Run migrations if requested
if [ "$RUN_MIGRATIONS" = "true" ]; then
    echo "Running database migrations..."
    python manage.py migrate --noinput
fi

# Collect static files if requested
if [ "$COLLECT_STATIC" = "true" ]; then
    echo "Collecting static files..."
    python manage.py collectstatic --noinput
fi

# Choose server based on environment
if [ "$DEV_MODE" = "true" ]; then
    echo "Starting development server with hot reload..."
    if [ "$AUTO_RELOAD" = "true" ]; then
        exec python manage.py runserver 0.0.0.0:$PORT
    else
        exec python manage.py runserver --noreload 0.0.0.0:$PORT
    fi
else
    echo "Starting production server with gunicorn..."
    # Set Gunicorn environment variables
    export GUNICORN_BIND="0.0.0.0:$PORT"
    export GUNICORN_WORKERS="$WORKERS"
    export GUNICORN_THREADS="$THREADS"
    export GUNICORN_TIMEOUT="600"  # 10 minutes for large file uploads
    export GUNICORN_LOG_LEVEL="${LOG_LEVEL:-info}"

    # Use gunicorn with clean logging config
    exec gunicorn \
        --config /app/gunicorn_config.py \
        depot.wsgi:application
fi