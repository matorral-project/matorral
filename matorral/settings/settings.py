import os
import sys
from datetime import timedelta
from pathlib import Path

from django.utils.translation import gettext_lazy

import environ
from celery import schedules

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
env.read_env(os.path.join(BASE_DIR, ".env"))

SECRET_KEY = env("SECRET_KEY", default="django-insecure-kwQTI8dKSWE4aUivXgxYKyKFwRl1rCKLaqZUgz4N")

DEBUG = env.bool("DEBUG", default=True)
ENABLE_DEBUG_TOOLBAR = env.bool("ENABLE_DEBUG_TOOLBAR", default=False) and "test" not in sys.argv

# Environment name: "local", "production", or any custom value (e.g. "demo", "staging").
# Controls the badge shown in the top nav: local → "local", production → "beta", other → "demo".
ENVIRONMENT = env("ENVIRONMENT", default="local")

# Wildcard is fine in dev; restrict to actual hostnames in production
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["*"])


# --- Apps ---

DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.postgres",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "django.forms",
]

THIRD_PARTY_APPS = [
    "allauth",  # allauth account/registration management
    "allauth.account",
    "allauth.socialaccount",
    # "allauth.socialaccount.providers.google",
    "allauth.socialaccount.providers.github",
    "channels",
    "django_htmx",
    "django_watchfiles",
    "django_vite",
    "celery_progress",
    "hijack",  # "login as" functionality
    "hijack.contrib.admin",  # hijack buttons in the admin
    "whitenoise.runserver_nostatic",  # whitenoise runserver
    "waffle",
    "health_check",
    "health_check.db",
    "health_check.contrib.celery",
    "health_check.contrib.redis",
    "django_celery_beat",
    "polymorphic",  # polymorphic models for issues
    "django_comments_xtd",
    "django_comments",
    "auditlog",  # audit history for models
]

PROJECT_APPS = [
    "apps.users.apps.UserConfig",
    "apps.utils.apps.UtilsConfig",
    "apps.landing_pages.apps.LandingPagesConfig",
    "apps.dashboard.apps.DashboardConfig",
    "apps.workspaces.apps.WorkspacesConfig",
    "apps.projects.apps.ProjectsConfig",
    "apps.issues.apps.IssuesConfig",
    "apps.sprints.apps.SprintsConfig",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + PROJECT_APPS

if DEBUG:
    # daphne must be first to enable ASGI/async support in dev
    INSTALLED_APPS.insert(0, "daphne")

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "matorral.middlewares.HtmxPageTitleMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "apps.workspaces.middleware.WorkspacesMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "apps.users.middleware.UserTimezoneMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "hijack.middleware.HijackUserMiddleware",
    "waffle.middleware.WaffleMiddleware",
]

if ENABLE_DEBUG_TOOLBAR:
    MIDDLEWARE.insert(0, "debug_toolbar.middleware.DebugToolbarMiddleware")
    INSTALLED_APPS.append("debug_toolbar")
    INTERNAL_IPS = ["127.0.0.1"]
    try:
        import socket

        # Discover the host gateway IP for Docker environments
        hostname, _, ips = socket.gethostbyname_ex(socket.gethostname())
        INTERNAL_IPS += [ip[: ip.rfind(".")] + ".1" for ip in ips] + [
            "192.168.65.1",
            "10.0.2.2",
        ]
    except OSError as e:
        print(f"{e} while attempting to resolve system hostname. Using INTERNAL_IPS={INTERNAL_IPS}")

if DEBUG:
    INSTALLED_APPS.append("django_browser_reload")
    MIDDLEWARE.append("django_browser_reload.middleware.BrowserReloadMiddleware")

ROOT_URLCONF = "matorral.urls"

# Template caching is off in dev (loaders swap based on DEBUG) and on in production.
_DEFAULT_LOADERS = [
    "django.template.loaders.filesystem.Loader",
    "django.template.loaders.app_directories.Loader",
]

_CACHED_LOADERS = [("django.template.loaders.cached.Loader", _DEFAULT_LOADERS)]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [
            BASE_DIR / "templates",
            BASE_DIR / "apps/users/templates",  # Must precede allauth in app_directories lookup
        ],
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "matorral.context_processors.base_context",
                "apps.workspaces.context_processors.default_workspace",
                "apps.dashboard.context_processors.onboarding_context",
            ],
            "loaders": _DEFAULT_LOADERS if DEBUG else _CACHED_LOADERS,
        },
    },
]

