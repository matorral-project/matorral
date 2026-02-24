# flake8: noqa: F405
from .settings import *  # noqa F401

# Override DEBUG via the environment variable rather than editing this file.
DEBUG = False

# Required when running behind a reverse proxy that terminates SSL.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# HSTS — uncomment once you're confident SSL is stable.
# Ramp SECURE_HSTS_SECONDS up gradually (60 → 3600 → 86400 → 31536000).
# Only enable subdomains/preload if every subdomain also runs HTTPS.
# SECURE_HSTS_SECONDS = 60
# SECURE_HSTS_INCLUDE_SUBDOMAINS = True
# SECURE_HSTS_PRELOAD = True

USE_HTTPS_IN_ABSOLUTE_URLS = True

# Override in the environment or uncomment below to lock down allowed hosts.
# ALLOWED_HOSTS = ["example.com"]

# Mailgun via django-anymail. Set MAILGUN_API_KEY and MAILGUN_SENDER_DOMAIN in the environment.
EMAIL_BACKEND = "anymail.backends.mailgun.EmailBackend"

ANYMAIL = {
    "MAILGUN_API_KEY": env("MAILGUN_API_KEY", default=None),
    "MAILGUN_SENDER_DOMAIN": env("MAILGUN_SENDER_DOMAIN", default=None),
}

ADMINS = ["matagus@gmail.com"]
