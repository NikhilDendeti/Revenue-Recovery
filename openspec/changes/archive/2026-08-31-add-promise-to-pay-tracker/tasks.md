## 1. `PromiseToPay` model and migration

- [x] 1.1 Add the `PromiseToPay` model to `backend/recovery/models.py` (`transaction` FK
      with `related_name="promises"`, `promised_amount`, `promise_date` as `DateField`,
      `source` `TextChoices` [`voice`, `manual`], `status` `TextChoices` [`pending`,
      `kept`, `broken`] defaulting to `pending`, `created_at`), with a partial unique
      constraint (one `pending` row per transaction), matching design.md Decision 1 —
      verify with `python manage.py makemigrations --check` showing no missing migration
      once 1.2 is done.
- [x] 1.2 Generate and review the migration (`python manage.py makemigrations recovery`)
      — verify it creates exactly the `PromiseToPay` table and its constraint, with no
      changes to `AuditLogEntry` or its append-only trigger.
- [x] 1.3 Add a model test asserting a `PromiseToPay` created for a transaction records
      its transaction, promised amount, promise date, source, and defaults to `pending`
      status — verify the test passes (`automated-testing` capability: model coverage).
- [x] 1.4 Add a model/DB test asserting a second `pending` row cannot be created for the
      same transaction while one already exists (the partial unique constraint fires) —
      verify the test passes.

## 2. Voice showcase creates a real promise

- [x] 2.1 Update `trigger_voice_showcase` (`backend/recovery/tasks.py`) to
      `update_or_create` a `PromiseToPay` (`source=voice`, `status=pending`,
      `promised_amount=txn.amount`, `promise_date` matching the existing computed date)
      alongside its existing `Action`/audit/WS-push behavior — verify with a test that
      triggering the voice showcase for a transaction leaves exactly one pending
      `PromiseToPay` row with the expected fields, retrievable independently of the audit
      log entry (`promise-to-pay-tracking` capability, "recorded as trackable data").
- [x] 2.2 Verify (existing test or a small addition) that the audit entry and WS `voice`
      push written by `trigger_voice_showcase` are unchanged in shape — no regression to
      the existing voice-moment behavior.

## 3. Sweep task and Beat schedule

- [x] 3.1 Add `sweep_promises_to_pay` to `backend/recovery/tasks.py`: select `pending`
      promises with `promise_date` on or before today; for each, if its transaction's
      status is `RECOVERED`, mark it `kept`; otherwise mark it `broken`, append an audit
      entry recording the broken promise, and — unless the transaction is already
      `ESCALATED` — re-run `evaluate_guardrails` using the latest diagnosis (0.5-confidence
      fallback) and latest contact-type decision (or an unsaved `VOICE_REMINDER`
      stand-in), per design.md Decision 3, executing the resulting `ESCALATE` action
      through the existing `_execute_action` helper when the verdict escalates.
- [x] 3.2 Register `sweep_promises_to_pay` in `CELERY_BEAT_SCHEDULE`
      (`backend/config/settings.py`) at the same 30-second cadence as
      `sweep-scheduled-actions` — verify the schedule entry is present and the task is
      importable by Celery (`celery -A config inspect registered` or an equivalent
      settings-level test/assertion).
