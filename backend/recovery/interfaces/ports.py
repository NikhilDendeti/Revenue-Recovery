"""Ports — the four things the outside world supplies to a use case.

Each of these has exactly one production adapter today. That is a fair criticism of three
of them and not of the fourth: `PaymentGatewayInterface` wraps a module that already
contains its own real-vs-simulated switch, while `RandomnessInterface` and `ClockInterface`
exist so that the two genuinely untestable things in the money path — the outcome draw and
the wall clock — can be pinned in a test without patching a global.
"""

from abc import ABC, abstractmethod
from datetime import datetime


class PaymentGatewayInterface(ABC):
    """The payment provider. Implementations translate provider-specific failures into
    `GatewayError` / `GatewayArtifactNotFound` at this boundary, so no caller above ever
    reads an HTTP status code."""

    @abstractmethod
    def reopen_order_checkout(self, order_id: str | None, amount_paise: int, receipt: str) -> dict:
        ...

    @abstractmethod
    def create_payment_link(self, amount_paise: int, description: str, customer_name: str, customer_phone: str) -> dict:
        ...

    @abstractmethod
    def create_registration_link(self, amount_paise: int, description: str, customer_name: str, customer_phone: str) -> dict:
        ...

    @abstractmethod
    def resend_invoice(self, invoice_id: str, medium: str = "sms") -> dict:
        ...


class DiagnosisPipelineInterface(ABC):
    """The agent graph. Kept behind a port not because a second implementation is coming,
    but because importing it pulls LangGraph in at module scope — and anything that
    imports it transitively lands in Daphne's boot."""

    @abstractmethod
    def run(self, transaction_fields: dict) -> dict:
        ...


class TaskQueueInterface(ABC):
    """Deferred work. Two real implementations: Celery in production, and an inline
    runner for `manage.py replay_batch --sync`, which must work with no broker at all."""

    @abstractmethod
    def enqueue_process_transaction(self, transaction_id: str, countdown: float = 0) -> None:
        ...

    @abstractmethod
    def enqueue_dispatch_scheduled_action(self, scheduled_action_id: int) -> None:
        ...


class ClockInterface(ABC):
    """Time. Every method takes the instant to work from rather than reading the clock
    again, so that one evaluation compares every rule against a single `now` — mixing
    bases is how `max(hold_until, next_window)` starts producing nonsense."""

    @abstractmethod
    def now(self) -> datetime:
        ...

    @abstractmethod
    def local_hour(self, at: datetime) -> int:
        ...

    @abstractmethod
    def local_window_start(self, at: datetime, hour: int) -> datetime:
        """The local wall-clock `hour` on the same local day as `at`, WITHOUT any
        next-day rollover. The rollover is a business rule and belongs to the compliance
        rule that needs it, not here."""
        ...


class RandomnessInterface(ABC):
    """A uniform [0, 1) draw, keyed so that a seeded run stays reproducible regardless of
    the order transactions happen to be processed in."""

    @abstractmethod
    def uniform(self, key: str) -> float:
        ...
