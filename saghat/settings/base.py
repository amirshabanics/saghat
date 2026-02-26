from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn
from typing import Optional
from enum import Enum


class AppEnv(str, Enum):
    dev = "dev"
    prod = "prod"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Django
    STATIC_ROOT: str = "/static_root"
    SECRET_KEY: str
    DEBUG: bool = False
    ALLOWED_HOSTS: list[str] = ["*"]

    APP_ENV: AppEnv = AppEnv.dev

    # Database
    DATABASE_URL: PostgresDsn

    # Redis
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"  # type: ignore[assignment]

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 days

    # Bitpin
    BITPIN_API_BASE_URL: str = "https://api.bitpin.ir"
    BITPIN_API_KEY: Optional[str] = None


settings = Settings()
print("hereee", settings)
if settings.APP_ENV == AppEnv.dev:
    from .dev import *  # noqa: F403
elif settings.APP_ENV == AppEnv.prod:
    from .prod import *  # noqa: F403

# ── Django configuration ──────────────────────────────────────────────────────

SECRET_KEY = settings.SECRET_KEY
DEBUG = settings.DEBUG
ALLOWED_HOSTS = settings.ALLOWED_HOSTS

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "ninja",
    "apps.users.apps.UsersConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.loans.apps.LoansConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "saghat.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "saghat.wsgi.application"
ASGI_APPLICATION = "saghat.asgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": (
            settings.DATABASE_URL.path.lstrip("/")
            if settings.DATABASE_URL.path
            else "saghat"
        ),
        "USER": settings.DATABASE_URL.hosts()[0]["username"] or "saghat",
        "PASSWORD": settings.DATABASE_URL.hosts()[0]["password"] or "saghat",
        "HOST": settings.DATABASE_URL.hosts()[0]["host"] or "localhost",
        "PORT": str(settings.DATABASE_URL.hosts()[0]["port"] or 5432),
    }
}

# Cache (django-redis)
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": str(settings.REDIS_URL),
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
    }
}

# Auth
AUTH_USER_MODEL = "users.User"

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"
    },
]

# Internationalisation
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files
STATIC_ROOT = settings.STATIC_ROOT
STATIC_URL = "static/"

# Primary key type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
