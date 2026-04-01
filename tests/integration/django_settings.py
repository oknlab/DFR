"""Minimal Django settings for integration tests."""

SECRET_KEY = "dfr-test-key"
DEBUG = True
ROOT_URLCONF = "tests.integration.urls"
ALLOWED_HOSTS = ["*"]
INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
]
MIDDLEWARE = []
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}
