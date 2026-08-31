"""In-memory test doubles for every port.

The point of these is that a use-case test needs no database, no broker, no network and no
`mock.patch`. A test constructs the fakes, runs the interactor, and asserts on what the
fakes recorded — which also means the assertions read as "what should have happened",
not "which private function was called with what".
"""

from datetime import datetime, timedelta, timezone as dt_timezone
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
from ..exceptions import TransactionNotFound, TransactionNotOpen
from ..interfaces import (
    ClockInterface,
    DiagnosisPipelineInterface,
    PaymentGatewayInterface,
    RandomnessInterface,
    RecoveryRoomPresenterInterface,
    StorageInterface,
    TaskQueueInterface,
)

UTC = dt_timezone.utc


def make_transaction(**overrides) -> TransactionDTO:
    """A payment-degradation transaction with sane defaults. Override only what the test
    is actually about."""
    defaults = dict(
        id="11111111-1111-1111-1111-111111111111",
        kind="payment_degradation",
        amount=Decimal("8420.00"),
        currency="INR",
        customer_id="cust_abc123",
        customer_name="Test Customer",
        customer_phone="+919000000000",
        merchant_id="demo_merchant",
        failure_code="insufficient_funds",
        razorpay_order_id="order_sim_a3f9c17b204e",
        status="processing",
        created_at=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
        updated_at=datetime(2026, 8, 25, 9, 0, tzinfo=UTC),
    )
    defaults.update(overrides)
    return TransactionDTO(**defaults)


class FakeStorage(StorageInterface):
    def __init__(self, transactions=None, prior_retries=0, contact_slot=None,
                 latest_confidence=0.5, summary=None):
        self.transactions = {t.id: t for t in (transactions or [])}
        self.audit: list[AuditEntryDTO] = []
        self.actions: list[ActionDTO] = []
        self.diagnoses: list[DiagnosisDTO] = []
        self.decisions: list[DecisionDTO] = []
        self.guardrail_events: list[dict] = []
        self.scheduled: list[dict] = []
        self.dispatched: list[int] = []
        self.statuses: list[tuple[str, str]] = []
        self.decision_checks: list[tuple[int, list]] = []
        self.created: list[dict] = []
        self._prior_retries = prior_retries
        self._contact_slot = contact_slot or ContactSlotDTO(claimed=True)
        self._latest_confidence = latest_confidence
        self._summary = summary or {"recovered_total": 0.0, "recovery_rate": 0.0}
        self._next_id = 1

    def _id(self):
        self._next_id += 1
        return self._next_id

    def get_transaction(self, transaction_id):
        try:
            return self.transactions[transaction_id]
        except KeyError:
            raise TransactionNotFound(transaction_id) from None

    def claim_open_transaction(self, transaction_id):
        txn = self.get_transaction(transaction_id)
        if txn.status != "open":
            raise TransactionNotOpen(transaction_id, txn.status)
        claimed = TransactionDTO(**{**txn.__dict__, "status": "processing"})
        self.transactions[transaction_id] = claimed
        self.statuses.append((transaction_id, "processing"))
        return claimed

    def set_status(self, transaction_id, status):
        self.statuses.append((transaction_id, status))
        txn = self.transactions.get(transaction_id)
        if txn is not None:
            self.transactions[transaction_id] = TransactionDTO(**{**txn.__dict__, "status": status})

    def create_transaction(self, **kwargs):
        self.created.append(kwargs)
        txn = make_transaction(id=f"created-{self._id()}", status="open", **{
            k: v for k, v in kwargs.items() if k in TransactionDTO.__dataclass_fields__
        })
        self.transactions[txn.id] = txn
        return txn

    def open_transaction_ids(self):
        return [t.id for t in self.transactions.values() if t.status == "open"]

    def record_diagnosis(self, transaction_id, diagnosis):
        stored = DiagnosisDTO(**{**diagnosis.__dict__, "id": self._id()})
        self.diagnoses.append(stored)
        return stored

    def record_decision(self, transaction_id, decision):
        stored = DecisionDTO(**{**decision.__dict__, "id": self._id()})
        self.decisions.append(stored)
        return stored

    def set_decision_guardrail_checks(self, decision_id, checks):
        self.decision_checks.append((decision_id, checks))

    def record_action(self, transaction_id, *, action_type, api_response, result, amount_recovered):
        stored = ActionDTO(action_type=action_type, result=result, api_response=api_response,
                           amount_recovered=amount_recovered, id=self._id())
        self.actions.append(stored)
        return stored

    def latest_diagnosis_confidence(self, transaction_id, default=0.5):
        return self._latest_confidence

    def append_audit(self, transaction_id, *, event_type, actor, payload):
        entry = AuditEntryDTO(transaction_id=transaction_id, event_type=event_type,
                              actor=actor, payload=payload,
                              timestamp=datetime(2026, 8, 25, 9, 0, tzinfo=UTC))
        self.audit.append(entry)
        return entry

    @property
    def audit_events(self):
        """Just the event_type sequence — what most assertions actually care about."""
        return [e.event_type for e in self.audit]

    def count_prior_retries(self, transaction_id):
        return self._prior_retries

    def log_guardrail_event(self, transaction_id, *, rule_name, rule_result, detail):
        self.guardrail_events.append(
            {"rule_name": rule_name, "rule_result": rule_result, "detail": detail}
        )

    def reserve_contact_slot(self, transaction_id, customer_id, *, cooldown_hours, now, rule_name):
        slot = self._contact_slot
        self.guardrail_events.append({
            "rule_name": rule_name,
            "rule_result": "passed" if slot.claimed else "blocked",
            "detail": "fake contact slot",
        })
        return slot

    def upsert_pending_scheduled_action(self, transaction_id, *, action_type, reason, run_after):
        self.scheduled.append({"transaction_id": transaction_id, "action_type": action_type,
                               "reason": reason, "run_after": run_after})

    def due_scheduled_actions(self, now):
        return [ScheduledActionDTO(id=i, transaction_id=s["transaction_id"],
                                   action_type=s["action_type"], reason=s["reason"],
                                   run_after=s["run_after"], status="pending")
                for i, s in enumerate(self.scheduled, start=1)
                if s["run_after"] <= now]

    def mark_scheduled_action_dispatched(self, scheduled_action_id):
        self.dispatched.append(scheduled_action_id)

    def get_scheduled_action(self, scheduled_action_id):
        for i, s in enumerate(self.scheduled, start=1):
            if i == scheduled_action_id:
                return ScheduledActionDTO(id=i, transaction_id=s["transaction_id"],
                                          action_type=s["action_type"], reason=s["reason"],
                                          run_after=s["run_after"], status="pending")
        return None

    def get_summary(self):
        return SummaryDTO(values=dict(self._summary))


