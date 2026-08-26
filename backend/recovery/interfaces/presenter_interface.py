"""Presenters — the only place an outbound shape is decided.

`RecoveryRoomPresenterInterface` is the live-feed output port. The important move is that
`ws.push` is modelled as something a use case *calls*, not something it reaches for: the
interactor holds this interface, so it never imports `channels`, never sees
`settings.CHANNELS_USE_REDIS`, and cannot know whether its frame ends up on a Redis group
or in a `BroadcastEvent` row.

The four frame shapes below are a frozen contract — `frontend/src/lib/useRecoveryRoom.js`
switches on `type` and reads specific `payload` keys. `test_feed_presenter.py` pins the
exact key sets.
"""

from abc import ABC, abstractmethod

from ..dtos import AuditEntryDTO, GuardrailCheckDTO, SummaryDTO, TransactionDTO


class RecoveryRoomPresenterInterface(ABC):
    @abstractmethod
    def present_ticker(self, txn: TransactionDTO, *, outcome: str, action_type: str | None,
                       summary: SummaryDTO) -> None:
        """Frame `ticker` — payload keys: transaction_id, kind, amount, currency,
        customer_id, outcome, action_type, summary."""

    @abstractmethod
    def present_guardrail(self, transaction_id: str, check: GuardrailCheckDTO) -> None:
        """Frame `guardrail` — payload keys: transaction_id, rule_name, rule_result,
        detail."""

    @abstractmethod
    def present_audit(self, entry: AuditEntryDTO) -> None:
        """Frame `audit` — payload keys: transaction_id, event_type, actor, payload,
        timestamp."""

    @abstractmethod
    def present_voice(self, transaction_id: str, *, transcript: str, customer_response: str,
                      promise_to_pay_date: str) -> None:
        """Frame `voice` — payload keys: transaction_id, transcript, customer_response,
        promise_to_pay_date."""


class WebhookPresenterInterface(ABC):
    @abstractmethod
    def present_created(self, txn: TransactionDTO):
        """201 with the full transaction body."""

    @abstractmethod
    def raise_unrecognized_event(self, event: str):
        """400 with `{"error": "unrecognized event '<event>'"}`."""
