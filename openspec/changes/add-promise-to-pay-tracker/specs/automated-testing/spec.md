## ADDED Requirements

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
