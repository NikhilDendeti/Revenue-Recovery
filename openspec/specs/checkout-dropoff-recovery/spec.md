# checkout-dropoff-recovery Specification

## Purpose

Defines end-to-end handling of checkout drop-off as a fourth revenue-recovery flow: a
transaction with no failure code, detected from checkout/order signals rather than a
failure event, diagnosed from time/value/payment-method signals, and recovered through
the same bounded, guardrailed pipeline as the other three flows.

## Requirements

### Requirement: A checkout drop-off transaction carries no failure code
The system SHALL represent a checkout drop-off as a `checkout_dropoff` transaction kind
with an empty failure code, and SHALL carry the signals needed to diagnose it without
one: when the checkout was initiated, and the last payment method attempted, if any.

#### Scenario: Ingesting a checkout-abandonment event creates an at-risk transaction
- **WHEN** a checkout-abandonment event is ingested for an order with no successful payment within the configured at-risk window
- **THEN** the system SHALL create an open `checkout_dropoff` transaction with an empty failure code, carrying the order amount, the time the checkout was initiated, and the last payment method attempted, if any

### Requirement: Checkout drop-off recovery never assumes a resumable checkout
When a checkout drop-off transaction is diagnosed with sufficient confidence to act, the
system SHALL recover it by issuing a fresh payment link, and SHALL NOT attempt to
reopen or resume the original checkout session, even when a Razorpay order id is
present on the transaction.

#### Scenario: A confidently-diagnosed drop-off issues a fresh payment link
- **WHEN** a `checkout_dropoff` transaction's diagnosis confidence clears the confidence floor
- **THEN** the chosen action SHALL be issuing a fresh payment link
- **AND** the system SHALL NOT choose the same-order retry action, regardless of whether a Razorpay order id is present

### Requirement: Checkout drop-off is subject to the same guardrails as other consumer flows, scoped the same way
The system SHALL evaluate a `checkout_dropoff` transaction against the confidence
floor, spend ceiling, and contact-frequency-cap guardrails identically to the other
consumer-facing flows, and SHALL NOT apply the B2B compliance-hours restriction to it.

#### Scenario: A high-value checkout drop-off is escalated instead of auto-executed
- **WHEN** a `checkout_dropoff` transaction's cart value exceeds the configured spend ceiling
- **THEN** the system SHALL escalate it rather than issuing a payment link automatically

#### Scenario: A checkout drop-off is not restricted to business hours
- **WHEN** a `checkout_dropoff` transaction is diagnosed with sufficient confidence to act, outside configured business hours
- **THEN** the system SHALL NOT hold it for a business-hours window, unlike a B2B receivable

### Requirement: Checkout drop-off is visible and filterable in the Recovery Room dashboard
The dashboard SHALL let an operator filter the transaction list by the checkout
drop-off flow and SHALL present it with a distinct flow label, consistent with how the
other three flows are presented.

#### Scenario: Filtering by checkout drop-off
- **WHEN** an operator applies the checkout drop-off flow filter
- **THEN** the transaction list SHALL show only `checkout_dropoff` transactions
