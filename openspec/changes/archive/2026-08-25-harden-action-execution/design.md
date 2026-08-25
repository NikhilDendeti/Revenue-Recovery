## Context

See `proposal.md` — Why. The relevant current state:

- `recovery/tasks.py::_execute_action` calls `_call_razorpay(txn, action_type)` on its
  first line with no error handling, then unconditionally creates an `Action` row and
  flips the transaction to `RECOVERED`/`FAILED`.
- `recovery/tasks.py::process_transaction_event` sets the transaction to `PROCESSING`
  up front (and audits `"detected"`), then runs diagnose → decide → guardrails → act
  with no surrounding `try`. `dispatch_scheduled_action` is the same shape for the
  delayed path. Its idempotency guard (`if txn.status != OPEN: return`) means a
  transaction left in `PROCESSING` by a crash can never be reprocessed.
- `recovery/razorpay_client.py::_post` raises `RazorpayError(f"{path} -> {code}: {text}")`
  — the HTTP status is only in the string, not structured. In simulated mode (no keys)
  every client function returns a dict and never raises, so all failure paths below are
  reachable only with live keys or a forced error in tests.
- Escalation already exists: `_execute_action(txn, Decision.Action.ESCALATE, conf)`
  sets `status = ESCALATED`, appends an `"escalated"` audit entry, and pushes an
  `escalated` ticker event. The `ESCALATE` branch calls `_call_razorpay`, which for
  `ESCALATE` returns a static simulated dict and never hits the network — so reusing it
  as the failure resolution cannot itself raise.

## Goals / Non-Goals

**Goals:**
- No execution error — expected (`RazorpayError`) or unexpected — can leave a
  transaction in `PROCESSING`.
- A stale/never-created order or invoice id (the seed_data gap) degrades to a fresh
  payable artifact instead of failing.
- The failure resolution is legible in the audit trail and on the ticker, and distinct
  from a guardrail escalation.

**Non-Goals:**
- No bounded-retry / exponential-backoff mechanism for transient API errors — a
  transient failure escalates to a human this iteration. A backoff design is a separate
  follow-up.
- No change to `seed_data` (it stays offline-only and network-free).
- No change to simulated-mode behavior, the guardrail logic, the audit-log trigger, or
  any REST/WS contract.

## Decisions

### Decision 1: Two-layer error handling — inner (per-action) + outer (safety net)
- **Inner**, in `_execute_action`: wrap the `_call_razorpay` call. This layer has the
  transaction and action type in hand, so it can (a) do the 404 fallback and (b)
  escalate with a precise, action-specific audit reason.
- **Outer**, in `process_transaction_event` and `dispatch_scheduled_action`: a
  `try/except` around the pipeline body that, on any otherwise-unhandled exception,
  moves the transaction to `ESCALATED` with an audit entry. This guarantees the
  "never stuck in `PROCESSING`" invariant even for bugs outside the Razorpay call
  (e.g. a future action type, an ORM error).
- **Alternative considered — outer catch only:** rejected. It cannot perform the 404
  fallback (no per-action context) and would produce a generic reason for every
  failure. The inner layer is what closes the seed_data gap.

### Decision 2: Escalate on unrecoverable failure (not FAILED, not auto-reschedule)
Reuse the existing `ESCALATE` resolution for an API failure that no fallback recovers.
- **vs. marking `FAILED`:** `FAILED` means "we acted and the customer didn't pay" — it
  would misreport an infrastructure error as a customer non-payment and pollute the
  recovery-rate metric. An operator should see it, so escalation is correct.
- **vs. auto-rescheduling** via a `ScheduledAction`: risks silent repeated failures with
  no bounded backoff (out of scope, see Non-Goals). Escalation surfaces the problem to a
  human immediately, which is the safer default.

### Decision 3: Fall back to a fresh payment link on a 404, over seeding real artifacts
For a resource-not-found response on `retry_order`/`invoice_reminder`, issue a new
payment link (`razorpay_client.create_payment_link`) and continue to the normal
outcome.
- **vs. seeding real Orders/Invoices in `seed_data`:** rejected. That makes `seed_data`
  network-dependent, only works with keys set, and creates real artifacts on Razorpay's
  side on every seed run. The fallback is self-contained, preserves the offline-first
  posture, and hardens against *any* stale id — not just seeded ones.
- Consistent with the "no force-retry endpoint" invariant: the fallback is a fresh
  payable artifact, exactly the model the rest of the system already uses.

### Decision 4: Give `RazorpayError` a structured status code
Attach the HTTP status to the exception (e.g. a `status_code` attribute set in `_post`)
so `_execute_action` can branch on 404 directly. **Alternative — string-parse the
message:** rejected as brittle. This is a minimal, backward-compatible addition.

### Decision 5: A distinct audit `event_type` for API-failure escalation
Emit a new event type (e.g. `action_failed`) — separate from the guardrail-driven
`escalated` — carrying the failing action, the error detail, and (for the fallback
case) a note that a fresh artifact was substituted. The ticker push keeps
`outcome="escalated"`. No new `GuardrailEvent` is written for an API failure: a Razorpay
error is not a compliance decision, and manufacturing a guardrail event would blur the
"guardrails are deterministic compliance" line. Live surfacing is via the ticker + audit
trail, which is what the dashboard already renders.

## Risks / Trade-offs

- **Fallback substitutes the channel** (an invoice reminder becomes a payment link) →
  Acceptable: a fresh payable artifact is still a valid recovery, and the substitution
  is recorded in the audit payload so it's not silent.
- **Escalating every transient error** could turn a provider outage into a flood of
  escalations → Acceptable at hackathon scale; bounded backoff is an explicit Non-Goal
  and documented as a follow-up.
- **Contact-cooldown already consumed before an escalation** — the contact-frequency
  guardrail records the nudge before execution, so an escalate-on-failure leaves the
  24h slot "spent" without a message sent. Pre-existing, rare (escalations are
  human-reviewed), and not worsened by this change; noted, not fixed here. The fallback
  path still sends a real contact, so its cooldown consumption stays correct.

## Migration Plan

Pure code + tests — **no database migration**, no data backfill, no contract change.
Deploy is a normal code deploy; rollback is a plain revert. Offline/simulated mode is
byte-for-byte unaffected (the new branches are unreachable without live keys or a
test-forced error), so the deterministic demo and the existing 71-test suite behavior
are preserved, with new tests added on top.
