## Context

`agents/pipeline.py::_heuristic_diagnosis` is the deterministic fallback used
whenever no LLM key is configured (CLAUDE.md: "no LLM key -> rule-based diagnosis
fallback"). It currently resolves a lowercased `failure_code` string against
`_DIAGNOSIS_RULES`, an ordered list of `(needle, root_cause, confidence,
reasoning)` substring rules, first-match-wins, then falls back to
`_KIND_DEFAULTS[kind]` when nothing matches. `_heuristic_decision` then maps
`diagnosis["root_cause"]` to an action via `_PAYMENT_DEGRADATION_ACTIONS` (for
`payment_degradation`) or `_SUBSCRIPTION_RETRIABLE_ROOT_CAUSES` (for
`subscription_failure`, gating `registration_link` vs `escalate`); anything absent
from either mapping falls through `.get(..., "escalate")`.

The 6 existing needles (`insufficient_funds`, `expired`, `card_declined`,
`timeout`, `network`, `mandate`) were tuned against `seed_data.py`'s own invented
codes and do not cover real Razorpay reason codes — see proposal.md for the
concrete gap. `Transaction.failure_code` is an unconstrained `CharField`, and
`WebhookView` passes an inbound webhook's `failure_code` through with no
allowlist, so this heuristic runs against real Razorpay vocabulary whenever no
LLM key is configured (the default posture per CLAUDE.md — nothing here requires
credentials to run).

See proposal.md for the full "why" and the complete list of real Razorpay reason
codes in scope.

## Goals / Non-Goals

**Goals:**
- Recognize real Razorpay reason codes and resolve the ones with an unambiguous
  root cause to a specific diagnosis, not a generic default.
- Fix the `timed_out`/`timeout` near-miss so `payment_timed_out` and
  `request_timed_out` are recognized as timeouts.
- Give seed data a way to generate UPI-flavored failures for the first time.
- Keep every new root cause routed to an explicit action (no code silently lands
  on `escalate` only because nobody updated the action-mapping dict).
- Preserve `test_tasks.py`/`test_pipeline.py`'s existing behavioral guarantees;
  update only the specific parametrized cases that reference retired invented
  codes.

**Non-Goals:**
- Classifying all ~90 real Razorpay reason codes. This change covers the
  prioritized "unambiguous root cause" set from the proposal plus a
  representative mandate/UPI set for the newly added seed pools; anything else
  continues to rely on the existing (safe) fallback-to-kind-default path.
  Extending coverage further is a natural follow-up change, not a blocker here.
- Changing `guardrails.py` or any guardrail logic — guardrails stay deterministic
  Python untouched by this change (CLAUDE.md invariant).
- Any Django model or migration change. No new field is added to distinguish UPI
  from card payments (see Decision 3).

## Decisions

### 1. Restructure `_DIAGNOSIS_RULES` into an exact-match table with the existing substring list as a secondary fallback tier

**Decision:** Introduce `_CODE_DIAGNOSES: dict[str, tuple[root_cause, confidence,
reasoning]]`, keyed by the exact, verbatim Razorpay reason code string, as the
first tier `_heuristic_diagnosis` consults. The existing ordered substring-needle
list is kept as a second tier, consulted only when the code has no exact-match
entry, preserving its current specificity-ordering behavior (most-specific
pattern first) for any code outside the table — including forward-compatibility
with Razorpay codes not yet enumerated, or a merchant's own custom suffix on a
code. `_KIND_DEFAULTS` remains the final tier, unchanged.

**Why:** Razorpay's reason codes are a fixed, known enumeration (a real API
concept, not free text), so exact string matching is the more precise and less
error-prone primary mechanism once there are ~30+ codes in scope. Substring
matching at this scale risks new accidental collisions the current 6-needle list
never had to worry about (e.g. a future code containing `card_` as a substring
matching `card_declined` unintentionally). Exact match also makes each code's
diagnosis independently reviewable as a table row instead of requiring reasoning
about interaction with every other needle's position in the list.

**Alternatives considered:**
- *Keep pure substring matching, just add ~25 more needles carefully ordered by
  specificity.* Rejected: correctness would depend on a single global list's
  ordering remaining correct as it grows past 30 entries — exactly the kind of
  implicit, hard-to-review invariant the original code's own comment already
  flags as fragile ("list order encodes specificity").
