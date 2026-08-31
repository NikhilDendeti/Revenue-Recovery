## 1. Data model — `customer_email`

- [x] 1.1 Add `customer_email = models.EmailField(blank=True)` to `Transaction`
      (`backend/recovery/models.py`), matching `customer_phone`'s style. Generate the
      migration (`python manage.py makemigrations recovery`) and verify it contains
      only an `AddField` on `Transaction` — no change to `AuditLogEntry` or its
      trigger.
- [x] 1.2 Update `seed_data.py`'s `_customer()` helper to populate
      `customer_email=f"{customer_id}@example.test"`. Verify `python manage.py
      seed_data --flush` runs cleanly and every seeded `Transaction.customer_email`
      is non-blank.
- [x] 1.3 Update `WebhookView.post` (`backend/recovery/views.py`, alongside the
      existing `customer_name`/`customer_phone` lines) to read
      `customer_email=payload.get("customer_email", "")`. Verify an existing webhook
      test that omits `customer_email` from its payload still creates a `Transaction`
      successfully with `customer_email == ""`.

## 2. `reopen_order_checkout` — issue a real payment link, not an order-reopen call

- [x] 2.1 Widen `reopen_order_checkout`'s signature to `reopen_order_checkout(
      order_id: str | None, amount_paise: int, receipt: str, customer_name: str,
      customer_phone: str) -> dict`. Verify the module still imports cleanly and the
      old 3-arg call sites are all updated (grep for `reopen_order_checkout(` across
      `backend/` finds no remaining 3-arg call).
- [x] 2.2 Rewrite its live-mode body (the `_configured()` True branch) to call
      `create_payment_link(amount_paise, description, customer_name, customer_phone)`
      — build a `description` from `receipt` consistent with `create_payment_link`'s
      existing callers — and merge `{"retried_order_id": order_id}` into the
      returned dict. Remove the `POST /orders/{order_id}` and `POST /orders` calls
      entirely. Verify no code path in `razorpay_client.py` posts to `/orders` or
      `/orders/{id}` anymore (grep confirms zero occurrences of `"/orders"`).
- [x] 2.3 Change its simulated-mode branch to return a payment-link-shaped response
      (`{"simulated": True, "id": f"sim_plink_{...}", "short_url":
      "https://rzp.io/l/sim...", "amount": amount_paise, "retried_order_id":
      order_id}`), mirroring `create_payment_link`'s simulated shape. Verify by
      inspection that the two simulated shapes differ only in the added
      `retried_order_id` key.
- [x] 2.4 Update `tasks.py::_call_razorpay`'s `RETRY_ORDER` branch to pass
      `txn.customer_name, txn.customer_phone` as the two new arguments. Verify
      `backend/recovery/tests/test_tasks.py`'s existing `RETRY_ORDER`-path tests
      (`test_execute_action_escalates_on_non_404_api_error`,
      `test_execute_action_falls_back_to_payment_link_on_404_order`,
      `test_execute_action_escalates_when_fallback_also_fails`) still pass unchanged
      — they patch `_call_razorpay` itself, not its arguments.
- [x] 2.5 Update `test_razorpay_client.py::test_reopen_order_checkout_is_simulated`
      to call the new 5-arg signature and assert on `resp["short_url"].startswith(
      "https://rzp.io/l/sim")` instead of the old `id`/`order_sim` assertions. Verify
      `pytest backend/recovery/tests/test_razorpay_client.py -q` passes.
- [x] 2.6 Add a `TestLiveMode` case exercising `reopen_order_checkout` for real
      (gated the same way `test_create_and_cancel_a_real_payment_link` is), asserting
      the response is payment-link-shaped (`short_url` present, no `simulated` key)
      and cancelling the created link the same way the existing payment-link test
      does. Verify it's skipped with no live keys configured and passes when they are
      (per README's live-mode test instructions).

## 3. `create_registration_link` — correct payload for Razorpay's e-mandate flow

- [x] 3.1 Add a `customer_email: str` parameter to `create_registration_link`
      (`backend/recovery/razorpay_client.py`), and update `tasks.py::_call_razorpay`'s
      `REGISTRATION_LINK` branch to pass `txn.customer_email`. Verify the module
      imports cleanly and the one production call site is updated.
- [x] 3.2 In the live-mode body: raise `RazorpayError("create_registration_link
      requires a customer email in live mode", status_code=None)` before any network
      call when `customer_email` is blank. Verify a unit test patches `_configured`
      to `True`, calls `create_registration_link(..., customer_email="")`, and gets
      a `RazorpayError` with `status_code is None`, with `requests.post` never called
      (same `_fail_if_called` pattern already used in
      `TestSimulatedMode`).
- [x] 3.3 Otherwise, build the payload with `"customer": {"name": customer_name,
      "contact": customer_phone, "email": customer_email}`, add
      `"subscription_registration": {"method": "emandate", "auth_type": <picked
      default per design.md Decision 2>}`, and force `"amount": 0` regardless of the
      `amount_paise` argument — fold the real amount into `description` instead
      (update `tasks.py::_call_razorpay`'s `REGISTRATION_LINK` branch to append the
      due amount to its `label` string before passing it as `description`). Verify a
      unit test patches `requests.post` and asserts the posted JSON body contains
      `amount == 0`, the `subscription_registration` key, and `customer.email`.
- [x] 3.4 Add a `TestLiveMode` case calling `create_registration_link` for real (test
      keys) with a real-shaped email, asserting the response has no `simulated` key
      and contains the fields Razorpay's auth-link response documents (e.g. `id`
      starting with the provider's registration-link prefix). Verify it's skipped
      with no live keys and passes when they are; if no cancellation endpoint exists
      for a test-mode auth link, state that explicitly in a code comment next to the
      test rather than silently omitting cleanup.
- [x] 3.5 Update `test_razorpay_client.py::test_create_registration_link_is_simulated`
      to call the new signature (with a `customer_email` argument) and verify it
      still asserts `resp["simulated"] is True`.

## 4. Coexistence updates for `refactor-clean-architecture-layering`'s committed files

- [x] 4.1 Update `recovery/interfaces/ports.py`'s `PaymentGatewayInterface.
      reopen_order_checkout` abstract method signature to accept the two new
      parameters. Verify `python -c "import recovery.interfaces.ports"` succeeds.
- [x] 4.2 Update `recovery/adapters/razorpay_gateway.py`'s `RazorpayGateway.
      reopen_order_checkout` to accept and forward the two new parameters to
      `self._translate(...)`. Verify `backend/recovery/tests/test_adapters.py`'s
      `test_a_404_becomes_a_not_found_domain_error` passes when updated to call
      `RazorpayGateway().reopen_order_checkout("order_x", 100, "receipt", "Name",
      "+919821123456")`.
- [x] 4.3 Update `recovery/tests/fakes.py`'s `FakeGateway.reopen_order_checkout` to
      accept and record the two new parameters. Verify
      `backend/recovery/tests/test_interactors/test_fakes_satisfy_ports.py` passes
      with its call site updated to the 5-arg form.

## 5. Regression pass

- [x] 5.1 Run the full backend suite (`cd backend && .venv/Scripts/python.exe -m
      pytest -q`) and confirm no pre-existing test outside the ones explicitly
      updated above fails, is deleted, or is weakened. Record the before/after
      passed count in the PR description.
- [x] 5.2 With no live keys configured, run `python manage.py seed_data --flush`
      followed by a batch replay (`python manage.py replay_batch --sync`) and confirm
      `retry_order` and `registration_link` decisions still resolve transactions to
      `recovered`/`failed`/`escalated` as before — no transaction is left in
      `processing`.
