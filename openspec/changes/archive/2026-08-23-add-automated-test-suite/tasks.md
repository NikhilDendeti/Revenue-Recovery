## 1. Setup

- [x] 1.1 Add `pytest`, `pytest-django`, `pytest-asyncio` to `backend/requirements.txt` and verify `pip install -r requirements.txt` succeeds
- [x] 1.2 Add `backend/pytest.ini` pointing `DJANGO_SETTINGS_MODULE=config.settings` and test discovery at `recovery/tests` and `agents/tests`, and verify `pytest --collect-only` runs with zero errors
- [x] 1.3 Add `backend/conftest.py` with shared fixtures (a seeded `Transaction` factory helper, a `razorpay_live` skip-marker fixture keyed on `RAZORPAY_KEY_ID`/`SECRET` presence) and verify it imports cleanly
- [x] 1.4 Create `backend/recovery/tests/__init__.py` and `backend/agents/tests/__init__.py`

## 2. Guardrail tests

- [x] 2.1 Write `backend/recovery/tests/test_guardrails.py` covering confidence floor (blocked + passed), max retry attempts (blocked + passed) and verify both pass with `pytest recovery/tests/test_guardrails.py -k confidence or max_retry`
- [x] 2.2 Add spend/action ceiling (blocked + passed) and cooldown-between-retries (blocked with future `run_after`, passed for non-card codes) cases to the same file and verify they pass
- [x] 2.3 Add contact-frequency-cap cases including a same-customer concurrent-evaluation race check (two evaluations for one customer inside overlapping transactions, only one may pass), and compliance-hours (blocked outside window, passed inside) and verify the full file passes: `pytest recovery/tests/test_guardrails.py -v` — 15/15 passing, race test stable across 5 runs

## 3. Diagnosis/decision pipeline tests

- [x] 3.1 Write `backend/agents/tests/test_pipeline.py` asserting the heuristic diagnosis table's failure-code matches (insufficient_funds, card_declined, expired, timeout/network, blank code -> low confidence) and verify with `pytest agents/tests/test_pipeline.py`
- [x] 3.2 Add the subscription-vs-payment-degradation regression test: a `subscription_failure` transaction with a card-decline-pattern failure code SHALL decide `registration_link`, never `retry_order`; a `payment_degradation` transaction with the same failure code SHALL decide `retry_order`
- [x] 3.3 Add the low-confidence/unknown-root-cause escalation case and verify the full file passes — 14/14 passing. Also found and documented (not fixed, out of scope) a pre-existing rule-ordering quirk: "card_declined_expired" always classifies as card_declined, never card_expired, since the "card_declined" rule is checked before "expired" and matches by substring — see test_diagnosis_rule_order_card_declined_beats_expired_on_overlap

## 4. Append-only audit log test

- [x] 4.1 Write `backend/recovery/tests/test_audit_log.py` asserting a normal `AuditLogEntry.objects.create(...)` succeeds
- [x] 4.2 Add a raw-SQL `UPDATE recovery_auditlogentry ...` test inside a nested atomic block, asserting Postgres raises and the row is unchanged afterward
- [x] 4.3 Add the equivalent raw-SQL `DELETE` test and verify the whole file passes: `pytest recovery/tests/test_audit_log.py -v` — 5/5 passing (also added ORM-level save()/delete() guard tests)

## 5. Razorpay client tests

- [x] 5.1 Write `backend/recovery/tests/test_razorpay_client.py` asserting every client function returns `simulated: true` and makes no HTTP call when credentials are unset (mock/monkeypatch `requests.post` to fail the test if called)
- [x] 5.2 Add a live-mode test marked to skip when `RAZORPAY_KEY_ID`/`SECRET` are absent, that calls `create_payment_link`, asserts a real `id` and `short_url` come back, then cancels the link via the Razorpay cancel endpoint
- [x] 5.3 Run with real keys present (they are, in this environment) and verify the live test passes and the created Payment Link is cancelled afterward — 7/7 passing, live test ran (not skipped), cancel confirmed status=cancelled

## 6. Pipeline / Celery task integration tests

- [x] 6.1 Write `backend/recovery/tests/test_tasks.py::test_process_transaction_event_cleared` — a high-confidence, low-amount, non-cooldown transaction ends in `recovered` or `failed` status with a matching `Action` and audit entries, called as `process_transaction_event(str(txn.id))` directly (no worker)
- [x] 6.2 Add `test_process_transaction_event_held` — a card-decline transaction produces exactly one pending `ScheduledAction` and the transaction status is `held`
- [x] 6.3 Add `test_process_transaction_event_escalated` — a low-confidence or over-ceiling transaction is escalated and no `ScheduledAction` is created
- [x] 6.4 Add `test_sweep_scheduled_actions` — a `ScheduledAction` with `run_after` in the future is not dispatched by the sweeper; one with `run_after` in the past is dispatched and its status becomes `dispatched`
- [x] 6.5 Add a `test_trigger_voice_showcase` asserting an `Action` (type voice) and an `AuditLogEntry` (event_type voice_promise_to_pay) are created, and verify the full file passes — 8/8 passing (also added an idempotency test and a direct dispatch_scheduled_action test)

## 7. REST API tests

- [x] 7.1 Write `backend/recovery/tests/test_api.py` using DRF's `APIClient` covering: transaction list, transaction chain detail, summary, guardrail-events list, scheduled-actions list — each asserts HTTP 200 and the expected top-level shape
- [x] 7.2 Add audit-log endpoint tests: list/retrieve succeed (200); POST/PUT/PATCH/DELETE against it are rejected (405) and create/modify/remove nothing
- [x] 7.3 Add batch-replay-trigger (202, queues a task) and webhook-ingestion (valid event creates a Transaction and enqueues processing; unrecognized event returns 400) tests and verify the full file passes — 13/13 passing. Surfaced (not fixed, out of scope) a `django.core.paginator` `UnorderedObjectListWarning` on `ScheduledAction` — it has no `Meta.ordering`, so paginated listing isn't guaranteed stable across pages

## 8. WebSocket test

- [x] 8.1 Write `backend/recovery/tests/test_consumers.py` using `channels.testing.WebsocketCommunicator` against `config.asgi.application`: connect, call `recovery.ws.push("ticker", {...})` from the test, and assert the client receives a matching `{"type": "ticker", "payload": {...}}` message via `receive_json_from()` — 2/2 passing (ticker + guardrail events)

## 9. Full run and docs

- [x] 9.1 Run the entire suite from `backend/`: `pytest -v` and verify every test passes (the live Razorpay test runs, not skips, since keys are configured in this environment) — 64/64 passing, run twice for stability, and re-verified the live test skips cleanly (63 passed, 1 skipped) when RAZORPAY_KEY_ID/SECRET are cleared from the environment
- [x] 9.2 Add a "Running tests" section to `README.md` documenting `pytest` from `backend/`, and that the live Razorpay test auto-skips without credentials
