"""
Django settings for matorral project.

For more information on this file, see
https://docs.djangoproject.com/en/dev/topics/settings/

For the full list of settings and their values, see
https://docs.djangoproject.com/en/dev/ref/settings/
"""

import re
import sys

import environ

from celery.schedules import crontab

ROOT_DIR = environ.Path(__file__) - 2  # (matorral/config/settings/common.py - 2 = matorral/)
APPS_DIR = ROOT_DIR.path("matorral")

env = environ.Env()
environ.Env.read_env(env_file="config/.env")  # reading .env file

ENVIRONMENT = env("ENVIRONMENT", default="production")

# SECRET CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#secret-key
# Raises ImproperlyConfigured exception if DJANGO_SECRET_KEY not in os.environ
SECRET_KEY = env("DJANGO_SECRET_KEY")

# SITE CONFIGURATION
# ------------------------------------------------------------------------------
# Hosts/domain names that are valid for this site
# See https://docs.djangoproject.com/en/1.6/ref/settings/#allowed-hosts
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
# END SITE CONFIGURATION

# APP CONFIGURATION
# ------------------------------------------------------------------------------
DJANGO_APPS = (
    # Default Django apps:
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.sites",
    "django.contrib.messages",
    "whitenoise.runserver_nostatic",
    "django.contrib.staticfiles",
    "django.forms",
    # Admin
    "django.contrib.admin",
    "django_admin_listfilter_dropdown",
)

THIRD_PARTY_APPS = (
    "django_extensions",
    "watchman",
    "simple_history",
    "tagulous",
)

# Apps specific for this project go here.
LOCAL_APPS = (
    "matorral.users",  # custom users app
    # Your stuff: custom apps go here
    "matorral.workspaces",
    "matorral.sprints",
    "matorral.stories",
)

# See: https://docs.djangoproject.com/en/dev/ref/settings/#installed-apps
INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# MIDDLEWARE CONFIGURATION
# ------------------------------------------------------------------------------
MIDDLEWARE = (
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "matorral.workspaces.middlewares.WorkspaceMiddleware",
)

# MIGRATIONS CONFIGURATION
# ------------------------------------------------------------------------------
MIGRATION_MODULES = {"sites": "matorral.contrib.sites.migrations"}

# DEBUG
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#debug
DEBUG = env.bool("DJANGO_DEBUG", False)

# FIXTURE CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-FIXTURE_DIRS
FIXTURE_DIRS = (str(APPS_DIR.path("fixtures")),)

# EMAIL CONFIGURATION
# ------------------------------------------------------------------------------
EMAIL_BACKEND = env("DJANGO_EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
DEFAULT_FROM_EMAIL = env("DJANGO_DEFAULT_FROM_EMAIL", default="matorral <noreply@localhost>")
EMAIL_SUBJECT_PREFIX = env("DJANGO_EMAIL_SUBJECT_PREFIX", default="[matorral] ")
SERVER_EMAIL = env("DJANGO_SERVER_EMAIL", default=DEFAULT_FROM_EMAIL)

# MANAGER CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#admins
ADMINS = (("matagus@gmail.com", ""),)

# See: https://docs.djangoproject.com/en/dev/ref/settings/#managers
MANAGERS = ADMINS

# DATABASE CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#databases
DATABASES = {
    "default": env.db("DJANGO_DATABASE_URL", default="sqlite:///matorral.db"),
}
DATABASES["default"]["ATOMIC_REQUESTS"] = True


# GENERAL CONFIGURATION
# ------------------------------------------------------------------------------
# Local time zone for this installation. Choices can be found here:
# http://en.wikipedia.org/wiki/List_of_tz_zones_by_name
# although not all choices may be available on all operating systems.
# In a Windows environment this must be set to your system time zone.
TIME_ZONE = "UTC"

# See: https://docs.djangoproject.com/en/dev/ref/settings/#language-code
LANGUAGE_CODE = "en-us"

# See: https://docs.djangoproject.com/en/dev/ref/settings/#site-id
SITE_ID = 1

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-i18n
USE_I18N = True

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-l10n

# See: https://docs.djangoproject.com/en/dev/ref/settings/#use-tz
USE_TZ = True

# TEMPLATE CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#templates
TEMPLATES = [
    {
        # See: https://docs.djangoproject.com/en/dev/ref/settings/#std:setting-TEMPLATES-BACKEND
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        # See: https://docs.djangoproject.com/en/dev/ref/settings/#template-dirs
        "DIRS": [
            str(APPS_DIR.path("templates")),
        ],
        "OPTIONS": {
            # See: https://docs.djangoproject.com/en/dev/ref/settings/#template-debug
            "debug": DEBUG,
            # See: https://docs.djangoproject.com/en/dev/ref/settings/#template-loaders
            # https://docs.djangoproject.com/en/dev/ref/templates/api/#loader-types
            "loaders": [
                "django.template.loaders.filesystem.Loader",
                "django.template.loaders.app_directories.Loader",
            ],
            # See: https://docs.djangoproject.com/en/dev/ref/settings/#template-context-processors
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.template.context_processors.i18n",
                "django.template.context_processors.media",
                "django.template.context_processors.static",
                "django.template.context_processors.tz",
                "django.contrib.messages.context_processors.messages",
                # Your stuff: custom template context processors go here
                "matorral.context_processors.site",
                "matorral.context_processors.navigation",
                "matorral.context_processors.search",
            ],
        },
    },
]

