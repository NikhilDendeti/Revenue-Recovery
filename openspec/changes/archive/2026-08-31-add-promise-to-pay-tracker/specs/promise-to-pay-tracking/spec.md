## Purpose

Tracks promise-to-pay commitments made during a recovery attempt — today from the voice
channel, later from manual B2B follow-ups — from creation through resolution, and feeds
a broken promise back into guardrail enforcement instead of letting it pass unnoticed.

## ADDED Requirements

### Requirement: A promise-to-pay commitment is recorded as trackable data
When a recovery attempt elicits a promise to pay — from the voice channel today, and
from a manual B2B follow-up in future — the system SHALL record the promise as its own
trackable commitment: the transaction it belongs to, the promised amount, the promised
date, its source, and a pending status. The commitment SHALL be retrievable on its own,
not only as text inside an audit-log payload.

#### Scenario: Triggering the voice recovery moment records a pending promise
- **WHEN** the voice recovery moment is triggered for a transaction and the customer promises a payment date
- **THEN** a promise-to-pay commitment SHALL be recorded for that transaction with its promised amount, promise date, source marked voice, and status pending
- **AND** that commitment SHALL be retrievable independently of the audit log

### Requirement: A pending promise resolves automatically once its date passes
The system SHALL periodically check every pending promise whose promise date has
passed and resolve it: to kept when its transaction has reached the recovered state, and
to broken otherwise. A promise SHALL NOT remain pending indefinitely once its promise
date is in the past.

#### Scenario: A promise on a recovered transaction is marked kept
- **WHEN** a pending promise's promise date has passed and its transaction's status is recovered
- **THEN** the promise SHALL be resolved to kept

#### Scenario: A promise on a still-unresolved transaction is marked broken
- **WHEN** a pending promise's promise date has passed and its transaction's status is anything other than recovered
- **THEN** the promise SHALL be resolved to broken

### Requirement: A broken promise escalates rather than earning a fresh nudge
Marking a promise broken SHALL cause the transaction's guardrail evaluation to run
again, and a customer with any unresolved broken promise SHALL have any further
contact-type action (voice, payment link, registration link, or invoice reminder)
blocked and escalated to the human queue — never silently held for later retry, and
never allowed through on the strength of the ordinary contact-frequency cooldown alone.

#### Scenario: Marking a promise broken triggers guardrail evaluation
- **WHEN** a pending promise is resolved to broken
- **THEN** guardrail evaluation SHALL run for that promise's transaction as a direct result

#### Scenario: A broken promise blocks a further contact action even outside the ordinary cooldown
- **WHEN** a customer has an unresolved broken promise and a contact-type action is evaluated for that customer, even outside the existing 24-hour contact-cooldown window
- **THEN** guardrail evaluation SHALL block the action and escalate rather than clear it

#### Scenario: A customer with no broken promise is unaffected
- **WHEN** a customer has no unresolved broken promise and is outside the existing contact-frequency cooldown window
- **THEN** guardrail evaluation SHALL clear the contact action exactly as it did before this capability existed

### Requirement: The batch summary reports the promise-kept rate
The batch-level summary SHALL include the proportion of resolved promises (kept versus
broken) as a distinct metric, computed only from promises that have left the pending
state, and SHALL report zero rather than failing when no promise has resolved yet.

#### Scenario: The kept rate reflects resolved promises
- **WHEN** the batch summary is computed and at least one promise has resolved to kept or broken
- **THEN** the summary SHALL include a promise-kept rate equal to the share of resolved promises marked kept

#### Scenario: No resolved promises yet reports zero, not an error
- **WHEN** the batch summary is computed and no promise has resolved yet
- **THEN** the promise-kept rate SHALL be reported as zero

### Requirement: Promise-to-pay commitments are exposed through a read-only API
The system SHALL expose promise-to-pay commitments through a list endpoint that
supports filtering by status and by transaction, and SHALL reject any request to
create, modify, or remove a commitment through that endpoint.

#### Scenario: Listing and filtering promises
- **WHEN** a client requests the promise-to-pay list endpoint, optionally filtered by status or by transaction
- **THEN** the API SHALL return the matching commitments with their status, source, promised amount, and promise date

#### Scenario: Writing to the promise-to-pay endpoint is rejected
- **WHEN** a client sends a POST, PUT, PATCH, or DELETE request to the promise-to-pay endpoint
- **THEN** the API SHALL reject the request without creating, modifying, or removing any commitment

### Requirement: The dashboard presents a promise-to-pay tracker
The dashboard SHALL present a tracker showing the count of promises in each status
(pending, kept, broken) and a list of the underlying commitments, and SHALL present an
explanatory empty state when no commitment exists yet.

#### Scenario: The tracker shows counts and a list
- **WHEN** the operator views the Recovery Room dashboard and promise-to-pay commitments exist
- **THEN** the tracker SHALL display the pending, kept, and broken counts and a list of the commitments

#### Scenario: No commitments yet shows an explanatory empty state
- **WHEN** no promise-to-pay commitment has been recorded yet
- **THEN** the tracker SHALL present an empty state explaining that no promises have been made yet, rather than blank space

### Requirement: A promise's resolution is captured in the append-only audit trail
Resolving a promise to broken, and the escalation that follows it, SHALL each be
recorded as a new audit-log entry. No existing audit-log entry SHALL be modified or
removed as part of resolving a promise.

#### Scenario: A broken promise and its escalation are both audited
- **WHEN** a promise is resolved to broken and the resulting guardrail evaluation escalates its transaction
- **THEN** a new audit-log entry SHALL be appended recording the broken promise
- **AND** a new audit-log entry SHALL be appended recording the escalation
- **AND** no prior audit-log entry SHALL be altered
