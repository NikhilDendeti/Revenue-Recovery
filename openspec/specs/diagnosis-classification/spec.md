# diagnosis-classification Specification

## Purpose
Defines how the rule-based diagnosis fallback resolves a transaction's failure code to
a root cause when the code could plausibly match more than one pattern.

## Requirements

### Requirement: More specific failure-code patterns are matched before general ones
When a failure code contains more than one recognized pattern, the diagnosis SHALL
resolve to the most specific, most actionable root cause rather than the first
alphabetically or positionally convenient match. A failure code that exactly matches a
known Razorpay reason code SHALL resolve via that exact match rather than via a
general substring pattern, even when a substring pattern would also match; substring
patterns are a fallback tier for codes that are not an exact, known match.

#### Scenario: An expired-card code with a decline substring diagnoses as expired, not declined
- **WHEN** a failure code contains both a decline indicator and an expiry indicator (e.g. `card_declined_expired`)
- **THEN** the diagnosis root cause SHALL be `card_expired`, since a same-card retry cannot succeed on an expired card and the decision path (fresh payment link) differs from a plain decline (same-card retry)

#### Scenario: A plain decline code with no expiry indicator still diagnoses as declined
- **WHEN** a failure code contains a decline indicator and no expiry indicator (e.g. `card_declined`)
- **THEN** the diagnosis root cause SHALL be `card_declined`

#### Scenario: An exact known-code match is used even when it would also satisfy a general pattern
- **WHEN** a failure code is an exact match for a known Razorpay reason code (e.g. `card_expired`)
- **THEN** the diagnosis SHALL resolve using that exact match
- **AND** the result SHALL be the same regardless of whether the code would also satisfy a broader substring pattern

### Requirement: Real Razorpay failure codes with an unambiguous cause resolve to a specific root cause
The diagnosis SHALL recognize real Razorpay payment-failure reason codes — not only an
invented or seed-specific vocabulary — and SHALL resolve each code in the following set
to its own specific root cause, distinct from any generic kind-level default, with a
confidence at or above the guardrail confidence floor: `card_expired`,
`insufficient_funds`, `authentication_failed`, `card_not_enrolled`, `invalid_vpa`,
`vpa_resolution_failed`, `bank_technical_error`, `gateway_technical_error`,
`issuer_technical_error`, `transaction_limit_exceeded`, `incorrect_cvv`,
`debit_instrument_blocked`, and `debit_instrument_inactive`.

#### Scenario: An authentication failure diagnoses as an authentication-specific root cause
- **WHEN** a failure code is `authentication_failed`
- **THEN** the diagnosis root cause SHALL be specific to authentication failure, not the generic payment-decline default
- **AND** the confidence SHALL be at or above the guardrail confidence floor

#### Scenario: A card not enrolled for the required authentication method diagnoses distinctly from a plain decline
- **WHEN** a failure code is `card_not_enrolled`
- **THEN** the diagnosis root cause SHALL reflect that the card itself cannot complete this authentication method, distinct from `card_declined`

#### Scenario: An invalid VPA diagnoses as a UPI-specific root cause
- **WHEN** a failure code is `invalid_vpa`
- **THEN** the diagnosis root cause SHALL be specific to an invalid VPA, not the generic payment-decline default

#### Scenario: A VPA resolution failure diagnoses distinctly from an invalid VPA
- **WHEN** a failure code is `vpa_resolution_failed`
- **THEN** the diagnosis root cause SHALL reflect a resolution/lookup failure, distinct from `invalid_vpa`, since a same-VPA retry is plausible for a resolution failure but not for an invalid one

#### Scenario: A bank, gateway, or issuer technical error diagnoses as a technical-failure root cause
- **WHEN** a failure code is `bank_technical_error`, `gateway_technical_error`, or `issuer_technical_error`
- **THEN** the diagnosis root cause SHALL reflect a provider-side technical failure, distinct from a customer-caused decline

#### Scenario: A transaction-limit code diagnoses distinctly from a plain decline
- **WHEN** a failure code is `transaction_limit_exceeded`
- **THEN** the diagnosis root cause SHALL reflect that the instrument's limit was exceeded, distinct from `card_declined`

#### Scenario: An incorrect CVV diagnoses as a correctable input-error root cause
- **WHEN** a failure code is `incorrect_cvv`
- **THEN** the diagnosis root cause SHALL reflect a correctable entry error, distinct from `card_declined`

#### Scenario: A blocked or inactive debit instrument diagnoses distinctly from a plain decline
- **WHEN** a failure code is `debit_instrument_blocked` or `debit_instrument_inactive`
- **THEN** the diagnosis root cause SHALL reflect that the instrument itself is blocked or inactive, distinct from `card_declined`, since a same-instrument retry cannot succeed

### Requirement: A near-miss timeout-flavored code is still recognized as a timeout
The diagnosis SHALL recognize Razorpay's `payment_timed_out` and `request_timed_out`
reason codes as timeout-class failures. A code containing `timed_out` SHALL be treated
equivalently to one containing `timeout` for diagnosis purposes.

#### Scenario: A payment_timed_out code diagnoses as a timeout, not a generic default
- **WHEN** a failure code is `payment_timed_out`
- **THEN** the diagnosis root cause SHALL be the same timeout-class root cause used for a code containing `timeout`
- **AND** the diagnosis SHALL NOT fall through to the generic kind-level default

#### Scenario: A request_timed_out code diagnoses as a timeout, not a generic default
- **WHEN** a failure code is `request_timed_out`
- **THEN** the diagnosis root cause SHALL be the same timeout-class root cause used for a code containing `timeout`
- **AND** the diagnosis SHALL NOT fall through to the generic kind-level default

### Requirement: An unrecognized failure code still resolves safely via the kind-level default
A failure code that is neither an exact known match nor a match for any fallback
pattern SHALL still resolve to the existing kind-level default root cause and
confidence, without error, preserving prior behavior for codes outside the recognized
vocabulary.

#### Scenario: A wholly novel, unrecognized code falls back to the kind default
- **WHEN** a failure code matches neither the exact-match table nor any fallback pattern
- **THEN** the diagnosis SHALL resolve to the kind-level default root cause and confidence
- **AND** no error SHALL be raised

### Requirement: A transaction kind with no failure code by design uses a different signal set
When a transaction's kind does not use failure codes at all — its failure code is empty
by design, not because the signal is weak — the diagnosis SHALL derive root cause and
confidence from that kind's own signals (e.g. elapsed time since an originating event,
transaction value, and last known payment method) rather than treating the empty
failure code itself as a low-confidence signal.

#### Scenario: An empty failure code on a checkout drop-off is not treated as an unknown-cause signal
- **WHEN** a transaction of kind `checkout_dropoff` (which never carries a failure code) is diagnosed
- **THEN** the diagnosis SHALL NOT resolve to the generic low-confidence `unknown` root cause used for other kinds' missing failure codes
- **AND** the diagnosis SHALL be derived from that kind's own signals instead

#### Scenario: A very recent, high-intent drop-off produces a confident diagnosis
- **WHEN** a `checkout_dropoff` transaction was initiated recently and a payment method was already attempted before abandonment
- **THEN** the diagnosis confidence SHALL clear the confidence floor, so the transaction can be acted on autonomously

#### Scenario: A long-stale drop-off produces a low-confidence diagnosis
- **WHEN** a `checkout_dropoff` transaction was initiated far in the past relative to the configured at-risk window
- **THEN** the diagnosis confidence SHALL be low enough to route to escalation rather than autonomous action