WSGI_APPLICATION = "matorral.wsgi.application"

FORM_RENDERER = "django.forms.renderers.TemplatesSetting"


# --- Database ---

if "DATABASE_URL" in env:
    DATABASES = {"default": env.db()}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": env("DJANGO_DATABASE_NAME", default="matorral"),
            "USER": env("DJANGO_DATABASE_USER", default="postgres"),
            "PASSWORD": env("DJANGO_DATABASE_PASSWORD", default="***"),
            "HOST": env("DJANGO_DATABASE_HOST", default="localhost"),
            "PORT": env("DJANGO_DATABASE_PORT", default="5432"),
        }
    }


# --- Auth ---

AUTH_USER_MODEL = "users.User"
LOGIN_URL = "account_login"
LOGIN_REDIRECT_URL = "/"

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

ACCOUNT_ADAPTER = "apps.workspaces.adapter.AcceptInvitationAdapter"
ACCOUNT_LOGIN_METHODS = {"email"}
ACCOUNT_SIGNUP_FIELDS = ["email*", "password1*"]

ACCOUNT_EMAIL_SUBJECT_PREFIX = ""
ACCOUNT_EMAIL_UNKNOWN_ACCOUNTS = False  # don't send "forgot password" emails to unknown accounts
ACCOUNT_CONFIRM_EMAIL_ON_GET = True
ACCOUNT_UNIQUE_EMAIL = True
# Honeypot field to block naive bot signups; tweak the ID if browsers start auto-filling it.
ACCOUNT_SIGNUP_FORM_HONEYPOT_FIELD = "phone_number_x"
ACCOUNT_SESSION_REMEMBER = True
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_LOGIN_ON_EMAIL_CONFIRMATION = True
ACCOUNT_USER_DISPLAY = lambda user: user.get_display_name()  # noqa: E731

ACCOUNT_FORMS = {
    "signup": "apps.workspaces.forms.WorkspaceSignupForm",
}
SOCIALACCOUNT_FORMS = {
    "signup": "apps.users.forms.CustomSocialSignupForm",
}
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"

# Set to "mandatory" to gate access behind email confirmation, "optional" to send but not require.
ACCOUNT_EMAIL_VERIFICATION = env("ACCOUNT_EMAIL_VERIFICATION", default="none")

# False = invitation-only signups.
ACCOUNT_ALLOW_SIGNUPS = env.bool("ACCOUNT_ALLOW_SIGNUPS", default=False)

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "allauth.account.auth_backends.AuthenticationBackend",
)

SOCIALACCOUNT_PROVIDERS = {
    "github": {
        "SCOPE": [
            "user",
        ],
    },
}


# --- Internationalization ---

LANGUAGE_CODE = "en-us"
LANGUAGE_COOKIE_NAME = "matorral_language"
LANGUAGES = [
    ("en", gettext_lazy("English")),
]
LOCALE_PATHS = (BASE_DIR / "locale",)

TIME_ZONE = "UTC"

USE_I18N = True

USE_TZ = True


# --- Static & Media Files ---

STATIC_ROOT = BASE_DIR / "static_root"
STATIC_URL = "/static/"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        # Swap to CompressedManifestStaticFilesStorage for cache-busting, but note that
        # it can break image references inside CSS/Sass files.
        # "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        "BACKEND": "whitenoise.storage.CompressedStaticFilesStorage",
    },
}

MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"

USE_S3_MEDIA = env.bool("USE_S3_MEDIA", default=False)
if USE_S3_MEDIA:
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="matorral-media")
    AWS_S3_CUSTOM_DOMAIN = f"{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com"
    PUBLIC_MEDIA_LOCATION = "media"
    MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{PUBLIC_MEDIA_LOCATION}/"
    STORAGES["default"] = {
        "BACKEND": "matorral.storage.PublicMediaStorage",
    }

DJANGO_VITE = {
    "default": {
        "dev_mode": env.bool("DJANGO_VITE_DEV_MODE", default=DEBUG),
        "manifest_path": BASE_DIR / "static" / ".vite" / "manifest.json",
    }
}

# Keeping AutoField (not BigAutoField) avoids spurious migration files from third-party packages.
DEFAULT_AUTO_FIELD = "django.db.models.AutoField"

