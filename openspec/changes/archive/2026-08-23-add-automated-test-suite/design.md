## Context

See proposal.md - Why. RecoverAI's existing tooling (Postgres, Redis via Docker,
Django, DRF, Channels, Celery) is already in place; this change only adds a test
layer on top. No existing test infrastructure exists to build on or reconcile with.

## Goals / Non-Goals

**Goals**: deterministic-core coverage (guardrails, pipeline heuristic), a database-
level proof of the audit log's append-only guarantee, integration coverage for the
Celery pipeline / REST API / WebSocket push, and a real (not mocked) smoke test against
Razorpay's live test-mode API now that credentials exist.

**Non-Goals**: frontend (React) tests — out of scope for this change, tracked
separately if wanted. Load/performance testing. CI pipeline wiring (GitHub Actions
etc.) — this change makes the suite runnable locally; wiring it into CI is a follow-up.
Testing LLM-backed diagnosis/decision output when an API key is present — that path is
inherently non-deterministic; only the heuristic fallback is asserted on exact output.

## Decisions

**pytest + pytest-django, not Django's built-in `TestCase`/`manage.py test`.**
pytest's fixture model is a better fit for the "simulated vs. live Razorpay" split
(a `razorpay_live` fixture that skips cleanly via `pytest.mark.skipif` when credentials
are absent, vs. `unittest`'s clunkier `skipUnless` decorators) and for parametrizing
the six guardrail rules without six near-duplicate test classes. `pytest-django`
still uses Django's test database machinery underneath (transactional rollback per
test), so no behavior changes, just a nicer authoring surface.

**Test database: Django's standard `test_<dbname>` on the existing Postgres
container**, not a separate SQLite or in-memory database. The append-only trigger
(migration 0002) is Postgres-specific PL/pgSQL — SQLite would silently skip the one
guarantee most worth testing. `pytest-django` creates/migrates/drops it automatically;
no docker-compose changes needed.

**The append-only test uses `django.db.connection.cursor()` for a raw SQL
UPDATE/DELETE, wrapped in `pytest.raises` and an explicit savepoint
(`django.db.transaction.atomic()`) so the failed statement doesn't poison the rest of
the test's transaction.** Alternative considered: asserting via `AuditLogEntry.save()`
on an existing instance (already covered by existing model-level guard) — kept as a
separate, cheaper test, but the raw-SQL version is the one that actually proves the
trigger works, which is the point of this requirement.

**Channels testing via `channels.testing.WebsocketCommunicator`**, Channels' own
first-party test client — connects a real (in-memory) WS client to the ASGI
application and asserts on `receive_json_from()`. No new dependency: `channels` is
already installed.

**Celery tasks are called directly as plain functions in tests (e.g.
`process_transaction_event(str(txn.id))`), not via `.delay()`.** This is the same
pattern the `replay_batch --sync` management command already uses — it runs the task
body synchronously in the test process, no broker/worker required, and is how Celery
tasks are meant to be unit-tested.

**The live Razorpay smoke test is one test, not a full duplicate suite.** Given a real
test-mode key is now configured, the risk being managed is "the client's request
shape stops matching what Razorpay's API actually accepts" (this exact class of bug
surfaced once already this session — a phone number format rejection). One passing
live call per test run is enough signal for that; broader live coverage would slow the
suite and burn Razorpay API quota for no proportional benefit.

## Risks / Trade-offs

- [Live Razorpay test creates real (test-mode) objects] → the test cancels what it
  creates immediately after asserting on it, mirroring the manual cleanup already done
  earlier in this session.
- [Live test flakes on network/API downtime, blocking local runs] → it's the only test
  gated on real network access; everything else in the suite runs fully offline. It's
  additionally skipped automatically (not failed) when credentials are absent, so a
  clone of this repo without keys still gets a clean, fully-passing suite.
- [Postgres-specific trigger test doesn't run if a contributor points `DATABASE_URL`
  at a non-Postgres database] → out of scope to guard against; the project's stack is
  Postgres-only by design (see CLAUDE.md), so this isn't a supported configuration.

## Migration Plan

Additive only — no existing code changes, no schema changes. `pip install -r
requirements.txt` after this change picks up the three new test dependencies.
`pytest` (run from `backend/`) is the new entry point; documented in README.md.

## Open Questions

None — scope, approach, and task breakdown are all resolved above.
