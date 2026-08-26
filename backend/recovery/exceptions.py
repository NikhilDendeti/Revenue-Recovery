"""Domain errors raised by interactors and by the ports they depend on.

These exist so that business logic can branch on *what went wrong* rather than on how the
failure happened to be transported. The motivating case is the 404 fallback: today
`tasks.py` asks `razorpay_client.is_not_found(err)`, which reads an HTTP status code from
inside a business decision. `GatewayArtifactNotFound` moves that translation to the
provider boundary, where it belongs — the execution logic then branches on a type and
stays correct if the provider's status vocabulary ever changes.
"""


class RecoveryError(Exception):
    """Base for everything raised by this app's own logic."""


class TransactionNotFound(RecoveryError):
    def __init__(self, transaction_id):
        super().__init__(f"transaction {transaction_id} does not exist")
        self.transaction_id = transaction_id


class TransactionNotOpen(RecoveryError):
    """The idempotency guard fired: a duplicate webhook or a re-dispatched task tried to
    reprocess a transaction that has already left `open`."""

    def __init__(self, transaction_id, status):
        super().__init__(f"transaction {transaction_id} is {status}, not open")
        self.transaction_id = transaction_id
        self.status = status


class UnrecognizedWebhookEvent(RecoveryError):
    def __init__(self, event):
        super().__init__(f"unrecognized event '{event}'")
        self.event = event


class GatewayError(RecoveryError):
    """The payment provider failed in a way with no safe fallback — a timeout, a 5xx, a
    refused credential. The caller escalates."""

    def __init__(self, message, cause=None):
        super().__init__(message)
        self.cause = cause


class GatewayArtifactNotFound(GatewayError):
    """The order or invoice being acted on does not exist at the provider — a stale or
    never-created id. Recoverable by issuing a fresh payable artifact instead.

    Subclasses GatewayError deliberately, so a caller that does not care about the
    distinction can still write one `except GatewayError` and catch both.
    """