class FakeGateway(PaymentGatewayInterface):
    """`raises` fires on the first call; `raises_all` fires on every call (including the
    payment-link fallback), which is how the fallback-also-fails path gets exercised."""

    def __init__(self, raises=None, raises_all=None, response=None):
        self._raises = raises
        self._raises_all = raises_all
        self._response = response or {"simulated": True, "id": "sim_fake_001",
                                      "short_url": "https://rzp.io/l/simfake"}
        self.calls: list[tuple[str, tuple, dict]] = []

    def _call(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))
        if self._raises_all is not None:
            raise self._raises_all
        if self._raises is not None and len(self.calls) == 1:
            raise self._raises
        return dict(self._response)

    def reopen_order_checkout(self, order_id, amount_paise, receipt, customer_name, customer_phone):
        return self._call("reopen_order_checkout", order_id, amount_paise, receipt, customer_name, customer_phone)

    def create_payment_link(self, amount_paise, description, customer_name, customer_phone):
        return self._call("create_payment_link", amount_paise, description, customer_name, customer_phone)

    def create_registration_link(self, amount_paise, description, customer_name, customer_phone):
        return self._call("create_registration_link", amount_paise, description, customer_name, customer_phone)

    def resend_invoice(self, invoice_id, medium="sms"):
        return self._call("resend_invoice", invoice_id, medium)

    @property
    def called(self):
        return [c[0] for c in self.calls]


class FakePipeline(DiagnosisPipelineInterface):
    def __init__(self, result=None, raises=None):
        self._result = result or {
            "diagnosis": {"root_cause": "insufficient_funds", "confidence": 0.82,
                          "reasoning_text": "fake diagnosis"},
            "decision": {"chosen_action": "retry_order", "reasoning_text": "fake decision"},
        }
        self._raises = raises
        self.calls = []

    def run(self, transaction_fields):
        self.calls.append(transaction_fields)
        if self._raises is not None:
            raise self._raises
        return self._result


class FakeTaskQueue(TaskQueueInterface):
    def __init__(self):
        self.processed: list[tuple[str, float]] = []
        self.dispatched: list[int] = []

    def enqueue_process_transaction(self, transaction_id, countdown=0):
        self.processed.append((transaction_id, countdown))

    def enqueue_dispatch_scheduled_action(self, scheduled_action_id):
        self.dispatched.append(scheduled_action_id)


class FakeClock(ClockInterface):
    """Defaults to 14:00 — comfortably inside the 09:00–19:00 business window, so a test
    that isn't about compliance hours doesn't accidentally trip it."""

    def __init__(self, at=None, local_hour=14):
        self._at = at or datetime(2026, 8, 25, 8, 30, tzinfo=UTC)
        self._local_hour = local_hour

    def now(self):
        return self._at

    def local_hour(self, at):
        return self._local_hour

    def local_window_start(self, at, hour):
        return at.replace(hour=hour, minute=0, second=0, microsecond=0)


class FakeRandomness(RandomnessInterface):
    def __init__(self, draw=0.5):
        self._draw = draw
        self.keys: list[str] = []

    def uniform(self, key):
        self.keys.append(key)
        return self._draw


class FakePresenter(RecoveryRoomPresenterInterface):
    def __init__(self):
        self.frames: list[tuple[str, dict]] = []

    def present_ticker(self, txn, *, outcome, action_type, summary):
        self.frames.append(("ticker", {"transaction_id": txn.id, "outcome": outcome,
                                       "action_type": action_type}))

    def present_guardrail(self, transaction_id, check):
        self.frames.append(("guardrail", {"transaction_id": transaction_id,
                                          "rule_name": check.rule_name,
                                          "rule_result": check.rule_result}))

    def present_audit(self, entry):
        self.frames.append(("audit", {"transaction_id": entry.transaction_id,
                                      "event_type": entry.event_type}))

    def present_voice(self, transaction_id, *, transcript, customer_response, promise_to_pay_date):
        self.frames.append(("voice", {"transaction_id": transaction_id,
                                      "promise_to_pay_date": promise_to_pay_date}))

    @property
    def frame_types(self):
        return [f[0] for f in self.frames]
