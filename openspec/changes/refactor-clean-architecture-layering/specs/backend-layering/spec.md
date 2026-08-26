## Purpose

Defines how write-path code in the backend is organised across transports, interactors,
storages, presenters and ports; which code paths the layering applies to and which are
deliberately exempt; and how the layer boundaries are enforced mechanically rather than by
convention.

## ADDED Requirements

### Requirement: The layering applies only to code paths that change the world
The system SHALL apply the transport → interactor → storage/presenter/port structure to a
code path only when that path writes a row, calls an external system, branches on a
business rule, or is reachable from more than one transport. A path that only reads and
serialises SHALL NOT be required to have an interactor, and the framework's own read-path
machinery — read-only viewsets, serializers, pagination, filtering and URL routing — SHALL
be retained rather than reimplemented.

This rule SHALL be recorded in the codebase itself, at the root of the interactor package,
so that placement of new code is decidable without consulting this specification.

#### Scenario: A write path is layered
- **WHEN** a code path executes a recovery action, evaluates guardrails, or creates a transaction from an inbound webhook
- **THEN** its business logic SHALL live in an interactor
- **AND** its database access SHALL live in a storage
- **AND** its outbound response or event shaping SHALL live in a presenter

#### Scenario: A read-only path is exempt
- **WHEN** an endpoint only lists or retrieves records and branches on no business rule
- **THEN** it SHALL be served by the framework's read-only viewset and serializer directly
- **AND** it SHALL NOT be required to introduce an interactor, storage or presenter

### Requirement: Interactors are free of framework and infrastructure dependencies
A module containing use-case logic SHALL NOT import the web framework, the ORM, the task
queue, the WebSocket library, an HTTP client, a random-number source, or the agent/LLM
packages. Anything a use case needs from the outside world SHALL be supplied through an
injected abstraction.

The prohibition on the agent and LLM packages is what makes the guardrail invariant —
compliance logic is deterministic and never consults a model — a mechanically checked
property rather than an observed one.

#### Scenario: A forbidden import fails the build
- **WHEN** a module under the interactor package or the guardrail rules module imports a banned package
- **THEN** an automated test SHALL fail and identify the offending module and import

#### Scenario: Guardrail rules cannot reach a model
- **WHEN** the guardrail rule module is scanned for imports
- **THEN** no import path SHALL reach the agent pipeline or any LLM client library

### Requirement: The ORM is confined to the storage layer
Django model access SHALL occur only in modules under the storage layer. Transaction
management primitives — explicit atomic blocks and row-level locking — SHALL likewise
appear only there, so that a use case cannot accidentally split an operation that must be
atomic across two commits.

#### Scenario: A locked read-modify-write stays in one transaction
- **WHEN** a guardrail reserves a customer's contact slot and records why it did so
- **THEN** both the slot update and the corresponding guardrail event SHALL be written inside a single database transaction under the same row lock

### Requirement: The audit log's append-only guarantee is structural
The abstraction through which the system reaches the audit log SHALL expose no operation
that updates or deletes an entry. Exactly one module SHALL be permitted to reference the
audit-log model directly, and no code path SHALL issue a queryset-level update against it,
since such an update bypasses the model's own guard and would leave only the database
trigger standing.

#### Scenario: The storage abstraction has no mutation verb
- **WHEN** the audit-log storage interface is inspected
- **THEN** it SHALL offer only append and read operations

#### Scenario: Only one module reaches the audit model
- **WHEN** the codebase is scanned for references to the audit-log model outside its own definition, migrations, admin, serializers and tests
- **THEN** exactly one module SHALL match

### Requirement: The live event feed is an output port, not a side effect
Publishing a live dashboard event SHALL be modelled as an injected output abstraction that
a use case calls, not as a module-level function reached from inside business logic. The
existing dual delivery mechanism — a shared channel layer where one is configured, and a
database relay table otherwise — SHALL remain unchanged behind that abstraction, and the
wire format of published frames SHALL be unchanged.

#### Scenario: A use case publishes without knowing the transport
- **WHEN** an interactor reports a ticker, guardrail, audit or voice event
- **THEN** it SHALL call the injected presenter
- **AND** it SHALL NOT import the WebSocket library or reference the channel-layer configuration

#### Scenario: The WebSocket server's import graph is unchanged
- **WHEN** the ASGI application is imported
- **THEN** neither the agent pipeline nor the LLM graph library SHALL be loaded as a side effect

### Requirement: Background task names are pinned independently of module paths
Every background task SHALL declare an explicit registered name, so that the identifier
referenced by the periodic-task schedule and carried by already-queued messages remains
resolvable regardless of where the task function subsequently lives.

#### Scenario: A queued message survives a module move
- **WHEN** a task function is relocated to a different module
- **THEN** its registered name SHALL be unchanged
- **AND** the periodic schedule SHALL continue to resolve it
