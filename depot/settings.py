import os
import sys
from pathlib import Path
import environ
import yaml

# Initialize environment variables
env = environ.Env()

# Reading .env file
environ.Env.read_env(".env")

# Helper function to read Docker secrets from files
def read_secret(env_var_name, file_env_var_name, default=""):
    """Read secret from file if *_FILE env var exists, otherwise from env var."""
    secret_file = os.environ.get(file_env_var_name)
    if secret_file and os.path.exists(secret_file):
        with open(secret_file, 'r') as f:
            return f.read().strip()
    return env(env_var_name, default=default)

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
STORAGE_DIR = BASE_DIR / "resources" / "storage"
UPLOADS_DIR = STORAGE_DIR / "uploads"
AUDIT_UPLOADS_DIR = UPLOADS_DIR / "audit"
CONFIG_DIR = BASE_DIR / "depot" / "config"

# Load application configuration
def load_app_config():
    config_path = CONFIG_DIR / "application.yml"
    if not config_path.exists():
        return {}
    
    with open(config_path) as f:
        return yaml.safe_load(f)

APP_CONFIG = load_app_config()

# Quarto settings
QUARTO_CONFIG = {
    'binary_path': env('QUARTO_BINARY_PATH', default='/usr/local/bin/quarto'),
}

# DuckDB settings
# Parallel CSV reading causes hangs even on Linux - disable by default
naaccord_env = env('NAACCORD_ENVIRONMENT', default='development')
DUCKDB_PARALLEL_CSV = env.bool('DUCKDB_PARALLEL_CSV', default=False)

# Storage settings
# Determine server role from environment
SERVER_ROLE = os.environ.get('SERVER_ROLE', 'services')

# Read internal API key from secret file if available
INTERNAL_API_KEY = read_secret('INTERNAL_API_KEY', 'INTERNAL_API_KEY_FILE', default='')

# Configure storage based on server role
if SERVER_ROLE == 'web':
    # Web server uses remote storage driver to stream from services server
    STORAGE_CONFIG = {
        'disks': {
            'local': {
                'driver': 'remote',
                'type': 'remote',
                'service_url': os.environ.get('SERVICES_URL', 'http://localhost:8001'),
                'api_key': INTERNAL_API_KEY,
            },
            'data': {
                'driver': 'remote',
                'type': 'remote',
                'service_url': os.environ.get('SERVICES_URL', 'http://localhost:8001'),
                'api_key': INTERNAL_API_KEY,
            },
            'downloads': {
                'driver': 'remote',
                'type': 'remote',
                'service_url': os.environ.get('SERVICES_URL', 'http://localhost:8001'),
                'api_key': INTERNAL_API_KEY,
            },
            'uploads': {
                'driver': 'remote',
                'type': 'remote',
                'service_url': os.environ.get('SERVICES_URL', 'http://localhost:8001'),
                'api_key': INTERNAL_API_KEY,
            },
            'attachments': {
                'driver': 'remote',
                'type': 'remote',
                'service_url': os.environ.get('SERVICES_URL', 'http://localhost:8001'),
                'api_key': INTERNAL_API_KEY,
            },
            'scratch': {
                'driver': 'remote',
                'type': 'remote',
                'service_url': os.environ.get('SERVICES_URL', 'http://localhost:8001'),
                'api_key': INTERNAL_API_KEY,
            },
            'workspace': {
                'driver': 'remote',
                'type': 'remote',
                'service_url': os.environ.get('SERVICES_URL', 'http://localhost:8001'),
                'api_key': INTERNAL_API_KEY,
            },
            'reports': {
                'driver': 'remote',
                'type': 'remote',
                'service_url': os.environ.get('SERVICES_URL', 'http://localhost:8001'),
                'api_key': INTERNAL_API_KEY,
            },
        }
    }
else:
    # Services server uses local storage
    STORAGE_CONFIG = {
        'disks': {
            'local': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'nas'),
            },
            'data': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'data'),
            },
            'downloads': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'downloads'),
            },
            'uploads': {
                'driver': 'local',
                'type': 'local',
                'root': os.environ.get('NAS_UPLOADS_PATH', '/mnt/nas/uploads'),
            },
            'attachments': {
                'driver': 'local',
                'type': 'local',
                'root': os.environ.get('NAS_UPLOADS_PATH', '/mnt/nas/uploads'),  # Keep with uploads
            },
            'scratch': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'scratch'),
            },
            'workspace': {
                'driver': 'local',
                'type': 'local',
                'root': os.environ.get('NAS_WORKSPACE_PATH', str(BASE_DIR / 'storage' / 'nas' / 'workspace')),
            },
            'reports': {
                'driver': 'local',
                'type': 'local',
                'root': os.environ.get('NAS_REPORTS_PATH', '/mnt/nas/reports'),
            },
        }
    }

