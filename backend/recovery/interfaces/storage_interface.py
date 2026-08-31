"""The only abstraction through which a use case reaches the database.

Two things about its shape are load-bearing:

**There is no audit mutation verb.** `append_audit` is the only audit operation, and there
is deliberately no `update_audit` / `delete_audit` to call. The append-only guarantee is
already enforced twice below this line — a `PermissionError` in `AuditLogEntry.save()` and
a per-vendor `BEFORE UPDATE OR DELETE` trigger from migration 0002 — but both of those
reject a mistake at runtime. Having no verb for it means the mistake cannot be written.

**`claim_open_transaction` is named for the guard it carries.** It applies the
`status != open` idempotency check and flips to `processing`. `dispatch_scheduled_action`
must NOT call it: that transaction is `held`, and "tidying up" the dispatch path to use the
same method for consistency would silently deadlock every scheduled retry.

Known and accepted: this is one interface with ~17 methods and one implementation, which
violates interface segregation. The seam to split along when it starts hurting is pipeline
state (Transaction / Diagnosis / Decision / Action / Audit) versus scheduling
(ScheduledAction / ContactCooldown).
"""

from abc import ABC, abstractmethod
from datetime import datetime
from decimal import Decimal

from ..dtos import (
    ActionDTO,
    AuditEntryDTO,
    ContactSlotDTO,
    DecisionDTO,
    DiagnosisDTO,
    ScheduledActionDTO,
    SummaryDTO,
    TransactionDTO,
)


class StorageInterface(ABC):
    @abstractmethod
    def get_transaction(self, transaction_id: str) -> TransactionDTO:
        """Raises TransactionNotFound."""

    @abstractmethod
    def claim_open_transaction(self, transaction_id: str) -> TransactionDTO:
        """Idempotency guard + flip to `processing`. Raises TransactionNotFound or
        TransactionNotOpen. Never call from the scheduled-dispatch path."""

    @abstractmethod
    def set_status(self, transaction_id: str, status: str) -> None:
        ...

    @abstractmethod
    def create_transaction(self, *, kind: str, amount, currency: str, customer_id: str,
                           customer_name: str, customer_phone: str, failure_code: str,
                           razorpay_order_id: str) -> TransactionDTO:
        ...

    @abstractmethod
    def open_transaction_ids(self) -> list[str]:
        """Every `open` transaction, oldest first — the replay batch's work list."""

    @abstractmethod
    def record_diagnosis(self, transaction_id: str, diagnosis: DiagnosisDTO) -> DiagnosisDTO:
        ...

    @abstractmethod
    def record_decision(self, transaction_id: str, decision: DecisionDTO) -> DecisionDTO:
        ...

    @abstractmethod
    def set_decision_guardrail_checks(self, decision_id: int, checks: list[dict]) -> None:
        ...

    @abstractmethod
    def record_action(self, transaction_id: str, *, action_type: str, api_response: dict,
                      result: str, amount_recovered: Decimal) -> ActionDTO:
        ...

    @abstractmethod
    def latest_diagnosis_confidence(self, transaction_id: str, default: float = 0.5) -> float:
        ...

    @abstractmethod
    def append_audit(self, transaction_id: str, *, event_type: str, actor: str,
                     payload: dict) -> AuditEntryDTO:
        ...

    @abstractmethod
    def count_prior_retries(self, transaction_id: str) -> int:
        ...

    @abstractmethod
    def log_guardrail_event(self, transaction_id: str, *, rule_name: str,
                            rule_result: str, detail: str) -> None:
        ...

    @abstractmethod
    def reserve_contact_slot(self, transaction_id: str, customer_id: str, *,
                             cooldown_hours: int, now: datetime,
                             rule_name: str) -> ContactSlotDTO:
        """Claim the customer's contact slot AND write the corresponding guardrail event
        inside one transaction under one row lock. Splitting these would let a crash
        between them consume a slot with no audit-visible reason."""

    @abstractmethod
    def upsert_pending_scheduled_action(self, transaction_id: str, *, action_type: str,
                                        reason: str, run_after: datetime) -> None:
        ...

    @abstractmethod
    def due_scheduled_actions(self, now: datetime) -> list[ScheduledActionDTO]:
        ...

    @abstractmethod
    def mark_scheduled_action_dispatched(self, scheduled_action_id: int) -> None:
        ...

    @abstractmethod
    def get_scheduled_action(self, scheduled_action_id: int) -> ScheduledActionDTO | None:
        ...

    @abstractmethod
    def get_summary(self) -> SummaryDTO:
        ...
