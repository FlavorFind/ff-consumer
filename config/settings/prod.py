"""Production settings."""

from .base import *  # noqa: F401, F403
from .base import env  # noqa: F401

DEBUG = False

# Render terminates TLS at the load balancer
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = False  # Render handles this at the edge

# Security headers
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
CSRF_TRUSTED_ORIGINS = env.list(  # type: ignore[misc]  # noqa: F405
    "CSRF_TRUSTED_ORIGINS", default=[]
)

# CORS — explicitly listed origins only
CORS_ALLOWED_ORIGINS = env.list(  # type: ignore[misc]  # noqa: F405
    "CORS_ALLOWED_ORIGINS", default=[]
)
CORS_ALLOW_ALL_ORIGINS = False

# Structured JSON logging in production
LOGGING["handlers"]["console"]["formatter"] = "json"  # noqa: F405

# Static files — served by Whitenoise with compression
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}


def _make_cache_config():  # noqa: E302
    _redis_url = env("REDIS_URL", default="")  # noqa: F405
    if not _redis_url:
        return {
            "default": {
                "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
                "LOCATION": "ffconsumer-locmem",
            }
        }
    return {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": _redis_url,
            "KEY_PREFIX": "ffconsumer",
            "TIMEOUT": 300,
        }
    }


CACHES = _make_cache_config()