# Default storage disk for submissions
DEFAULT_STORAGE_DISK = 'local'
SUBMISSION_STORAGE_DISK = 'uploads'
WORKSPACE_STORAGE_DISK = 'workspace'

# NAS storage configuration
NAS_MOUNT_PATH = env('NAS_SUBMISSIONS_PATH', default='/mnt/nas/submissions')

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = read_secret("SECRET_KEY", "SECRET_KEY_FILE", default="unsafe-secret-key")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool("DEBUG", default=False)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# CSRF Configuration - Django 4.0+ requires explicit trusted origins
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

INTERNAL_IPS = env.list("INTERNAL_IPS", default=["localhost"])

TESTING = "test" in sys.argv


# Application definition
INSTALLED_APPS = [
    "depot",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_components",
    "django_cotton",
    "django_celery_results",
]

# Add Axes only when not testing
if not TESTING:
    INSTALLED_APPS.append("axes")  # Django-axes for rate limiting

# Celery beat only needed on services server (not web server)
if SERVER_ROLE == 'services':
    INSTALLED_APPS.append("django_celery_beat")

# User model
AUTH_USER_MODEL = "depot.User"

# Celery
CELERY_BROKER_URL = env('CELERY_BROKER_URL', default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = "django-db"

# Debug logging for broker configuration
import logging
logging.info(f"CELERY_BROKER_URL configured as: {CELERY_BROKER_URL}")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "depot.middleware.log_sanitizer.LogSanitizerMiddleware",  # HIPAA: Sanitize PII/PHI from logs
    "depot.middleware.session_activity.RequestTimingMiddleware",  # Request timing for audit
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
]

# Add Axes middleware only when not testing
if not TESTING:
    MIDDLEWARE.append("axes.middleware.AxesMiddleware")  # Rate limiting for failed login attempts

MIDDLEWARE.extend([
    "depot.middleware.session_activity.SessionActivityMiddleware",  # Session timeout & activity logging
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "depot.middleware.signed_in.SignedInMiddleware",
])

# Security Note: Development bypass removed for production readiness
# All access control checks are now enforced

# Session timeout configuration (Johns Hopkins requirement)
SESSION_TIMEOUT_SECONDS = env.int("SESSION_TIMEOUT_SECONDS", default=3600)  # 1 hour default
SESSION_TIMEOUT_EXCLUDED_PATHS = [
    '/sign-in',
    '/saml2/',
    '/admin/',
    '/static/',
    '/media/',
]

# Session cookie settings to prevent premature logout
SESSION_COOKIE_AGE = 3600  # 1 hour in seconds
SESSION_SAVE_EVERY_REQUEST = True  # Save session on every request to update expiry
SESSION_EXPIRE_AT_BROWSER_CLOSE = False  # Keep session after browser close (use timeout instead)
SESSION_COOKIE_HTTPONLY = True  # Security: prevent JavaScript access
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)  # HTTPS only in production

# Authentication backends
USE_DOCKER_SAML = env.bool('USE_DOCKER_SAML', default=False)
USE_MOCK_SAML = env.bool('USE_MOCK_SAML', default=DEBUG and not USE_DOCKER_SAML)
DISABLE_SAML = env.bool('DISABLE_SAML', default=False)  # Bypass SAML entirely (for staging)

if TESTING or DISABLE_SAML:
    # During tests or when SAML disabled, use standard Django auth only
    AUTHENTICATION_BACKENDS = [
        "django.contrib.auth.backends.ModelBackend",  # Standard Django auth
    ]
elif USE_DOCKER_SAML:
    # Real SAML with Docker SimpleSAMLphp IdP
    AUTHENTICATION_BACKENDS = [
        "axes.backends.AxesStandaloneBackend",  # Rate limiting backend
        "djangosaml2.backends.Saml2Backend",  # djangosaml2 backend (required for SAML)
        "depot.auth.saml_backend.SAMLBackend",  # Custom SAML backend (no auto-create)
        "django.contrib.auth.backends.ModelBackend",  # Fallback for superusers
    ]
elif USE_MOCK_SAML:
    # Mock SAML for simple development
    AUTHENTICATION_BACKENDS = [
        "axes.backends.AxesStandaloneBackend",  # Rate limiting backend
        "depot.auth.mock_backend.MockSAMLBackend",  # Mock SAML backend
        "django.contrib.auth.backends.ModelBackend",  # Fallback for superusers
    ]
