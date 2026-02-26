from saghat.settings.base import *  # noqa: F401, F403

# ── Dev overrides ─────────────────────────────────────────────────────────────

# In dev, DEBUG is driven by the .env value (default True via pydantic Settings),
# but we make it explicit here so it's obvious when reading this file.
DEBUG = settings.DEBUG  # noqa: F405 — `settings` imported via base *

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
        # Root Django logger — INFO so framework noise stays manageable
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # Log 4xx/5xx request errors
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # SQL query logging — DEBUG level shows every query in dev
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        # All app loggers under the `apps.*` namespace
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
    # Catch-all root logger
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
}
