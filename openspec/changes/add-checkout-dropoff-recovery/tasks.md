## 1. Data model

- [ ] 1.1 Add `Transaction.Kind.CHECKOUT_DROPOFF`, `checkout_initiated_at`
      (`DateTimeField(null=True, blank=True)`), and `last_payment_method`
      (`CharField(max_length=32, blank=True)`) to `backend/recovery/models.py`, per
      design.md Decision 1. Verify `python manage.py makemigrations recovery` detects
      the new choice and the two new fields cleanly (no errors, no unexpected changes
      to other fields).
- [ ] 1.2 Generate and review the resulting migration file (next number after
      `0004_broadcastevent.py`). Verify `python manage.py migrate` applies cleanly on a
      fresh SQLite database and a subsequent `python manage.py makemigrations --check`
      reports no further changes. Confirm the migration touches only `Transaction` —
      `AuditLogEntry` and its migration-0002 trigger are untouched.
- [ ] 1.3 Add `CHECKOUT_DROPOFF_AT_RISK_HOURS` (default `1.0`) and `HIGH_VALUE_CART_INR`
      (default `8000`) as env-overridable settings in `backend/config/settings.py`, per
      design.md Decisions 2 and 3. Verify both resolve via
      `python manage.py shell -c "from django.conf import settings; print(settings.CHECKOUT_DROPOFF_AT_RISK_HOURS, settings.HIGH_VALUE_CART_INR)"`.

## 2. Webhook ingestion

- [ ] 2.1 Add `"checkout.abandoned": Transaction.Kind.CHECKOUT_DROPOFF` to
      `WEBHOOK_KIND_MAP` in `backend/recovery/views.py`, with a comment stating plainly
      that this is not a real Razorpay webhook event (per design.md Decision 2, matching
      the existing caveat style for the other three simulated events). Extend
      `WebhookView.post` to read `checkout_initiated_at` and `last_payment_method` from
      the payload (parsing an ISO datetime string for the former, defaulting both to
      `None`/`""` if absent) and pass them into `Transaction.objects.create(...)`.
      Verify a new test in `backend/recovery/tests/test_api.py` that POSTs a
      `checkout.abandoned` event creates an open `checkout_dropoff` transaction with an
      empty `failure_code` and both new fields populated from the payload.

## 3. Diagnosis and decision heuristics

- [ ] 3.1 Implement `_heuristic_checkout_dropoff_diagnosis(txn)` in
      `backend/agents/pipeline.py` per the decision tree in design.md Decision 3
      (`hours_since_initiated`, `amount`, `method_attempted`). Route `_heuristic_diagnosis`
      to it when `txn["kind"] == "checkout_dropoff"`, checked *before* the existing
      "no failure code → `unknown`" fallback so that fallback keeps its current meaning
      for the other three kinds. Verify new parametrized tests in
      `backend/agents/tests/test_pipeline.py` cover all six rows of the design.md table
      (root cause and confidence for each).
- [ ] 3.2 Add the `checkout_dropoff` branch to `_heuristic_decision` (always
      `new_payment_link` when confidence clears the floor; inline reasoning text per
      design.md Decision 4, not the shared `_REASONING["new_payment_link"]` string).
      Verify a regression test — mirroring
      `test_subscription_failure_never_produces_retry_order` — asserting a
      `checkout_dropoff` transaction never chooses `retry_order` across the full range
      of signal inputs (fresh/stale, method attempted or not, low/high value), and that
      a low-confidence case (`aging_dropoff`/`cold_dropoff`/`browse_abandonment`)
      escalates via the existing confidence-floor branch with zero new escalation code.
- [ ] 3.3 Extend the diagnosis and decision LLM system prompts in
      `backend/agents/pipeline.py` with the `checkout_dropoff` paragraph/sentence from
      design.md Decision 5. Verify the existing heuristic-fallback tests in
      `test_pipeline.py` (run under that file's `heuristic_only` skip-fixture
      convention, matching how it already tests every other kind) still pass unchanged
      — the prompt text change must not alter heuristic behavior.