else:
    # Production with real Shibboleth
    AUTHENTICATION_BACKENDS = [
        "axes.backends.AxesStandaloneBackend",  # Rate limiting backend
        "depot.auth.saml_backend.SAMLBackend",  # Custom SAML backend (no auto-create)
        "django.contrib.auth.backends.ModelBackend",  # Fallback for superusers
    ]

# Add djangosaml2 when using Docker SAML or production (but not mock SAML)
if USE_DOCKER_SAML or (not DEBUG and not USE_MOCK_SAML):
    INSTALLED_APPS.append("djangosaml2")
    # Add SAML middleware after AuthenticationMiddleware
    MIDDLEWARE.insert(
        MIDDLEWARE.index("django.contrib.auth.middleware.AuthenticationMiddleware") + 1,
        "djangosaml2.middleware.SamlSessionMiddleware",
    )


# Debug toolbar removed - not needed

ROOT_URLCONF = "depot.urls"

APPEND_SLASH = False

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "depot/data/templates",
            BASE_DIR / "templates",
        ],
        "APP_DIRS": False,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "depot.context_processors.vite_asset_processor",
                "depot.context_processors.debug",
                "depot.context_processors.add_url_name",
                "depot.context_processors.user_cohorts",
                "depot.context_processors.user_submissions",
            ],
            "builtins": [
                "django_components.templatetags.component_tags",
            ],
            "loaders": [
                (
                    "django.template.loaders.cached.Loader",
                    [
                        "django.template.loaders.filesystem.Loader",
                        "django.template.loaders.app_directories.Loader",
                        "django_components.template_loader.Loader",
                    ],
                )
            ],
        },
    },
]

COMPONENTS = {
    "dirs": [
        os.path.join(BASE_DIR, "depot/components"),
    ],
}

COTTON_DIR = "components"

WSGI_APPLICATION = "depot.wsgi.application"

# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

DATABASES = {
    "default": {
        "NAME": env("DB_NAME", default="naaccord"),
        "ENGINE": env("DB_ENGINE", default="django.db.backends.mysql"),
        "HOST": env("DB_HOST", default="127.0.0.1"),
        "PORT": env("DB_PORT", default="3306"),
        "USER": env("DB_USER", default="root"),
        "PASSWORD": read_secret("DB_PASSWORD", "DATABASE_PASSWORD_FILE", default=""),
        "OPTIONS": {
            "isolation_level": "READ COMMITTED",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
        "CONN_MAX_AGE": 0,  # Close connections after each request to prevent connection exhaustion
        "CONN_HEALTH_CHECKS": True,  # Check connection health before use to prevent "Server has gone away" errors
    }
}

# Use SQLite for testing to avoid database permission issues
if TESTING:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": ":memory:",
            "CONN_MAX_AGE": 0,  # Don't persist connections during tests to prevent leaks
        }
    }
    # Use custom test runner for better cleanup
    TEST_RUNNER = 'depot.tests.runner.CleanupTestRunner'

    # Override storage paths for testing - use local paths instead of /mnt/nas
    STORAGE_CONFIG = {
        'disks': {
            'local': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'test' / 'nas'),
            },
            'data': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'test' / 'data'),
            },
            'downloads': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'test' / 'downloads'),
            },
            'uploads': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'test' / 'uploads'),
            },
            'attachments': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'test' / 'attachments'),
            },
            'scratch': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'test' / 'scratch'),
            },
            'workspace': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'test' / 'workspace'),
            },
            'reports': {
                'driver': 'local',
                'type': 'local',
                'root': str(BASE_DIR / 'storage' / 'test' / 'reports'),
            },
        }
    }

# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = "en-us"

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True

# File Upload Configuration
# Optimized for large clinical data files
FILE_UPLOAD_MAX_MEMORY_SIZE = 2.5 * 1024 * 1024  # 2.5MB - files larger go to temp disk
DATA_UPLOAD_MAX_MEMORY_SIZE = 3 * 1024 * 1024 * 1024  # 3GB max POST body
FILE_UPLOAD_TEMP_DIR = env('FILE_UPLOAD_TEMP_DIR', default='/tmp')  # Temp directory for uploads

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "static/"
STATIC_ROOT = env('STATIC_ROOT', default=str(BASE_DIR / 'staticfiles'))
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STATICFILES_FINDERS = [
    # Default finders
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
    # Django components
    "django_components.finders.ComponentsFileSystemFinder",
]

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

DJANGO_SONAR = {
    "excludes": [
        STATIC_URL,
        "/sonar/",
        "/admin/",
        "/__reload__/",
    ],
}

