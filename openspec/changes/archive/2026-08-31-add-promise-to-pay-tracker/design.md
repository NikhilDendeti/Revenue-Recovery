## Context

See `proposal.md` - Why for motivation. Relevant current-state facts this design builds
on:

- `trigger_voice_showcase` (`backend/recovery/tasks.py`) already computes a promise
  date (`(timezone.now() + timedelta(days=3)).date().isoformat()`) and writes it only
  into an `AuditLogEntry.payload` and a WS `voice` push. Nothing reads it back later.
- `ScheduledAction` (`backend/recovery/models.py`) is the existing precedent for
  "a DB row + a Beat-swept periodic task" instead of a raw multi-day Celery ETA task. It
  carries a partial unique constraint — one `pending` row per transaction — enforced at
  the DB level, and callers use `update_or_create` to respect it.
- `evaluate_guardrails(txn, diagnosis, decision)` (`backend/recovery/guardrails.py`) is
  a pure function of a transaction plus a `Diagnosis`-shaped and `Decision`-shaped
  object: it only reads `diagnosis.confidence` and `decision.chosen_action` (plus fields
  on `txn` itself). It never saves either argument. Its six rules run in a fixed order;
  rules 1-3 can set `escalate = True` and short-circuit immediately after; rules 4-6 can
  currently only set `hold_until`/`hold_reason` — none of them can escalate today.
- `dispatch_scheduled_action` already has a fallback for a transaction with no
  `Diagnosis` yet (`confidence = 0.5`) — the sweep task added here reuses that pattern
  rather than inventing a new one.
- `_execute_action(txn, Decision.Action.ESCALATE, confidence)` is the single existing
  entry point that resolves a transaction to `ESCALATED`, writes the `Action` +
  audit entry, and pushes the ticker event — every escalation path in the codebase
  (guardrail, API-failure, unexpected-error) already funnels through it.

## Goals / Non-Goals

**Goals:**
- Make a promise-to-pay a durable, queryable row, not audit-log prose.
- Resolve it automatically (kept/broken) via the same Beat-sweep shape as
  `ScheduledAction`, so it survives a worker restart.
- Make a broken promise change real guardrail behavior (escalate) for that customer's
  next contact attempt, via an extension of the existing `contact_frequency_cap` rule —
  not a bolted-on side channel that bypasses `evaluate_guardrails`.
- Surface the kept/broken signal in the batch summary and a small dashboard panel.

**Non-Goals:**
- No manual/B2B promise-creation UI or endpoint in this change. The model's
  `source=manual` value exists for forward compatibility only; every promise created by
  this change has `source=voice`.
- No backfill of `PromiseToPay` rows from historical `voice_promise_to_pay` audit
  entries. The tracker starts counting from the point this change ships.
- No new WebSocket event type for promise resolution. `promise_kept_rate` already rides
  the existing `ticker` push (it's just one more field inside the `compute_summary()`
  payload every ticker event already carries); the promise list/count panel fetches over
  REST. A broken-promise escalation is still visible live through the *existing*
  escalation path (`_execute_action` already pushes a ticker event and writes an audit
  entry) — only the promise-status list itself doesn't push live.
- No changes to the per-transaction reasoning-chain dialog (`TransactionChainSerializer`,
  the chain dialog UI). The tracker is a separate, standalone panel, matching the
  proposal's "small frontend tracker panel" scope.
- No new guardrail rule name. The broken-promise check extends `contact_frequency_cap`'s
  existing logging and branch, per the proposal's recorded assumption.

## Decisions

### 1. `PromiseToPay` model shape and constraint
Fields exactly as scoped in the proposal: `transaction` (FK, `related_name="promises"`),
`promised_amount` (`DecimalField`, same precision as `Transaction.amount`),
`promise_date` (`DateField` — the existing code already truncates to a date via
`.date().isoformat()`, so a `DateTimeField` would just invite an unused time component),
`source` (`TextChoices`: `voice`, `manual`), `status` (`TextChoices`: `pending`, `kept`,
`broken`, default `pending`), `created_at` (`auto_now_add`).

Add a partial unique constraint — one `pending` `PromiseToPay` per transaction — mirroring
`ScheduledAction`'s `one_pending_scheduled_action_per_txn`. `trigger_voice_showcase`
creates the row via `update_or_create(transaction=txn, status=PENDING, defaults=...)`,
so re-triggering the voice showcase for the same transaction (the showcase button has no
guard against repeat clicks) replaces the pending promise rather than accumulating
duplicates that would each independently resolve later.

