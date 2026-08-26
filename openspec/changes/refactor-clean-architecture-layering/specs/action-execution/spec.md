## Purpose

Defines how the system executes a decided recovery action against the payment provider
and resolves the transaction's outcome, with particular emphasis on failure handling so
a transaction always reaches a defined state and is never stranded mid-execution.

## MODIFIED Requirements

### Requirement: A not-found payable artifact falls back to a fresh one
When executing a `retry_order` or `invoice_reminder` action, if the referenced order or
invoice does not exist at the payment provider, the system SHALL fall back to issuing a
fresh payable artifact (a new payment link) rather than escalating, and SHALL then resolve
the transaction through the normal recovery outcome. The system SHALL NOT assume any
force-retry endpoint exists.

The distinction between a not-found artifact and any other provider failure SHALL be
carried as a **typed domain error raised at the provider boundary**, not as an HTTP status
code inspected by the execution logic. Execution logic SHALL therefore branch on the error
type alone and SHALL remain correct if the provider's transport or status-code vocabulary
changes.

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

#### Scenario: Execution logic does not inspect transport status codes
- **WHEN** the execution logic decides whether to fall back or escalate
- **THEN** it SHALL branch on a typed not-found domain error
- **AND** it SHALL NOT read an HTTP status code

## ADDED Requirements

### Requirement: The recovery outcome model is an explicit, testable rule with an injectable draw
Because a batch replay has no real customer completing a payment, the system resolves
whether a recovery succeeded from a probability weighted by the diagnosis confidence. That
resolution SHALL be expressed as a pure function of the confidence and a supplied uniform
random draw, so that the rule's boundaries are directly testable, and the source of the
draw SHALL be supplied to the execution logic as an injected abstraction rather than read
from a global random source.

The rule SHALL retain its existing clamping behaviour: a recovery is never treated as
certain in either direction, regardless of how high or low the diagnosis confidence is.

#### Scenario: The clamp bounds the outcome at both ends
- **WHEN** the diagnosis confidence is at its minimum and the supplied draw falls below the lower clamp
- **THEN** the outcome SHALL still resolve as recovered
- **WHEN** the diagnosis confidence is at its maximum and the supplied draw falls above the upper clamp
- **THEN** the outcome SHALL still resolve as not recovered

#### Scenario: Outcome resolution is testable without a database or a payment provider
- **WHEN** the outcome rule is exercised with a chosen confidence and a chosen draw
- **THEN** it SHALL return a result without any database, network or framework dependency

### Requirement: A replay may be made reproducible without becoming degenerate
The system SHALL support an optional configured seed that makes a batch replay's sequence
of outcomes reproducible across runs. When no seed is configured, outcomes SHALL be drawn
from the system random source and behaviour SHALL be unchanged.

A configured seed SHALL be combined with the identity of the transaction being resolved, so
that the resulting draws remain distributed across transactions and remain reproducible
independently of the order in which transactions are processed or the number of concurrent
workers. A seed SHALL NOT cause every transaction to receive the same draw.

#### Scenario: A seeded replay is reproducible
- **WHEN** the same set of transactions is replayed twice with the same configured seed
- **THEN** each transaction SHALL resolve to the same outcome in both runs

#### Scenario: A seeded replay still produces a distribution
- **WHEN** many transactions are resolved under a single configured seed
- **THEN** the draws SHALL vary across transactions rather than collapsing to a single constant value

#### Scenario: Reproducibility does not depend on processing order
- **WHEN** a seeded replay is processed by more than one concurrent worker, or in a different order
- **THEN** each transaction SHALL resolve to the same outcome as in a serial run
