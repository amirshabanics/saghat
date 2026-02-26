from saghat.settings.base import *  # noqa: F401, F403

# ── Prod overrides ────────────────────────────────────────────────────────────

# Ensure DEBUG is always False in production regardless of .env
DEBUG = False

# ── Logging ───────────────────────────────────────────────────────────────────

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            "datefmt": "%Y-%m-%d %H:%M:%S",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "stream": "ext://sys.stdout",
        },
    },
    "loggers": {
        # Root Django logger — WARNING to reduce noise in production
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # Log 4xx/5xx request errors at ERROR level in prod
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Suppress SQL query logging in production
        "django.db.backends": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # App loggers — WARNING in prod; use explicit logger.error() for critical paths
        "apps": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
    },
    # Catch-all root logger — WARNING in prod
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}
