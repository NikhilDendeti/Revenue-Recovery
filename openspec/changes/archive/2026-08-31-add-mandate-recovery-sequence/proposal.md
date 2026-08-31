## Why

`_heuristic_decision`/the LLM decision prompt in `backend/agents/pipeline.py` route every
`subscription_failure` transaction to a single `registration_link` decision and stop —
there is no follow-up. Razorpay's own mandate auto-retry is a black box we can't hook
into, so a customer who ignores the first registration-link nudge is never re-approached
and never reaches a human queue; the transaction just sits `RECOVERED`-or-not with no
further lever pulled. Mandate/subscription recovery needs a real cadence — nudge, then a
different-channel follow-up, then escalate — not a single fire-and-forget decision, so
revenue at risk from an ignored first nudge isn't silently abandoned.

## What Changes

- Add a `MandateSequence` model (`transaction` FK, `current_step`, `status`) that tracks
  a `subscription_failure` transaction through a fixed 3-step cadence: step 0 —
  registration-link nudge (immediate, the existing behavior); step 1 — a follow-up nudge
  on a different channel after a configurable delay, only if the transaction hasn't
  recovered; step 2 — escalate to the human queue if still unresolved.
- Chain each step as a `ScheduledAction` row (the same DB-backed, Beat-swept pattern
  `sweep_scheduled_actions` already sweeps for cooldown/retry) rather than a raw
  multi-day Celery ETA task, so the sequence survives a worker restart.
- Before firing, every step re-checks the transaction's current status: if it has already
  left `OPEN`/`HELD` for a recovered (or otherwise resolved) state, the step is cancelled
  and no further step is scheduled — a mid-sequence recovery stops the cadence instead of
  continuing to nudge a recovered customer.
- Every step's action still runs through the existing `evaluate_guardrails()` (contact
  cooldown, business hours, spend ceiling, confidence floor) unchanged — the sequencer
  only decides *when* to re-invoke the recovery pipeline for the next step; it never
  bypasses or duplicates guardrail logic.
- Surface sequence progress ("step 2 of 3", per-step status) on the transaction's
  reasoning-chain view (`TransactionChainSerializer` / the chain dialog's existing
  Scheduled tab), consistent with how scheduled actions are already shown there.
- Add tests for step progression, cancellation-on-recovery, and survival of a simulated
  worker restart (a `MandateSequence`/chained `ScheduledAction` row is read from the DB,
  not held in Celery/worker memory).

Out of scope: changing the diagnosis root-cause rules, changing what happens on the
*first* pass for `payment_degradation` or `receivable` transactions (unaffected — only
`subscription_failure` gets a sequence), and building a real WhatsApp/voice channel
integration (step 1 reuses the existing simulated `voice_reminder`/`WHATSAPP` action
channel already modeled in `Action.Type` and `Decision.Action`, not a new provider).

**Assumption recorded** (not asked, since it doesn't change externally-observable
contracts): a 3-day gap before step 1, and a 4-day gap before step 2, both configurable
via `settings.GUARDRAILS`-style env vars with these as defaults — same convention as the
existing `RETRY_COOLDOWN_HOURS`/`CONTACT_COOLDOWN_HOURS` knobs. `design.md` fixes exact
values and setting names.

## Capabilities

### New Capabilities
- `mandate-recovery-sequencing`: tracking a `subscription_failure` transaction through a
  fixed, guardrail-respecting, DB-backed multi-step nudge-then-escalate cadence, with
  cancellation when the transaction recovers mid-sequence and survival across a worker
  restart.

### Modified Capabilities
- `recovery-room-ui`: the reasoning-chain dialog's presentation requirements extend to
  show mandate-sequence progress (current step / total steps, per-step status) as part of
  "the full reasoning chain is presented, not only the audit entries" — a transaction with
  no active sequence states so explicitly rather than omitting the section.

## Impact

- **Backend models**: new `MandateSequence` model + migration in `backend/recovery/`;
  reuses `ScheduledAction` (no schema change to it) and `Action.Type`/`Decision.Action`
  (no new enum values — step 1 reuses the existing voice/WhatsApp-shaped channel).
- **Pipeline**: `backend/agents/pipeline.py`'s decision heuristic (and LLM prompt) need a
  way to know which step is firing so step 1/2 route to the follow-up/escalate action
  instead of re-deriving `registration_link` from the diagnosis every time — both the LLM
  path and `_heuristic_decision` need this, consistent with the existing
  documented-fallback pattern.
- **Guardrails**: `backend/recovery/guardrails.py`'s `evaluate_guardrails()` is called
  unchanged from each step; no new rule, no bypass path.
- **Tasks/scheduling**: `backend/recovery/tasks.py` — `sweep_scheduled_actions` continues
  to be the single sweeper; step chaining logic lives alongside
  `dispatch_scheduled_action` and `_run_recovery_pipeline`.
- **API/serializers**: `TransactionChainSerializer` gains a mandate-sequence field;
  frontend `ChainDrawer.jsx` gains a small progress affordance (existing Scheduled tab or
  a new one — `design.md` decides).
- **Coexistence note**: `openspec/changes/refactor-clean-architecture-layering` is
  in-flight and, once applied, moves `tasks.py`/`guardrails.py` logic into
  `interactors/`/`storages/`/`adapters/`. This proposal targets the current (pre-refactor)
  flat module layout per the task brief; `design.md` flags the ordering risk rather than
  silently assuming one change applies before the other.
- **Tests**: new tests under `backend/recovery/tests/` (and/or `test_interactors/` if the
  layering refactor lands first) for step progression, cancellation-on-recovery, and
  worker-restart survival; heuristic-path tests continue to patch
  `agents.pipeline.complete_json` to `None` rather than assuming no LLM key is configured.
