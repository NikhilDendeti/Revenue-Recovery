## Purpose

Defines how the system executes a decided recovery action against the payment provider
and resolves the transaction's outcome, with particular emphasis on failure handling so
a transaction always reaches a defined state and is never stranded mid-execution.

## ADDED Requirements

### Requirement: Action execution always resolves the transaction to a defined state
Once a transaction enters execution, the system SHALL resolve it to a defined outcome
state — recovered, failed, or escalated — even when the recovery action's underlying
API call fails. A transaction SHALL NOT be left in the `processing` state because of an
execution error, and SHALL NOT become permanently unprocessable.

#### Scenario: An unrecoverable API error escalates rather than wedging the transaction
- **WHEN** a decided action is executed and its payment-provider API call fails in a way that no fallback can recover
- **THEN** the transaction SHALL be resolved to the escalated state
- **AND** the transaction SHALL NOT remain in the `processing` state

#### Scenario: An unexpected error anywhere in processing still resolves the transaction
- **WHEN** any unexpected error is raised while processing a detected transaction, in either the main pipeline task or the scheduled-action dispatch task
- **THEN** the transaction SHALL be moved out of the `processing` state to the escalated state rather than left mid-execution

### Requirement: API-failure escalation is recorded distinctly and surfaced live
When a recovery action is escalated because its API call failed — as distinct from a
guardrail block — the system SHALL append a new audit-log entry that identifies the
cause as an execution/API failure, and SHALL surface the escalation on the live ticker.
The audit log SHALL remain append-only: the failure path writes a new entry and never
mutates or deletes an existing one.

#### Scenario: An API-failure escalation writes a distinct audit event
- **WHEN** a transaction is escalated because its action's API call failed
- **THEN** a new audit-log entry SHALL be appended whose event type distinguishes an API-failure escalation from a guardrail-driven escalation
- **AND** the escalation SHALL be pushed to the live ticker as an escalated outcome

### Requirement: A not-found payable artifact falls back to a fresh one
When executing a `retry_order` or `invoice_reminder` action, if the referenced order or
invoice does not exist at the payment provider (a resource-not-found / 404-class
response), the system SHALL fall back to issuing a fresh payable artifact (a new payment
link) rather than escalating, and SHALL then resolve the transaction through the normal
recovery outcome. The system SHALL NOT assume any force-retry endpoint exists.

#### Scenario: A retry against a non-existent order falls back to a fresh payment link
- **WHEN** a `retry_order` action targets an order that the provider reports does not exist
- **THEN** the system SHALL issue a fresh payment link instead
- **AND** the transaction SHALL proceed to a recovered-or-failed outcome rather than escalation

#### Scenario: An invoice reminder against a non-existent invoice falls back to a fresh payment link
- **WHEN** an `invoice_reminder` action targets an invoice that the provider reports does not exist
- **THEN** the system SHALL issue a fresh payment link instead
- **AND** the transaction SHALL proceed to a recovered-or-failed outcome rather than escalation

#### Scenario: A non-not-found API error does not trigger the fallback
- **WHEN** an action's API call fails with a transient or otherwise non-not-found error, such as a timeout or a server (5xx) error
- **THEN** the system SHALL escalate the transaction rather than issue a fresh payment link
