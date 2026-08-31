## Context

`backend/recovery/razorpay_client.py` is a thin, transparent wrapper: every function
is meant to reflect one real Razorpay primitive, with a deterministic simulated
response standing in when no live keys are configured (see proposal.md - Why for how
each of the two bugs was confirmed against Razorpay's documented API).

Two things make this file's blast radius larger than "edit two functions":

1. An in-flight, unrelated change, `refactor-clean-architecture-layering`, has
   already committed (phase 1, commit `ed54e53`) a set of files that wrap
   `razorpay_client` behind a port: `recovery/interfaces/ports.py`
   (`PaymentGatewayInterface`), `recovery/adapters/razorpay_gateway.py`
   (`RazorpayGateway`, which resolves `razorpay_client.<fn>` by name at call time so
   `mock.patch` on the module keeps working), and `recovery/tests/fakes.py` /
   `recovery/tests/test_adapters.py`. None of this is wired into `tasks.py` yet —
   `tasks.py::_call_razorpay` still calls `razorpay_client` functions directly. That
   refactor's own `tasks.md` phase 2.3 (adding the gateway) is checked as not-yet-done
   even though the file exists; the vocabulary phase (1.x) is what actually landed.
2. `recovery/dtos.py`'s `TransactionDTO` (also phase 1 of that refactor) states in its
   docstring that it "deliberately carries all thirteen fields" mirroring
   `TransactionSerializer.Meta.fields` as of that commit.

Both are load-bearing for Decision 4 and Decision 5 below: this change touches files
that a concurrent, independently-landing change also touches, and needs to leave both
changes independently applicable in either order.

## Goals / Non-Goals

**Goals:**
- `retry_order` and `registration_link` issue Razorpay calls that match Razorpay's
  documented API, in live mode, without inventing an endpoint or omitting a required
  field.
- Neither fix depends on, or blocks, `refactor-clean-architecture-layering` landing
  first, last, or interleaved.
- Local (no-keys) behavior stays fully simulated and now honestly mirrors the
  corrected live behavior rather than the old, incorrect one.

**Non-Goals:**
- Building a real Razorpay Checkout.js integration in the frontend. `reopen_order_
  checkout`'s existing docstring claims the frontend reopens Checkout against a
  confirmed order; nothing in `frontend/src` does this today (confirmed by a
  repo-wide search for `checkout`/`razorpay` — the three hits are a table column, a
  login-page label, and an audit-response viewer, none of them a Checkout.js call).
  A `GET /orders/:id`-plus-frontend-Checkout design is real and defensible, but it is
  net-new frontend scope this change does not attempt — see Decision 1.
- Changing `tasks.py::_execute_action`'s 404-fallback mechanism (`is_not_found()` /
  `_FALLBACK_ACTIONS`) — see Decision 3.
- Exposing `customer_email` over the REST API or in `TransactionDTO` — see Decision 5.
- Finishing or advancing `refactor-clean-architecture-layering` — this change only
  makes the minimum mechanical adjustment to the files it already committed so both
  changes keep applying cleanly (Decision 4).

## Decisions

### Decision 1 — `retry_order`'s live call becomes a fresh payment link, not an order-reopen call

Three options were on the table:

- **(a) Always issue a fresh payment link for `retry_order` too.** Razorpay has no
  reopen/confirm/re-attempt endpoint on Orders; `create_payment_link` already exists
  and already works. `retry_order` and `new_payment_link` become behaviorally
  identical in live mode — only their `Decision.Action` label (and therefore their
  audit trail and diagnosis-reasoning text) differs.
- **(b) `GET /orders/:id` to confirm the order is still payable, hand the id to the
  frontend to reopen Checkout.** This matches the *docstring's* stated intent, but
  nothing in the frontend today opens Checkout against anything — there is no
  Checkout.js integration at all. Shipping only the backend half of (b) would not
  recover anything; a customer would need to already be looking at a Checkout modal
  for a "confirmed" order to matter, and no such modal exists. Making (b) actually
  work requires new frontend surface (a Checkout trigger wired to a transaction),
  which is a materially larger, separately-reviewable change.