*Alternative considered*: no uniqueness constraint, let every trigger create a new row.
Rejected — it would let the same transaction carry N pending promises with different
dates, which makes "resolve past-due pending promises" ambiguous about which one is
authoritative, and duplicates the exact bug class `ScheduledAction`'s constraint already
exists to prevent.

No `resolved_at` field: the audit-log entry written at resolution time already carries a
timestamp, so a second timestamp on the row itself would be redundant for this change's
scope.

### 2. Sweep task cadence and idempotency
New task `sweep_promises_to_pay`, added to `CELERY_BEAT_SCHEDULE` next to
`sweep-scheduled-actions`, same 30-second demo-friendly cadence (`schedule: 30.0`) for
consistency with the existing entry and so a demo operator flipping a transaction to
`RECOVERED` sees the promise flip to `kept` without a long wait. The query
(`status=PENDING, promise_date__lte=timezone.localdate()`) is naturally idempotent: a
row leaves the `pending` state the first time it's processed, so a task overlap or retry
can't double-resolve it — the same shape `sweep_scheduled_actions` already relies on.

*Alternative considered*: a longer interval (e.g. 5 minutes), since promise dates are
day-granularity and don't need 30-second freshness in production. Rejected for this
change — a second, differently-tuned cadence adds a config knob with no demo benefit;
revisit only if Beat load ever becomes a real concern.

### 3. Re-running `evaluate_guardrails` from the sweep
When a promise resolves to `broken`, the sweep needs a `Diagnosis`-shaped and
`Decision`-shaped object to call `evaluate_guardrails(txn, diagnosis, decision)`, exactly
as every other caller does. It builds them the same way `dispatch_scheduled_action`
already does for a transaction with no fresh diagnosis:

- `diagnosis`: `txn.diagnoses.latest("agent_run_at")`, falling back to a stand-in with
  `confidence=0.5` if none exists yet.
- `decision`: `txn.decisions.latest("decided_at")` if one exists **and** its
  `chosen_action` is already a contact action; otherwise an **unsaved**
  `Decision(chosen_action=Decision.Action.VOICE_REMINDER)` instance. `evaluate_guardrails`
  never persists the decision object it's given (it only reads `.chosen_action`), so
  constructing one in memory writes no extra row. `VOICE_REMINDER` is the right stand-in
  because every promise this change creates originates from the voice channel.

This reuses the *exact* function guardrail evaluation everywhere else uses — the
contact-frequency branch's new broken-promise check (Decision 4) is what actually
produces the escalation; the sweep task does not decide to escalate on its own.

To avoid a no-op re-escalation, the sweep skips this re-evaluation when
`txn.status` is already `ESCALATED` (marking the promise `broken` still happens; only the
redundant guardrail re-run is skipped). `FAILED`/`HELD`/`OPEN`/`PROCESSING` transactions
still get re-evaluated and escalated — a broken promise is new information even on top
of an existing failure or hold.

### 4. Extending `contact_frequency_cap`, not adding a rule
Inside `evaluate_guardrails`'s existing `if decision.chosen_action in CONTACT_ACTIONS:`
branch, add an independent check — "does this customer have any unresolved `broken`
`PromiseToPay` (`PromiseToPay.objects.filter(transaction__customer_id=txn.customer_id,
status=BROKEN).exists()`)" — alongside the existing cooldown-timestamp check. Both use
the same `_log(txn, "contact_frequency_cap", ...)` call site (extended detail text), so
no seventh rule name appears in the Guardrail Console or the six-rule test-coverage
requirement. The two conditions are independent (either can block); the broken-promise
condition sets `escalate = True` where the timestamp condition sets `hold_until`.

Because escalation from a rule *after* rule 3 didn't previously exist, the function's
tail is restructured from:
```
if hold_until: return ...(hold)
return ...(cleared)
```
to check `escalate` again first:
```
if escalate: return ...(escalate)
if hold_until: return ...(hold)
return ...(cleared)
```
This is additive to existing behavior: rules 4-6 never set `escalate` before this change,
so every existing scenario (including the "held, not escalated" card-decline-cooldown and
plain-cooldown scenarios already covered by `automated-testing`) is unaffected — only the
new broken-promise condition can take this new branch.

*Alternative considered*: a standalone seventh guardrail rule
(`broken_promise_check`) evaluated before the escalate-early-return (like rules 1-3).
Rejected per the proposal's explicit instruction to extend the existing rule rather than
add a new one, and because the six-rule enumeration is itself asserted by the existing
`automated-testing` spec ("Guardrail rules have independent automated coverage") — adding
a rule would be a spec-level change to that requirement, not just this one.

