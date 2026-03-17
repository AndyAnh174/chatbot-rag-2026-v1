import environ
from .base import *  # noqa: F401, F403

BASE_DIR = BASE_DIR  # noqa: F405

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env.dev")

DEBUG = True

CORS_ALLOW_ALL_ORIGINS = True

LOGGING["root"]["level"] = "DEBUG"  # noqa: F405
LOGGING["loggers"]["apps"]["level"] = "DEBUG"  # noqa: F405
