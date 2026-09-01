## Purpose

Defines what happens when an operator triggers a batch replay from the dashboard — that the
action is always well-defined and produces new, visible activity, regardless of how many times
it has already been triggered or what state prior batches are in.

## ADDED Requirements

### Requirement: Triggering a batch replay always produces new, processable transactions
When an operator triggers a batch replay, the system SHALL seed a fresh set of synthetic
transactions across all in-scope flows before queuing the replay, so the action always has
new work to process regardless of whether any previously-seeded transactions have already been
fully resolved.

#### Scenario: Triggering replay after a prior batch is fully resolved still produces activity
- **WHEN** an operator triggers a batch replay and every previously-seeded transaction has already reached a terminal state (recovered, escalated, held, or failed)
- **THEN** the system SHALL seed a new set of transactions across all in-scope flows
- **AND** the newly-seeded transactions SHALL be queued for processing as part of the same trigger

#### Scenario: Triggering replay repeatedly always yields a non-empty run
- **WHEN** an operator triggers a batch replay any number of times in succession
- **THEN** each trigger SHALL result in a nonzero number of transactions queued for processing

### Requirement: A batch replay trigger never resets or reprocesses existing transactions
Triggering a batch replay SHALL NOT reset, delete, or force a re-processing pass on any
transaction that has already reached a terminal state or is already in flight. Newly-seeded
transactions SHALL be independent rows with their own identity, distinguishable from prior
batches, so that a transaction's guardrail history (contact frequency, retry counts) from an
earlier batch is never revisited by a later trigger.

#### Scenario: A previously-resolved transaction is left untouched by a later trigger
- **WHEN** an operator triggers a batch replay while a previously-seeded transaction already sits in a terminal state
- **THEN** that previously-seeded transaction's status and guardrail history SHALL remain unchanged
- **AND** the new trigger's transactions SHALL be newly-created rows, not the same transaction re-entering the pipeline

#### Scenario: A transaction still open from an unfinished prior batch is included, not orphaned
- **WHEN** an operator triggers a batch replay while a transaction from an earlier, unfinished batch is still in the open state
- **THEN** that still-open transaction SHALL be included in the same replay pass as the newly-seeded transactions
- **AND** it SHALL NOT be skipped or left permanently unprocessed