- [x] 3.3 Add a test: a pending promise past its date on a `RECOVERED` transaction is
      swept to `kept` — verify the test passes (`promise-to-pay-tracking`: "A promise on
      a recovered transaction is marked kept").
- [x] 3.4 Add a test: a pending promise past its date on a non-`RECOVERED` transaction
      (e.g. still `OPEN` or `HELD`) is swept to `broken`, and guardrail evaluation runs
      for that transaction as a result — verify the test passes (`promise-to-pay-tracking`:
      "A promise on a still-unresolved transaction is marked broken" and "Marking a
      promise broken triggers guardrail evaluation").
- [x] 3.5 Add a test: sweeping one due `kept`-bound promise and one due `broken`-bound
      promise in the same run resolves both correctly in one pass — verify the test
      passes (`automated-testing`: "The sweep resolves both outcomes correctly in one
      run").
- [x] 3.6 Add a test: a promise past its date on an already-`ESCALATED` transaction is
      marked `broken` without a redundant second `ESCALATE` action/audit entry being
      written — verify the test passes (design.md Decision 3's no-op-avoidance).

## 4. Guardrail extension: broken promise blocks contact, without bypassing the existing rule

- [x] 4.1 In `evaluate_guardrails` (`backend/recovery/guardrails.py`), inside the existing
      `CONTACT_ACTIONS` branch, add the broken-promise check (any `PromiseToPay` with
      `status=broken` whose transaction shares `txn.customer_id`) alongside the existing
      cooldown-timestamp check, logging both outcomes under the existing
      `contact_frequency_cap` rule name (extended detail text, no new rule name) — verify
      per design.md Decision 4.
- [x] 4.2 Restructure the function's tail to check `escalate` again after rules 4-6 (not
      only after rules 1-3), before falling through to `hold_until`/`cleared`, exactly as
      described in design.md Decision 4 — verify every existing guardrail test still
      passes unchanged (rules 1-6's current behavior is preserved).
- [x] 4.3 Add a test: a customer with an unresolved broken promise has a proposed
      contact-type action blocked and escalated even when evaluated well outside the
      ordinary 24-hour cooldown window — verify the test passes
      (`promise-to-pay-tracking`: "A broken promise blocks a further contact action even
      outside the ordinary cooldown"; `automated-testing`: "A broken promise blocks a
      contact action even when the cooldown timestamp alone would pass").
- [x] 4.4 Add a test: a customer with no broken promise, outside the cooldown window,
      still clears the contact-frequency check exactly as before this change — verify the
      test passes (`promise-to-pay-tracking`: "A customer with no broken promise is
      unaffected").
- [x] 4.5 Confirm (existing test or a small addition) that the plain cooldown-timestamp
      scenario (`automated-testing`: "Repeated contact within the cooldown window is
      held") still results in a hold, not an escalate, when no broken promise is present
      — verify no regression.

## 5. Batch summary: `promise_kept_rate`

- [x] 5.1 Add `promise_kept_rate` to `compute_summary()` (`backend/recovery/analytics.py`)
      as kept ÷ (kept + broken) among resolved promises, `0.0` when none have resolved —
      verify with a test asserting the computed rate for a mix of kept/broken/pending
      rows, and a separate test asserting `0.0` (not an error) with zero resolved
      promises (`promise-to-pay-tracking`: "The kept rate reflects resolved promises" and
      "No resolved promises yet reports zero, not an error").

## 6. Read-only API for `PromiseToPay`

- [x] 6.1 Add `PromiseToPaySerializer` (`backend/recovery/serializers.py`) exposing `id`,
      `transaction`, `promised_amount`, `promise_date`, `source`, `status`, `created_at`.
- [x] 6.2 Add `PromiseToPayViewSet(viewsets.ReadOnlyModelViewSet)`
      (`backend/recovery/views.py`) with `filterset_fields = ["status", "transaction"]`,
      registered at `promises-to-pay` in `backend/recovery/urls.py`, matching the
      existing `ScheduledActionViewSet` pattern.
- [x] 6.3 Add a test: listing the endpoint and filtering by `status` and by `transaction`
      each return the expected rows — verify the test passes (`promise-to-pay-tracking`:
      "Listing and filtering promises").
- [x] 6.4 Add a test: POST, PUT, PATCH, and DELETE against the endpoint are each rejected
      without creating, modifying, or removing a row — verify the test passes
      (`promise-to-pay-tracking`: "Writing to the promise-to-pay endpoint is rejected";
      `automated-testing`: "The promise-to-pay endpoint supports read access and rejects
      writes").

## 7. Frontend tracker panel

- [x] 7.1 Add `api.promisesToPay(params)` to `frontend/src/lib/api.js`
      (`GET /promises-to-pay/`), matching the existing `req()`/auth pattern.
- [x] 7.2 Add `frontend/src/components/PromiseTracker.jsx`: a `Panel` (from
      `ui/Surface`) showing pending/kept/broken counts as `Badge`s in the header and a
      list of promises in the body, with loading, error (with retry), and — via
      `EmptyState` — a "no promises yet" empty state, per design.md Decision 7.
- [x] 7.3 Wire `PromiseTracker` into `Dashboard.jsx`, fetching once on mount — verify by
      running the app (see the `run` skill) and confirming the panel renders with seed
      data after triggering a voice showcase, and confirming the empty state renders when
      no promises exist.
      NOTE (judgment call): per the calling agent's explicit instruction, did not start a
      dev server for a live browser check — verified instead via `npm run build` (clean)
      and `npm run lint` (clean) plus code review against the ChainDrawer/GuardrailConsole
      self-fetch pattern.
- [x] 7.4 Add a frontend test (or extend the existing component-test setup, matching
      whatever test tooling the frontend already uses) asserting the panel shows the
      correct pending/kept/broken counts for a given promise list, and the empty state
      when the list is empty — verify the test passes (`promise-to-pay-tracking`: "The
      tracker shows counts and a list" and "No commitments yet shows an explanatory empty
      state").
      NOTE (judgment call): no frontend test framework (vitest/jest/@testing-library) or
      test file exists anywhere in this repo — "the existing component-test setup" this
      task assumes doesn't exist. Introducing one is an infrastructure decision beyond
      this task's scope, so instead the panel's counting/empty-state logic was extracted
      into a pure `frontend/src/lib/promiseSummary.js` and unit-tested with Node's
      built-in test runner (`frontend/src/lib/promiseSummary.test.js`, wired to
      `npm test`) — zero new dependencies. This covers the counting/empty-list logic the
      scenario describes, not a full DOM-rendered assertion on `PromiseTracker.jsx`
      itself; flagged for review rather than silently treated as fully equivalent.

## 8. Full-suite regression pass

- [x] 8.1 Run the full backend test suite and confirm everything passes, including every
      pre-existing guardrail, pipeline, and audit-log test alongside the new tests added
      above.
- [x] 8.2 Run `openspec validate add-promise-to-pay-tracker --strict` and resolve any
      reported issues before archiving.