# STATIC FILE CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-root
STATIC_ROOT = str(ROOT_DIR("staticfiles"))

# See: https://docs.djangoproject.com/en/dev/ref/settings/#static-url
STATIC_URL = "/static/"

# See: https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#std:setting-STATICFILES_DIRS
STATICFILES_DIRS = (str(APPS_DIR.path("static")),)

# See: https://docs.djangoproject.com/en/dev/ref/contrib/staticfiles/#staticfiles-finders
STATICFILES_FINDERS = (
    "django.contrib.staticfiles.finders.FileSystemFinder",
    "django.contrib.staticfiles.finders.AppDirectoriesFinder",
)

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# MEDIA CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-root
MEDIA_ROOT = str(APPS_DIR("media"))

# See: https://docs.djangoproject.com/en/dev/ref/settings/#media-url
MEDIA_URL = "/media/"

# URL Configuration
# ------------------------------------------------------------------------------
ROOT_URLCONF = "config.urls"

# See: https://docs.djangoproject.com/en/dev/ref/settings/#wsgi-application
WSGI_APPLICATION = "config.wsgi.application"

# AUTHENTICATION CONFIGURATION
# ------------------------------------------------------------------------------
AUTHENTICATION_BACKENDS = ("django.contrib.auth.backends.ModelBackend",)

DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# cookies
LANGUAGE_COOKIE_NAME = "matorral-lang"
CSRF_COOKIE_NAME = "matorral-csrf"
SESSION_COOKIE_NAME = "matorral-session"

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"

# Some really nice defaults
ACCOUNT_AUTHENTICATION_METHOD = "username"
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_EMAIL_VERIFICATION = "mandatory"

ACCOUNT_ALLOW_REGISTRATION = env.bool("DJANGO_ACCOUNT_ALLOW_REGISTRATION", True)
ACCOUNT_ADAPTER = "matorral.users.adapters.AccountAdapter"
SOCIALACCOUNT_ADAPTER = "matorral.users.adapters.SocialAccountAdapter"

# Custom user app defaults
# Select the correct user model
AUTH_USER_MODEL = "users.User"
LOGIN_REDIRECT_URL = "/"
LOGIN_URL = "login"

# SLUGLIFIER
AUTOSLUG_SLUGIFY_FUNCTION = "slugify.slugify"

# CELERY
INSTALLED_APPS += ("matorral.taskapp.celery.CeleryConfig",)
BROKER_URL = env("CELERY_BROKER_URL", default="amqp://")
CELERY_TIMEZONE = "UTC"
CELERY_ACCEPT_CONTENT = ["msgpack"]
CELERY_TASK_SERIALIZER = "msgpack"
CELERY_RESULT_SERIALIZER = "msgpack"

CELERY_QUEUES = {
    "celery": {"exchange": "celery", "binding_key": "celery"},
}