- *Regex-based matching.* Rejected as unnecessary complexity: Razorpay codes are
  fixed literal strings, not a pattern language; regex would add a dependency on
  correct escaping for zero benefit over exact string equality.

### 2. Every new root cause gets an explicit action-mapping entry in the same task

**Decision:** For each new root cause added to `_CODE_DIAGNOSES`, the
corresponding task in tasks.md also adds it to `_PAYMENT_DEGRADATION_ACTIONS`
and/or `_SUBSCRIPTION_RETRIABLE_ROOT_CAUSES` as applicable to the flows that root
cause can occur in. A representative mapping for the prioritized codes:

| root cause (new) | payment_degradation action | subscription_failure eligible for `registration_link`? |
|---|---|---|
| `authentication_failed` | `retry_order` (same order, customer re-authenticates) | yes |
| `card_not_enrolled` | `new_payment_link` (this card can't complete the auth method) | yes |
| `invalid_vpa` | `new_payment_link` (force re-entry of payment details) | yes |
| `vpa_resolution_failed` | `retry_order` (transient PSP-side lookup failure) | yes |
| `technical_error` (bank/gateway/issuer) | `retry_order` (transient, provider-side) | yes |
| `transaction_limit_exceeded` | `new_payment_link` (same instrument will fail again) | yes |
| `incorrect_cvv` | `retry_order` (same order, customer re-enters CVV) | yes |
| `debit_instrument_blocked` | `new_payment_link` (instrument itself is blocked) | yes |
| `debit_instrument_inactive` | `new_payment_link` (instrument itself is inactive) | yes |
| `risk_check_failed` | `escalate` (fraud/risk hold — never auto-retry) | no (escalate) |

Mandate-context codes added to the subscription seed pool (`funds_blocked_by_mandate`,
`mandate_creation_declined`, `mandate_creation_expired`, `mandate_creation_failed`,
`reqauth_mandate_not_acknowledged`) each get their own root cause and are added to
`_SUBSCRIPTION_RETRIABLE_ROOT_CAUSES`, since re-driving registration is the only
lever available regardless of why the mandate charge/registration failed;
`recurring_payment_not_enabled` is the one exception (a merchant/customer
configuration gap a registration link can't fix) and maps to `escalate`.

**Why explicit, not a default-`escalate` fallthrough:** `.get(root_cause,
"escalate")` already makes an *unmapped* root cause safe (it escalates rather
than crashing), but silently relying on that for new root causes this change
itself introduces would be an unreviewed decision by omission — the proposal
calls this out directly. Every root cause this change adds is a deliberate,
reviewable table row instead.

`risk_check_failed` in particular is mapped to `escalate` for a reason distinct
from "we don't have an action for it yet": a risk/fraud-engine block should never
be auto-retried regardless of confidence, since retrying can compound a fraud
signal. This is a decision-layer routing choice, not a diagnosis-layer one — it
is not asserted in the diagnosis-classification spec delta (that capability
covers root-cause/confidence resolution only), but it's recorded here since it's
part of this change's implementation.

### 3. UPI codes fold into the existing `payment_degradation` pool; no new model field

**Decision:** Add a UPI-flavored weighted code pool in `seed_data.py` and merge it
into `_seed_payment_degradation`'s existing code selection (e.g. an additional
weighted pool alongside the existing card-flavored one), rather than introducing
a new `Transaction.Kind` or a new `payment_method` field.

**Why:** `Transaction.kind` already models the three *flow* types (payment
degradation, subscription failure, receivable) — it is not a payment-method
axis, and UPI failures are a payment-degradation-flow concern, not a new flow.
The failure code itself is sufficient signal for diagnosis: `invalid_vpa` and
`vpa_resolution_failed` are unambiguously UPI-specific by name alone, so no
additional field is needed to tell the heuristic (or a human reading the audit
trail) that a transaction was a UPI attempt. Adding a model field/migration for
this would be a data-model change with no corresponding behavioral requirement —
avoided per this design's non-goals.

**Alternative considered:** A new `payment_method` field on `Transaction`.
Rejected for this change as unnecessary scope: nothing in the diagnosis or
decision heuristics needs to branch on payment method independent of failure
code, and CLAUDE.md's OpenSpec workflow discourages data-model changes not
justified by a concrete behavioral requirement.

### 4. Retire the invented codes from seed data entirely, not just add real ones alongside them

**Decision:** `card_declined_expired`, `network_timeout`,
`issuer_unavailable_timeout`, `mandate_charge_failed`, and `card_declined_mandate`
are removed from `PAYMENT_FAILURE_CODES`/`SUBSCRIPTION_FAILURE_CODES` and replaced
with real-code equivalents (e.g. `card_expired` for the expired-card case,
`payment_timed_out`/`bank_technical_error` for the timeout/network cases,
`card_declined` alone for the mandate-context decline, and a real mandate-specific
code for the generic mandate failure — see tasks.md for the exact pool). The
diagnosis heuristic's substring-fallback tier still handles the old invented
shapes correctly if they ever appear (Decision 1 keeps that tier's behavior
intact), so this is a seed-data-only removal, not a breaking change to the
pipeline's input contract.

**Why:** The point of this change is that seeded/demo data should exercise the
same vocabulary production traffic actually uses. Keeping the invented codes
around "just in case" would leave the demo silently exercising a vocabulary that
doesn't exist in reality, defeating the purpose.

## Risks / Trade-offs

- **[Risk] The exact-match table and the substring fallback could disagree for a
  code that happens to contain another table entry's exact string as a
  substring** (e.g. a hypothetical future code containing `card_expired` as a
  sub-string but meaning something else) → **Mitigation:** exact match is
  checked first and wins outright; the substring tier is only ever consulted
  when no exact match exists, so there is no ordering ambiguity between the two
  tiers, only within the substring tier itself (which retains its current,
  documented specificity-first ordering).
- **[Risk] Confidence values assigned to new root causes are judgment calls
  (e.g. is `vpa_resolution_failed` a 0.60 or a 0.70?), not derived from real
  recovery-rate data** → **Mitigation:** this mirrors how the existing 6 rules'
  confidences were already set (judgment calls documented inline in code
  comments); tasks.md will carry the same inline-reasoning convention so the
  rationale for each number is reviewable, and nothing here claims these are
  empirically calibrated.
- **[Trade-off] Not classifying all ~90 real codes now** means some real codes
  (e.g. `otp_expired`, `emi_plan_unavailable`) still fall through to the generic
  kind default even after this change → accepted as a deliberate non-goal (see
  above); the fallback path is safe, just less specific.

### 5. Generic-fallback confidence moves strictly below `GUARDRAIL_CONFIDENCE_FLOOR`

**Decision:** Lower `_KIND_DEFAULTS["payment_degradation"]`'s confidence from
`0.60` to `0.55` — matching the existing ambiguous-signal convention already
used for the `timeout`/`network` substring rules — so any payment-degradation
code this change doesn't explicitly classify (including a real, common,
maximally-uninformative code like `payment_declined`'s generic sibling cases,
or `payment_collect_request_expired`, which isn't in the exact-match table)
escalates to a human by default instead of silently auto-acting.

**Why:** Today, `_KIND_DEFAULTS["payment_degradation"]` returns confidence
exactly `0.60`, equal to `GUARDRAIL_CONFIDENCE_FLOOR`'s default. Since
`guardrails.py` blocks on strict `confidence < floor`, a confidence exactly at
the floor currently *passes* and auto-acts — an inherently generic diagnosis
was moving real money without human review. This was flagged as an open
question rather than decided by this change's initial draft; the reviewer
selected escalate-by-default (Option B from the original draft) as more
consistent with the project's own philosophy (CLAUDE.md / the guardrail's
purpose: don't act autonomously on a low-quality signal).

**Trade-off accepted:** This shifts more transactions to human escalation
(operational cost not quantified here) and changes one existing, previously
passing test expectation:
`test_diagnosis_unrecognized_code_falls_back_to_kind_default` currently asserts
`confidence >= 0.60` for an unrecognized code and must be updated to assert the
new value and the resulting escalation (see tasks.md 2.7 and 3.8).

**Alternative considered:** Keep the default at `0.60` (Option A — no code
change, zero risk of behavior change elsewhere). Rejected by reviewer decision:
the "generic code silently auto-acts" gap this change's own analysis surfaced
was judged worth closing now rather than deferring to a follow-up change.

## Open Questions

None — the confidence-floor boundary question is resolved above (Decision 5).