- **(c) Do nothing / leave as-is.** Rejected outright — this is the bug.

**Decision: (a).** It is the only option that fixes the bug within this change's
scope without adding a frontend dependency, and it is honest about what Razorpay
actually offers: a fresh payable artifact, not a resurrection of a specific attempt.
(b) is recorded here as a legitimate future direction, not dismissed — if a real
Checkout.js integration is ever built, `retry_order` could re-diverge from
`new_payment_link` at that point, on its own change.

**Mechanical consequence:** `reopen_order_checkout(order_id, amount_paise, receipt)`
has no `customer_name`/`customer_phone` parameters, but a real `POST /payment_links`
call requires a `customer: {name, contact}` object (see `create_payment_link`, same
file). Two ways to close that gap:

- **(a1) Widen the signature.** Add `customer_name`, `customer_phone` as two more
  positional/keyword parameters, and have the live-mode body delegate to
  `create_payment_link(amount_paise, description, customer_name, customer_phone)`,
  merging in `{"retried_order_id": order_id}` for audit traceability (`order_id` is
  otherwise unused in the new call — it stops being a lookup key and becomes
  provenance metadata). `tasks.py::_call_razorpay`'s `RETRY_ORDER` branch passes
  `txn.customer_name, txn.customer_phone` alongside what it already passes.
- **(a2) Delete `reopen_order_checkout`, route `RETRY_ORDER` through
  `create_payment_link` directly** in `tasks.py::_call_razorpay`, and remove the
  now-redundant port method, gateway method, and fake method.

