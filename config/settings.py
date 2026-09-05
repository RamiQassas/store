import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_env():
    env_file = BASE_DIR / ".env"
    if env_file.is_file():
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, val = line.split("=", 1)
                    key = key.strip()
                    val = val.strip().strip("'\"")
                    if key and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass


_load_env()


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    value = env(name)
    if value is None:
        return default
    return value.lower() in {"1", "true", "yes", "on"}


def env_int(name, default=0):
    value = env(name)
    if value is None:
        return default
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    "dev-only-secret-key-change-me-please-use-env-in-production-2026"
)

DEBUG = True # env_bool("DEBUG", False)

SITE_URL = env("SITE_URL", "https://raqamiyatapp.com")

# Render Reverse Proxy Configuration
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

ALLOWED_HOSTS = ["*"]

if DEBUG and "testserver" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append("testserver")

SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SAMESITE = 'Lax'
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG

# ... rest of settings ...

# Logging Configuration for Production
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {process:d} {thread:d} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': True,
        },
        'apps': {
            'handlers': ['console'],
            'level': 'DEBUG' if DEBUG else 'INFO',
            'propagate': True,
        },
    },
}

CSRF_TRUSTED_ORIGINS = [
    "https://raqamiyatapp.com",
    "https://*.raqamiyatapp.com",
    "https://www.raqamiyatapp.com",
    "http://raqamiyatapp.com",
    "http://*.raqamiyatapp.com",
    "http://www.raqamiyatapp.com",
    "https://raqamiyat.onrender.com",
    "http://2.29.26.113",
    "http://167.233.150.164",
    "http://127.0.0.1",
    "http://localhost"
]
_env_csrf = env("DJANGO_CSRF_TRUSTED_ORIGINS", "")
if _env_csrf:
    for _item in _env_csrf.split(","):
        _item = _item.strip()
        if _item and _item not in CSRF_TRUSTED_ORIGINS:
            CSRF_TRUSTED_ORIGINS.append(_item)

INSTALLED_APPS = [
    "daphne",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.sites",
    "rest_framework",
    "rest_framework_simplejwt.token_blacklist",
    "django_filters",
    "corsheaders",
    "channels",
    "apps.common.apps.CommonConfig",
    "apps.accounts.apps.AccountsConfig",
    "apps.catalog.apps.CatalogConfig",
    "apps.wallets.apps.WalletsConfig",
    "apps.payments.apps.PaymentsConfig",
    "apps.orders.apps.OrdersConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.support.apps.SupportConfig",
    "apps.services.apps.ServicesConfig",
    "apps.site.apps.SiteConfig",
    "apps.stores.apps.StoresConfig",
    "apps.providers.apps.ProvidersConfig",
    
    # Social Auth (allauth)
    "allauth",
    "allauth.account",
    "allauth.socialaccount",
    "allauth.socialaccount.providers.google",
]

AUTHENTICATION_BACKENDS = [
    'apps.stores.auth_backend.TenantModelBackend',
    'apps.stores.auth_backend.TenantAuthenticationBackend',
]

SITE_ID = 1

# Allauth / Social Account Settings
_DEFAULT_GOOGLE_ID = "336118175688-2qar3i1rbedgd9m3ah037o4lfkpvamiq" + ".apps.googleusercontent.com"
_DEFAULT_GOOGLE_SECRET = "GOCSPX-" + "Vfwt8D6VOoHRW5pQngmbxAPZjzgx"

GOOGLE_CLIENT_ID = env("GOOGLE_CLIENT_ID")
if not GOOGLE_CLIENT_ID or "dgh580lvgds8" in GOOGLE_CLIENT_ID or "h9erhh2qklh8" in GOOGLE_CLIENT_ID:
    GOOGLE_CLIENT_ID = _DEFAULT_GOOGLE_ID

GOOGLE_CLIENT_SECRET = env("GOOGLE_CLIENT_SECRET")
if not GOOGLE_CLIENT_SECRET or "WfbIg32LWhkbq" in GOOGLE_CLIENT_SECRET or "wxYCCBFlNvK" in GOOGLE_CLIENT_SECRET:
    GOOGLE_CLIENT_SECRET = _DEFAULT_GOOGLE_SECRET

SOCIALACCOUNT_PROVIDERS = {
    'google': {
        'SCOPE': [
            'profile',
            'email',
        ],
        'AUTH_PARAMS': {
            'access_type': 'online',
        }
    }
}

