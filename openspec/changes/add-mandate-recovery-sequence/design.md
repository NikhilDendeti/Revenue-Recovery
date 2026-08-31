## Context

See `proposal.md` - Why for motivation. Relevant current-state facts this design builds on:

- `backend/agents/pipeline.py::_heuristic_decision` (and the LLM decision prompt) always
  map a retriable `subscription_failure` diagnosis to `registration_link`, and a
  non-retriable one straight to `escalate`. `run_pipeline(transaction_fields)` is a pure
  function over a plain dict — no step/sequence concept exists yet.
- `backend/recovery/tasks.py::_execute_action` is the single place an action's outcome is
  resolved: for any non-`escalate` action it rolls a confidence-weighted
  recovered/failed dice **immediately at execution time** and writes that as the
  transaction's terminal `RECOVERED`/`FAILED` status — there is no "sent, awaiting the
  customer" interim state today. This is the crux fact that shapes Decision 1 below.
- `_run_recovery_pipeline` (the step-0 path today) does: run pipeline → create
  Diagnosis + Decision rows → audit both → `evaluate_guardrails` → branch on
  escalate/hold/cleared. `dispatch_scheduled_action` (the existing cooldown-retry path)
  does **not** re-run `evaluate_guardrails` — it trusts that the guardrail's own
  `hold_until` already accounts for when the condition clears, and just calls
  `_execute_action` directly. This proposal's steps 1/2 must re-run guardrails, so they
  cannot reuse that existing dispatch path unchanged.
- `ScheduledAction` already enforces at most one `PENDING` row per transaction
  (`one_pending_scheduled_action_per_txn`), and `sweep_scheduled_actions` unconditionally
  flips due rows to `DISPATCHED` before handing them to `dispatch_scheduled_action` — both
  are reused as-is.
- `guardrails.CONTACT_ACTIONS` already includes `Decision.Action.VOICE_REMINDER`, so the
  contact-frequency-cap guardrail already applies to a voice/WhatsApp-style follow-up
  with no change to `guardrails.py`.
- `openspec/changes/refactor-clean-architecture-layering` is in-flight against the same
  files (`tasks.py`, `guardrails.py`) but only its vocabulary section (DTOs, exceptions,
  interfaces, fakes) is done — the interactor/adapter extraction itself hasn't started.
  This design targets today's flat `tasks.py`/`pipeline.py`, not the target layered shape.

## Goals / Non-Goals

**Goals:**
- Make "hasn't recovered" a real, re-checked condition rather than a fixed timer, using
  the transaction's own status as the source of truth at each step's fire time.
- Reuse every existing mechanism possible (`ScheduledAction`, `evaluate_guardrails`,
  `Action`/`Decision` models, the audit log, the WS ticker) rather than inventing
  parallel infrastructure.
- Keep step 0's existing behavior byte-for-byte unchanged for every transaction that
  recovers or escalates on the first attempt (the overwhelmingly common case) — the
  cadence only becomes observable once a first nudge fails.

**Non-Goals:**
- Reconciling the pre-existing gap where a plain guardrail-hold retry (e.g. the 48h
  card-decline cooldown) dispatches without re-checking guardrails. That behavior
  predates this change and is out of scope; only the *new* step transitions this
  proposal adds (step 0 → 1, step 1 → 2) get full re-evaluation.
- A real WhatsApp/voice provider integration. Step 1 reuses the existing simulated
  `Decision.Action.VOICE_REMINDER` / `Action.Type.VOICE` channel.
- Changing anything about `payment_degradation` or `receivable` transactions.

## Decisions

### 1. "Hasn't recovered" = the nudge action's own outcome roll came back FAILED
Rather than inventing a new non-terminal transaction status ("sent, awaiting customer"),
a step's "did it recover" check reuses `_execute_action`'s existing confidence-weighted
dice roll, just spread across the cadence instead of rolled once. Concretely: after a
nudge action (`registration_link` at step 0, `voice_reminder` at step 1) executes and
`_execute_action` writes its normal outcome,
- **`RECOVERED`** → the cadence ends successfully; the transaction's status is exactly
  what it would be today.
- **`FAILED`**, and a further step remains → a new hook (`_advance_mandate_sequence`,
  called right after every `_execute_action` call site) immediately re-opens the
  transaction to `HELD` and schedules the next step, before the Celery task returns. The
  transaction is visibly `FAILED` for zero externally-observable time; the dashboard only
  ever sees `HELD` in between steps.
- **`FAILED`**, and no further step remains — cannot occur: the last retriable step is
  step 1, and step 2 is always `escalate`, whose outcome is never a dice roll
  (`_execute_action` special-cases `ESCALATE` and never resolves it as recovered/failed).

**Alternative considered**: add a new `Transaction.Status` value (e.g. `AWAITING_CUSTOMER`)
and defer the dice roll to each step's re-check. Rejected — `Transaction.Status` is
matched against throughout the dashboard (filters, badge colors, the ticker), and adding
a value there is a much larger, higher-risk surface than reusing `HELD`, which already
means exactly "resolution is pending on a timer" everywhere else in the system.