# MinIO configuration removed - no longer used


# ==========================================
# SAML Configuration for djangosaml2
# ==========================================

if not DISABLE_SAML and (USE_DOCKER_SAML or (not DEBUG and not USE_MOCK_SAML)):
    try:
        import saml2
        from saml2.sigver import get_xmlsec_binary
        from saml2 import saml
        SAML_AVAILABLE = True
    except ImportError:
        SAML_AVAILABLE = False
        get_xmlsec_binary = None

    if SAML_AVAILABLE:
        # SAML Configuration
        SAML_CONFIG = {
            # Full path to the xmlsec1 binary program
            'xmlsec_binary': get_xmlsec_binary(['/opt/homebrew/bin/xmlsec1', '/usr/bin/xmlsec1']) if not USE_MOCK_SAML else None,
        
        # Required config for djangosaml2
        'entityid': env('SAML_ENTITY_ID', default='http://localhost:8000'),
        
        # Directory for SAML certificates and keys (test certs for development)
        'key_file': env('SAML_KEY_FILE', default=str(BASE_DIR / 'saml' / 'certs_test' / 'sp.key')),
        'cert_file': env('SAML_CERT_FILE', default=str(BASE_DIR / 'saml' / 'certs_test' / 'sp.crt')),
        
        # Service provider configuration
        'service': {
            'sp': {
                'name': 'NA-ACCORD Data Depot',
                'name_id_format': saml2.saml.NAMEID_FORMAT_EMAILADDRESS,
                'endpoints': {
                    'assertion_consumer_service': [
                        (env('SAML_ACS_URL', default='http://localhost:8000/saml2/acs/'), saml2.BINDING_HTTP_POST),
                    ],
                    'single_logout_service': [
                        (env('SAML_SLS_URL', default='http://localhost:8000/saml2/ls/'), saml2.BINDING_HTTP_REDIRECT),
                    ],
                },
                'allow_unsolicited': True,
                'authn_requests_signed': False,
                'logout_requests_signed': True,
                'want_assertions_signed': True,
                'want_response_signed': False,
            },
        },
        
        }

        # Identity providers metadata
        # Use local file if it exists (staging), otherwise remote URL (production)
        saml_idp_metadata_file = env('SAML_IDP_METADATA_FILE', default='')
        saml_idp_metadata_url = env('SAML_IDP_METADATA_URL', default='')

        if saml_idp_metadata_file and os.path.exists(saml_idp_metadata_file):
            # Staging: Use local metadata file (avoids all redirect/network issues)
            SAML_CONFIG['metadata'] = {'local': [saml_idp_metadata_file]}
        elif saml_idp_metadata_url:
            # Production: Fetch from JHU Shibboleth URL
            SAML_CONFIG['metadata'] = {'remote': [{'url': saml_idp_metadata_url}]}
        else:
            # Fallback: metadata not configured properly
            import logging
            logging.warning(f"SAML metadata not configured: file={saml_idp_metadata_file} (exists={os.path.exists(saml_idp_metadata_file) if saml_idp_metadata_file else False}), url={saml_idp_metadata_url}")

        SAML_CONFIG.update({

        # Allow unknown attributes to be processed
        'allow_unknown_attributes': True,
        
        # Debug mode for SAML (only in development)
        'debug': DEBUG,
        
        # Optional: custom attribute requirements
        'required_attributes': [
            'email',
            'eduPersonPrincipalName',
        ],
        
        # Optional: attribute mapping
        'optional_attributes': [
            'displayName',
            'givenName',
            'sn',
            'eduPersonAffiliation',
            'cohortAccess',
            'naaccordRole',
            'organization',
        ],
        })

        # SAML session timeout (in seconds)
        SAML_DJANGO_USER_MAIN_ATTRIBUTE = 'email'
        SAML_DJANGO_USER_MAIN_ATTRIBUTE_LOOKUP = '__iexact'
        SAML_SESSION_TIMEOUT = env.int('SAML_SESSION_TIMEOUT', default=3600)  # 1 hour

        # SAML attribute mapping - maps SAML attributes to Django user model fields
        SAML_ATTRIBUTE_MAPPING = {
            'uid': ('username',),
            'email': ('email',),
            'givenName': ('first_name',),
            'sn': ('last_name',),
            'eduPersonPrincipalName': ('email',),  # Fallback for email
        }

        # SAML settings for djangosaml2
        SAML_IGNORE_AUTHENTICATED_USERS_ON_LOGIN = True
        SAML_USE_NAME_ID_AS_USERNAME = False
        SAML_CREATE_UNKNOWN_USER = False
        SAML_CSP_HANDLER = ''  # Disable CSP warning for development

        # Login/logout URLs for SAML
        LOGIN_URL = '/saml2/login/'
        LOGIN_REDIRECT_URL = '/'
        LOGOUT_URL = '/saml2/logout/'
        LOGOUT_REDIRECT_URL = '/auth/sign-in/'
    else:
        SAML_CONFIG = {}

        # Fallback to local auth if SAML not available
        LOGIN_URL = '/sign-in'
        LOGIN_REDIRECT_URL = '/'