**Decision: (a1).** It is strictly the smaller diff against the concurrent refactor's
already-committed files: (a2) would require deleting a port method and retargeting
`test_adapters.py::test_a_404_becomes_a_not_found_domain_error` (which specifically
exercises `reopen_order_checkout`'s 404→`GatewayArtifactNotFound` translation) onto a
different function, for a behavioral outcome (a) already achieves either way. (a1)
also keeps a clear code home for retry_order-specific concerns (the `retried_order_id`
provenance field) if this action's live behavior ever needs to diverge from
`new_payment_link`'s again.

**Simulated-mode shape:** changes from order-shaped (`{"simulated": True, "id":
"sim_order_...", "order_id": ..., "amount": ...}`) to payment-link-shaped (mirroring
`create_payment_link`'s simulated response: `{"simulated": True, "id":
"sim_plink_...", "short_url": "https://rzp.io/l/sim...", "amount": ...}`), so a
demo run with no live keys shows the same artifact shape the live path would actually
produce. `test_razorpay_client.py::test_reopen_order_checkout_is_simulated`'s
assertion on `resp["id"].startswith("sim_order_")` is expected, sanctioned churn —
it moves to asserting a `short_url` prefix, exactly as
`test_create_payment_link_is_simulated` already does.

### Decision 2 — `create_registration_link`'s live payload gets the three missing/wrong fields

Fixed per the confirmed findings: `customer.email` added, `subscription_registration:
{method, auth_type}` added, `amount` forced to `0`. The real due amount is folded into
the `description` string already built by `tasks.py::_call_razorpay` (e.g. `"RecoverAI
recovery — <txn id> — ₹1,234 due"`), so the customer's registration-link page can still
show what's owed even though the registration call itself requests ₹0.

`method`/`auth_type` values: this change picks `method: "emandate"` and a
representative `auth_type` as documented defaults, explicitly flagged in code comments
as not independently re-verified beyond what informed this proposal — see Open
Questions. Getting the exact enum value wrong is a live-mode-only risk (it fails loud,
as a rejected API call → escalation, not silently), and is cheap to correct in a
follow-up once a live-mode test run against Razorpay's test-mode API confirms the
accepted values.

### Decision 3 — customer email: add `Transaction.customer_email`, don't synthesize or omit it

Three options considered, per the task brief:

- **Add a nullable-equivalent `customer_email` field to `Transaction`.** Real data,
  threaded through the same three places `customer_name`/`customer_phone` already
  flow (model, `seed_data.py`, `WebhookView.post`).
- **Synthesize a placeholder email per-call.** Rejected: this would be fabricated
  contact data sent to Razorpay's records under a transaction's *real* name and phone
  number the moment live keys point at real customers — a correctness fix should not
  introduce a new dishonesty to close the old one.
- **Treat "required" as untested and try sending no email.** Rejected: nothing found
  during research contradicts Razorpay's documented requirement, and CLAUDE.md's own
  standard for this file is "no Razorpay-API mistake" — guessing that documentation is
  wrong, with no evidence, repeats the same category of error this change exists to
  fix.

**Decision:** add `customer_email = models.EmailField(blank=True)` to `Transaction`
(migration), matching the existing style of `customer_phone` (blank-ok, not
`null=True`). Populate it in `seed_data.py`'s `_customer()` helper using the
RFC 2606 test-reserved TLD — `f"{customer_id}@example.test"` — so synthetic seed data
is recognizable as synthetic even if it ever leaked into a real API call by mistake.
Accept it in `WebhookView.post` as `payload.get("customer_email", "")`, alongside the
existing `customer_name`/`customer_phone` lines, since a real Razorpay webhook's
customer object can carry an email and there is no reason to drop it if a caller
supplies one.

**Pre-flight guard trace:** in live mode, a blank `customer_email` makes
`create_registration_link` raise `RazorpayError(msg, status_code=None)` before any
network call. Tracing this through `tasks.py::_execute_action`: `REGISTRATION_LINK` is
not in `_FALLBACK_ACTIONS`, and `is_not_found()` returns `False` for `status_code=
None`, so the existing `except razorpay_client.RazorpayError` branch falls straight to
`_escalate_api_failure` → an `action_failed` audit entry and an escalated ticker push —
the same path a real Razorpay rejection would take. No new escalation branch is
needed; this is the existing error-handling contract doing exactly what it already
does for any other unrecoverable `RazorpayError`.

### Decision 4 — keep `customer_email` off the public API and off `TransactionDTO`

`customer_email`'s only consumer is the outbound `create_registration_link` call
inside `tasks.py`/`razorpay_client.py`, which today reads `txn.customer_name`/
`txn.customer_phone` straight off the Django model instance — there is no DTO layer
between the model and that call yet (`refactor-clean-architecture-layering`'s phase 4,
which would introduce one, is not done). So:

- **Not added to `TransactionSerializer.Meta.fields`** — no REST/dashboard consumer
  needs it, and adding it would be a new, unrequested piece of customer PII on a
  read-only API with no access-control story of its own beyond the existing JWT auth.
  Minimal surface change: only add what the fix requires.
- **Not added to `TransactionDTO`** — since the serializer doesn't change, the DTO's
  "mirrors all thirteen `TransactionSerializer.Meta.fields`" invariant (its own
  docstring, from the concurrent refactor's phase 1) stays true without modification.
  This is a deliberate consequence of the point above, not an oversight: if a future
  change ever does expose `customer_email` over the API, that change updates both the
  serializer and the DTO together, in one place.

### Decision 5 — `tasks.py::_execute_action`'s 404-fallback needs no change

`_FALLBACK_ACTIONS = {RETRY_ORDER, INVOICE_REMINDER}` and `is_not_found()` stay exactly
as they are.

- **`INVOICE_REMINDER`**: `resend_invoice`'s `POST /invoices/{id}/notify_by/{medium}`
  is untouched by this change and is a real, id-targeted endpoint that can genuinely
  404 on a stale invoice id (seed data's synthetic ids, or any invoice since deleted/
  expired at Razorpay). The fallback remains necessary and correct here, unchanged.
- **`RETRY_ORDER`**: after Decision 1, `reopen_order_checkout`'s live call is a
  `POST /payment_links` call with no id in the request path — there is no longer an
  "artifact referenced by id" for Razorpay to report as not-found, so this branch of
  the fallback becomes unreachable through the real call path. Leaving `RETRY_ORDER`
  in `_FALLBACK_ACTIONS` is harmless dead-path, not incorrect: `is_not_found()` simply
  never returns `True` for a call that itself never raises a 404 status. Removing it
  was considered and rejected — it buys nothing (no code path currently relies on its
  absence) and would be one more edit to a file this change otherwise doesn't need to
  touch, for a purely cosmetic reason. The existing tests that exercise this branch
  (`test_execute_action_falls_back_to_payment_link_on_404_order`, etc.) mock at the
  `_call_razorpay` level, not inside `reopen_order_checkout`, so they continue to
  validly test the fallback *mechanism* itself regardless of what `reopen_order_
  checkout`'s internals do.

### Decision 6 — coexistence with `refactor-clean-architecture-layering`

That change's phase 1 (committed) added, unused by `tasks.py` today:
`recovery/interfaces/ports.py` (`PaymentGatewayInterface.reopen_order_checkout(
order_id, amount_paise, receipt)`), `recovery/adapters/razorpay_gateway.py`
(`RazorpayGateway.reopen_order_checkout`, resolving `razorpay_client.reopen_order_
checkout` by name at call time), `recovery/tests/fakes.py`'s `FakeGateway.reopen_
order_checkout`, and two assertions in `recovery/tests/test_adapters.py` that call
`RazorpayGateway().reopen_order_checkout("order_x", 100, "receipt")` positionally.

Widening `reopen_order_checkout`'s signature (Decision 1) means these three
production files' method signatures gain the same two parameters, purely mechanically:
none of the affected tests assert on request payload shape, only on exception
translation (`RazorpayError` → `GatewayArtifactNotFound`/`GatewayError`) and pass-
through behavior, so appending two arguments to each call site
(`RazorpayGateway().reopen_order_checkout("order_x", 100, "receipt", "Name",
"+91...")`) preserves every existing assertion unchanged. `recovery/tests/
test_interactors/test_fakes_satisfy_ports.py`'s `gateway.reopen_order_checkout(
"order_x", 100, "receipt")` call gets the same treatment.

This is the same kind of file-level (not proposal-level) overlap `add-checkout-
dropoff-recovery` and `add-mandate-recovery-sequence` already documented against the
same refactor: independently applicable in either order, because this change adds
parameters rather than removing or renaming anything the refactor's committed code
already depends on.

## Risks / Trade-offs

- **`method`/`auth_type` enum values may be wrong.** [Risk] A live-mode call could be
  rejected by Razorpay for an invalid `subscription_registration.method`/`auth_type`
  combination → [Mitigation] this fails as a loud, escalated `action_failed` audit
  entry (Decision 3's guard doesn't apply here, but the existing generic error path
  does — see the action-execution spec's "unrecoverable API error escalates" rule),
  never as a silent success or a wedged transaction; the new `TestLiveMode` case
  (see tasks.md) catches a wrong value against Razorpay's real test-mode API before
  this ships.
- **`retry_order` and `new_payment_link` become indistinguishable in live-mode API
  traffic.** [Risk] Anyone inspecting only the Razorpay dashboard, not this app's
  audit trail, loses the ability to tell which decision produced a given payment link
  → [Mitigation] the distinction is preserved exactly where it's actually consumed —
  `Action.Type`, `Decision.Action`, the audit log, and the reasoning-chain UI — none
  of which this change touches.
- **A live `subscription_failure` transaction with no `customer_email` on file now
  escalates instead of attempting a registration link.** [Risk] Slightly more
  escalations for legacy/incompletely-populated transactions → [Mitigation] this is
  strictly safer than the alternative (sending a payload Razorpay likely rejects
  anyway, arriving at the same escalated outcome through a live network round-trip
  instead of a local pre-flight check) — same terminal state, one less network call.

## Open Questions

- Whether a different `subscription_registration.method` (e.g. `upi`) relaxes
  Razorpay's `amount: 0` requirement for e-mandate registration. Not confirmed either
  way by the research behind this proposal. Doesn't change this change's approach —
  `method: "emandate"` with `amount: 0` is the documented-safe combination — but is
  worth settling with a real test-mode call before anyone builds a UPI-specific
  registration path on top of this.
- The exact accepted value(s) for `subscription_registration.auth_type` under
  `method: "emandate"` — picked a representative default (see Decision 2); the new
  live-mode test (tasks.md) is the mechanism for catching a wrong value, not a
  substitute for confirming it against Razorpay's docs/dashboard ahead of time if a
  reviewer has access to check.
