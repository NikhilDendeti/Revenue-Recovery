from datetime import timedelta
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-secret-key-change-me")
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
# Render sets this automatically on every service (its own public hostname) — add it
# so a deploy works even if ALLOWED_HOSTS itself was never manually configured.
_render_hostname = env("RENDER_EXTERNAL_HOSTNAME", default="")
if _render_hostname and _render_hostname not in ALLOWED_HOSTS:
    ALLOWED_HOSTS.append(_render_hostname)

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

# Local dev default is a plain SQLite file — no Postgres, no Docker required. Set
# DATABASE_URL to a real connection string (Postgres in production, via render.yaml)
# to use that instead. Built directly rather than through env.db()'s URL parsing:
# a Windows absolute path (C:\...) inside a sqlite:// URL is a well-known footgun
# (the drive-letter colon and backslashes don't round-trip through URL parsing
# cleanly), so the SQLite case is constructed as a plain dict instead.
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

# --- REST framework ---
REST_FRAMEWORK = {
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    # PageNumberPagination, not CursorPagination: DRF's CursorPagination defaults its
    # `ordering` to a field literally named "created", which none of these models use
    # (created_at / agent_run_at / decided_at / triggered_at / timestamp) — it would
    # 500 on every list endpoint without a per-view override. Page numbers are plenty
    # for a 50-100 record hackathon dataset.
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    # Hackathon batch scale is 50-200 records — one page covers the whole Recovery Room
    # dashboard without the frontend needing pagination UI.
    "PAGE_SIZE": 200,
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework_simplejwt.authentication.JWTAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

# --- JWT auth: one seeded operator account, not a registration flow — see
# recovery/management/commands/seed_dashboard_user.py and CLAUDE.md. ---
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}
DASHBOARD_USERNAME = env("DASHBOARD_USERNAME", default="operator")
DASHBOARD_PASSWORD = env("DASHBOARD_PASSWORD", default="")

# --- CORS ---
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:5173", "http://127.0.0.1:5173"]
)

# --- Channels ---
# No REDIS_URL set (the local-dev default) -> live dashboard events (ticker/guardrail/
# audit pushes) route through recovery.models.BroadcastEvent + a polling loop in
# RecoveryConsumer instead of a channel layer at all (see recovery/ws.py and
# recovery/consumers.py) — NOT channels.layers.InMemoryChannelLayer, which was tried
# first and doesn't work here: the publisher (a Celery worker) and the WebSocket
# server (Daphne) are separate processes with no shared memory, and in-memory pub/sub
# can't bridge that. CHANNEL_LAYERS is still configured (Channels expects one to
# exist) but isn't relied on for delivery in this mode. Render always sets REDIS_URL,
# so production always takes the real Redis pub/sub path.
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

# --- Celery ---
# No CELERY_BROKER_URL set (the local-dev default) -> kombu's filesystem transport:
# two local folders standing in for a broker. Celery's countdown/eta scheduling lives
# in the worker process, not the transport, so replay_batch's staggered dispatch
# still works — this isn't the same as CELERY_TASK_ALWAYS_EAGER, which would run
# everything instantly and kill the "watch the ticker climb live" demo. Render always
# sets CELERY_BROKER_URL to its managed Redis, so production is unaffected.
CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="")
if CELERY_BROKER_URL:
    CELERY_RESULT_BACKEND = CELERY_BROKER_URL
else:
    # Both options point at the SAME folder, not two different ones. kombu's
    # filesystem transport names these from the queue's point of view, not the
    # process's: publish always writes to data_folder_out and consume always reads
    # from data_folder_in (confirmed in kombu/transport/filesystem.py's _put/_get).
    # A two-folder split only makes sense across two independently-configured
    # connections with their in/out deliberately swapped relative to each other; here
    # every producer (Django views, Beat, a worker task enqueuing another task) and
    # the one consumer (the worker) all load this same settings module, so they need
    # to agree on a single shared folder, not talk past each other into two.
    _celery_queue_dir = BASE_DIR / ".celery" / "queue"
    _celery_queue_dir.mkdir(parents=True, exist_ok=True)
    CELERY_BROKER_URL = "filesystem://"
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "data_folder_in": str(_celery_queue_dir),
        "data_folder_out": str(_celery_queue_dir),
    }
    # No result backend needed — nothing in this app calls .get()/.wait() on a task
    # result, only .delay()'s returned id (see recovery/views.py::BatchReplayView).
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = TIME_ZONE
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BEAT_SCHEDULE = {
    "sweep-scheduled-actions": {
        "task": "recovery.tasks.sweep_scheduled_actions",
        "schedule": 30.0,  # seconds — demo-friendly cadence; real cooldowns are hours/days out
    },
}

# --- RecoverAI: LLM (optional) ---
OPENAI_API_KEY = env("OPENAI_API_KEY", default="")
ANTHROPIC_API_KEY = env("ANTHROPIC_API_KEY", default="")
LLM_MODEL = env("LLM_MODEL", default="gpt-4o-mini")

# --- RecoverAI: Razorpay (optional) ---
RAZORPAY_KEY_ID = env("RAZORPAY_KEY_ID", default="")
RAZORPAY_KEY_SECRET = env("RAZORPAY_KEY_SECRET", default="")
RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"

# --- RecoverAI: guardrail thresholds ---
GUARDRAILS = {
    "MAX_RETRIES": env.int("GUARDRAIL_MAX_RETRIES", default=3),
    "CONTACT_COOLDOWN_HOURS": env.int("GUARDRAIL_CONTACT_COOLDOWN_HOURS", default=24),
    "RETRY_COOLDOWN_HOURS": env.int("GUARDRAIL_RETRY_COOLDOWN_HOURS", default=48),
    "SPEND_CEILING_INR": env.int("GUARDRAIL_SPEND_CEILING_INR", default=50000),
    "CONFIDENCE_FLOOR": env.float("GUARDRAIL_CONFIDENCE_FLOOR", default=0.60),
    "BUSINESS_HOURS_START": env.int("GUARDRAIL_BUSINESS_HOURS_START", default=9),
    "BUSINESS_HOURS_END": env.int("GUARDRAIL_BUSINESS_HOURS_END", default=19),
}

# Demo pacing: seconds of stagger between each transaction during a batch replay.
REPLAY_STAGGER_SECONDS = env.float("REPLAY_STAGGER_SECONDS", default=1.5)

# Optional: make a batch replay's recovered/failed outcomes reproducible across runs.
# The outcome of a replay is drawn against diagnosis confidence (there is no real customer
# clicking "pay"), so it varies every run. Setting this seeds the draw per transaction, so
# a rehearsal and the real thing produce the same board. Unset (the default) draws from the
# system RNG and behaviour is exactly as before.
RECOVERY_OUTCOME_SEED = env.str("RECOVERY_OUTCOME_SEED", default="") or None
