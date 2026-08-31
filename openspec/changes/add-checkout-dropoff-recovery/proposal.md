## Why

Checkout drop-off — a customer who opens Razorpay Checkout, sees the Order, and never
completes payment — is real revenue at risk that today is invisible to RecoverAI. All
three existing flows key their diagnosis off `failure_code`: something *failed* and
left a code behind. An abandoned checkout never fails; it just never finishes, so there
is no code to pattern-match against. Without a fourth `Transaction.Kind` and a
non-failure-code diagnosis path, this category of at-risk revenue has no detection
story, no diagnosis, and no recovery action at all.

## What Changes

- Add `checkout_dropoff` as a fourth `Transaction.Kind`, alongside
  `payment_degradation` / `subscription_failure` / `receivable`.
- Add two new `Transaction` fields — `checkout_initiated_at` (nullable datetime) and
  `last_payment_method` (blank-ok free-text, mirroring `failure_code`'s open-vocabulary
  style) — the two signals a checkout-drop-off diagnosis needs and that no existing
  field can honestly carry. `amount` is reused as-is for cart/order value; no new field
  for that.
- Add a `checkout.abandoned` entry to `WEBHOOK_KIND_MAP` (`recovery/views.py`) so the
  existing simulated-webhook ingestion path can create `checkout_dropoff` transactions
  the same way the other three kinds already do. **Razorpay has no such webhook** —
  this is the same synthetic ingestion shape the other three kinds already use for the
  demo/batch simulator, not a claim of a real Razorpay event.
- Add a deterministic heuristic diagnosis path in `backend/agents/pipeline.py` keyed on
  time-since-initiated, cart value, and last payment method instead of `failure_code`,
  plus an LLM prompt path that receives the same signals — both wired into the existing
  `_diagnose_node`/`_decide_node` graph, no new graph node.
- Add decision routing: a confidently-diagnosed `checkout_dropoff` transaction always
  chooses `new_payment_link` (the existing action — Razorpay has no "resume checkout"
  API, so even though a real Order id may exist, it is never reopened via
  `retry_order`); a low-confidence one escalates, via the existing confidence-floor
  branch.
- No changes to `recovery/guardrails.py`: all six existing rules already apply
  correctly to the new kind by construction (see design.md). This proposal adds test
  coverage proving that, not new rule code.
- Add synthetic seed data for the new kind in `seed_data.py`, with an explicit,
  documented distribution for `checkout_initiated_at` age, `last_payment_method`, and
  cart value (see design.md — there is no real abandonment webhook to model this on).
- Add frontend support: a `checkout_dropoff` entry in `KIND_META`/`KIND_FILTERS`
  (`frontend/src/lib/format.js`, consumed by `SearchFilterBar.jsx` unchanged) and one
  new hand-authored icon glyph (`frontend/src/components/ui/Icon.jsx`) since no
  existing glyph fits "abandoned checkout." No `Status` changes — the four kinds share
  the same six-state lifecycle already.
- Tests: new diagnosis-heuristic unit tests, new guardrail-coverage tests exercising
  the new kind against all six rules, and a seed-data test asserting the documented
  distribution shape (age buckets present, at least one over-ceiling record for
  guardrail-escalation coverage, consistent with the existing receivable-seeding
  pattern).

## Capabilities

### New Capabilities
- `checkout-dropoff-recovery`: detection (webhook + seed), the new `Transaction.Kind`
  and its two signal fields, decision routing to `new_payment_link`, and guardrail
  applicability for the checkout-drop-off flow end to end.

### Modified Capabilities
- `diagnosis-classification`: adds a requirement for the case the existing spec
  doesn't cover — a transaction that has no `failure_code` by design (not as a weak
  signal to fall back on) and must be diagnosed from a different signal set entirely.

## Impact

- **Code**: `backend/recovery/models.py` (new `Kind` member, two new fields, one
  migration — no change to `AuditLogEntry` or its trigger), `backend/recovery/views.py`
  (`WEBHOOK_KIND_MAP`), `backend/agents/pipeline.py` (new heuristic function, decision
  branch, LLM prompt text), `backend/recovery/management/commands/seed_data.py` (new
  seeding function + CLI arg), `frontend/src/lib/format.js`,
  `frontend/src/components/ui/Icon.jsx`.
- **Not modified**: `recovery/guardrails.py`, `recovery/tasks.py`'s action-execution
  logic (`new_payment_link` already exists and needs no new branch — see design.md),
  `recovery/razorpay_client.py`, `Transaction.Status`, the WebSocket contract, the
  audit-log trigger.
- **Sequencing note**: `refactor-clean-architecture-layering` is in flight (7/40 tasks
  done at proposal time) and is mid-way through moving `recovery/tasks.py` and
  `recovery/guardrails.py` behind an interactors/storages/ports layering. This
  proposal adds zero lines to either file (see design.md Decisions 4/6), so the only
  literal file-level overlap is a small, order-independent dict addition in
  `recovery/views.py` — see design.md's "Risks / Trade-offs" for why this change can
  land before, after, or interleaved with that refactor without redesign.
- **Tests**: new tests only, additive to `backend/agents/tests/test_pipeline.py`,
  `backend/recovery/tests/test_guardrails.py`, and a new
  `backend/recovery/tests/test_seed_data.py` (no such file exists yet for the other
  three kinds' seeding — see design.md).
- **No** changes to the REST/WebSocket API contracts, no new Razorpay endpoints, no new
  dependencies.
