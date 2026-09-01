from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-secret-key-change-me")
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
_render_hostname = env("RENDER_EXTERNAL_HOSTNAME", default="")
if _render_hostname and _render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_hostname)
_railway_hostname = env("RAILWAY_PUBLIC_DOMAIN", default="")
if _railway_hostname and _railway_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_railway_hostname)

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "channels",
    "django_celery_beat",
    "recovery",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

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

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

_database_url = env("DATABASE_URL", default="")
if _database_url:
    DATABASES = {"default": environ.Env.db_url_config(_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 200,
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}
DASHBOARD_USERNAME = env("DASHBOARD_USERNAME", default="operator")
DASHBOARD_PASSWORD = env("DASHBOARD_PASSWORD", default="")

CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173", "http://127.0.0.1:5173"]
)

REDIS_URL = env("REDIS_URL", default="")
CHANNELS_USE_REDIS = bool(REDIS_URL)
if CHANNELS_USE_REDIS:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {"hosts": [REDIS_URL]},
        }
    }
else:
    CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="")
if CELERY_BROKER_URL:
    CELERY_RESULT_BACKEND = CELERY_BROKER_URL
else:
    _celery_queue_dir = BASE_DIR / ".celery" / "queue"
    _celery_queue_dir.mkdir(parents=True, exist_ok=True)
    CELERY_BROKER_URL = "filesystem://"
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "data_folder_in": str(_celery_queue_dir),
        "data_folder_out": str(_celery_queue_dir),
    }
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "sweep-scheduled-actions": {
        "task": "recovery.tasks.sweep_scheduled_actions",
        "schedule": 30.0,
    },
    "sweep-promises-to-pay": {
        "task": "recovery.tasks.sweep_promises_to_pay",
        "schedule": 30.0,
    },
}

OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
LLM_MODEL = env("LLM_MODEL", default="gpt-4o-mini")

RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"

GUARDRAILS = {
    "MAX_RETRIES": env.int("GUARDRAIL_MAX_RETRIES", default=3),
    "CONTACT_COOLDOWN_HOURS": env.int("GUARDRAIL_CONTACT_COOLDOWN_HOURS", default=24),
    "RETRY_COOLDOWN_HOURS": env.int("GUARDRAIL_RETRY_COOLDOWN_HOURS", default=48),
    "SPEND_CEILING_INR": env.int("GUARDRAIL_SPEND_CEILING_INR", default=50000),
    "CONFIDENCE_FLOOR": env.float("GUARDRAIL_CONFIDENCE_FLOOR", default=0.60),
    "BUSINESS_HOURS_START": env.int("GUARDRAIL_BUSINESS_HOURS_START", default=9),
    "BUSINESS_HOURS_END": env.int("GUARDRAIL_BUSINESS_HOURS_END", default=19),
    "MANDATE_SEQUENCE_STEP1_DELAY_DAYS": env.int("GUARDRAIL_MANDATE_SEQUENCE_STEP1_DELAY_DAYS", default=3),
    "MANDATE_SEQUENCE_STEP2_DELAY_HOURS": env.int("GUARDRAIL_MANDATE_SEQUENCE_STEP2_DELAY_HOURS", default=1),
}

CHECKOUT_DROPOFF_AT_RISK_HOURS = env.float("CHECKOUT_DROPOFF_AT_RISK_HOURS", default=1.0)
HIGH_VALUE_CART_INR = env.int("HIGH_VALUE_CART_INR", default=8000)

REPLAY_STAGGER_SECONDS = env.float("REPLAY_STAGGER_SECONDS", default=1.5)

RECOVERY_OUTCOME_SEED = env.str("RECOVERY_OUTCOME_SEED", default="") or None
