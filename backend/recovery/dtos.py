"""The values that cross a layer boundary.

Django model instances never leave the storage layer — an interactor that receives a
`Transaction` can reach `txn.diagnoses.latest(...)` and issue a query from inside what is
supposed to be pure logic, which is exactly the coupling this refactor removes. Storages
convert at the boundary; everything above them speaks these.

Every dataclass here is frozen. `TransactionDTO` deliberately carries all thirteen fields
of `TransactionSerializer.Meta.fields` in the same order and with the same types (notably
`amount` as `Decimal`, not `float`) so that DRF — which resolves fields by `getattr` — can
serialise the DTO byte-identically to the model it replaced.
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class TransactionDTO:
    id: str
    kind: str
    amount: Decimal
    currency: str
    customer_id: str
    customer_name: str
    customer_phone: str
    merchant_id: str
    failure_code: str
    razorpay_order_id: str
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class DiagnosisDTO:
    root_cause: str
    confidence: float
    reasoning_text: str
    id: int | None = None


@dataclass(frozen=True)
class DecisionDTO:
    chosen_action: str
    reasoning_text: str
    id: int | None = None


@dataclass(frozen=True)
class ActionDTO:
    action_type: str
    result: str
    api_response: dict
    amount_recovered: Decimal
    id: int | None = None


@dataclass(frozen=True)
class GuardrailCheckDTO:
    """One rule's verdict. `blocked` is carried explicitly rather than derived from the
    string so the pure rules never have to know the model's TextChoices values."""

    rule_name: str
    rule_result: str
    detail: str

    @property
    def blocked(self) -> bool:
        return self.rule_result == "blocked"

    def as_summary(self) -> dict:
        """The shape persisted into `Decision.guardrail_checks_passed` — matching exactly
        what `.values("rule_name", "rule_result")` produced before."""
        return {"rule_name": self.rule_name, "rule_result": self.rule_result}


@dataclass(frozen=True)
class GuardrailVerdictDTO:
    cleared: bool
    escalate: bool = False
    hold_until: datetime | None = None
    hold_reason: str = ""
    events: list[GuardrailCheckDTO] = field(default_factory=list)


@dataclass(frozen=True)
class ContactSlotDTO:
    """The result of asking for a customer's 24h contact slot. `claimed` False means the
    cooldown is still running and `next_allowed_at` is when it lifts."""

    claimed: bool
    next_allowed_at: datetime | None = None
    last_contacted_at: datetime | None = None


@dataclass(frozen=True)
class ScheduledActionDTO:
    id: int
    transaction_id: str
    action_type: str
    reason: str
    run_after: datetime
    status: str


@dataclass(frozen=True)
class AuditEntryDTO:
    transaction_id: str
    event_type: str
    actor: str
    payload: dict
    timestamp: datetime | None = None


@dataclass(frozen=True)
class GatewayArtifactDTO:
    """Whatever the payment provider returned. `raw` is passed through to
    `Action.api_response` unchanged — the frontend's chain drawer renders it verbatim, so
    this must not be normalised."""

    raw: dict


@dataclass(frozen=True)
class PipelineResultDTO:
    diagnosis: DiagnosisDTO
    decision: DecisionDTO


@dataclass(frozen=True)
class WebhookEventDTO:
    event: str
    payload: dict

    @classmethod
    def from_request_data(cls, data: Any) -> "WebhookEventDTO":
        return cls(event=data.get("event"), payload=data.get("payload", {}) or {})


@dataclass(frozen=True)
class SummaryDTO:
    """Mirrors `analytics.compute_summary()`. Kept as a passthrough of the plain dict
    rather than a field-by-field copy: the ticker frame's `summary` key is a frozen
    frontend contract, and a DTO that enumerated the nine keys would silently drop any
    tenth one added to `analytics.py` later."""

    values: dict

    def as_payload(self) -> dict:
        return dict(self.values)
