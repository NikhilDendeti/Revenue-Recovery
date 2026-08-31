## Why

`seed_data.py` invents its own failure-code vocabulary (`card_declined_expired`,
`network_timeout`, `issuer_unavailable_timeout`, `mandate_charge_failed`,
`card_declined_mandate`) and `agents/pipeline.py`'s deterministic diagnosis
heuristic — the fallback used whenever no LLM key is configured, which is the
default local-dev and no-API-key production posture per CLAUDE.md — has only 6
substring needles tuned to match that invented vocabulary rather than Razorpay's
real payment-failure reason codes. `Transaction.failure_code` is an unconstrained
`CharField` and `WebhookView` passes an inbound webhook's `failure_code` straight
through with no validation, so a real Razorpay code reaches this exact heuristic in
production. Most real codes (`payment_timed_out`, `bank_technical_error`,
`authentication_failed`, `card_not_enrolled`, the entire UPI vocabulary, etc.) match
none of the 6 needles — including a near-miss bug where `timed_out` doesn't match
the `timeout` needle — and fall through to a generic default whose confidence
(0.60) is not strictly below `GUARDRAIL_CONFIDENCE_FLOOR` (also 0.60 by default),
so the system silently auto-acts on a generic diagnosis for codes it could
otherwise diagnose specifically. Seed data also cannot produce a UPI-flavored
transaction at all today, leaving that failure surface completely untested by the
demo data.

## What Changes

- Replace `seed_data.py`'s invented failure codes with real Razorpay reason codes
  in `PAYMENT_FAILURE_CODES` and `SUBSCRIPTION_FAILURE_CODES`, and add a
  UPI-flavored code pool folded into the payment-degradation weighting so seeded
  data can exercise a UPI failure path for the first time.
- Fix the `timed_out`/`timeout` substring-matching bug and restructure
  `agents/pipeline.py::_DIAGNOSIS_RULES` from a flat substring-needle list into an
  exact-match code table (primary) with the existing ordered substring rules
  retained as a secondary fallback for codes outside the table — substring
  matching alone does not scale cleanly to ~30+ real codes that share substrings
  (e.g. `debit_instrument_blocked` vs `debit_instrument_inactive`).
- Give ~15 real Razorpay codes with an unambiguous root cause (card_expired,
  insufficient_funds, authentication_failed, card_not_enrolled, invalid_vpa,
  vpa_resolution_failed, the three `*_technical_error` codes,
  transaction_limit_exceeded, incorrect_cvv, debit_instrument_blocked/inactive,
  plus a representative set of mandate-specific codes) their own root_cause,
  confidence, and reasoning, each with an explicit decision-action mapping —
  no new root cause is left to fall through to `escalate` by accident.
- **Open question, not resolved by this change** (see design.md): whether the
  generic-fallback confidence (currently exactly 0.60, equal to the default
  `GUARDRAIL_CONFIDENCE_FLOOR`) should move strictly below the floor so
  unrecognized/generic codes escalate by default.
- Update `agents/tests/test_pipeline.py`'s parametrized cases that reference
  now-removed invented codes to their real-code equivalents, preserving the same
  behavioral assertions (the "more specific pattern wins" and "subscription never
  produces retry_order" regression guards), and add new coverage for the newly
  classified real codes.

## Capabilities

### New Capabilities
(none)

### Modified Capabilities
- `diagnosis-classification`: the rule-based diagnosis fallback's failure-code
  vocabulary and matching strategy change from an invented-code substring scan to
  a real-Razorpay-code exact-match table (with substring fallback), including new
  requirements for codes that were previously unclassifiable.

## Impact

- `backend/recovery/management/commands/seed_data.py` — `PAYMENT_FAILURE_CODES`,
  `SUBSCRIPTION_FAILURE_CODES` constants replaced/extended.
- `backend/agents/pipeline.py` — `_DIAGNOSIS_RULES` restructured into an
  exact-match table + fallback rules; `_PAYMENT_DEGRADATION_ACTIONS` and
  `_SUBSCRIPTION_RETRIABLE_ROOT_CAUSES` extended for new root causes.
- `backend/agents/tests/test_pipeline.py` — parametrized cases updated to real
  codes; new cases added for newly classified codes.
- `backend/recovery/tests/test_tasks.py` — audited for impact; its existing
  failure codes (`insufficient_funds`, `card_declined`, `invoice_overdue`, `""`)
  are unaffected and are not expected to require changes.
- No change to `backend/recovery/guardrails.py`, the audit-log trigger, the
  Celery/Channels event-delivery architecture, or any API/WS contract.
- No Django model or migration changes (no new field is introduced for UPI vs.
  card distinction — see design.md).
