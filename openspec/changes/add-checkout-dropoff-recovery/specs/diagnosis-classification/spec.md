## ADDED Requirements

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
