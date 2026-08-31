# automated-testing Specification

## Purpose
Establishes automated, repeatable verification of RecoverAI's deterministic core, data
integrity guarantees, and integration surface, so a regression is caught by a test run
instead of by hand in a live demo.

## Requirements

### Requirement: Guardrail rules have independent automated coverage
Each of the six guardrail rules (confidence floor, max retry attempts, spend/action
ceiling, cooldown between retries, contact frequency cap, compliance hours) SHALL have
at least one automated test asserting its blocked outcome and one asserting its passed
outcome, independent of the other five rules.

#### Scenario: Low-confidence diagnosis is blocked
- **WHEN** a transaction's diagnosis confidence is below the configured floor
- **THEN** guardrail evaluation reports escalation and logs a blocked confidence-floor event

#### Scenario: Over-ceiling spend is blocked regardless of confidence
- **WHEN** a transaction's amount exceeds the configured autonomous spend ceiling, even with a high-confidence diagnosis
- **THEN** guardrail evaluation reports escalation rather than clearing the action

#### Scenario: Card-decline retry is held, not executed immediately
- **WHEN** the chosen action is a same-order retry and the failure code indicates a card decline
- **THEN** guardrail evaluation reports a hold with a run-after time in the future, not an immediate clearance

#### Scenario: Repeated contact within the cooldown window is held
- **WHEN** a customer was already contacted within the configured cooldown window and a new contact-type action is proposed
- **THEN** guardrail evaluation reports a hold, and a concurrent second evaluation for the same customer cannot both pass the check

### Requirement: Diagnosis/decision heuristic routes each flow to a real Razorpay-backed action
The rule-based diagnosis/decision fallback SHALL map each of the three transaction
kinds (payment degradation, subscription failure, receivable) to an action that has a
real Razorpay counterpart, and SHALL escalate rather than guess when the diagnosed root
cause is unclear.

#### Scenario: Subscription failures never resolve to a same-order retry
- **WHEN** a subscription_failure transaction is diagnosed with a card-decline or insufficient-funds root cause
- **THEN** the decision SHALL be a registration-link re-authorization, never a same-order retry

#### Scenario: An unclear root cause escalates instead of guessing
- **WHEN** a transaction has no matching failure-code pattern and no kind-specific default applies
- **THEN** the diagnosis confidence SHALL fall below the confidence floor and the decision SHALL be escalate

### Requirement: The audit log is append-only at the database level
Inserting a new `AuditLogEntry` row SHALL succeed; any attempt to update or delete an
existing row, including via raw SQL bypassing the Django ORM, SHALL be rejected by the
database itself.

#### Scenario: A raw SQL UPDATE against the audit log table is rejected
- **WHEN** a raw SQL UPDATE statement targets an existing audit log row, inside a test transaction
- **THEN** the database raises an error and the row's contents are unchanged

#### Scenario: A raw SQL DELETE against the audit log table is rejected
- **WHEN** a raw SQL DELETE statement targets an existing audit log row
- **THEN** the database raises an error and the row still exists afterward

### Requirement: The Razorpay client's simulated and live modes are both verified
When no Razorpay credentials are configured, every client function SHALL return a
clearly-flagged simulated response without making a network call. When credentials are
configured, at least one client function SHALL be verified against the real Razorpay
test-mode API, and any object it creates SHALL be cleaned up (cancelled) by the test.

#### Scenario: Simulated mode never calls the network
- **WHEN** RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are unset
- **THEN** every razorpay_client function returns a response with a simulated flag set to true and issues no HTTP request

#### Scenario: Live mode creates and cleans up a real test-mode object
- **WHEN** RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are present in the environment
- **THEN** a live-mode test creates a real Razorpay test-mode Payment Link, asserts it has a real id and short_url, and cancels it before the test ends

### Requirement: The end-to-end pipeline is covered for each guardrail outcome
The Celery task pipeline (detect → diagnose → decide → guardrail → act → audit) SHALL
have an automated test for each of its three possible outcomes for a processed
transaction: cleared and executed, held pending a scheduled action, and escalated.

#### Scenario: A clean transaction is recovered or fails and is recorded
- **WHEN** a transaction with a high-confidence, low-amount, non-cooldown-triggering diagnosis is processed
- **THEN** the transaction ends in either the recovered or failed status, with an Action row and matching audit log entries

#### Scenario: A held transaction produces exactly one pending scheduled action
- **WHEN** a transaction triggers a guardrail hold (e.g. a card-decline cooldown)
- **THEN** exactly one ScheduledAction row exists for that transaction with status pending and a future run_after

#### Scenario: The scheduled-action sweeper only dispatches due actions
- **WHEN** the sweeper task runs while a ScheduledAction's run_after is still in the future
- **THEN** that action is not dispatched, and it is dispatched once run_after has passed

### Requirement: The REST API enforces read-only access to the audit log
The audit log API endpoint SHALL support list and retrieve operations and SHALL reject
create, update, and delete requests.

#### Scenario: Listing and retrieving audit entries succeeds
- **WHEN** a client requests the audit log list endpoint or a single entry's detail endpoint
- **THEN** the API returns the matching entries with a success status

#### Scenario: Writing to the audit log endpoint is rejected
- **WHEN** a client sends a POST, PUT, PATCH, or DELETE request to the audit log endpoint
- **THEN** the API rejects the request without creating, modifying, or removing any row

### Requirement: Live dashboard events reach a connected WebSocket client
A message pushed through the recovery event broadcaster SHALL be delivered to a
connected Recovery Room WebSocket client with the same type and payload it was sent
with.

#### Scenario: A ticker event is received by a connected client
- **WHEN** a client is connected to the recovery WebSocket endpoint and a ticker event is pushed
- **THEN** the client receives a message whose type and payload match what was pushed

### Requirement: Promise-to-pay tracking has independent automated coverage
The promise-to-pay model, its periodic sweep resolution, its guardrail interaction, and
its read-only API/serializer SHALL each have at least one automated test, independent of
the tests covering the other guardrail rules and the main recovery pipeline.

#### Scenario: A promise-to-pay commitment records its defining fields at creation
- **WHEN** a promise-to-pay commitment is created for a transaction
- **THEN** it records the transaction, promised amount, promise date, source, and a pending status by default

#### Scenario: The sweep resolves both outcomes correctly in one run
- **WHEN** the sweep processes one past-due pending promise on a recovered transaction and one past-due pending promise on a transaction that is not recovered
- **THEN** the first is left kept and the second is left broken

#### Scenario: A broken promise blocks a contact action even when the cooldown timestamp alone would pass
- **WHEN** a customer has a broken promise and is otherwise outside the ordinary contact-frequency cooldown window
- **THEN** guardrail evaluation still blocks the contact action and escalates rather than clearing it

#### Scenario: The promise-to-pay endpoint supports read access and rejects writes
- **WHEN** a client lists promise-to-pay commitments, filters them by status or by transaction, and then sends a write request to the same endpoint
- **THEN** the reads return the matching commitments and the write request is rejected
