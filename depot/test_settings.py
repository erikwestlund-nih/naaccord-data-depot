"""
Test settings for NA-ACCORD
Uses SQLite for testing to avoid MySQL permission issues
"""
from depot.settings import *

# Override database to use SQLite for tests
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # Use in-memory database for speed
    }
}

# Disable Celery during tests
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Simplify password hashers for faster tests
PASSWORD_HASHERS = [
    'django.contrib.auth.hashers.MD5PasswordHasher',
]

# Disable migrations for faster test setup
class DisableMigrations:
    def __contains__(self, item):
        return True
    
    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()

# Disable debug toolbar for tests
DEBUG = False
DEBUG_TOOLBAR_CONFIG = {
    'IS_RUNNING_TESTS': False
}
INTERNAL_IPS = []

# Remove debug toolbar from installed apps
INSTALLED_APPS = [app for app in INSTALLED_APPS if app != 'debug_toolbar']
MIDDLEWARE = [m for m in MIDDLEWARE if 'debug_toolbar' not in m]

# Override authentication backends for testing
# Remove Axes backend which requires request parameter that test client.login() doesn't provide
AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",  # Standard Django backend for tests
]

# Disable Axes middleware for tests
MIDDLEWARE = [m for m in MIDDLEWARE if 'axes' not in m.lower()]