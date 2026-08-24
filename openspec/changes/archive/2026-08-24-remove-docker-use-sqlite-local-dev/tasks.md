## 1. Settings: SQLite, filesystem broker

- [x] 1.1 In `backend/config/settings.py`, change the `DATABASE_URL` default to `sqlite:///{BASE_DIR}/db.sqlite3` and verify `python manage.py check` passes — built as a plain dict instead of via URL parsing (Windows drive-letter paths don't round-trip cleanly through `sqlite://` URLs, verified empirically)
- [x] 1.2 Make the Celery broker default to `filesystem://` when `CELERY_BROKER_URL` is unset, and the existing Redis URL when it is set — see 1.2a for a mid-implementation correction
- [x] 1.2a **Correction**: `data_folder_in`/`data_folder_out` must point at the *same* single folder, not two different ones, when every producer and the one consumer share this same `settings.py` (kombu names them from the queue's point of view — publish always writes `data_folder_out`, consume always reads `data_folder_in` — a two-folder split assumes two independently-configured connections with swapped settings, which doesn't apply here). Verified live: staggered dispatches now land through a real stop/restart of the worker.
- [x] 1.3 Update `backend/.env.example` and `backend/.env`: comment out `DATABASE_URL`/`REDIS_URL`/`CELERY_BROKER_URL` with a note that setting them switches to Postgres/Redis
- [x] 1.4 Add `db.sqlite3` and `.celery/` to `backend/.gitignore`
- [x] 1.5 Add `pywin32` to `backend/requirements.txt` gated on `sys_platform == "win32"` — kombu's filesystem transport imports `pywintypes` on Windows, not installed by default

## 2. Migration: append-only trigger on both backends

- [x] 2.1 Rewrite `backend/recovery/migrations/0002_audit_log_append_only_trigger.py` as a `RunPython` operation branching on `schema_editor.connection.vendor`, with SQLite trigger SQL added alongside the existing Postgres SQL, and matching reverse functions
- [x] 2.2 Run `python manage.py migrate` against a fresh SQLite database and verify it applies cleanly

## 3. Verify the append-only guarantee and full pipeline on SQLite

- [x] 3.1 Run `pytest recovery/tests/test_audit_log.py -v` against the new SQLite default and verify all pass (the raw-SQL UPDATE/DELETE rejection must still work) — 5/5 passing
- [x] 3.2 Add a `connection.features.has_select_for_update` skip guard to the guardrail concurrency test in `backend/recovery/tests/test_guardrails.py`, with a comment explaining why
- [x] 3.3 Run the full suite (`pytest -v`) against SQLite and verify everything passes (the concurrency test should show as skipped, not failed) — 71 passed, 1 skipped
- [x] 3.4 Seed data and run `python manage.py replay_batch --sync` against SQLite to confirm the full pipeline still works end-to-end with no Postgres/Redis running — works; also fixed a stale `docker compose down -v` message in `seed_data.py`'s flush-failure warning. (Unrelated pre-existing bug found separately and flagged, not fixed here: live Razorpay keys + seed data's fake `order_sim_...` IDs 404 on a real retry_order/invoice_reminder call — out of scope for this change.)

## 4. Cross-process live dashboard events without Redis

- [x] 4.1 Live-test the original plan (bare `channels.layers.InMemoryChannelLayer` when `REDIS_URL` is unset) against the real process topology: Daphne + a separate `celery worker` process. **Result: broken** — a ticker event pushed from the worker process never reached a WS client connected to Daphne, because `InMemoryChannelLayer` only bridges consumers within one process, and the worker and Daphne are different processes with no shared memory.
- [x] 4.2 Add `BroadcastEvent` model (`id`, `event_type`, `payload` JSONField, `created_at`) + migration, as the cross-process channel when Redis isn't configured — both processes already share the database regardless of broker choice
- [x] 4.3 Add `settings.CHANNELS_USE_REDIS = bool(REDIS_URL)`; update `recovery/ws.py::push()` to write a `BroadcastEvent` row instead of calling `channel_layer.group_send()` when it's `False`
- [x] 4.4 Update `recovery/consumers.py::RecoveryConsumer`: when `CHANNELS_USE_REDIS` is `False`, skip `group_add`/`group_discard` and instead run a ~300ms polling loop (started on connect, cancelled on disconnect) that tails `BroadcastEvent` by id since connect-time and forwards each new row to the client directly
- [x] 4.5 Update `recovery/tests/test_consumers.py` to cover both paths (or confirm the existing tests exercise the new default polling path correctly, since `REDIS_URL` is unset in the test environment) — confirmed: existing tests exercise the polling path as-is (REDIS_URL unset), 4/4 passing
- [x] 4.6 Re-run the full test suite and verify it still passes — 71 passed, 1 skipped
- [x] 4.7 Live-verify with Docker Desktop and all containers stopped: start Daphne, a Celery worker, and Celery beat directly; confirm a live batch replay streams ticker/guardrail events over the WebSocket with correct staggered timing (proving both the filesystem broker's countdown handling and the new cross-process relay work together) — confirmed via a real WS client: 8 ticker events, cross-process delivery working, gaps of 1.25-1.89s matching the configured 1.5s stagger
- [x] 4.8 Confirm Celery Beat's scheduled sweep still runs on schedule against the filesystem broker — confirmed, two consecutive 30s cycles, received and succeeded each time

## 5. Remove Docker and update docs

- [x] 5.1 Delete `docker-compose.yml`
- [x] 5.2 Update `README.md`: remove Docker from prerequisites and the run-it-locally steps; document the new zero-dependency default, the DB-polling relay, and how to opt into real Postgres/Redis — also documented the pre-existing Razorpay/seed-data gap found in section 3
- [x] 5.3 Update `CLAUDE.md`'s stack description and architectural invariants to describe SQLite-by-default / Postgres-in-production, the append-only trigger as backend-appropriate rather than Postgres-only, and the polling relay — also fixed a stale line claiming `openspec/specs/`/`changes/` "don't exist yet" (they now hold 4 archived capabilities)
- [x] 5.4 Update `openspec/config.yaml`'s `context:` block to match
- [x] 5.5 Confirm `render.yaml` needs no changes (production continues to get `DATABASE_URL`/`REDIS_URL` from Render's managed services, so it always takes the `RedisChannelLayer`/real-broker path) — confirmed by inspection: all three env vars are set unconditionally via `fromDatabase`/`fromService` for every service. Also confirmed `pywin32` (gated on `sys_platform == "win32"`) won't attempt to install on Render's Linux build.
