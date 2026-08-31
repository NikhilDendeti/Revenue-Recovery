Green gate, run at the end of every task: `cd backend && .venv/Scripts/python.exe -m pytest -q`.
The baseline measured at proposal time is **`96 passed, 15 skipped`**. New tests may push
the passed count up; the skipped count must not rise above 15, and no pre-existing test
may fail, be deleted, or be weakened to keep the count. A rising pass count is progress;
a rising skip count is a regression in disguise.

## 0. Coordination check with the in-flight layering refactor

- [ ] 0.1 Re-run `openspec status --change refactor-clean-architecture-layering --json` and diff its `tasks.md` against the copy read while planning this change. If sections 3–6 (guardrails package, storages, execute-action interactor, pipeline task shells) have landed since, re-target every file path in tasks 2–4 below onto the new module locations (`recovery/interactors/`, `recovery/storages/`, `recovery/adapters/`) before writing any code, rather than editing the old flat files. Verify: a written note (commit message or PR description) states which layout this change was implemented against.

## 1. Data model — `MandateSequence`

- [ ] 1.1 Add `MandateSequence` to `backend/recovery/models.py`: `transaction` (`OneToOneField(Transaction, related_name="mandate_sequence")`), `current_step` (0/1/2), `status` (`ACTIVE`/`RECOVERED`/`ESCALATED`/`CANCELLED`), `created_at`, `updated_at`. Generate and apply the migration. Verify: `python manage.py makemigrations --check` is clean after `migrate`, and `MandateSequence.objects.create(transaction=txn)` round-trips in the shell.
- [ ] 1.2 Add `MandateSequenceSerializer` (`current_step`, a computed `total_steps` constant of `3`, `status`) and register `MandateSequence` in `admin.py` for inspectability, matching how `ScheduledAction` is already registered. Verify: `admin.py` lists it and the serializer instantiates against a saved instance.

## 2. Pipeline — step-aware decisions

- [ ] 2.1 Add an optional `sequence_step` key (default `None`) to the `transaction_fields` dict accepted by `agents/pipeline.py::run_pipeline`, threaded into `PipelineState`. Verify: calling `run_pipeline({...})` with no `sequence_step` key behaves identically to today (existing pipeline tests unchanged and green).
- [ ] 2.2 Add `voice_reminder` to `_decide_node`'s LLM `valid_actions` set and to the decision system prompt's listed actions; add one sentence to the prompt conveying the current `sequence_step` when it is not `None`/`0`. Verify: a test asserting `"voice_reminder"` is now accepted from a mocked LLM response where it was previously coerced to the heuristic fallback.
- [ ] 2.3 Extend `_heuristic_decision` so `sequence_step == 1` maps a retriable `subscription_failure` diagnosis to `voice_reminder` (same retriable-root-cause gate as today) instead of `registration_link`, and `sequence_step == 2` always returns `escalate` regardless of diagnosis. Verify: three new unit tests in `backend/agents/tests/` — step 0/`None` unchanged, step 1 retriable → `voice_reminder`, step 2 → `escalate` even for a high-confidence retriable diagnosis.

## 3. Sequencing logic in the task layer