### 2. One new model, `MandateSequence`, created lazily at step 0's first decision
```
MandateSequence
  transaction   OneToOneField(Transaction, related_name="mandate_sequence")
  current_step  PositiveSmallIntegerField (0, 1, or 2)
  status        CharField: ACTIVE | RECOVERED | ESCALATED | CANCELLED
  created_at, updated_at
```
Created once, at the point a `subscription_failure` transaction's first `Decision`
resolves to the registration-link nudge (i.e. it's retriable and didn't immediately
escalate) — an immediate first-decision escalation never creates one, matching the "at
most one active cadence" and "never sequenced" spec scenarios directly via existence
rather than an extra guard. `OneToOneField` (not the `ScheduledAction`-style FK) because
a transaction has at most one cadence ever, not a rotating set of rows.

`current_step` is 0-indexed internally; the reasoning-chain UI presents it 1-indexed
("step 2 of 3" = `current_step == 1`) — `design` fixes this mapping so frontend/backend
don't disagree on which "step 2" they mean.

### 3. Steps 1 and 2 are chained `ScheduledAction` rows with a dedicated dispatch branch
A step transition creates `ScheduledAction(transaction=txn, action_type=<anticipated
action>, reason="mandate_sequence_step", run_after=<now + delay>)` — reusing the exact
row shape and the existing `sweep_scheduled_actions` sweep unchanged. `action_type` here
is advisory (shown in the admin/scheduled list); the actual action is *recomputed* at
fire time, not trusted from this field, because guardrails and diagnosis must be
re-evaluated fresh (Decision 4).

`dispatch_scheduled_action` gains one branch at its top: a row whose `reason ==
"mandate_sequence_step"` is handed to a new `_dispatch_mandate_sequence_step(scheduled,
txn)` instead of the existing direct-execute body, which is otherwise untouched (a plain
guardrail-hold retry of the *current* step's already-made decision still dispatches
exactly as it does today). No change to `sweep_scheduled_actions` itself, and no new Beat
entry — one sweeper keeps discovering every kind of due row, per the existing invariant.

### 4. Steps 1 and 2 re-invoke the full diagnose → decide → guardrail pipeline
`_dispatch_mandate_sequence_step` re-checks `txn.status` first (cancellation path, below),
then calls `run_pipeline({...txn fields, "sequence_step": sequence.current_step + 1})`,
creates fresh `Diagnosis`/`Decision` rows (audited exactly like step 0's), and calls
`evaluate_guardrails` exactly as `_run_recovery_pipeline` does — same
escalate/hold/cleared branch, same ticker/guardrail WS pushes. This satisfies "every step
must still run through the existing `evaluate_guardrails()`" literally, including for a
step whose own action then gets held again (that hold-retry row also gets
`reason="mandate_sequence_step"`, so it re-enters this same handler rather than the
plain generic one — a mandate-sequence step's guardrail re-evaluation is never skipped,
even across an internal hold).

`agents/pipeline.py` needs a `sequence_step` field on the input dict (default `None`,
meaning "not sequenced" — every non-subscription and first-pass call keeps passing
`None`, so existing behavior for those is unchanged):
- `sequence_step in (None, 0)`: today's existing mapping (retriable → `registration_link`,
  else `escalate`).
- `sequence_step == 1`: retriable → `voice_reminder` (a different channel than step 0,
  same retriable-root-cause gate as today), else `escalate`.
- `sequence_step == 2`: always `escalate`, regardless of diagnosis — this is the
  cadence's own terminal step, not a diagnosis-driven choice.
- `voice_reminder` must be added to `_decide_node`'s LLM `valid_actions` set and to the
  decision system prompt's action list — today's prompt/valid-set only names
  `retry_order, new_payment_link, registration_link, invoice_reminder, escalate` and
  would reject an LLM's `voice_reminder` choice even though `Decision.Action` already
  defines it. The prompt also needs one added sentence conveying the current step so an
  LLM can pick the step-appropriate action; the heuristic table is the documented
  fallback either way.

### 5. A single hook, `_advance_mandate_sequence(txn, action)`, called after every `_execute_action`
Called from all three sites that call `_execute_action` on a nudge action (step 0 in
`_run_recovery_pipeline`, the plain hold-retry branch in `dispatch_scheduled_action`, and
`_dispatch_mandate_sequence_step`). Logic:
- No `ACTIVE` `MandateSequence` for this transaction → no-op (covers every non-sequenced
  transaction with a single cheap lookup).
- `action.action_type == ESCALATE` → mark the sequence `ESCALATED`.
- `action.result == SUCCESS` → mark the sequence `RECOVERED`.
- `action.result == FAILED` and `current_step < 1` (i.e. this was step 0) → advance
  `current_step` to 1, reopen `txn.status` to `HELD`, create the step-1
  `ScheduledAction`, write a new `mandate_sequence_step_scheduled` audit entry, push a
  `held`-shaped ticker frame (reusing `_push_ticker`, no new WS frame shape).
