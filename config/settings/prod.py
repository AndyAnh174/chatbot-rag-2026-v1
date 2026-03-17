import environ
from .base import *  # noqa: F401, F403

BASE_DIR = BASE_DIR  # noqa: F405

_env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env.prod")

DEBUG = False

CORS_ALLOWED_ORIGINS = _env.list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True

# ── Security headers ──────────────────────────────────────────────────────
SECURE_HSTS_SECONDS = _env.int("SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_SSL_REDIRECT = _env.bool("SECURE_SSL_REDIRECT", default=False)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
SECURE_CONTENT_TYPE_NOSNIFF = True
