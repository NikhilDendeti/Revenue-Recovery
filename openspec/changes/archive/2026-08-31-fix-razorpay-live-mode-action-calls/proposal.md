## Why

Two of `recovery/razorpay_client.py`'s live-mode calls target Razorpay operations
that do not exist as documented: `reopen_order_checkout` `POST`s to `/orders/{id}`
with an empty body to "reopen" an order — Razorpay's Orders API documents no such
verb (only `PATCH`, which updates `notes` only) — and `create_registration_link`
posts to the correct `/subscription_registration/auth_links` endpoint but with a
payload missing fields the real e-mandate authorization flow requires
(`customer.email`, a `subscription_registration` object, and `amount: 0`). Both
bugs are invisible today: locally there are no live keys, so neither branch runs,
and even with live keys `reopen_order_checkout`'s call currently happens to 404
against seed data's synthetic order ids, which accidentally routes into the
existing 404-fallback and issues a working payment link anyway. That accident stops
protecting the demo the moment Razorpay returns anything other than 404 for an
undocumented verb+path (a 405 is plausible), at which point every `retry_order`
decision — the majority of `payment_degradation`'s weight in `seed_data.py` —
escalates instead of recovering. `create_registration_link`'s payload would likely
be rejected by Razorpay's live API outright once real keys are configured, since
the documented requirements are missing entirely, not just mis-valued.

## What Changes

- `reopen_order_checkout`'s live-mode body no longer calls the undocumented
  `POST /orders/{id}`. It now issues a real Payment Link — the same call
  `create_payment_link` makes — so a `retry_order` decision recovers in live mode
  the same way `new_payment_link` does; the two decisions keep distinct
  audit/decision labels, but their underlying Razorpay call converges. Its
  signature gains `customer_name`/`customer_phone` (required to build the
  Payment Link's `customer` object), and its response echoes the original
  `order_id` for audit traceability.
- `reopen_order_checkout`'s simulated-mode response shape changes from
  order-shaped (`id`, `order_id`) to payment-link-shaped (`short_url`), so local
  demo behavior honestly mirrors the corrected live behavior.
- `create_registration_link`'s live-mode payload gains `customer.email`
  (**BREAKING** for any live-mode caller relying on the current 4-argument
  signature — see below), a `subscription_registration: {method, auth_type}`
  object, and forces `amount: 0` per Razorpay's e-mandate registration
  requirement (the actual due amount moves into the `description` text only).
  It also gains a pre-flight guard: in live mode, a blank `customer_email`
  raises `RazorpayError` before the network call rather than sending a payload
  Razorpay will likely reject.
- Add a `customer_email` field to `Transaction` (migration), threaded through
  `seed_data.py`'s synthetic customer generation and `WebhookView`'s inbound
  payload parsing — the only place this data can come from, since `Transaction`
  had no email field at all. Not added to `TransactionSerializer`/the REST API:
  its only consumer is the outbound Razorpay call.
- No change to `tasks.py::_execute_action`'s 404-fallback (`is_not_found()` /
  `_FALLBACK_ACTIONS`): confirmed still correct and necessary for
  `invoice_reminder` (a real id-targeted endpoint that can genuinely 404);
  confirmed harmless-but-unreachable for `retry_order` now that its call can no
  longer 404 the way an order-lookup could.
- Test coverage: new/updated simulated-mode assertions for `reopen_order_checkout`,
  a new `TestLiveMode` case for `create_registration_link`, and a design-level call
  on whether `reopen_order_checkout` still warrants its own `TestLiveMode` case.
- **Open question, not resolved by this change** (see design.md): whether a
  different `subscription_registration.method` (e.g. `upi`) relaxes Razorpay's
  `amount: 0` requirement for e-mandate registration.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `action-execution`: the requirement governing how `retry_order` and
  `registration_link` decisions call the payment provider changes — `retry_order`
  no longer assumes an order-reopen endpoint exists and instead issues a fresh
  payment link in live mode; `registration_link`'s live payload must carry the
  fields Razorpay's e-mandate authorization flow actually requires, and must not
  attempt the call at all with no customer email on file.

## Impact

- **Code**: `backend/recovery/razorpay_client.py` (both functions rewritten),
  `backend/recovery/models.py` (+`customer_email` field, +migration),
  `backend/recovery/management/commands/seed_data.py` (`_customer()` populates a
  synthetic email), `backend/recovery/views.py` (`WebhookView.post` reads an
  optional `customer_email` from the inbound payload), `backend/recovery/tasks.py`
  (`_call_razorpay`'s `RETRY_ORDER`/`REGISTRATION_LINK` branches pass the new
  arguments).
- **Not modified**: `tasks.py::_execute_action`'s fallback logic,
  `recovery/guardrails.py`, the audit-log trigger, `TransactionSerializer`/the
  REST API contract, the WebSocket contract, `TransactionDTO` (stays a correct
  mirror of the unchanged 13 serializer fields — `customer_email` is deliberately
  not one of them).
- **Coexistence with `refactor-clean-architecture-layering`** (in-flight, phase 1
  committed): that change already added `recovery/interfaces/ports.py`
  (`PaymentGatewayInterface.reopen_order_checkout`), `recovery/adapters/
  razorpay_gateway.py`, and `recovery/tests/fakes.py`/`test_adapters.py`, none of
  which are wired into `tasks.py` yet. Widening `reopen_order_checkout`'s
  signature requires the same two new parameters added to those three files'
  method signatures — mechanical, since none of their tests assert on payload
  shape, only exception translation. See design.md.
- **Tests**: `backend/recovery/tests/test_razorpay_client.py` (updated simulated
  assertions, new live-mode case), `backend/recovery/tests/test_adapters.py` and
  `backend/recovery/tests/test_interactors/test_fakes_satisfy_ports.py` (signature
  update only, no assertion changes), `backend/recovery/tests/test_tasks.py`
  (audited — see design.md for why no assertion changes are expected there).
- **Other specs checked, no delta needed**: `openspec/specs/local-dev-environment/
  spec.md` covers zero-external-service startup and the audit-log trigger only —
  it does not reference either function's payload or behavior. A repo-wide search
  of `openspec/specs/` for both function names, `registration_link`,
  `subscription_registration`, and `auth_link` found no other references.