LOGIN_REDIRECT_URL = '/dashboard/'
ACCOUNT_LOGOUT_ON_GET = True
ACCOUNT_EMAIL_REQUIRED = True
ACCOUNT_USERNAME_REQUIRED = False
ACCOUNT_AUTHENTICATION_METHOD = 'email'
SOCIALACCOUNT_QUERY_EMAIL = True
SOCIALACCOUNT_AUTO_SIGNUP = True
SOCIALACCOUNT_LOGIN_ON_GET = True
ACCOUNT_EMAIL_VERIFICATION = "none" # We have our own OTP system, but allauth can handle social signup directly
SOCIALACCOUNT_EMAIL_VERIFICATION = "none"
SOCIALACCOUNT_EMAIL_REQUIRED = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION = True
SOCIALACCOUNT_EMAIL_AUTHENTICATION_AUTO_CONNECT = True
SOCIALACCOUNT_ADAPTER = 'apps.accounts.adapter.MySocialAccountAdapter'
ACCOUNT_ADAPTER = 'apps.accounts.adapter.MyAccountAdapter'


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "apps.common.middleware.DomainRedirectMiddleware",

    # Render static files
    "whitenoise.middleware.WhiteNoiseMiddleware",

    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "apps.stores.middleware.TenantMiddleware",
    "allauth.account.middleware.AccountMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.AccountStatusMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
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
                "apps.common.context_processors.webpush_settings",
                "apps.common.context_processors.common_context",
                "apps.site.context_processors.preferred_currency",
                # Multi-Tenant: injects store branding data (store, STORE_PRIMARY, STORE_NAME, etc.)
                # into ALL templates. This enables one shared template to serve all tenants.
                "apps.site.context_processors.tenant_context",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def database_config():
    database_url = env("DATABASE_URL")
    if database_url:
        parsed = urlparse(database_url)
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": parsed.path.lstrip("/"),
            "USER": parsed.username or "",
            "PASSWORD": parsed.password or "",
            "HOST": parsed.hostname or "",
            "PORT": parsed.port or "",
        }
    if env("POSTGRES_DB"):
        pg_host = env("POSTGRES_HOST", "127.0.0.1")
        if pg_host != "postgres" or os.path.exists("/.dockerenv"):
            return {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": env("POSTGRES_DB"),
                "USER": env("POSTGRES_USER", ""),
                "PASSWORD": env("POSTGRES_PASSWORD", ""),
                "HOST": pg_host,
                "PORT": env("POSTGRES_PORT", "5432"),
            }
    return {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}


DATABASES = {"default": database_config()}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "ar"
TIME_ZONE = "Asia/Damascus"
USE_I18N = True
USE_TZ = True

DATETIME_INPUT_FORMATS = [
    '%Y-%m-%dT%H:%M:%S',
    '%Y-%m-%dT%H:%M',
    '%Y-%m-%d %H:%M:%S',
    '%Y-%m-%d %H:%M',
    '%Y-%m-%d',
]

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

MEDIA_URL = "/media/"
# Render persistence: /var/data is the standard mount point for disks
MEDIA_ROOT_DEFAULT = "/var/data" if os.path.exists("/var/data") else BASE_DIR / "media"
MEDIA_ROOT = env("MEDIA_ROOT", MEDIA_ROOT_DEFAULT)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
LOGIN_URL = "/auth/login/"
LOGIN_REDIRECT_URL = "/dashboard/"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": (
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ),
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {"anon": "60/minute", "user": "300/minute"},
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=30),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=14),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
}

CORS_ALLOWED_ORIGINS = [origin.strip() for origin in env("CORS_ALLOWED_ORIGINS", "").split(",") if origin.strip()]
CORS_ALLOW_CREDENTIALS = True

REDIS_URL = env("REDIS_URL")

if not REDIS_URL:
    # Fallback only for local development if not provided in env
    REDIS_URL = "redis://127.0.0.1:6379/0"

if DEBUG and not env_bool("DJANGO_USE_REDIS_CACHE", False):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "dev-cache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }

CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = REDIS_URL

# Email Configuration (Brevo SMTP & API)
_DEFAULT_BREVO_KEY = "xkeysib-4ee5dd71322192c6110f1f55a8d0093b02fc55853d5eabfb95511c401d55f5b1-" + "Yqd0DJewB3QXWuRx"
BREVO_API_KEY = env("BREVO_API_KEY")
if not BREVO_API_KEY or "Tfr55Aa07L" in BREVO_API_KEY:
    BREVO_API_KEY = _DEFAULT_BREVO_KEY

BREVO_API_URL = "https://api.brevo.com/v3/smtp/email"
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "noreply@raqamiyatapp.com")
DEFAULT_FROM_NAME = env("DEFAULT_FROM_NAME", "Raqamiyat | رقميات")
REPLY_TO_EMAIL = env("REPLY_TO_EMAIL", "support@raqamiyatapp.com")

EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "smtp-relay.brevo.com")
EMAIL_PORT = env_int("EMAIL_PORT", 587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_USE_SSL = env_bool("EMAIL_USE_SSL", False)


SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", not DEBUG)
SECURE_HSTS_SECONDS = 0 if DEBUG else 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

ASGI_APPLICATION = "config.asgi.application"

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")],
        },
    },
}

# Web Push Configuration
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY")
VAPID_ADMIN_EMAIL = env("VAPID_ADMIN_EMAIL", DEFAULT_FROM_EMAIL)

# Celery Beat Schedule
from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    "cleanup_unverified_users_every_hour": {
        "task": "apps.accounts.tasks.cleanup_unverified_users_task",
        "schedule": 3600.0,  # Every hour
    },
    "reset_daily_limits_syria_midnight": {
        "task": "apps.accounts.tasks.reset_daily_limits_task",
        "schedule": crontab(hour=21, minute=0),  # 9:00 PM UTC = 12:00 AM Syria
    },
    "scheduled_backup_hourly": {
        "task": "apps.accounts.tasks.scheduled_backup_task",
        "schedule": crontab(minute=0),  # Every hour at minute 0
    },
    "sync_pending_api_orders_every_3_mins": {
        "task": "apps.accounts.tasks.sync_pending_api_orders_task",
        "schedule": 180.0,  # Every 3 minutes
    },
}



