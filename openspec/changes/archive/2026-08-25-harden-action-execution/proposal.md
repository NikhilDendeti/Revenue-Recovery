## Why

The action-execution layer has no failure handling. `_execute_action` calls
`_call_razorpay` with no guard, and neither `process_transaction_event` nor
`dispatch_scheduled_action` wraps its pipeline body, so any Razorpay API error — a 404
from a stale or never-created ID, a transient 5xx, a network timeout — propagates
uncaught: the Celery task crashes and the transaction is stranded in `PROCESSING`, which
the idempotency guard then permanently blocks from reprocessing. This is asymmetric with
the LLM path, which already degrades to a heuristic on failure. It also turns the
documented "known gap" (seed_data's synthetic `order_sim_...` IDs, and receivables with
no invoice ID, 404 against live keys) into a transaction wedge rather than a clean
failure — making the product unsafe to run against real Razorpay test-mode keys.

## What Changes

- Guard the Razorpay call in `_execute_action` so an API failure resolves the
  transaction to a **defined terminal state** — escalation to the human queue — with an
  audit-log entry and a live ticker push, never a stranded `PROCESSING` row.
- Add a **top-level safety net** in the pipeline tasks (`process_transaction_event`,
  `dispatch_scheduled_action`) so any otherwise-uncaught exception moves the transaction
  out of `PROCESSING` into escalation with an audit trail, rather than leaving it wedged.
- On a **resource-not-found (404-class)** error for the `retry_order` / `invoice_reminder`
  paths — a stale or never-created order/invoice ID — **fall back to issuing a fresh
  payable artifact** (a new payment link) instead of escalating, so seeded data (and any
  stale ID) works against live Razorpay keys. This closes the documented seed_data gap
  without seed_data itself making live API calls.
- Add tests covering escalation-on-API-failure, the 404 fallback path, and the guarantee
  that no failure path leaves a transaction in `PROCESSING`.

Invariants preserved: the audit log stays append-only (failures write **new** rows,
never mutate); guardrails stay deterministic Python (this is execution-layer error
handling, not a new guardrail — nothing here calls an LLM); and no code assumes a
force-retry endpoint (the fallback is a fresh payable artifact, exactly the existing
Razorpay model).

## Capabilities

### New Capabilities
- `action-execution`: How the system executes a decided recovery action against Razorpay
  and resolves the transaction's outcome — including how API failures are handled so a
  transaction always reaches a defined state (recovered, failed, or escalated) and never
  remains stuck mid-execution.

### Modified Capabilities
<!-- None. No existing capability's requirements change; this introduces new behavior. -->

## Impact

- **Code**: `backend/recovery/tasks.py` (`_execute_action`, `_call_razorpay`,
  `process_transaction_event`, `dispatch_scheduled_action`),
  `backend/recovery/razorpay_client.py` (surface a distinguishable not-found error so the
  fallback can tell a 404 apart from a transient failure),
  `backend/recovery/tests/test_tasks.py` (new API-failure-path tests).
- **Behavior**: transactions can now reach `ESCALATED` via an API-failure path (in
  addition to guardrail escalation); a distinct audit `event_type` separates
  API-failure escalation from guardrail escalation so the two are legible in the audit
  trail.
- **No** schema/migration changes, **no** REST/WS contract changes, **no** new
  dependencies.
- **Runtime**: with live `RAZORPAY_KEY_ID`/`RAZORPAY_KEY_SECRET` set, seeded
  transactions no longer 404-wedge — they either fall back to a fresh payment link or
  escalate cleanly; offline (simulated) mode is unchanged.
