## Context

All three existing `Transaction.Kind`s are created two ways: `seed_data.py` (synthetic,
for the replay demo) and `WebhookView.post` (`recovery/views.py`), which maps a
simulated webhook `event` string through `WEBHOOK_KIND_MAP` to a `Kind` and creates the
`Transaction` directly from the payload — there is no live polling of Razorpay from
this codebase for any existing flow. `_heuristic_diagnosis` (`backend/agents/pipeline.py`)
keys entirely off `failure_code`; an empty code is itself treated as a weak signal
(`root_cause="unknown"`, confidence 0.35) that routes straight to escalation.
`evaluate_guardrails` (`backend/recovery/guardrails.py`) branches only on
`decision.chosen_action` and `txn.kind`/`txn.amount`/`txn.failure_code` — nothing in it
is failure-code-specific except rule 4's `"card" in failure_code` check.

A second change, `refactor-clean-architecture-layering`, is in flight (7/40 tasks done)
and is moving `recovery/tasks.py` and `recovery/guardrails.py` behind an
interactors/storages/ports layering. Its own proposal commits to two things relevant
here: `evaluate_guardrails`'s call signature and behavior are preserved behind a
"signature-preserving facade," and its own file-impact list does not touch
`models.py`, `agents/`, or `seed_data.py`. That scopes the overlap with this change
precisely — see Risks below.

## Goals / Non-Goals

**Goals:**
- Give checkout drop-off a real diagnosis signal set (time-since-initiated, cart
  value, last payment method) that produces both confidently-actionable and
  honestly-low-confidence outcomes, the same way the other three flows do.
- Reuse every existing mechanism that already generalizes across kinds (guardrails,
  `new_payment_link`, the webhook ingestion shape, the dashboard's kind-driven
  filter/badge rendering) rather than special-casing a new one.
- Make the synthetic seed distribution's assumptions explicit and inspectable, since
  there is no real abandonment webhook to calibrate against.

**Non-Goals:**
- A live detector that polls Razorpay's Orders API for stale orders. Nothing in this
  codebase polls Razorpay today (every existing flow is webhook- or seed-driven); adding
  one would be new infrastructure disproportionate to this change and is left as
  explicit future work. "Detection" here means: the data shape a detector would produce,
  ingested through the existing generic webhook path, plus synthetic seed data standing
  in for that detector in the demo/replay harness — matching exactly how the other three
  flows are already detected in this system.
- Any change to `Transaction.Status`, the WebSocket frame contract, or
  `recovery/razorpay_client.py`.
- Resolving the `refactor-clean-architecture-layering` sequencing question by picking an
  order for the user — see Risks for why either order is safe, and Open Questions for
  what's left genuinely deferrable.

## Decisions

