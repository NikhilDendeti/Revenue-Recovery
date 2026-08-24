# local-dev-environment Specification

## Purpose
Defines what running RecoverAI locally requires, so the barrier to a fresh clone
starting the app is a Python/Node install — not a container runtime.

## Requirements

### Requirement: Local development requires no external services by default
Running the backend locally with no `DATABASE_URL`, `REDIS_URL`, or
`CELERY_BROKER_URL` set SHALL work end-to-end — migrations, the seed command, the
Celery pipeline, and the WebSocket dashboard — without Docker, Postgres, or Redis
installed or running.

#### Scenario: A fresh checkout runs with only `pip install` and `migrate`
- **WHEN** a developer clones the repo, installs backend dependencies, and runs `migrate` with no database/broker/channel-layer environment variables set
- **THEN** the app starts, serves the API and WebSocket, and processes the Celery task pipeline without any other service running

### Requirement: The append-only audit log guarantee holds regardless of backend
Attempting to update or delete an `AuditLogEntry` row SHALL be rejected by the database
itself whether the configured database is SQLite or PostgreSQL.

#### Scenario: An update is rejected on SQLite
- **WHEN** a raw SQL UPDATE targets an existing audit log row and the app is running on the default local SQLite database
- **THEN** the database rejects the statement and the row is unchanged

#### Scenario: An update is rejected on PostgreSQL
- **WHEN** a raw SQL UPDATE targets an existing audit log row and the app is running against a configured PostgreSQL database
- **THEN** the database rejects the statement and the row is unchanged

### Requirement: Configuring a real database or broker overrides the local default
Setting `DATABASE_URL`, `REDIS_URL`, or `CELERY_BROKER_URL` SHALL switch the
corresponding component to that configured backend instead of the zero-dependency
local default, with no code change required.

#### Scenario: Setting DATABASE_URL to a Postgres connection string uses Postgres
- **WHEN** `DATABASE_URL` is set to a PostgreSQL connection string
- **THEN** the app connects to that PostgreSQL database instead of the local SQLite file

#### Scenario: Setting REDIS_URL uses the Redis-backed channel layer and broker
- **WHEN** `REDIS_URL` (and `CELERY_BROKER_URL`) are set
- **THEN** the WebSocket layer and Celery both use Redis instead of the local database-backed relay and filesystem broker
