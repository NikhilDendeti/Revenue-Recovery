## Why

RecoverAI has no automated tests. Every guardrail rule, the diagnosis/decision
heuristic, the audit-log append-only trigger, and the Razorpay client's live/simulated
split were only verified manually in this session. The buildathon's own judging bar
explicitly asks "does it run, is it structured, would you trust it" — an untested
codebase fails that on inspection alone, and a real Razorpay test-mode key is now
configured, which raises the cost of a regression (a bad diagnosis→decision mapping or
a broken guardrail can now trigger real (test-mode) API calls, not just simulated ones).
This change adds a pytest-based suite covering the deterministic core (guardrails,
pipeline heuristics), the data-integrity guarantee (append-only audit log), and the
integration surface (REST API, Celery tasks, WebSocket consumer) end-to-end.

## What Changes

- Add `pytest` + `pytest-django` + `pytest-asyncio` + Channels' test client as backend
  dev dependencies, with a `pytest.ini`/`conftest.py` configured against a throwaway
  test database (reuses the same Postgres container; Django creates/drops a `test_`
  database on it — no new infra).
- Unit tests for `recovery/guardrails.py` — one test per rule (confidence floor, max
  retries, spend ceiling, card-decline cooldown, contact frequency cap incl. a
  concurrency/race check, business-hours) plus a full-pass "cleared" case.
- Unit tests for `agents/pipeline.py`'s heuristic fallback — including a regression
  test locking in the subscription-vs-payment-degradation `registration_link` vs
  `retry_order` fix made earlier this session, and the confidence-floor-triggering
  "unknown root cause" path.
- A model test proving `AuditLogEntry` is append-only at the database level (attempts
  a raw-SQL `UPDATE`/`DELETE` against the table inside a test transaction and asserts
  Postgres rejects it) — this was previously only verified by hand.
- Integration tests for `recovery/tasks.py::process_transaction_event` covering the
  three cleared/held/escalated outcome paths, `sweep_scheduled_actions`, and
  `trigger_voice_showcase`, run in-process (no live Celery worker required).
- `recovery/razorpay_client.py` tests: the simulated-mode fallback (`RAZORPAY_KEY_ID`
  unset) always exercised; a live-mode smoke test that only runs when
  `RAZORPAY_KEY_ID`/`SECRET` are present in the environment (skipped otherwise) and
  cleans up (cancels) anything it creates.
- API tests via DRF's `APIClient` for the transaction list/chain, summary, guardrail
  events, audit log (read-only — assert write methods are rejected), batch replay
  trigger, webhook ingestion, and voice-showcase endpoints.
- A WebSocket test using Channels' `WebsocketCommunicator` proving a `ticker`/
  `guardrail`/`audit` event pushed via `recovery.ws.push()` is received by a connected
  client.
- Document `pytest` as the standard way to run the suite in `README.md`.

## Capabilities

### New Capabilities
- `automated-testing`: a pytest suite covering guardrail determinism, the diagnosis/
  decision heuristic, the append-only audit log guarantee, the Razorpay client's
  simulated/live split, the Celery task pipeline, the REST API, and the WebSocket push
  path — establishing what "tested" means for this project going forward.

### Modified Capabilities
(none — this change adds test coverage for existing behavior; it does not change any
requirement of the system itself)

## Impact

- New: `backend/pytest.ini`, `backend/conftest.py`, `backend/recovery/tests/` (package),
  `backend/agents/tests/` (package).
- New backend dev dependencies: `pytest`, `pytest-django`, `pytest-asyncio`.
- No production code paths change. `config/settings.py` gains no new required env
  vars — tests read `RAZORPAY_KEY_ID`/`SECRET` from the environment the same way the
  app already does, and skip live-mode assertions when they're absent.
- `README.md` gains a short "Running tests" section.
