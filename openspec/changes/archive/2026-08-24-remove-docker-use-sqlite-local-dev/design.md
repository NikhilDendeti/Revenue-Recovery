## Context

See proposal.md - Why. Today: `docker-compose.yml` runs Postgres 16 + Redis 7;
`DATABASE_URL`/`REDIS_URL`/`CELERY_BROKER_URL` all default to pointing at those
containers; migration `0002` has Postgres-only PL/pgSQL. `render.yaml` (production)
gets its `DATABASE_URL`/`REDIS_URL` from Render's own managed Postgres/Redis via
`fromDatabase`/`fromService` — it has never referenced `docker-compose.yml` and is
untouched by this change.

## Goals / Non-Goals

**Goals**: zero external services for local dev by default; the append-only guarantee
and every existing behavior guarantee hold on the new default backend; switching to
real Postgres/Redis locally (e.g. to debug something Postgres-specific) stays a one
env-var change, not a code change; production untouched.

**Non-Goals**: making SQLite the production database (never — Render's separate
web/worker/beat processes each have their own disk, so a file-based DB can't be shared
across them; production stays on Postgres). Preserving identical concurrency semantics
between SQLite and Postgres (SQLite's locking model is genuinely coarser — see the
concurrency test decision below).

## Decisions

**SQLite via a `RunPython`-branched migration, not two separate migration paths.**
Migration `0002` becomes one `RunPython` operation whose forward/reverse functions
check `schema_editor.connection.vendor` and execute vendor-appropriate raw SQL via
`schema_editor.execute(...)`. SQLite trigger syntax
(`CREATE TRIGGER ... BEFORE UPDATE ON t BEGIN SELECT RAISE(ABORT, '...'); END;`) is
less expressive than PL/pgSQL but sufficient here — it needs one job: reject the
statement and raise. Kept in the same migration file (not a new one) since it's the
same logical change (add the append-only guarantee), just implemented per-backend.

**A DB-backed polling relay, not bare `InMemoryChannelLayer`, when `REDIS_URL` is
unset — discovered mid-implementation, not assumed upfront.** The original plan here
was `channels.layers.InMemoryChannelLayer`. Live-tested against the real multi-process
setup (Daphne + a separate `celery worker`), it doesn't work: `InMemoryChannelLayer`
only bridges consumers *within one process*, and the ticker/guardrail pushes
`recovery.tasks._execute_action` fires come from the Celery worker process — a
different OS process with no shared memory with Daphne. A worker-pushed event never
reached a connected WS client; confirmed by direct WS test before writing a line of
the fix. Redis solved this in the original design specifically *because* it's a real
cross-process broker, which is the one property actually required here — plain
in-memory pub/sub was never going to have it regardless of local-dev intentions.

Fix: `recovery.ws.push()` writes a `BroadcastEvent` row (id, event_type, payload,
created_at) instead of calling `channel_layer.group_send()` when no Redis is
configured; `RecoveryConsumer` runs a ~300ms polling loop per connection (tailing
`BroadcastEvent` by id since connect-time) instead of joining a channel-layer group.
Both processes already share the same database regardless of broker choice, so this
adds no new moving part — it reuses the one cross-process channel that was always
there. When `REDIS_URL` **is** set, the original `RedisChannelLayer` + `group_send`
path is used unchanged (lower latency, well-tested, matches production) — the branch
point is `settings.CHANNELS_USE_REDIS = bool(REDIS_URL)`, referenced from both
`ws.py` and `consumers.py`.

**Filesystem Celery broker, not `CELERY_TASK_ALWAYS_EAGER`.** Eager mode runs tasks
synchronously in the calling process and ignores `countdown`/`eta` — it would collapse
`replay_batch`'s staggered dispatch into one instant batch, killing the "watch the
ticker climb live" demo behavior this build is specifically designed to prove.
Celery's ETA/countdown scheduling is implemented in the *worker* (a local heap/timer),
not the broker, so a real (if simple) broker — kombu's built-in `filesystem://`
transport — preserves that behavior without needing Redis. Verified live: staggered
`process_transaction_event` dispatches landed ~1.5s apart as configured, through a
stopped-and-restarted worker, confirming the broker itself (not just in-process
scheduling) is doing the work.

One implementation trap worth recording: kombu's filesystem transport names
`data_folder_in`/`data_folder_out` from the *queue's* point of view, not the
process's — `_put()` (publish) always writes to `data_folder_out`, `_get()` (consume)
always reads from `data_folder_in` (confirmed in `kombu/transport/filesystem.py`).
The transport's own docstring example sets these to two *different* folders,
deliberately swapped between a producer-side and a consumer-side connection config —
but every producer here (Django views, Beat, a worker task enqueuing another task)
and the one consumer (the worker) load the *same* `settings.py`, so a two-folder split
under one shared config means publishes and consumes never meet: messages piled up in
one folder while the worker polled an empty one, and nothing was ever delivered.
Fixed by pointing both options at the *same* single folder (`backend/.celery/queue`),
created at settings-import time (`Path.mkdir(parents=True, exist_ok=True)`) so the
transport never fails on a missing directory on a fresh checkout.

**The guardrail concurrency test skips on SQLite via
`connection.features.has_select_for_update`, rather than being rewritten to pass on
both backends.** SQLite has no row-level locking — `select_for_update()` is a silent
no-op on it (Django's own documented behavior), so the test's premise (two threads
racing on a row lock) doesn't hold there regardless of application code correctness.
Rewriting the guardrail's own locking strategy to work identically on SQLite would
mean designing to the weaker backend's constraints for a guarantee that only matters
in production, where the real backend is always Postgres. The skip makes that
boundary explicit instead of leaving a test that either flakes or silently verifies
nothing.

## Risks / Trade-offs

- [SQLite's coarser file-level locking means other concurrent-write scenarios not
  covered by the one skipped test could behave differently locally than in production]
  → acceptable: this is a single-operator local dev tool, not a concurrency stress
  environment; the behavior that matters ships against Postgres on Render.
- [Filesystem Celery broker is unsuited to any real multi-worker/production
  deployment] → intentional; it's local-dev-only, selected only when
  `CELERY_BROKER_URL` is unset, and `render.yaml` always sets a real Redis URL.
- [Removing `docker-compose.yml` is a hard break for the Docker-based workflow the
  README currently documents] → intentional and stated as **BREAKING** in the
  proposal; replaced by a strictly lower-friction default.
- [The DB-polling relay adds up to ~300ms of latency to live dashboard events, and
  `BroadcastEvent` rows accumulate unbounded over a dev session] → the latency is
  imperceptible for a "watch the ticker climb" demo; unbounded growth is a non-issue
  at hackathon dev scale (hundreds of rows per session) and the table isn't the audit
  log — no compliance reason to keep or prune it carefully. Not addressed here.

## Migration Plan

1. Update settings/migration/tests as scoped above.
2. Delete `docker-compose.yml`.
3. Fresh local setup: `rm -f backend/db.sqlite3` (if a stale one exists from testing
   this change), `python manage.py migrate`, `python manage.py seed_dashboard_user`,
   `python manage.py seed_data`. No data is carried over from the old Postgres
   container — that's expected and fine for a hackathon dev database.
4. `render.yaml` requires no changes — verify by inspection, not by touching it.

## Open Questions

None.