- [ ] 3.1 Add settings `MANDATE_SEQUENCE_STEP1_DELAY_DAYS` (default 3) and `MANDATE_SEQUENCE_STEP2_DELAY_HOURS` (default 1) to `config/settings.py`, env-overridable via `django-environ`, matching the existing `GUARDRAILS` dict convention. Document both in `backend/.env.example`. Verify: unset, the defaults apply; overriding the env var changes the computed `run_after`.
- [ ] 3.2 In `_run_recovery_pipeline` (step 0's existing path), after a `subscription_failure` transaction's decision resolves to `registration_link` (not an immediate escalate), create its `MandateSequence(current_step=0, status=ACTIVE)` before guardrail evaluation runs. Verify: a decision that escalates immediately (non-retriable root cause, or guardrail escalation) never creates a `MandateSequence` row — assert `MandateSequence.objects.count() == 0` in that case.
- [ ] 3.3 Add `_advance_mandate_sequence(txn, action)` in `tasks.py`: no-op if no `ACTIVE` sequence exists; mark `ESCALATED` if `action.action_type == ESCALATE`; mark `RECOVERED` if `action.result == SUCCESS`; if `action.result == FAILED` and `current_step < 1`, advance `current_step` to 1, reopen `txn.status` to `HELD`, create the step-1 `ScheduledAction` (`reason="mandate_sequence_step"`, `run_after` = now + the step-1 delay), and append a `mandate_sequence_step_scheduled` audit entry. Call it from every existing call site of `_execute_action` on a nudge action. Verify: a unit test with a `FakeGateway`/patched `_execute_action`-adjacent seam driving a `FAILED` step-0 outcome ends with `txn.status == HELD`, `MandateSequence.current_step == 1`, and exactly one `PENDING` `ScheduledAction` with `reason="mandate_sequence_step"`.
- [ ] 3.4 Add `_dispatch_mandate_sequence_step(scheduled, txn)` and branch to it from the top of `dispatch_scheduled_action` when `scheduled.reason == "mandate_sequence_step"`: re-check `txn.status` first (cancellation path, task 3.5), else re-invoke `run_pipeline` with `sequence_step = sequence.current_step + 1`, create fresh `Diagnosis`/`Decision` rows, call `evaluate_guardrails`, and branch escalate/hold/cleared exactly as `_run_recovery_pipeline` does (a held step re-schedules another `reason="mandate_sequence_step"` row rather than falling through to the plain generic branch). Verify: a step-1 dispatch with a cleared guardrail verdict creates a `voice_reminder` `Action`, and a held verdict creates another `mandate_sequence_step`-reason `ScheduledAction` without advancing `current_step`.
- [ ] 3.5 In `_dispatch_mandate_sequence_step`, before doing anything else, re-fetch `txn.status`; if it is not `OPEN` or `HELD`, mark the `MandateSequence` `CANCELLED`, append a `mandate_sequence_cancelled` audit entry, and return without executing any action or scheduling a next step. Verify: a transaction manually flipped to `RECOVERED` between scheduling and firing a step-1 row results in `MandateSequence.status == CANCELLED`, zero new `Action` rows, and zero new `ScheduledAction` rows.

## 4. API surface

- [ ] 4.1 Add `mandate_sequence` (nullable) to `TransactionChainSerializer`, serialized via `MandateSequenceSerializer` when the related object exists and `null` otherwise. Verify: the chain endpoint response for a non-sequenced transaction has `"mandate_sequence": null`; for a sequenced one it has `{"current_step": ..., "total_steps": 3, "status": ...}`.

## 5. Frontend — reasoning-chain progress

- [ ] 5.1 In `ChainDrawer.jsx`, render the mandate-sequence progress near the existing Scheduled tab: "Step N of 3 — <status>" when `mandate_sequence` is present, and an explicit "No active recovery sequence" state when it is `null` — matching the existing pattern used for other empty chain sections. Verify: a manual run against a seeded sequenced transaction and a non-sequenced one shows both states; no console errors.

## 6. Tests

- [ ] 6.1 Add `backend/recovery/tests/test_mandate_sequence.py` covering step progression end-to-end: seed a `subscription_failure` transaction, force step 0's outcome to `FAILED` (patch the outcome dice, matching the existing pattern of patching `agents.pipeline.complete_json` to `None` for the heuristic path plus a controlled random draw), run the sweep, and assert step 1 fires as `voice_reminder` through guardrails; repeat for step 1 → step 2 escalation. Verify: both assertions pass and each step's `Diagnosis`/`Decision`/`GuardrailEvent`/audit rows exist.
- [ ] 6.2 Add a cancellation-on-recovery test: schedule a step-1 `mandate_sequence_step` `ScheduledAction`, then externally mark the transaction `RECOVERED` before the sweep runs, then run the sweep and assert the row is discovered, the sequence becomes `CANCELLED`, and no `voice_reminder` action is created. Verify: test passes and asserts zero new `Action` rows from that dispatch.
- [ ] 6.3 Add a worker-restart-survival test: create a step-1 `ScheduledAction` with `run_after` in the past (simulating a step that was due while a worker was down), instantiate the sweep task fresh (no reliance on any in-process state from scheduling it), and assert it is picked up and dispatched correctly — proving the row alone, not worker memory, carries the pending step. Verify: test passes without any Celery ETA/ETA-task mechanism involved, only DB state plus `sweep_scheduled_actions`.
- [ ] 6.4 Confirm the layer-boundary test (`test_layer_boundaries.py`) still passes unmodified if any new module was added under `recovery/interactors/`/`recovery/adapters/` per task 0.1's re-targeting. Verify: `pytest backend/recovery/tests/test_layer_boundaries.py -q` green.
- [ ] 6.5 Run the full suite and confirm the pass count rose by at least the number of tests added in 2.2, 2.3, 6.1–6.3, the skip count is still 15, and nothing pre-existing failed. Verify: `cd backend && .venv/Scripts/python.exe -m pytest -q` output matches this expectation.

## 7. Documentation

- [ ] 7.1 Update `CLAUDE.md`'s repo-layout/invariants section to mention `MandateSequence` and the `mandate_sequence_step` `ScheduledAction` reason alongside the existing cooldown/retry description, so a future contributor finds both patterns documented in one place. Verify: the added text names the model and cross-references `sweep_scheduled_actions`.
