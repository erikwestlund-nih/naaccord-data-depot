#!/bin/bash
# Flexible entrypoint for services container
# Supports Django services API, Celery workers, and Celery beat

set -e

# Default values
: ${DJANGO_SETTINGS_MODULE:=depot.settings}
: ${SERVER_ROLE:=services}
: ${SERVICE_TYPE:=django}  # Can be: django, celery, celery-beat
: ${PORT:=8001}
: ${WORKERS:=4}
: ${THREADS:=2}
: ${CELERY_WORKERS:=4}
: ${CELERY_QUEUES:=celery,default,critical,low}
: ${DEV_MODE:=false}
: ${AUTO_RELOAD:=true}

echo "Starting NA-ACCORD Services"
echo "Environment: SERVER_ROLE=$SERVER_ROLE, SERVICE_TYPE=$SERVICE_TYPE, DEV_MODE=$DEV_MODE"

# Read Docker secrets from files into environment variables
if [ -n "$INTERNAL_API_KEY_FILE" ] && [ -f "$INTERNAL_API_KEY_FILE" ]; then
    export INTERNAL_API_KEY=$(cat "$INTERNAL_API_KEY_FILE")
    echo "Loaded INTERNAL_API_KEY from secret file"
fi

if [ -n "$SECRET_KEY_FILE" ] && [ -f "$SECRET_KEY_FILE" ]; then
    export SECRET_KEY=$(cat "$SECRET_KEY_FILE")
    echo "Loaded SECRET_KEY from secret file"
fi

if [ -n "$DATABASE_PASSWORD_FILE" ] && [ -f "$DATABASE_PASSWORD_FILE" ]; then
    export DATABASE_PASSWORD=$(cat "$DATABASE_PASSWORD_FILE")
    export DB_PASSWORD=$(cat "$DATABASE_PASSWORD_FILE")  # Django expects DB_PASSWORD
    echo "Loaded DATABASE_PASSWORD from secret file"
fi

# Translate DATABASE_* environment variables to DB_* for Django compatibility
# (Don't overwrite DB_PASSWORD if already set from secret file)
[ -n "$DATABASE_HOST" ] && export DB_HOST="$DATABASE_HOST"
[ -n "$DATABASE_PORT" ] && export DB_PORT="$DATABASE_PORT"
[ -n "$DATABASE_NAME" ] && export DB_NAME="$DATABASE_NAME"
[ -n "$DATABASE_USER" ] && export DB_USER="$DATABASE_USER"
[ -n "$DATABASE_PASSWORD" ] && [ -z "$DB_PASSWORD" ] && export DB_PASSWORD="$DATABASE_PASSWORD"
echo "Translated DATABASE_* variables to DB_* for Django"

# Read Redis password from secret and construct Redis URLs
if [ -f "/run/secrets/redis_password" ]; then
    REDIS_PASSWORD=$(cat /run/secrets/redis_password)
    export REDIS_URL="redis://:${REDIS_PASSWORD}@redis:6379/0"
    export CELERY_BROKER_URL="redis://:${REDIS_PASSWORD}@redis:6379/0"
    echo "Loaded Redis password from secret file and constructed REDIS_URL and CELERY_BROKER_URL"
fi

# Wait for database if needed
if [ "$WAIT_FOR_DB" = "true" ]; then
    echo "Waiting for database..."
    python manage.py wait_for_db || true
fi

# Run migrations if requested (only for Django service)
if [ "$RUN_MIGRATIONS" = "true" ] && [ "$SERVICE_TYPE" = "django" ]; then
    echo "Running database migrations..."
    python manage.py migrate --noinput
fi

# Choose service type
case "$SERVICE_TYPE" in
    django)
        if [ "$DEV_MODE" = "true" ]; then
            echo "Starting development services API server with hot reload..."
            if [ "$AUTO_RELOAD" = "true" ]; then
                exec python manage.py runserver 0.0.0.0:$PORT
            else
                exec python manage.py runserver --noreload 0.0.0.0:$PORT
            fi
        else
            echo "Starting production services API server with gunicorn..."
            # Export database credentials for Django
            export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD

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
        ;;

    celery)
        echo "Starting Celery worker..."
        if [ "$DEV_MODE" = "true" ] && [ "$AUTO_RELOAD" = "true" ]; then
            # Use watchdog for auto-reload in development
            exec env \
                DB_HOST="$DB_HOST" \
                DB_PORT="$DB_PORT" \
                DB_NAME="$DB_NAME" \
                DB_USER="$DB_USER" \
                DB_PASSWORD="$DB_PASSWORD" \
                watchmedo auto-restart \
                --directory=./ \
                --pattern='*.py' \
                --recursive \
                -- celery -A depot worker \
                -Q $CELERY_QUEUES \
                -l ${LOG_LEVEL:-info} \
                -c $CELERY_WORKERS \
                --max-tasks-per-child=100
        else
            exec env \
                DB_HOST="$DB_HOST" \
                DB_PORT="$DB_PORT" \
                DB_NAME="$DB_NAME" \
                DB_USER="$DB_USER" \
                DB_PASSWORD="$DB_PASSWORD" \
                celery -A depot worker \
                -Q $CELERY_QUEUES \
                -l ${LOG_LEVEL:-info} \
                -c $CELERY_WORKERS \
                --max-tasks-per-child=100
        fi
        ;;

    celery-beat)
        echo "Starting Celery beat scheduler..."
        export DB_HOST DB_PORT DB_NAME DB_USER DB_PASSWORD
        exec celery -A depot beat \
            -l ${LOG_LEVEL:-info} \
            --scheduler django_celery_beat.schedulers:DatabaseScheduler
        ;;

    flower)
        echo "Starting Flower monitoring..."
        exec celery -A depot flower \
            --port=${FLOWER_PORT:-5555} \
            --basic_auth=${FLOWER_USER:-admin}:${FLOWER_PASSWORD:-admin}
        ;;

    *)
        echo "Error: Unknown SERVICE_TYPE=$SERVICE_TYPE"
        echo "Valid options: django, celery, celery-beat, flower"
        exit 1
        ;;
esac