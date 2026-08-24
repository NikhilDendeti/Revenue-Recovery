## Why

Local dev has needed Docker Desktop running (for Postgres + Redis) all session — every
environment restart means relaunching Docker Desktop, waiting for its daemon, and
`docker compose up -d` before anything else can start. That's real, repeated friction
for a single-operator hackathon build with no need for Postgres/Redis's production
characteristics locally. This change makes local dev need **no external services at
all**: SQLite for the database, a filesystem-based Celery broker, and a small
database-backed relay standing in for Channels' Redis layer. Production (Render) is unaffected — it already gets managed Postgres
and managed Redis from `render.yaml`, independent of anything in `docker-compose.yml`.

## What Changes

- Remove `docker-compose.yml` entirely. **BREAKING**: anyone relying on
  `docker compose up -d` for local Postgres/Redis needs to stop; nothing here requires
  it anymore.
- `DATABASE_URL` defaults to a local SQLite file (`sqlite:///db.sqlite3`) instead of a
  Postgres connection string. Setting `DATABASE_URL` to a real Postgres URL still works
  unchanged — this is a default swap, not a hard requirement.
- The append-only audit log trigger (migration `0002`) gets a SQLite-native
  implementation alongside the existing Postgres one, selected at migration time by
  `schema_editor.connection.vendor` — the guarantee holds on both backends, not just
  Postgres.
- Live dashboard events (ticker/guardrail/audit pushes) route through a new
  `BroadcastEvent` DB table + a short-interval polling loop in the WebSocket consumer
  when `REDIS_URL` is unset, instead of Channels' Redis pub/sub — necessary because
  the Celery worker (publisher) and Daphne (the WebSocket server) are separate
  processes, so a bare in-memory channel layer can't bridge them; the database is the
  one channel both processes already share regardless of broker choice. The existing
  `RedisChannelLayer` path is used unchanged when `REDIS_URL` is set.
- Celery's broker defaults to `kombu`'s `filesystem://` transport (a local folder
  acting as the queue) when `CELERY_BROKER_URL` is unset, preserving staggered
  `apply_async(countdown=...)` scheduling — Celery's ETA/countdown handling lives in
  the worker, not the transport, so the "batch replay climbs live" behavior is
  unaffected. The existing Redis-backed broker still works unchanged if configured.
- The guardrail concurrency test (`test_contact_cap_race_...`) skips on backends
  without real row-level locking (SQLite) rather than asserting a guarantee SQLite's
  locking model can't actually provide — verified where it matters (Postgres, which is
  what production runs).
- Update `README.md`, `CLAUDE.md`, and `openspec/config.yaml` to describe SQLite +
  no-external-services as the local-dev default, Postgres/Redis as the
  production/opt-in path.

## Capabilities

### New Capabilities
- `local-dev-environment`: what running this project locally requires (or doesn't) —
  no external services by default, same behavior guarantees as production either way.

### Modified Capabilities
(none — no existing capability's observable behavior contract changes; the append-only
guarantee and the guardrail rules behave the same from the outside, just verified
against a different backend locally)

## Impact

- Removed: `docker-compose.yml`.
- `backend/config/settings.py`: `DATABASE_URL` default, `CHANNEL_LAYERS`/`CHANNELS_USE_REDIS`,
  and Celery broker config now branch on whether `REDIS_URL`/`CELERY_BROKER_URL` are set.
- `backend/recovery/migrations/0002_audit_log_append_only_trigger.py`: rewritten to
  branch on DB vendor.
- New: `BroadcastEvent` model + migration; `recovery/ws.py` and `recovery/consumers.py`
  branch between the Redis pub/sub path and the DB-polling relay path.
- `backend/.env.example`, `backend/.env`: `DATABASE_URL`/`REDIS_URL`/
  `CELERY_BROKER_URL` become optional, commented as "set to use Postgres/Redis
  instead."
- `backend/recovery/tests/test_guardrails.py`: one test gains a `skipif` guard.
- `backend/.gitignore` additions: `db.sqlite3`, `.celery/`.
- `README.md`, `CLAUDE.md`, `openspec/config.yaml`: local-dev instructions and stack
  description updated. `render.yaml` is unaffected — production keeps managed
  Postgres/Redis regardless of the local default.
