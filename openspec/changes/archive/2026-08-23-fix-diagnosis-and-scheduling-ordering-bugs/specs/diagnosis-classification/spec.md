## Purpose

Defines how the rule-based diagnosis fallback resolves a transaction's failure code to
a root cause when the code could plausibly match more than one pattern.

## ADDED Requirements

### Requirement: More specific failure-code patterns are matched before general ones
When a failure code contains more than one recognized pattern, the diagnosis SHALL
resolve to the most specific, most actionable root cause rather than the first
alphabetically or positionally convenient match.

#### Scenario: An expired-card code with a decline substring diagnoses as expired, not declined
- **WHEN** a failure code contains both a decline indicator and an expiry indicator (e.g. `card_declined_expired`)
- **THEN** the diagnosis root cause SHALL be `card_expired`, since a same-card retry cannot succeed on an expired card and the decision path (fresh payment link) differs from a plain decline (same-card retry)

#### Scenario: A plain decline code with no expiry indicator still diagnoses as declined
- **WHEN** a failure code contains a decline indicator and no expiry indicator (e.g. `card_declined`)
- **THEN** the diagnosis root cause SHALL be `card_declined`
