## MODIFIED Requirements

### Requirement: A not-found payable artifact falls back to a fresh one
When executing a `retry_order` or `invoice_reminder` action, if the referenced order or
invoice does not exist at the payment provider (a resource-not-found / 404-class
response), the system SHALL fall back to issuing a fresh payable artifact (a new payment
link) rather than escalating, and SHALL then resolve the transaction through the normal
recovery outcome. The system SHALL NOT assume any force-retry endpoint exists.

A `retry_order` action's payment-provider call SHALL NOT depend on re-opening or
confirming a pre-existing order through any provider operation that is not documented
by the payment provider. Where the provider documents no such operation, `retry_order`
SHALL instead issue a fresh payable artifact directly (a new payment link), the same
class of artifact `invoice_reminder`'s fallback and the `new_payment_link` action already
issue — differing from `new_payment_link` only in which decision/audit label produced it,
never in which provider endpoint is called.

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

#### Scenario: A retry_order action issues a fresh payment link directly, not an order-reopen call
- **WHEN** a `retry_order` action is executed against a configured live payment provider
- **THEN** the system SHALL issue a fresh payment link as the action's payment-provider call
- **AND** the system SHALL NOT call any provider operation that re-opens, confirms, or
  re-attempts the pre-existing order

## ADDED Requirements

### Requirement: A registration-link action carries the fields the provider's mandate-authorization flow requires
When executing a `registration_link` action against a configured live payment provider,
the system SHALL include the customer's email address, an explicit registration-method
descriptor, and a zero amount in the provider call, matching what the provider's
documented e-mandate authorization flow requires for a registration (as opposed to a
charge) request. The real outstanding amount SHALL remain available to the customer only
as informational text, never as the requested payment amount on this call.

#### Scenario: A registration-link call includes the customer's email
- **WHEN** a `registration_link` action is executed against a configured live payment provider
- **THEN** the provider call SHALL include the transaction's on-file customer email address

#### Scenario: A registration-link call declares its registration method
- **WHEN** a `registration_link` action is executed against a configured live payment provider
- **THEN** the provider call SHALL include a registration-method descriptor as the provider's mandate-authorization flow requires

#### Scenario: A registration-link call requests a zero amount
- **WHEN** a `registration_link` action is executed against a configured live payment provider
- **THEN** the provider call SHALL request a zero amount for the registration itself
- **AND** the transaction's actual outstanding amount SHALL be conveyed only as descriptive text, not as the requested amount

### Requirement: A registration-link action without an on-file customer email does not reach the provider
When a `registration_link` action would be executed against a configured live payment
provider and the transaction has no customer email on file, the system SHALL NOT send
the provider call, and SHALL instead resolve the transaction through the existing
API-failure escalation path — the same path used when the provider itself rejects a call
— rather than sending a payload the provider is expected to reject.

#### Scenario: A missing customer email escalates without an API call
- **WHEN** a `registration_link` action is due to be executed against a configured live payment provider and the transaction's customer email is blank
- **THEN** the system SHALL escalate the transaction via the API-failure escalation path
- **AND** the system SHALL NOT send a provider call for this action