- [ ] 3.4 Extend the plain-dict `transaction_fields` built in `_run_recovery_pipeline`
      (`backend/recovery/tasks.py`) to include `checkout_initiated_at` (ISO string or
      `None`) and `last_payment_method` (string or `""`) for every kind, per design.md
      Decision 5. Verify the existing `test_tasks.py` suite for the other three kinds
      passes unchanged — the two new keys are additive and unused by their code paths.

## 4. Guardrail coverage (no changes to `recovery/guardrails.py`)

- [ ] 4.1 Add `checkout_dropoff` guardrail-coverage tests to
      `backend/recovery/tests/test_guardrails.py`, calling `evaluate_guardrails`
      directly (same pattern as the existing tests), per design.md Decision 6:
      - confidence floor blocks a low-confidence `checkout_dropoff` diagnosis and
        passes a high-confidence one;
      - spend ceiling blocks a `checkout_dropoff` transaction whose amount exceeds
        `SPEND_CEILING_INR`, regardless of confidence;
      - contact frequency cap applies to a `checkout_dropoff` transaction's
        `new_payment_link` decision (a second contact within 24h is blocked), exactly
        as it already does for other kinds' `new_payment_link` decisions;
      - compliance hours does **not** hold a `checkout_dropoff` transaction outside
        business hours — a regression guard distinguishing it from `receivable`;
      - max-retry-attempts and cooldown-between-retries never block a
        `checkout_dropoff` decision, since it never selects `retry_order`.

## 5. Seed data

- [ ] 5.1 Add `_seed_checkout_dropoff(n)` to
      `backend/recovery/management/commands/seed_data.py` and a `--checkout-dropoff`
      CLI argument (default `14`), generating the distribution documented in design.md:
      `checkout_initiated_at` spread across fresh (≤2h), short-window (≤24h), aging
      (≤72h), and cold (>72h) buckets, every row satisfying
      `checkout_initiated_at <= now - CHECKOUT_DROPOFF_AT_RISK_HOURS`;
      `last_payment_method` a weighted choice including a blank ("never attempted")
      share; cart value drawn from a realistic range with at least one record above
      `SPEND_CEILING_INR` for guardrail-escalation coverage (mirroring
      `_seed_receivable`'s existing high-value-outlier pattern). Wire the new records
      into `handle()`'s `created` list and summary output.
- [ ] 5.2 Add `backend/recovery/tests/test_seed_data.py` (new file — none exists yet for
      the other three kinds) asserting: every seeded `checkout_dropoff` row has
      `failure_code == ""`, `checkout_initiated_at` at or before
      `now - CHECKOUT_DROPOFF_AT_RISK_HOURS`, at least one row with `amount` above
      `SPEND_CEILING_INR`, and `last_payment_method` values spanning both populated and
      blank across the seeded set.

## 6. Frontend

- [ ] 6.1 Add a `checkout_dropoff` entry to `KIND_META` and `KIND_FILTERS` in
      `frontend/src/lib/format.js` (label "Checkout drop-off", short "Drop-off", icon
      `"cart"`), per design.md Decision 7. Verify `SearchFilterBar` renders the new flow
      chip with no changes to `SearchFilterBar.jsx` itself, since it already iterates
      `KIND_FILTERS` generically.
- [ ] 6.2 Add a new `cart` glyph to the `STROKE` map in
      `frontend/src/components/ui/Icon.jsx`, matching the file's existing 24-unit
      coordinate-space and default `strokeWidth` conventions. Verify `<Icon name="cart" />`
      renders a visible path (no silent no-op from an unmatched icon name).

## 7. Verification sweep

- [ ] 7.1 Run the full backend suite (`pytest`, from `backend/`) and confirm every
      existing test still passes alongside all new tests added above.
- [ ] 7.2 Seed and replay locally (`python manage.py seed_data --checkout-dropoff 14`
      then `python manage.py replay_batch`, or the equivalent `/api/batch/replay/`
      call) against a fresh local SQLite database, and confirm `checkout_dropoff`
      transactions reach recovered / failed / escalated / held outcomes on the Recovery
      Room ticker, guardrail console, and audit trail — exercising the new diagnosis and
      guardrail paths end to end, not just in unit tests.