### 1. Two new `Transaction` fields, not a JSON blob or a repurposed existing field
Add `checkout_initiated_at` (`DateTimeField(null=True, blank=True)`) and
`last_payment_method` (`CharField(max_length=32, blank=True)`, free-text like
`failure_code` — not `TextChoices`, since it's descriptive gateway metadata the
application doesn't enforce a closed vocabulary over).

Rejected alternatives:
- **Reuse `created_at`** to represent "when the checkout started." `created_at` is
  `auto_now_add=True`, so it cannot be backdated through `Transaction.objects.create()`
  — it always means "when RecoverAI's record was created," which is the detection time,
  not the checkout-start time. Conflating the two also breaks once a real webhook exists:
  a genuine abandonment event would arrive well after the checkout started, and the
  diagnosis needs the gap between those two moments, not zero.
- **Reuse `failure_code`** to smuggle a signal string (e.g. `"upi"`). Rejected outright:
  the whole point of this kind is that it has no failure code, and overloading the field
  would corrupt `_heuristic_diagnosis`'s existing substring-matching table for every
  other kind that scans it.
- **A JSON `context` field** on `Transaction` for arbitrary future signals. Rejected as
  premature generality for exactly two well-known signals needed by every
  `checkout_dropoff` row; it would need its own migration and access pattern anyway,
  with none of the type-safety of two plain columns. `amount` already covers cart value
  — no field is added for that.

Both new fields are nullable/blank and populated only for `checkout_dropoff`, the same
way `razorpay_order_id` today is populated only for `payment_degradation` and left
blank for `subscription_failure`/`receivable`. This is the model's existing shape, not
a new pattern.

### 2. Detection story: a configurable at-risk window, enforced by the producer, not by ingestion
Add one setting, `CHECKOUT_DROPOFF_AT_RISK_HOURS` (env-configurable, default `1.0`) —
the minimum age an abandoned checkout must reach before it counts as at-risk. Neither
`WebhookView` nor `seed_data` re-validates this window at ingestion time — no existing
kind re-validates its own "is this actually at risk" precondition at ingestion either
(e.g. `invoice.expired` is trusted as already-expired by its caller). The setting exists
so:
- `seed_data` guarantees every synthetic `checkout_dropoff` row has
  `checkout_initiated_at <= now - CHECKOUT_DROPOFF_AT_RISK_HOURS`, i.e. every seeded row
  is already past the window by construction, standing in for what a real detector would
  have already filtered for.
- The new `WEBHOOK_KIND_MAP["checkout.abandoned"]` entry's docstring states the window
  is the producing system's responsibility to enforce before firing the event — matching
  how the other three synthetic event names document their own real-vs-simulated status.

**`checkout.abandoned` is not a real Razorpay webhook event** — Razorpay does not emit
one. It is added to `WEBHOOK_KIND_MAP` purely so the existing simulated-webhook
ingestion path (already used by the batch simulator and the other three kinds) can
create `checkout_dropoff` transactions the same way. This must be documented at the
call site exactly as prominently as the "no force-retry endpoint" caveats already are
elsewhere in this codebase, so it's never mistaken for a real integration.

### 3. Diagnosis heuristic: a signal-based decision tree, not a substring-match table
`_heuristic_diagnosis`'s existing table scans `failure_code` for substrings — there is
no string to scan here. Add a separate function, checked by kind before the existing
"empty code → `unknown`" fallback (that fallback stays correct for the other three
kinds, where an empty code really is a weak signal; it would be wrong here, where an
empty code is the norm, not a gap — see the `diagnosis-classification` spec delta).

Signals: `hours_since_initiated = (now - checkout_initiated_at) / 1h`; `amount`
(cart value); `method_attempted = bool(last_payment_method)`.

Decision tree (first matching branch wins; each row's rationale mirrors the "more
specific pattern wins" precedent already documented in `_DIAGNOSIS_RULES`):

| Condition | root_cause | confidence | Rationale |
|---|---|---|---|
| `hours_since_initiated ≤ 2` AND `amount ≥ HIGH_VALUE_CART_INR` AND `method_attempted` | `high_value_recent_dropoff` | 0.85 | Highest-intent, highest-value signal — worth the fastest, most confident nudge. |
| `hours_since_initiated ≤ 2` AND `method_attempted` | `recent_dropoff_payment_attempted` | 0.80 | Customer was mid-payment very recently; short recall window. |
| `hours_since_initiated ≤ 24` AND `method_attempted` | `short_window_dropoff` | 0.68 | Still same-day, but intent has cooled somewhat. |
| NOT `method_attempted` (any age) | `browse_abandonment` | 0.45 | Never attempted a payment method at all — weaker purchase intent than a mid-payment drop, checked ahead of the age-only bands below so a stale *and* method-less cart doesn't get miscounted as merely "aging." |
| `hours_since_initiated ≤ 72` | `aging_dropoff` | 0.55 | Multi-day-old but still plausible; deliberately near the default 0.60 confidence floor so it can exercise escalation honestly, same rationale as the existing "no code at all" case. |
| else | `cold_dropoff` | 0.32 | Past a week old — treat like any other genuinely low-confidence diagnosis. |

`HIGH_VALUE_CART_INR` is a heuristic-tuning constant (proposed default ₹8,000 — a
"notable cart," well under the ₹50,000 default `SPEND_CEILING_INR` autonomous-action
ceiling, which is a different concept: one gates *diagnosis confidence*, the other gates
*whether to act at all*). Like the `GUARDRAILS` thresholds, it belongs in `settings.py`,
not hard-coded, so it can be tuned without a code change — but its exact value is safely
deferrable (see Open Questions).

### 4. Decision heuristic: always `new_payment_link`, reasoning text written for this kind specifically
Add one branch to `_heuristic_decision`, evaluated alongside the existing
`subscription_failure`/`receivable`/default branches:
```
elif txn["kind"] == "checkout_dropoff":
    action = "new_payment_link"
```
The existing confidence-floor check (`confidence < 0.60 → escalate`) already in
`_heuristic_decision` handles `aging_dropoff`/`cold_dropoff`/`browse_abandonment`
correctly with zero new code — no kind-specific escalation logic is needed.

`retry_order` is deliberately never chosen here, even though `razorpay_order_id` may be
populated: reopening the *same* order intent assumes a payment attempt failed and can be
retried, which is what `reopen_order_checkout` models. A checkout drop-off never had a
failed payment to retry — Checkout was simply never completed — so the only honest lever
is a fresh payable artifact, exactly as the proposal states.

The shared `_REASONING["new_payment_link"]` string ("Same card/order can't be reused")
is factually wrong for this kind — nothing failed. Rather than force a shared string
across two different meanings, write the `checkout_dropoff` branch's reasoning text
inline (e.g. "Customer never completed Checkout — there's no failed payment to retry,
so a fresh payment link recaptures the cart."), bypassing the `_REASONING` dict lookup
for this one case.

### 5. LLM prompt path: extended context, unchanged JSON contract
Both prompts keep their existing `{root_cause, confidence, reasoning_text}` /
`{chosen_action, reasoning_text}` contracts and valid-action set (`new_payment_link`
already exists — no schema change). `_run_recovery_pipeline` (`recovery/tasks.py`)
extends the plain-dict `transaction_fields` it builds with `checkout_initiated_at`
(ISO string or `None`) and `last_payment_method` (string or `""`) for every kind — harmless
for the other three, where both are always empty. The diagnosis system prompt gains one
paragraph: a `checkout_dropoff` transaction has no failure code by design and must be
reasoned over using elapsed time, cart value, and last payment method instead. The
decision system prompt gains one sentence: a `checkout_dropoff` transaction has no order
to retry — prefer `new_payment_link`.

### 6. Guardrails: zero code changes to `recovery/guardrails.py`
Walking `evaluate_guardrails`'s six rules against a `checkout_dropoff` transaction whose
decision is always `new_payment_link` or `escalate`:
1. **Confidence floor** — generic by `diagnosis.confidence`. Applies unchanged.
2. **Max retry attempts** — gated on `chosen_action in RETRY_ACTIONS` (`{retry_order}`).
   Never entered for this kind (nothing logged, same as any other kind's non-retry
   decision today, e.g. `payment_degradation`'s `card_expired → new_payment_link`).
3. **Spend ceiling** — generic by `txn.amount`. Applies unchanged.
4. **Cooldown between retries** — gated on `chosen_action in RETRY_ACTIONS and "card" in
   failure_code`. Never true (action is never `retry_order`); logs PASSED
   ("no card-decline cooldown applies"), same as today's non-retry paths.
5. **Contact frequency cap** — gated on `chosen_action in CONTACT_ACTIONS`, which already
   includes `NEW_PAYMENT_LINK`. Applies unchanged — exactly the code path
   `payment_degradation`'s `new_payment_link` branch already exercises today.
6. **Compliance hours** — gated on `txn.kind == Kind.RECEIVABLE`. Never true for
   `checkout_dropoff`; no B2B business-hours restriction applies, matching
   `payment_degradation`/`subscription_failure` today.

Every rule is already correctly scoped by the combination of `chosen_action` and
`txn.kind` checks that exist today — nothing new to wire. "Guardrail wiring" in this
proposal means proving that with tests (task list), not writing new rule code.

### 7. Frontend: one data-table entry each, one new icon glyph
`KIND_META`/`KIND_FILTERS` (`frontend/src/lib/format.js`) get a `checkout_dropoff` entry;
`SearchFilterBar.jsx` needs no change, since it already renders `KIND_FILTERS` generically.
No existing glyph in `frontend/src/components/ui/Icon.jsx` reads as "abandoned
checkout" (`card`, `repeat`, `invoice` are the only "flow" icons, each already claimed);
add one new hand-authored `cart` glyph to the `STROKE` map, following the file's existing
coordinate-space and stroke-width conventions. The exact path is an implementation
detail for the apply phase, not a design decision.

If the frontend isn't deployed in the same release as the backend, `kindMeta()`'s
existing fallback (`{ label: humanize(kind), short: humanize(kind), icon: "card" }`)
already renders an unrecognized kind reasonably — so this isn't a strict deploy-order
dependency, just a completeness gap until both ship.

## Risks / Trade-offs

- **[Risk]** `refactor-clean-architecture-layering` is mid-flight and its own proposal
  claims a signature-preserving facade for `evaluate_guardrails` and zero changes to
  `models.py`/`agents/`/`seed_data.py`. → **Mitigation**: this change adds zero lines to
  `recovery/guardrails.py` and `recovery/tasks.py` (see Decisions 4 and 6 — the
  `new_payment_link` code path this kind uses already exists and needs no new branch in
  either file), so there is no code-level collision with that refactor's stated scope in
  either file. The only literal same-file overlap is `recovery/views.py`: the refactor's
  impact list names `WebhookView.post`'s body, while this change only adds one entry to
  the module-level `WEBHOOK_KIND_MAP` dict the method reads — a small, low-conflict,
  order-independent addition either way. This change can land before, after, or
  interleaved with that refactor without redesign.
- **[Risk]** The confidence bands in Decision 3 are hand-picked, not derived from real
  abandonment data (none exists). → **Mitigation**: every band is named for what it
  represents and is a single tunable constant per band, not baked into control flow —
  the `aging_dropoff` band is deliberately placed near the confidence floor for the same
  reason the existing "no failure code" case is, so the demo can honestly show both an
  autonomous action and an escalation from this flow, not just the happy path.
- **[Trade-off]** No live Razorpay Orders polling means "detection" is honest only up to
  what this codebase already does for the other three kinds (webhook + seed). This is
  named as a Non-Goal rather than hidden.

## Migration Plan

One Django migration, additive only:
- `AddField`: `checkout_initiated_at`, `last_payment_method` on `Transaction` (both
  nullable/blank; no backfill needed — existing rows of the other three kinds simply
  never populate them, same as `razorpay_order_id` today).
- `AlterField`: `Transaction.kind`'s `choices` metadata, picked up automatically by
  adding the new `Kind` member. This is a Django-level metadata change only — `kind` is
  a plain `CharField`, so no database constraint changes and no data migration.
- Does not touch `AuditLogEntry` or migration 0002's trigger in any way.

Rollout is not deploy-order-sensitive: the backend change is additive and the frontend
degrades gracefully on an unrecognized kind (see Decision 7), so backend and frontend
can ship in either order or the same release.

## Open Questions

- Exact numeric values for `HIGH_VALUE_CART_INR` and the three hour-band boundaries
  (2h / 24h / 72h) in Decision 3, and the default seed count for a new
  `--checkout-dropoff` `seed_data` argument. These are calibration constants in the same
  spirit as the existing `GUARDRAILS` defaults — tunable after the fact without changing
  the requirement shape in the spec delta (which only requires "recent + high-intent →
  confident" and "stale → low-confidence," not specific numbers). Proposed starting
  values are given in Decision 3 and tasks.md; revisit once the seeded demo is actually
  watched end to end.