CELERY_ROUTES = {}
# END CELERY


# Location of root django.contrib.admin URL, use {% url 'admin:index' %}
ADMIN_URL = re.sub("^/", "^", env("DJANGO_ADMIN_URL", default="^admin/"))

USER_AGENT = env("USER_AGENT", default="matorral/0.1.0")

WATCHMAN_CHECKS = (
    "watchman.checks.caches",
    "watchman.checks.databases",
    # we don't need to check media since its a webservice
)

# LOGGING CONFIGURATION
# ------------------------------------------------------------------------------
# See: https://docs.djangoproject.com/en/dev/ref/settings/#logging
# A sample logging configuration. The only tangible logging
# performed by this configuration is to send an email to
# the site admins on every HTTP 500 error when DEBUG=False.
# See http://docs.djangoproject.com/en/dev/topics/logging for
# more details on how to customize your logging configuration.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {"require_debug_false": {"()": "django.utils.log.RequireDebugFalse"}},
    "formatters": {
        "verbose": {"format": "%(levelname)s [%(asctime)s] %(name)s %(message)s"},
    },
    "handlers": {
        "console": {
            "level": "DEBUG",
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": True},
        "django.security.DisallowedHost": {"level": "ERROR", "handlers": ["console"], "propagate": True},
        "matorral": {
            "handlers": ["console"],
            "level": env("LOGGING_LOGGER_LEVEL", default="ERROR"),
            "formatter": "verbose",
            "propagate": True,
        },
    },
}

# Sentry related config vars
SENTRY_ENABLED = env.bool("SENTRY_ENABLED", default=False)
SENTRY_DSN = env("SENTRY_DSN", default="")

if SENTRY_ENABLED:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        environment=f"{ENVIRONMENT}",
        dsn=f"{SENTRY_DSN}",
        integrations=[DjangoIntegration(), CeleryIntegration()],
    )

# Your common stuff: Below this line define 3rd party library settings

COMMENTS_APP = "django_comments_xtd"
COMMENTS_XTD_MAX_THREAD_LEVEL = 2

# Other Celery settings
CELERY_ALWAYS_EAGER = env.bool("CELERY_ALWAYS_EAGER", default=False)

CELERYBEAT_SCHEDULE = {
    "sprints-update-state": {"task": "matorral.sprints.tasks.update_state", "schedule": crontab(hour="*/1")},
}

# Tagulous settings
SERIALIZATION_MODULES = {
    "xml": "tagulous.serializers.xml_serializer",
    "json": "tagulous.serializers.json",
    "python": "tagulous.serializers.python",
    "yaml": "tagulous.serializers.pyyaml",
}

# TESTING
# ------------------------------------------------------------------------------
TEST_RUNNER = "django.test.runner.DiscoverRunner"

if ENVIRONMENT == "production":
    INSTALLED_APPS += ("gunicorn",)

    # This ensures that Django will be able to detect a secure connection
    # properly on Heroku.
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # set this to 60 seconds and then to 518400 when you can prove it works
    SECURE_HSTS_SECONDS = 60
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
    SECURE_CONTENT_TYPE_NOSNIFF = env.bool("DJANGO_SECURE_CONTENT_TYPE_NOSNIFF", default=True)
    SECURE_BROWSER_XSS_FILTER = True
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_HTTPONLY = True
    SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=False)

else:
    # django-debug-toolbar
    # ------------------------------------------------------------------------------
    MIDDLEWARE += ("debug_toolbar.middleware.DebugToolbarMiddleware",)
    INSTALLED_APPS += ("debug_toolbar",)

    INTERNAL_IPS = ("127.0.0.1",)

    DEBUG_TOOLBAR_CONFIG = {
        "DISABLE_PANELS": [
            "debug_toolbar.panels.redirects.RedirectsPanel",
        ],
        "SHOW_TEMPLATE_CONTEXT": True,
    }

# if we are running tests, we want to use a fast hasher
if sys.argv[1:2] == ["test"]:
    PASSWORD_HASHERS = ("django.contrib.auth.hashers.MD5PasswordHasher",)
