"""The Guardrail Enforcer — deterministic code, never an LLM call.

Six rules, matching the BRD 1:1. Every rule always writes a GuardrailEvent, whether it
passes or blocks, so the Guardrail Console has something to show even on the happy path.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from .models import Action, ContactCooldown, Decision, GuardrailEvent

CONTACT_ACTIONS = {
    Decision.Action.NEW_PAYMENT_LINK,
    Decision.Action.REGISTRATION_LINK,
    Decision.Action.INVOICE_REMINDER,
    Decision.Action.VOICE_REMINDER,
}
RETRY_ACTIONS = {Decision.Action.RETRY_ORDER}


@dataclass
class GuardrailVerdict:
    cleared: bool
    escalate: bool = False
    hold_until: datetime | None = None
    hold_reason: str = ""
    events: list = field(default_factory=list)


def _log(txn, rule_name, result, detail):
    GuardrailEvent.objects.create(
        transaction=txn, rule_name=rule_name, rule_result=result, detail=detail
    )


def evaluate_guardrails(txn, diagnosis, decision) -> GuardrailVerdict:
    cfg = settings.GUARDRAILS
    now = timezone.now()
    escalate = False
    hold_until = None
    hold_reason = ""

    # 1. Confidence floor — never guess with money.
    if diagnosis.confidence < cfg["CONFIDENCE_FLOOR"]:
        _log(
            txn, "confidence_floor", GuardrailEvent.Result.BLOCKED,
            f"diagnosis confidence {diagnosis.confidence:.2f} < floor {cfg['CONFIDENCE_FLOOR']:.2f}",
        )
        escalate = True
    else:
        _log(txn, "confidence_floor", GuardrailEvent.Result.PASSED, f"confidence {diagnosis.confidence:.2f}")

    # 2. Max retry attempts — auto-escalate to human queue.
    if decision.chosen_action in RETRY_ACTIONS:
        prior_retries = Action.objects.filter(transaction=txn, action_type=Action.Type.RETRY).count()
        if prior_retries >= cfg["MAX_RETRIES"]:
            _log(
                txn, "max_retry_attempts", GuardrailEvent.Result.BLOCKED,
                f"{prior_retries}/{cfg['MAX_RETRIES']} retries already used",
            )
            escalate = True
        else:
            _log(txn, "max_retry_attempts", GuardrailEvent.Result.PASSED, f"{prior_retries}/{cfg['MAX_RETRIES']} used")

    # 3. Spend / action ceiling — route to escalation, not auto-execute.
    if txn.amount > cfg["SPEND_CEILING_INR"]:
        _log(
            txn, "spend_ceiling", GuardrailEvent.Result.BLOCKED,
            f"₹{txn.amount} exceeds autonomous ceiling ₹{cfg['SPEND_CEILING_INR']}",
        )
        escalate = True
    else:
        _log(txn, "spend_ceiling", GuardrailEvent.Result.PASSED, f"₹{txn.amount} within ceiling")

    # From here on, escalation (never-act-blind rules) takes priority over hold/schedule rules.
    if escalate:
        return GuardrailVerdict(cleared=False, escalate=True, events=[])

    # 4. Cooldown between retries — 48h for card declines, schedule don't act immediately.
    if decision.chosen_action in RETRY_ACTIONS and "card" in (txn.failure_code or "").lower():
        cooldown_until = now + timedelta(hours=cfg["RETRY_COOLDOWN_HOURS"])
        _log(
            txn, "cooldown_between_retries", GuardrailEvent.Result.BLOCKED,
            f"card decline — scheduling retry at {cooldown_until.isoformat()} instead of immediate",
        )
        hold_until = max(hold_until, cooldown_until) if hold_until else cooldown_until
        hold_reason = "cooldown_between_retries"
    else:
        _log(txn, "cooldown_between_retries", GuardrailEvent.Result.PASSED, "no card-decline cooldown applies")

    # 5. Contact frequency cap — 1 nudge / 24h / customer. Locked to avoid a
    #    concurrent-task race between the check and the write.
    if decision.chosen_action in CONTACT_ACTIONS:
        with db_transaction.atomic():
            cooldown, _ = ContactCooldown.objects.select_for_update().get_or_create(
                customer_id=txn.customer_id, defaults={"last_contacted_at": now - timedelta(days=2)}
            )
            next_allowed = cooldown.last_contacted_at + timedelta(hours=cfg["CONTACT_COOLDOWN_HOURS"])
            if next_allowed > now:
                _log(
                    txn, "contact_frequency_cap", GuardrailEvent.Result.BLOCKED,
                    f"last contacted {cooldown.last_contacted_at.isoformat()} — next allowed {next_allowed.isoformat()}",
                )
                hold_until = max(hold_until, next_allowed) if hold_until else next_allowed
                hold_reason = "contact_frequency_cap"
            else:
                _log(txn, "contact_frequency_cap", GuardrailEvent.Result.PASSED, "outside 24h cooldown")
                cooldown.last_contacted_at = now
                cooldown.save(update_fields=["last_contacted_at"])
    else:
        _log(txn, "contact_frequency_cap", GuardrailEvent.Result.PASSED, "not a contact action")

    # 6. Compliance hours — no B2B contact outside business hours.
    if txn.kind == txn.Kind.RECEIVABLE and decision.chosen_action in CONTACT_ACTIONS:
        local_hour = timezone.localtime(now).hour
        start, end = cfg["BUSINESS_HOURS_START"], cfg["BUSINESS_HOURS_END"]
        if not (start <= local_hour < end):
            next_window = timezone.localtime(now).replace(hour=start, minute=0, second=0, microsecond=0)
            if next_window <= now:
                next_window += timedelta(days=1)
            _log(
                txn, "compliance_hours", GuardrailEvent.Result.BLOCKED,
                f"outside {start}:00-{end}:00 — queued for {next_window.isoformat()}",
            )
            hold_until = max(hold_until, next_window) if hold_until else next_window
            hold_reason = "compliance_hours"
        else:
            _log(txn, "compliance_hours", GuardrailEvent.Result.PASSED, f"within business hours ({local_hour}:00)")
    else:
        _log(txn, "compliance_hours", GuardrailEvent.Result.PASSED, "not a B2B contact action")

    if hold_until:
        return GuardrailVerdict(cleared=False, escalate=False, hold_until=hold_until, hold_reason=hold_reason)

    return GuardrailVerdict(cleared=True)