# Suppresses URLField deprecation warning introduced in Django 4.x.
FORMS_URLFIELD_ASSUME_HTTPS = True


# --- Email ---

SERVER_EMAIL = env("SERVER_EMAIL", default="noreply@localhost:8000")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="matagus@gmail.com")

# Console backend prints emails locally; override in .env or production settings.
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")

EMAIL_SUBJECT_PREFIX = "[matorral] "


# --- Sites ---

SITE_ID = 1


# --- Pagination ---

DEFAULT_PAGE_SIZE = 14


# --- Redis / Cache / Celery ---

if "REDIS_URL" in env:
    REDIS_URL = env("REDIS_URL")
elif "REDIS_TLS_URL" in env:
    REDIS_URL = env("REDIS_TLS_URL")
else:
    REDIS_HOST = env("REDIS_HOST", default="localhost")
    REDIS_PORT = env("REDIS_PORT", default="6379")
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

if REDIS_URL.startswith("rediss"):
    REDIS_URL = f"{REDIS_URL}"

DUMMY_CACHE = {
    "BACKEND": "django.core.cache.backends.dummy.DummyCache",
}
REDIS_CACHE = {
    "BACKEND": "django.core.cache.backends.redis.RedisCache",
    "LOCATION": REDIS_URL,
}
CACHES = {
    "default": DUMMY_CACHE if DEBUG else REDIS_CACHE,
}

CELERY_BROKER_URL = CELERY_RESULT_BACKEND = REDIS_URL
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_WORKER_MAX_MEMORY_PER_CHILD = 400_000  # 400MB in kB; only effective with prefork pool

SCHEDULED_TASKS = {
    "create-next-sprints": {
        "task": "apps.sprints.tasks.create_next_sprints",
        "schedule": timedelta(minutes=60),
        "expire_seconds": 60 * 60,
    },
    "reset-demo-workspace-data": {
        "task": "apps.workspaces.tasks.reset_demo_workspace_data",
        "schedule": schedules.crontab(minute=0, hour=7),
        "expire_seconds": 60 * 60,
    },
}


# --- Channels / Daphne ---

ASGI_APPLICATION = "matorral.asgi.application"
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [REDIS_URL],
        },
    },
}


# --- Health Checks ---

HEALTH_CHECK_TOKENS = env.list("HEALTH_CHECK_TOKENS", default="")


# --- Waffle ---

WAFFLE_FLAG_MODEL = "workspaces.Flag"


SITE_DESCRIPTION = gettext_lazy("The project management tool that doesn't get in your way.")
SITE_KEYWORDS = "project management, django"

USE_HTTPS_IN_ABSOLUTE_URLS = env.bool("USE_HTTPS_IN_ABSOLUTE_URLS", default=False)

ADMINS = ["matagus@gmail.com"]

GOOGLE_ANALYTICS_ID = env("GOOGLE_ANALYTICS_ID", default="")

# --- Sentry ---

# Set SENTRY_DSN in the environment to enable error reporting.
SENTRY_DSN = env("SENTRY_DSN", default="")

if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(dsn=SENTRY_DSN, integrations=[DjangoIntegration()])

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": '[{asctime}] {levelname} "{name}" {message}',
            "style": "{",
            "datefmt": "%d/%b/%Y %H:%M:%S",  # match Django server time format
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": env("DJANGO_LOG_LEVEL", default="INFO"),
        },
        "matorral": {
            "handlers": ["console"],
            "level": env("MATORRAL_LOG_LEVEL", default="INFO"),
        },
    },
}


# --- Comments ---

COMMENTS_APP = "django_comments_xtd"
COMMENTS_XTD_CONFIRM_EMAIL = False
COMMENTS_XTD_MAX_THREAD_LEVEL = 2
COMMENTS_XTD_SALT = env("COMMENTS_XTD_SALT", default="change-me-in-production")


# --- Free Tier Limits ---

FREE_TIER_LIMITS = {
    "MAX_MEMBERS_PER_WORKSPACE": env.int("FREE_TIER_MAX_MEMBERS", default=10),
    "MAX_INVITATIONS_PER_WEEK": env.int("FREE_TIER_MAX_INVITATIONS_PER_WEEK", default=10),
    "MAX_WORK_ITEMS_PER_WORKSPACE": env.int("FREE_TIER_MAX_WORK_ITEMS", default=1000),
}
