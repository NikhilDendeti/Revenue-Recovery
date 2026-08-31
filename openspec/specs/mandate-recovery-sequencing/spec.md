# mandate-recovery-sequencing Specification

## Purpose
Defines how a subscription/mandate-failure transaction is carried through a fixed,
guardrail-respecting, multi-step nudge-then-escalate cadence, instead of stopping after
one decision, since Razorpay's own mandate auto-retry cannot be force-triggered.

## Requirements

### Requirement: A subscription-failure transaction is tracked through a fixed multi-step cadence
When a `subscription_failure` transaction's first decision resolves to a retriable nudge
action (not an immediate escalation — the existing non-retriable-root-cause or
low-confidence escalation paths are unaffected), the system SHALL begin tracking it
through a fixed 3-step cadence (step 0: the immediate registration-link nudge already
decided; step 1: a follow-up nudge on a different channel after a configured delay, if
step 0 did not recover the transaction; step 2: escalation to the human queue, if step 1
did not recover it either), and SHALL record which step the transaction is currently on.
A transaction of any other kind SHALL NOT be tracked through this cadence.

#### Scenario: A subscription-failure transaction starts the cadence at step 0
- **WHEN** a `subscription_failure` transaction's first decision resolves to the registration-link nudge
- **THEN** the system SHALL begin tracking it at step 0 of the cadence
- **AND** step 0's action SHALL execute immediately, subject to the existing guardrails, exactly as it does today

#### Scenario: An immediately-escalated first decision never starts a cadence
- **WHEN** a `subscription_failure` transaction's first decision resolves to escalation (a non-retriable root cause, or a guardrail escalation such as the confidence floor)
- **THEN** the system SHALL NOT begin a mandate-recovery cadence for it

#### Scenario: A payment-degradation or receivable transaction is never sequenced
- **WHEN** a `payment_degradation` or `receivable` transaction is diagnosed and decided
- **THEN** the system SHALL NOT begin a mandate-recovery cadence for it

#### Scenario: A transaction is never tracked by more than one active cadence at a time
- **WHEN** a `subscription_failure` transaction already has an active cadence in progress
- **THEN** the system SHALL NOT begin a second, concurrent cadence for the same transaction

### Requirement: Each step re-checks the transaction's current status before firing
Immediately before a scheduled step executes, the system SHALL re-check the
transaction's current status. If the transaction is no longer open or held (for example,
it has already recovered, failed terminally, or been escalated by some other path), the
system SHALL cancel that step and SHALL NOT schedule any further step in the cadence.

#### Scenario: A transaction that recovered mid-cadence cancels the remaining steps
- **WHEN** a scheduled cadence step becomes due
- **AND** the transaction has already left the open/held state (e.g. it recovered) since the step was scheduled
- **THEN** the system SHALL cancel that step without executing its action
- **AND** the system SHALL NOT schedule the next step in the cadence

#### Scenario: A transaction still unresolved at the step's due time proceeds
- **WHEN** a scheduled cadence step becomes due
- **AND** the transaction is still open or held
- **THEN** the system SHALL re-invoke the recovery decision for that step and proceed to guardrail evaluation

### Requirement: Every cadence step is subject to the existing deterministic guardrails
The mandate-recovery cadence SHALL determine only *when* the next step is re-evaluated.
It SHALL NOT bypass, duplicate, or weaken any existing guardrail (confidence floor, max
retries, spend ceiling, cooldown, contact-frequency cap, compliance hours). Every step's
action SHALL pass through the same guardrail evaluation used by a non-sequenced
transaction before it executes.

#### Scenario: A guardrail hold on a cadence step reschedules that step, not the whole cadence
- **WHEN** a cadence step's action is blocked by a hold-type guardrail (such as the contact-frequency cap)
- **THEN** the system SHALL hold that step's action until the guardrail's cooldown elapses
- **AND** the cadence's step tracking SHALL NOT advance until the held action actually executes

#### Scenario: A guardrail escalation on a cadence step ends the cadence
- **WHEN** a cadence step's action is escalated by a guardrail (such as the confidence floor or spend ceiling)
- **THEN** the transaction SHALL be resolved to the escalated state
- **AND** the cadence SHALL end without scheduling any further step

### Requirement: The final cadence step escalates an unresolved transaction to the human queue
If the transaction is still open or held when the last cadence step becomes due and
clears guardrails, the system SHALL escalate it to the human queue rather than continuing
to nudge automatically.

#### Scenario: The last step escalates a still-unresolved transaction
- **WHEN** the final step of the cadence becomes due
- **AND** the transaction is still open or held
- **AND** guardrail evaluation clears the step to execute
- **THEN** the system SHALL escalate the transaction to the human queue
- **AND** the cadence SHALL be marked complete

### Requirement: Cadence step delays are durable across a worker restart
Each pending cadence step SHALL be represented as a persisted, database-backed record
with a due time, discovered by a periodic sweep, rather than as an in-memory or
process-scheduled timer. A worker process restarting SHALL NOT cause a pending step to be
lost or silently skipped.

#### Scenario: A pending step still fires after a simulated worker restart
- **WHEN** a cadence step is scheduled with a future due time
- **AND** the worker process that scheduled it is restarted before the due time arrives
- **THEN** the step SHALL still be discovered and executed once its due time arrives, by the periodic sweep alone
