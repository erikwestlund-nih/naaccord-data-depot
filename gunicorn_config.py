# Gunicorn configuration for NA-ACCORD
# Clean logging configuration without format errors

import multiprocessing
import os

# Server socket
bind = os.getenv("GUNICORN_BIND", "0.0.0.0:8000")

# Worker processes
workers = int(os.getenv("GUNICORN_WORKERS", "4"))
worker_class = "gthread"
threads = int(os.getenv("GUNICORN_THREADS", "2"))
worker_tmp_dir = "/tmp"
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))

# Logging configuration
# Send error logs to stderr (captured by Docker)
errorlog = "-"
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info").lower()

# Disable access logging completely
# This prevents format string errors and reduces noise
accesslog = None
access_log_format = None

# Prevent worker logs from being duplicated
logconfig_dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "root": {"level": "INFO", "handlers": ["console"]},
    "loggers": {
        "gunicorn.error": {
            "level": "INFO",
            "handlers": ["console"],
            "propagate": False,
            "qualname": "gunicorn.error"
        },
        "gunicorn.access": {
            "level": "INFO",
            "handlers": [],  # Disable access logging
            "propagate": False,
            "qualname": "gunicorn.access"
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "generic",
            "stream": "ext://sys.stderr"
        }
    },
    "formatters": {
        "generic": {
            "format": "%(asctime)s [%(process)d] [%(levelname)s] %(message)s",
            "datefmt": "[%Y-%m-%d %H:%M:%S %z]",
            "class": "logging.Formatter"
        }
    }
}