### 5. `promise_kept_rate` in `compute_summary()`
`kept = PromiseToPay.objects.filter(status=KEPT).count()`,
`broken = PromiseToPay.objects.filter(status=BROKEN).count()`,
`promise_kept_rate = round(kept / (kept + broken) * 100, 1) if (kept + broken) else 0.0`
— same "guard the zero-denominator case" shape `recovery_rate` already uses in the same
function.

### 6. API surface
A `PromiseToPaySerializer` (`id`, `transaction`, `promised_amount`, `promise_date`,
`source`, `status`, `created_at`) and a `PromiseToPayViewSet(viewsets.ReadOnlyModelViewSet)`
with `filterset_fields = ["status", "transaction"]`, registered at
`promises-to-pay` — the same read-only shape as `ScheduledActionViewSet`. Behind the
dashboard's existing JWT auth (it's an operator-facing list, not a webhook receiver), no
different from every other `ViewSet` in `views.py` besides `WebhookView`.

### 7. Frontend panel
A new component (`frontend/src/components/PromiseTracker.jsx`) built on
`ui/Surface`'s `Panel`, `ui/Badge`, and `ui/EmptyState` — pending/kept/broken counts as
three small `Badge`s in the panel header (mirroring `GuardrailConsole`'s
blocked/total count in its `actions` slot) and the promise list as the panel body, one
row per promise (transaction customer, promised amount, promise date, status badge).
Fetched once on mount via a new `api.promisesToPay()` call (`GET /promises-to-pay/`),
with a manual retry control on failure — matching the existing
loading/empty/error contract every other panel already follows (`recovery-room-ui`'s
"every asynchronous surface" requirement, unmodified by this change since the panel is
new, not a redesign of an existing one). Placed in `Dashboard.jsx` alongside the other
panels; exact placement (e.g., beside `GuardrailConsole` vs. its own row) is a layout
detail for `tasks.md`/implementation, not a spec-level concern.

## Risks / Trade-offs

- **[Risk]** A promise resolving to `broken` on an already-`FAILED` or `HELD`
  transaction re-runs `evaluate_guardrails` and may escalate a transaction that a human
  might have preferred to leave `HELD` a while longer. → **Mitigation**: this matches the
  proposal's explicit intent ("a broken promise must not receive another nudge without
  escalation") — a broken promise is new, human-worthy information regardless of the
  transaction's prior state; only the already-`ESCALATED` case is special-cased to avoid
  pure noise (Decision 3).
- **[Risk]** Constructing an unsaved `Decision(chosen_action=VOICE_REMINDER)` as a
  stand-in for guardrail re-evaluation could mask a real, different chosen action if a
  future manual/B2B promise path is added without revisiting this fallback. →
  **Mitigation**: `manual` sourcing is explicitly out of scope for this change (Non-Goals);
  the fallback is documented in code and in this design doc as voice-specific, so the
  future change that adds manual creation is expected to revisit this exact spot.
- **[Risk]** Adding an `escalate`-check to the tail of `evaluate_guardrails` changes a
  15-line function's control flow that six existing guardrail tests already cover tightly.
  → **Mitigation**: the change is additive (an extra early-return that nothing currently
  reaches); the existing per-rule tests continue to exercise the unchanged rules 1-6
  behavior, and new tests cover only the new branch.

## Migration Plan

1. Add the `PromiseToPay` model and its migration (new `PromiseToPay` table + the
   partial-unique constraint; no data migration/backfill — see Non-Goals).
2. Wire `trigger_voice_showcase` to create the row; extend `guardrails.py` and
   `evaluate_guardrails`'s tail; add the sweep task and its `CELERY_BEAT_SCHEDULE` entry.
3. Add `promise_kept_rate` to `compute_summary()`.
4. Add the serializer/viewset/route.
5. Add the frontend panel and API client call.

Each step lands independently testable (model → task → guardrail → analytics → API →
UI), matching `tasks.md`'s ordering. Rollback is a straight revert — nothing in this
change mutates existing data or existing guardrail behavior for the cases already under
test.

## Open Questions

None — the questions that came up while designing this (whether "unresolved" means
"not recovered" for any other status, and how the sweep should re-invoke
`evaluate_guardrails` without a real `Decision`) are resolved above (Decisions 1 and 3)
rather than deferred, since both would otherwise change the spec or the task breakdown.