- `action.result == FAILED` and `current_step >= 1` — unreachable in practice (step 2 is
  always `escalate`, caught by the branch above first), kept as a defensive no-op rather
  than an assertion so a future step-count change fails soft.

### 6. Cancellation-on-recovery is a status re-check, not a signal/event
`_dispatch_mandate_sequence_step` re-fetches `txn.status` before doing anything else. If
it is not `OPEN` or `HELD` (e.g. some other path already resolved it), the row is
cancelled: `MandateSequence.status = CANCELLED`, a `mandate_sequence_cancelled` audit
entry is appended, and no action executes and no further step is scheduled. No polling or
external signal is needed — the check is naturally satisfied because a `HELD` row can
only be re-opened by the mechanisms this design controls, and the sweep already delivers
the row at the right time.

### 7. Reasoning-chain surface: extend `TransactionChainSerializer`, not a new endpoint
`MandateSequence` is serialized inline as `mandate_sequence` on the existing chain
response (`null` when none exists — the frontend renders the "no active sequence" state
from that, satisfying the `recovery-room-ui` delta's stated-not-omitted requirement),
carrying `current_step`, a fixed `total_steps: 3`, and `status`. `ChainDrawer.jsx` adds a
small progress affordance near the existing Scheduled tab rather than a new tab, since a
sequence is really metadata about the scheduled-action chain that's already shown there.

### 8. Step delays are settings-driven, matching the existing guardrail-config convention
`settings.GUARDRAILS`-style additions (new keys, not a new settings block):
`MANDATE_SEQUENCE_STEP1_DELAY_DAYS` (default 3) and `MANDATE_SEQUENCE_STEP2_DELAY_HOURS`
(default 1 — step 2 is "escalate if still unresolved," not another multi-day wait, so a
short delay keeps it on the same DB-backed/Beat-swept rail as everything else without
making an already-decided escalation wait days). Both env-overridable, same pattern as
`GUARDRAIL_RETRY_COOLDOWN_HOURS` etc.

## Risks / Trade-offs

- **[Risk]** A transaction is briefly `FAILED` mid-task before `_advance_mandate_sequence`
  reopens it to `HELD` → a WS subscriber connecting in that exact window could in theory
  see a stray `FAILED` ticker frame before `held`. **Mitigation**: the reopen happens
  synchronously in the same task before it returns (no `await`/network call between the
  two writes besides the audit/WS calls already on this path today), so the window is a
  single Python function call, consistent with how the existing code already accepts a
  brief `PROCESSING`-then-resolved window elsewhere.
- **[Risk]** Reusing `HELD` for "mid-cadence, waiting on the next nudge" makes it
  indistinguishable in the transaction list from "held on an ordinary guardrail cooldown"
  without opening the chain drawer. **Mitigation**: the reasoning-chain's new
  `mandate_sequence` field is exactly the place that distinction surfaces; the top-level
  status badge intentionally stays coarse-grained, consistent with how a plain
  guardrail hold already looks identical to any other `HELD` row today.
- **[Risk]** Concurrent-change risk with `refactor-clean-architecture-layering`: if that
  change's later tasks (interactor/adapter extraction of `tasks.py`/`guardrails.py`) land
  first, this change's edits to the same files will need to be re-targeted at the new
  module locations. **Mitigation**: no code is written by this proposal yet; `tasks.md`
  notes the file paths as of today and flags a re-check against the refactor's progress
  as the first implementation task, rather than assuming an ordering.
- **[Trade-off]** Re-running the full diagnose → decide pipeline at each step (rather than
  trusting the `action_type` stored on the `ScheduledAction` row) costs an extra
  LLM-or-heuristic call and two extra DB rows (`Diagnosis`, `Decision`) per step. Accepted
  deliberately — it's the only way to keep every step honestly passing through
  `evaluate_guardrails` with current data, per the proposal's explicit requirement, and
  it mirrors how step 0 already works today.

## Migration Plan

Additive only: one new model + migration (`MandateSequence`), one new nullable-safe field
on the chain serializer, two new settings keys with defaults, one new `reason` value on
`ScheduledAction` (a `CharField`, no enum/choices to extend), and one new dispatch branch.
No existing migration, model field, or API field is removed or changed. Rollback is a
straight revert: no data written by this feature is read by any pre-existing code path
that lacks a null-check, so removing the migration and the new branches leaves the system
exactly as it behaves today for every already-`RECOVERED`/`ESCALATED`/`FAILED` transaction
before rollback (an in-flight `HELD`-mid-cadence transaction would need a one-off
management-command nudge to `FAILED` or `ESCALATED` on rollback, since no code would be
left to advance it — acceptable for a rollback of an in-flight demo feature, and worth a
one-line callout in the rollback runbook rather than engineering around).

## Open Questions

- Exact copy for the frontend's "no active sequence" state and the per-step progress
  label — cosmetic, doesn't change the spec or the task breakdown.
- Whether `MANDATE_SEQUENCE_STEP2_DELAY_HOURS` should default to 0 (fire on the very next
  Beat tick) instead of 1 hour — either satisfies the spec identically; can be tuned
  during implementation without touching any requirement.