elif USE_MOCK_SAML:
    # Mock SAML configuration - minimal setup for USE_MOCK_SAML=True
    SAML_CONFIG = {}  # Empty config for mock mode

    # Login/logout URLs
    LOGIN_URL = '/saml2/login/'
    LOGIN_REDIRECT_URL = '/'
    LOGOUT_URL = '/saml2/logout/'
    LOGOUT_REDIRECT_URL = '/auth/sign-in/'
else:
    # SAML completely disabled - use Django auth
    SAML_CONFIG = {}
    LOGIN_URL = '/sign-in'
    LOGIN_REDIRECT_URL = '/'


# ==========================================
# LOGGING CONFIGURATION
# ==========================================

# Test environment detection
TESTING = len(sys.argv) > 1 and sys.argv[1] == 'test' or os.environ.get('TESTING', 'False').lower() == 'true'

# Comprehensive logging configuration
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
        'simple': {
            'format': '{levelname} {message}',
            'style': '{',
        },
        'test': {
            'format': '{message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'simple' if TESTING else 'verbose',
        },
        'null': {
            'class': 'logging.NullHandler',
        },
    },
    'root': {
        'handlers': ['null' if TESTING else 'console'],
        'level': 'CRITICAL' if TESTING else 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['null' if TESTING else 'console'],
            'level': 'CRITICAL' if TESTING else 'INFO',
            'propagate': False,
        },
        'django.db.backends': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'django.db.backends.schema': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'django.request': {
            'handlers': ['null' if TESTING else 'console'],
            'level': 'CRITICAL' if TESTING else 'ERROR',
            'propagate': False,
        },
        'django.security': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'django.contrib.staticfiles': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'depot': {
            'handlers': ['null' if TESTING else 'console'],
            'level': 'CRITICAL' if TESTING else 'INFO',
            'propagate': False,
        },
        'depot.views': {
            'handlers': ['null' if TESTING else 'console'],
            'level': 'CRITICAL' if TESTING else 'WARNING',
            'propagate': False,
        },
        'depot.middleware': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'depot.audit.observers': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'celery': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'urllib3': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'requests': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'boto3': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'botocore': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
        'paramiko': {
            'handlers': ['null'],
            'level': 'CRITICAL',
            'propagate': False,
        },
    }
}

# Feature flags for gradual rollout of new features
FEATURE_FLAGS = {
    'SECURE_ATTACHMENT_UPLOAD': os.environ.get('ENABLE_SECURE_ATTACHMENTS', 'false').lower() == 'true',
}

# Django-axes configuration for rate limiting
AXES_FAILURE_LIMIT = 5  # Block after 5 failed attempts
AXES_COOLOFF_TIME = 1  # 1 hour cooloff period
# AXES_LOCKOUT_CALLABLE = 'axes.lockout.database_lockout'  # Use database lockout - deprecated in newer versions
AXES_RESET_ON_SUCCESS = True  # Reset count on successful login
AXES_LOCKOUT_TEMPLATE = 'errors/rate_limited.html'  # Custom template for lockout
AXES_CLIENT_IP_CALLABLE = 'depot.security.axes.get_client_ip'
AXES_META_PRECEDENCE_ORDER = [
    'HTTP_CF_CONNECTING_IP',
    'HTTP_X_REAL_IP',
    'HTTP_X_FORWARDED_FOR',
    'REMOTE_ADDR',
]

# Additional test environment settings
if TESTING:
    # Suppress warnings during tests
    import warnings
    warnings.filterwarnings('ignore')

    # Don't set TEST_ACTIVITY_LOGGING globally - let individual tests control it
    # TEST_ACTIVITY_LOGGING will be set by ActivityTestCase when needed

    # Disable database migration output
    MIGRATION_MODULES = {
        'depot': None,
        'auth': None,
        'contenttypes': None,
        'sessions': None,
        'admin': None,
        'messages': None,
        'staticfiles': None,
        'axes': None,  # Skip axes migrations in tests
    }
