## Why

`trigger_voice_showcase` currently writes the customer's promise-to-pay date into a
single audit-log payload and stops there — nothing ever checks whether the promise was
kept, and a customer who ghosts the promised date gets no different treatment than one
who never promised anything. That silently defeats the point of tracking a promise at
all, and it means a broken promise can be re-nudged by the exact same voice/contact
channel, which the guardrail layer is supposed to bound. This change makes
"promised to pay" a first-class, resolvable commitment — for the voice channel today,
and for manual B2B follow-ups later — so it can be tracked, swept, escalated on breach,
and reported on, instead of living only as prose inside one audit entry.

## What Changes

- New `PromiseToPay` model (`backend/recovery/models.py`): `transaction` FK,
  `promised_amount`, `promise_date`, `source` (`voice` / `manual`), `status`
  (`pending` / `kept` / `broken`), `created_at`.
- `trigger_voice_showcase` (`backend/recovery/tasks.py`) creates a `PromiseToPay` row
  (`source=voice`) alongside its existing audit entry, instead of only recording the
  promise date as unstructured payload text.
- New Beat-swept periodic task, `sweep_promises_to_pay`, added to the Celery Beat
  schedule next to the existing `sweep_scheduled_actions` (same "a DB row + a periodic
  sweeper, not a raw multi-day ETA task" pattern). For every `pending` promise whose
  `promise_date` has passed:
  - if the transaction is now `RECOVERED`, mark the promise `kept`;
  - otherwise mark it `broken` and re-run `evaluate_guardrails()` for that transaction
    so the existing decision/escalation machinery — not the sweep task itself —
    resolves the consequence.
- `guardrails.py`'s contact-frequency check is **extended, not bypassed**: a customer
  with any unresolved `broken` promise fails that check even when the 24h cooldown
  timestamp alone would pass, and the outcome is escalation rather than a silent hold —
  a customer is not queued for another voice/contact nudge without a human seeing it
  first.
- `recovery/analytics.py::compute_summary()` gains `promise_kept_rate` (kept ÷
  (kept + broken) among resolved promises; `0` when none are resolved yet), so it rides
  along with the existing batch-level recovered-money metrics.
- New read-only DRF endpoint + serializer for `PromiseToPay` (list, filterable by
  `status`/`transaction`), following the existing `ScheduledActionViewSet` pattern, plus
  a corresponding `api.js` client call.
- New frontend tracker panel built from the existing `Surface`/`Badge`/`EmptyState`
  primitives: pending/kept/broken counts and a list of promises.
- Full automated test coverage: the model itself, the sweep task's kept/broken
  branching, the guardrail interaction (broken promise → blocked contact → escalation),
  and the API/serializer.

**Assumptions recorded here rather than left implicit** (flagged for review, not
blocking):
- "Still unresolved" at sweep time is read literally as "transaction status is anything
  other than `RECOVERED`" — including `ESCALATED`, `FAILED`, `HELD`, or still
  `OPEN`/`PROCESSING` — all mark the promise `broken`, not just an explicit failure.
- Marking a promise `broken` and the resulting guardrail escalation each append a new
  `AuditLogEntry` (never mutate the `PromiseToPay` row's own history) — consistent with
  the append-only audit invariant, and needed for the reasoning-chain view to show why a
  transaction escalated.
- The contact-frequency extension escalates immediately on a blocked broken-promise
  check (the decision path already distinguishes escalate from hold); it does not
  introduce a seventh guardrail rule name — it extends `contact_frequency_cap`'s
  existing check and logging.

## Capabilities

### New Capabilities
- `promise-to-pay-tracking`: tracks promise-to-pay commitments from creation (voice
  today, manual later) through resolution (kept/broken), routes a broken promise through
  guardrail escalation instead of a fresh nudge, contributes a kept-rate metric to the
  batch summary, and exposes the tracker via a read-only API and a dashboard panel.

### Modified Capabilities
- `automated-testing`: adds a requirement that promise-to-pay tracking (model, sweep
  task, guardrail interaction, API/serializer) has independent automated test coverage,
  following the same per-capability coverage pattern already used for guardrail rules
  and the pipeline.

## Impact

- **Backend**: new `PromiseToPay` model + migration; `backend/recovery/tasks.py`
  (`trigger_voice_showcase` change, new `sweep_promises_to_pay` task); Celery Beat
  schedule config; `backend/recovery/guardrails.py` (contact-frequency extension);
  `backend/recovery/analytics.py` (`promise_kept_rate`); `backend/recovery/serializers.py`
  + `views.py` + URL routing (new read-only viewset); new/updated tests under
  `backend/recovery/tests/`.
- **Frontend**: new tracker panel component under `frontend/src/components/` built on
  `frontend/src/components/ui/{Surface,Badge,EmptyState}.jsx`; a new `api.js` client
  call; wiring into the dashboard's data hook (`useRecoveryRoom.js`) and layout.
- **No change** to the append-only audit-log mechanics — `PromiseToPay` is an ordinary
  mutable row (its own `status` transitions), not an audit entry; a promise being
  created or broken continues to be *recorded* via a new, appended `AuditLogEntry`.
- **No change** to any Razorpay call shape — this feature tracks an outcome that already
  exists (the voice moment's promise date); it introduces no new provider-facing action.
