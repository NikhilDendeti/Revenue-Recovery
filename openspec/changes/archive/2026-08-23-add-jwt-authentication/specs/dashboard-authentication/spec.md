## Purpose

Controls who can read RecoverAI's transaction data and audit trail or trigger its
actions (batch replay, voice showcase) — via a JWT issued to a single seeded operator
account, sized for a single-tenant operator dashboard rather than a multi-user product.

## ADDED Requirements

### Requirement: REST API access requires a valid JWT
Every REST endpoint under `/api/` SHALL require a valid, unexpired JWT access token,
except the Razorpay webhook ingestion endpoint.

#### Scenario: An unauthenticated request is rejected
- **WHEN** a client calls any protected `/api/` endpoint without an `Authorization` header
- **THEN** the API responds 401 Unauthorized and performs no read or write

#### Scenario: A request with a valid token succeeds
- **WHEN** a client calls a protected endpoint with `Authorization: Bearer <valid access token>`
- **THEN** the API responds as it would have before this change

#### Scenario: The webhook endpoint remains open
- **WHEN** a client calls `POST /api/webhooks/razorpay/` without any `Authorization` header
- **THEN** the request is processed normally, not rejected for missing authentication

### Requirement: Credentials are exchanged for a token pair
The system SHALL provide an endpoint that exchanges a username and password for an
access/refresh token pair, and an endpoint that exchanges a valid refresh token for a
new access token.

#### Scenario: Valid credentials yield a token pair
- **WHEN** a client posts the seeded operator's correct username and password to the token endpoint
- **THEN** the response includes an access token and a refresh token

#### Scenario: Invalid credentials are rejected
- **WHEN** a client posts an incorrect username or password
- **THEN** the token endpoint responds 401 and issues no token

#### Scenario: A valid refresh token yields a new access token
- **WHEN** a client posts a valid, unexpired refresh token to the refresh endpoint
- **THEN** the response includes a new access token

### Requirement: The WebSocket feed requires the same JWT
Connecting to the recovery WebSocket endpoint SHALL require a valid access token
passed as a query parameter; a connection without one, or with an invalid or expired
one, SHALL be closed rather than accepted.

#### Scenario: A connection without a token is closed
- **WHEN** a client opens the recovery WebSocket endpoint with no `token` query parameter
- **THEN** the server closes the connection instead of accepting it

#### Scenario: A connection with a valid token is accepted
- **WHEN** a client opens the recovery WebSocket endpoint with `?token=<valid access token>`
- **THEN** the server accepts the connection and delivers pushed events as before

### Requirement: A single operator account is seedable from configuration
The system SHALL provide a way to create or update exactly one operator account from
environment configuration, without an interactive registration flow.

#### Scenario: Seeding creates the account on first run
- **WHEN** the seed command runs and no user with the configured username exists
- **THEN** a user is created with the configured username and password

#### Scenario: Seeding updates the password on a later run
- **WHEN** the seed command runs again with a changed `DASHBOARD_PASSWORD`
- **THEN** the existing user's password is updated to match, rather than a duplicate account being created
