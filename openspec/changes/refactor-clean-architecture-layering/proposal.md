## Why

All of this system's real business logic lives in `backend/recovery/tasks.py` — 364 lines
that simultaneously hold ORM writes, Razorpay HTTP calls, WebSocket pushes, the outcome
random draw, every business branch in the recovery pipeline, and the Celery transport
decorators. `recovery/guardrails.py` has the same shape at smaller scale: six compliance
rules interleaved with `GuardrailEvent.objects.create()` calls and a `select_for_update()`
transaction.

Three concrete costs follow from that, and they are all visible in the existing test suite:

- **The business rules cannot be tested without a database.** Every one of the 14 tests in
  `test_tasks.py` is a `django_db` test that drives a Celery task end to end. The single
  most important expression in the money path — `random.random() < min(0.95, max(0.05,
  confidence))` — has no test asserting its actual boundaries, because there is no seam to
  supply the draw.
- **The pipeline re-reads its own writes.** `_run_recovery_pipeline` queries
  `GuardrailEvent.objects.filter(transaction=txn).order_by("-triggered_at")[:6]` twice in
  a row — once to populate `decision.guardrail_checks_passed`, once to push the WebSocket
  frames — with a magic `[:6]` that silently truncates. Meanwhile `GuardrailVerdict.events`
  already exists as a field and is dead: `evaluate_guardrails` never populates it.
- **Tests couple to private helpers.** `test_tasks.py` patches `recovery.tasks._call_razorpay`
  in five places and imports `_execute_action` at module level, so the module's private
  surface is load-bearing public API and cannot be refactored without breaking the suite.

There is no seam between "decide what to do" and "talk to the outside world", so the second
cannot be substituted in order to test the first.

## What Changes

Apply a views / presenters / storages / interactors layering **only to code paths that
change the world** — that write a row, call an external system, branch on a business rule,
or are reachable from more than one transport. That is `recovery/tasks.py`,
`recovery/guardrails.py`, and exactly one HTTP handler (`WebhookView.post`).

- **Interactors** hold the use cases, as pure Python that imports no Django, no Celery, no
  `requests`, no `random`, and — enforcing the guardrail invariant mechanically — no
  `agents` or `langgraph`.
- **Storages** become the only place the Django ORM is touched, and the only place
  `atomic()` / `select_for_update()` may appear.
- **Ports and adapters** wrap the four things the outside world provides: the payment
  gateway, the diagnosis pipeline, the task queue, and the clock/randomness runtime.
- **Presenters** own response and frame shaping, including the WebSocket frames — `ws.push`
  is modelled as an output port injected into the use case, not a side effect reached from
  inside it.
- **The seven read-only `ReadOnlyModelViewSet`s are deliberately left alone.** DRF's
  serializer already *is* an adequate presenter for a read path that branches on nothing.
  The placement rule is written down so this is a stated boundary, not an omission.

Two behaviour changes are in scope, both deliberate and both flagged:

- `GuardrailVerdict` carries the checks it produced, so the pipeline stops re-querying
  `GuardrailEvent` twice and the magic `[:6]` truncation is removed. A transaction that
  evaluates fewer than six rules (any escalation short-circuit, or any non-retry action)
  now records exactly the checks that actually ran, rather than the six most recent rows
  by timestamp.
- A new `RECOVERY_OUTCOME_SEED` setting makes the batch replay's outcome sequence
  reproducible across runs. Unset (the default), behaviour is byte-identical to today.

Invariants preserved, and now mechanically enforced rather than merely observed: the audit
log stays append-only (the storage port has no vocabulary for update or delete, and an
architecture test asserts exactly one module may import `AuditLogEntry`); guardrails stay
deterministic Python (the architecture test bans `agents` and `langgraph` from the rules
module); delayed actions stay `ScheduledAction` rows; and the cross-process WebSocket relay
is untouched — `recovery/ws.py`, `consumers.py`, `routing.py`, `auth_middleware.py` and
`config/asgi.py` are not modified at all, so Daphne's import graph cannot change.

## Capabilities

### New Capabilities
- `backend-layering`: How write-path code is organised across transports, interactors,
  storages, presenters and ports; which paths the layering applies to and which are
  deliberately exempt; and how the layer boundaries are mechanically enforced.

### Modified Capabilities
- `action-execution`: The outcome draw becomes an injectable, optionally-seedable port with
  the clamp expressed as a tested pure function; and the not-found fallback branches on a
  typed domain error rather than sniffing an HTTP status code.

## Impact

- **Code**: `backend/recovery/tasks.py` (reduced to transport shells),
  `backend/recovery/guardrails.py` (becomes a package with pure rules behind a
  signature-preserving facade), `backend/recovery/views.py` (`WebhookView.post` body only),
  `backend/recovery/management/commands/replay_batch.py`, plus new `dtos`, `exceptions`,
  `interfaces`, `interactors`, `storages`, `presenters`, `adapters`, `domain_rules` and
  `wiring` modules.
- **Not modified**: `models.py`, `migrations/`, `serializers.py`, `urls.py`, `admin.py`,
  `analytics.py`, `razorpay_client.py`, `ws.py`, `consumers.py`, `routing.py`,
  `auth_middleware.py`, `config/asgi.py`. The REST and WebSocket contracts are therefore
  preserved by construction rather than by promise.
- **Behavior**: the two flagged changes above. No other behaviour change is intended, and
  the existing suite is the evidence: it must stay at `79 passed, 1 skipped` throughout.
- **Tests**: six patch targets in `test_tasks.py` are retargeted from private helpers onto
  the `recovery.razorpay_client` module functions (which resolve at call time and therefore
  keep working); every assertion is kept verbatim. New DB-free unit tests are added for the
  guardrail rules, the outcome rule, and the action interactors.
- **No** schema/migration changes, **no** new dependencies, **no** frontend change.
