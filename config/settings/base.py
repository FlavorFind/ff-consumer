"""
Base settings shared across all environments.
Never import this directly — import dev, test or prod instead.
"""

from pathlib import Path

import environ
from celery.schedules import crontab

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

# Read .env file if present (local development only)
environ.Env.read_env(BASE_DIR / ".env", overwrite=False)

# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG", default=False)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

# ---------------------------------------------------------------------------
# Application definition
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "drf_spectacular",
    "django_celery_beat",
    "django_celery_results",
    # Two-factor authentication (staff admin)
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "two_factor",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.profiles",
    "apps.engine_client",
    "apps.billing",
    "apps.pantry",
    "apps.search",
    "apps.library",
    "apps.planner",
    "apps.budget",
    "apps.content",
    "apps.sync",
    "apps.community",
    "apps.notifications",
    "apps.partners",
    "apps.moderation",
    "apps.api",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.core.middleware.RequestIDMiddleware",
    "apps.core.security.SecurityHeadersMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL"),
}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)
DATABASES["default"].setdefault("TEST", {})["NAME"] = env(
    "TEST_DATABASE_NAME", default="test_ff_consumer_test"
)

# ---------------------------------------------------------------------------
# Cache and Redis
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://localhost:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
        "KEY_PREFIX": "ffconsumer",
        "TIMEOUT": 300,
    }
}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.CustomUser"
LOGIN_URL = "two_factor:login"
LOGIN_REDIRECT_URL = "/admin/"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# Argon2id — the most secure password hasher available
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

# ---------------------------------------------------------------------------
# JWT (djangorestframework-simplejwt)
# ---------------------------------------------------------------------------
from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=30),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": "HS256",
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
    "TOKEN_OBTAIN_SERIALIZER": "apps.accounts.serializers.CustomTokenObtainPairSerializer",
}

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
    ],
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.CursorPagination",
    "PAGE_SIZE": env.int("API_PAGE_SIZE", default=20),
    "MAX_PAGE_SIZE": env.int("API_MAX_PAGE_SIZE", default=100),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "apps.core.exceptions.custom_exception_handler",
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("THROTTLE_ANON", default="60/minute"),
        "user": env("THROTTLE_USER", default="300/minute"),
        "otp": env("THROTTLE_OTP", default="5/minute"),
    },
}

# ---------------------------------------------------------------------------
# OpenAPI (drf-spectacular)
# ---------------------------------------------------------------------------
SPECTACULAR_SETTINGS = {
    "TITLE": "Flavor Find Consumer API",
    "DESCRIPTION": (
        "The Flavor Find consumer backend. Serves the website and Android app. "
        "Owns accounts, pantries, meal plans, saved recipes, subscriptions. "
        "Food data comes from the Recipe Engine.\n\n"
        "**Allergen disclaimer:** Allergen and dietary information is provided for "
        "informational purposes only. Always confirm with the kitchen before ordering."
    ),
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "CONTACT": {"email": "api@flavorfind.co.ke"},
    "LICENSE": {"name": "Proprietary"},
    "ENUM_NAME_OVERRIDES": {
        "LanguageEnum": ["en", "sw"],
        "MealTypeEnum": ["breakfast", "lunch", "dinner", "snack", "dessert", "drink", "any"],
    },
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])
CORS_ALLOW_ALL_ORIGINS = env.bool("CORS_ALLOW_ALL_ORIGINS", default=False)
CORS_ALLOW_CREDENTIALS = True  # needed for cookies (refresh token)

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL.replace("/0", "/1"))
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Africa/Nairobi"
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"
CELERY_BEAT_SCHEDULE = {
    "dataset-drift-check-nightly": {
        "task": "apps.engine_client.tasks.check_dataset_drift",
        "schedule": crontab(hour=2, minute=0),  # 2 AM Nairobi time
    },
    "subscription-expiry-check-daily": {
        "task": "apps.billing.tasks.check_subscription_expiry",
        "schedule": crontab(hour=1, minute=0),  # 1 AM daily
    },
    "trial-expiry-check-daily": {
        "task": "apps.billing.tasks.check_trial_expiry",
        "schedule": crontab(hour=1, minute=30),  # 1:30 AM daily
    },
    "renewal-reminders-daily": {
        "task": "apps.billing.tasks.send_renewal_reminders",
        "schedule": crontab(hour=8, minute=0),  # 8 AM daily
    },
}

# ---------------------------------------------------------------------------
# Engine client settings
# ---------------------------------------------------------------------------
ENGINE_BASE_URL = env("ENGINE_BASE_URL", default="https://engine.flavorfind.co.ke")
ENGINE_API_KEY = env("ENGINE_API_KEY", default="")
ENGINE_INTERNAL_KEY = env("ENGINE_INTERNAL_KEY", default="")
ENGINE_TIMEOUT = env.float("ENGINE_TIMEOUT", default=5.0)
ENGINE_CIRCUIT_BREAKER_THRESHOLD = env.int("ENGINE_CIRCUIT_BREAKER_THRESHOLD", default=5)
ENGINE_CIRCUIT_BREAKER_RECOVERY = env.int("ENGINE_CIRCUIT_BREAKER_RECOVERY", default=30)

# ---------------------------------------------------------------------------
# Paystack
# ---------------------------------------------------------------------------
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_CALLBACK_URL = env(
    "PAYSTACK_CALLBACK_URL",
    default="https://flavorfind.co.ke/plus/success",
)

# ---------------------------------------------------------------------------
# Email — Resend
# ---------------------------------------------------------------------------
RESEND_API_KEY = env("RESEND_API_KEY", default="")
# Use onboarding@resend.dev (Resend shared domain) until flavorfind.co.ke is verified
RESEND_FROM_EMAIL = env("RESEND_FROM_EMAIL", default="Flavor Find <onboarding@resend.dev>")

# ---------------------------------------------------------------------------
# Frontend URL (used in email verification links)
# ---------------------------------------------------------------------------
FRONTEND_URL = env("FRONTEND_URL", default="https://flavorfind.co.ke")

# ---------------------------------------------------------------------------
# Internationalisation
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static files
# ---------------------------------------------------------------------------
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# Only include the local static dir if it actually exists (avoids W004 in CI)
_static_dir = BASE_DIR / "static"
STATICFILES_DIRS = [_static_dir] if _static_dir.exists() else []
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Session security
# ---------------------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 8  # 8 hours
SESSION_COOKIE_HTTPONLY = True
SESSION_EXPIRE_AT_BROWSER_CLOSE = False
CSRF_COOKIE_HTTPONLY = True

# ---------------------------------------------------------------------------
# Logging — structured JSON logs with request IDs
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "apps.core.logging.JSONFormatter",
        },
        "simple": {
            "format": "[{levelname}] {name}: {message}",
            "style": "{",
        },
    },
    "filters": {
        "request_id": {
            "()": "apps.core.logging.RequestIDFilter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
            "filters": ["request_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# ---------------------------------------------------------------------------
# Sentry
# ---------------------------------------------------------------------------
SENTRY_DSN = env("SENTRY_DSN", default="")
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.1,
        send_default_pii=False,
    )

# ---------------------------------------------------------------------------
# App version
# ---------------------------------------------------------------------------
CONSUMER_VERSION = env("CONSUMER_VERSION", default="dev")
