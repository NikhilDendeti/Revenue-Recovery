"""The Diagnosis -> Decision graph. A LangGraph StateGraph, not a CrewAI crew — this
pipeline is a small, deterministic-shaped state machine (ingest -> diagnose -> decide),
which is exactly what LangGraph is good at: inspectable per-node state, easy to log,
easy to keep the Guardrail Enforcer (deterministic, no LLM) as a separate step outside
this graph entirely.

Runs synchronously inside a Celery task — never call this from a view or a Channels
consumer, an LLM round trip is seconds-to-tens-of-seconds and would stall the ASGI
event loop for every other dashboard viewer.
"""

from typing import TypedDict

from langgraph.graph import END, StateGraph

from .llm import complete_json

# --- heuristic fallback tables (used whenever no LLM key is configured, or the call fails) ---
#
# Two-tier resolution, checked in this order:
#   1. _CODE_DIAGNOSES  — exact match against a real, known Razorpay reason code. Razorpay's
#      reason codes are a fixed, known enumeration (a real API concept, not free text), so
#      exact string equality is the precise, independently-reviewable primary mechanism.
#   2. _DIAGNOSIS_RULES — an ordered substring-needle scan, first-match-wins, used only when
#      the code has no exact-match entry above. This tier exists for forward-compatibility
#      (a Razorpay code not yet enumerated in tier 1, or a merchant's own custom suffix on a
#      code) and is why list order still encodes specificity within *this* tier — e.g.
#      "expired" is checked before "card_declined" so a code containing both (like the
#      retired seed shape "card_declined_expired") resolves to the more actionable
#      "card_expired" diagnosis, not a generic decline.
#   3. _KIND_DEFAULTS   — final, unconditional fallback keyed by transaction kind.
#
# Tier 1 always wins outright when it has an entry, so there is no ordering ambiguity
# between tiers — only within tier 2 itself.

_CODE_DIAGNOSES: dict[str, tuple[str, float, str]] = {
    "insufficient_funds": ("insufficient_funds", 0.82, "Card/UPI declined for insufficient funds — this failure class historically recovers well on a short delay retry."),
    "card_declined": ("card_declined", 0.78, "Card issuer declined the charge. Recoverable via a fresh attempt, but subject to the card-decline cooldown."),
    "card_expired": ("card_expired", 0.90, "The card on file has expired — a same-card retry cannot succeed; the customer needs a fresh payment method."),
    "authentication_failed": ("authentication_failed", 0.75, "Customer failed 3DS/OTP authentication on the attempt — a retry with a fresh authentication step is plausible."),
    "card_not_enrolled": ("card_not_enrolled", 0.80, "The card isn't enrolled for the authentication method Razorpay required — the same card will fail again; needs a fresh payment method."),
    "invalid_vpa": ("invalid_vpa", 0.85, "The UPI VPA entered doesn't resolve to a real handle — a data-entry error, not a transient failure."),
    "vpa_resolution_failed": ("vpa_resolution_failed", 0.65, "The VPA itself may be valid, but the PSP-side lookup failed transiently — worth retrying the same VPA, hence lower confidence than a confirmed-invalid VPA."),
    "bank_technical_error": ("technical_error", 0.65, "Provider-side (bank) technical failure, not a customer-caused decline — transient and often recoverable on retry."),
    "gateway_technical_error": ("technical_error", 0.65, "Provider-side (gateway) technical failure, not a customer-caused decline — transient and often recoverable on retry."),
    "issuer_technical_error": ("technical_error", 0.65, "Provider-side (issuer) technical failure, not a customer-caused decline — transient and often recoverable on retry."),
    "transaction_limit_exceeded": ("transaction_limit_exceeded", 0.80, "The instrument's transaction limit was exceeded — the same instrument will fail again; needs a fresh payment method or a lower amount."),
    "incorrect_cvv": ("incorrect_cvv", 0.75, "Customer entered the wrong CVV — a correctable input error, not an instrument problem."),
    "debit_instrument_blocked": ("debit_instrument_blocked", 0.80, "The debit instrument itself is blocked — a same-instrument retry cannot succeed; needs a fresh payment method."),
    "debit_instrument_inactive": ("debit_instrument_inactive", 0.80, "The debit instrument itself is inactive — a same-instrument retry cannot succeed; needs a fresh payment method."),
    # "timed_out" is Razorpay's actual code suffix (payment_timed_out / request_timed_out);
    # confidence matches the existing "timeout"/"network" substring rules below — the
    # signal is genuinely ambiguous regardless of which tier resolves it.
    "payment_timed_out": ("network_timeout", 0.55, "Payment attempt timed out before a definitive result — ambiguous signal, moderate confidence."),
    "request_timed_out": ("network_timeout", 0.55, "Request to the provider timed out before a definitive result — ambiguous signal, moderate confidence."),
    # Kept at the pre-existing kind-default confidence (0.60, at the guardrail floor) even
    # though _KIND_DEFAULTS["payment_degradation"] itself moves to 0.55 below: this is a
    # real, known Razorpay code (not an unclassified mystery code), so it still earns an
    # explicit, reviewable table entry and still auto-acts — only a truly unrecognized
    # code now falls through to the lower, escalate-by-default kind fallback.
    "payment_declined": ("payment_declined", 0.60, "Generic decline with no more specific reason attached — still a real, known code, so we act rather than treat it as wholly unclassified."),
    "payment_cancelled": ("payment_cancelled", 0.65, "Customer cancelled the payment attempt themselves — nothing wrong with the instrument, so the same order is worth retrying."),
    # root_cause is intentionally NOT mapped in _PAYMENT_DEGRADATION_ACTIONS — a risk/fraud
    # hold must never be auto-retried regardless of confidence; it deliberately falls
    # through to the existing `.get(..., "escalate")` default (see design.md Decision 2).
    "payment_risk_check_failed": ("risk_check_failed", 0.85, "Razorpay's risk engine blocked the payment — this is a deliberate fraud/risk hold, not a technical or customer-caused failure, and must always escalate."),
    # Mandate/subscription-context codes (seed_data.py's SUBSCRIPTION_FAILURE_CODES).
    "reqauth_mandate_not_acknowledged": ("reqauth_mandate_not_acknowledged", 0.70, "The mandate's re-authorization request went unacknowledged by the customer's bank/app — re-driving registration is the only lever available."),
    "mandate_creation_failed": ("mandate_creation_failed", 0.70, "Mandate creation itself failed — there's no charge to retry, only re-registration."),
    "funds_blocked_by_mandate": ("funds_blocked_by_mandate", 0.65, "Funds were blocked under the mandate but the charge didn't complete — ambiguous enough to warrant re-driving registration rather than assuming a clean retry."),
    # The one mandate-context exception that must escalate, not re-drive registration: a
    # configuration gap (recurring payments disabled for this instrument/merchant) that a
    # registration link can't fix (see design.md Decision 2).
    "recurring_payment_not_enabled": ("recurring_payment_not_enabled", 0.80, "Recurring payments aren't enabled for this instrument/merchant configuration — a registration link can't fix a configuration gap."),
}

_DIAGNOSIS_RULES = [
    ("insufficient_funds", "insufficient_funds", 0.82, "Card/UPI declined for insufficient funds — this failure class historically recovers well on a short delay retry."),
    # "expired" is checked before "card_declined" deliberately: a code containing both
    # (e.g. the retired seed shape "card_declined_expired") is a more specific, more
    # actionable diagnosis as an expired card than as a generic decline — a same-card
    # retry cannot succeed on an expired card, so it needs to route to a fresh payment
    # link, not the card-decline retry/cooldown path. First-match-wins over a substring
    # scan means list order encodes specificity within this fallback tier; keep the more
    # specific pattern first.
    ("expired", "card_expired", 0.90, "The card on file has expired — a same-card retry cannot succeed; the customer needs a fresh payment method."),
    ("card_declined", "card_declined", 0.78, "Card issuer declined the charge. Recoverable via a fresh attempt, but subject to the card-decline cooldown."),
    ("timeout", "network_timeout", 0.55, "Payment attempt timed out before a definitive result — ambiguous signal, moderate confidence."),
    # "timed_out" (Razorpay's actual suffix, e.g. payment_timed_out) is a near-miss for
    # "timeout" alone — added as its own needle so any future/variant code shaped like
    # "..._timed_out" that isn't already in _CODE_DIAGNOSES still resolves as a timeout.
    ("timed_out", "network_timeout", 0.55, "Payment attempt timed out before a definitive result — ambiguous signal, moderate confidence."),
    ("network", "network_timeout", 0.55, "Network-level failure during the attempt — ambiguous signal, moderate confidence."),
    ("mandate", "mandate_charge_failed", 0.75, "Recurring mandate charge failed — Razorpay is likely already auto-retrying on its fixed schedule."),
]

_KIND_DEFAULTS = {
    # Strictly below GUARDRAIL_CONFIDENCE_FLOOR's default (0.60) on purpose: a code that
    # reaches this generic fallback is, by definition, one this heuristic couldn't
    # classify specifically — it should escalate to a human by default rather than
    # silently auto-act on a low-quality signal (design.md Decision 5 of
    # fix-diagnosis-razorpay-failure-codes; matches the existing ambiguous-signal
    # convention already used for the timeout/network substring rules above).
    "payment_degradation": ("payment_declined", 0.55, "Generic payment failure with no specific failure code — treating as a standard decline."),
    "subscription_failure": ("mandate_charge_failed", 0.65, "Subscription charge failed — Razorpay's own retry schedule applies; recovery here means driving re-authorization."),
    "receivable": ("invoice_overdue", 0.88, "B2B invoice has aged past its due date with no payment received."),
}


def _heuristic_diagnosis(txn: dict) -> dict:
    code = (txn.get("failure_code") or "").lower()
    if code in _CODE_DIAGNOSES:
        root_cause, confidence, reasoning = _CODE_DIAGNOSES[code]
        return {"root_cause": root_cause, "confidence": confidence, "reasoning_text": reasoning}
    for needle, root_cause, confidence, reasoning in _DIAGNOSIS_RULES:
        if needle in code:
            return {"root_cause": root_cause, "confidence": confidence, "reasoning_text": reasoning}
    if not code:
        # No failure code at all is itself a weak signal — keep confidence low so the
        # confidence-floor guardrail has a real, honest chance to fire in the demo.
        return {"root_cause": "unknown", "confidence": 0.35, "reasoning_text": "No failure code present and no rule matched — root cause is genuinely unclear."}
    root_cause, confidence, reasoning = _KIND_DEFAULTS.get(txn["kind"], ("unknown", 0.35, "Unrecognized failure pattern."))
    return {"root_cause": root_cause, "confidence": confidence, "reasoning_text": reasoning}


# Payment-degradation root causes route to Order re-attempt or a fresh Payment Link —
# there's a real order_id to reopen. Subscription-failure root causes ALWAYS route to
# registration_link regardless of root cause: Razorpay already auto-retries a failed
# mandate charge on its own fixed schedule, and there's no API to force an out-of-band
# retry — the only actionable lever a subscription-context transaction has is driving
# re-authorization. Collapsing this into one table keyed by root_cause alone (the
# original version of this function) would let a subscription transaction diagnosed as
# "card_declined" pick retry_order, which assumes an Order-reopen flow that doesn't
# apply to recurring billing — exactly the kind of Razorpay-API mistake this build is
# supposed to avoid.
_PAYMENT_DEGRADATION_ACTIONS = {
    "insufficient_funds": "retry_order",
    "card_declined": "retry_order",
    "network_timeout": "retry_order",
    "card_expired": "new_payment_link",
    "payment_declined": "new_payment_link",
    # New root causes from _CODE_DIAGNOSES (fix-diagnosis-razorpay-failure-codes) — every
    # one applicable to a payment_degradation transaction gets an explicit entry here per
    # design.md Decision 2, so none silently lands on `escalate` only because nobody
    # updated this map.
    "authentication_failed": "retry_order",
    "card_not_enrolled": "new_payment_link",
    "invalid_vpa": "new_payment_link",
    "vpa_resolution_failed": "retry_order",
    "technical_error": "retry_order",
    "transaction_limit_exceeded": "new_payment_link",
    "incorrect_cvv": "retry_order",
    "debit_instrument_blocked": "new_payment_link",
    "debit_instrument_inactive": "new_payment_link",
    "payment_cancelled": "retry_order",
    # "risk_check_failed" is the one deliberate exception: absent on purpose so it falls
    # through to the `.get(..., "escalate")` default below — a fraud/risk-engine hold
    # must never be auto-retried, regardless of diagnosis confidence.
}
_SUBSCRIPTION_RETRIABLE_ROOT_CAUSES = {
    "card_declined", "insufficient_funds", "mandate_charge_failed",
    # New root causes applicable to a subscription/mandate context (design.md Decision
    # 2) — re-driving registration is the only lever available regardless of which of
    # these caused the charge/registration to fail.
    "authentication_failed", "card_not_enrolled", "invalid_vpa", "vpa_resolution_failed",
    "technical_error", "transaction_limit_exceeded", "incorrect_cvv",
    "debit_instrument_blocked", "debit_instrument_inactive",
    "reqauth_mandate_not_acknowledged", "mandate_creation_failed", "funds_blocked_by_mandate",
    # "risk_check_failed" and "recurring_payment_not_enabled" are deliberately excluded —
    # both must escalate instead: a risk hold should never be re-driven, and a
    # merchant/customer configuration gap can't be fixed by a registration link.
}

_REASONING = {
    "retry_order": "Root cause is retriable on the same order intent — re-opening Checkout rather than inventing a retry call that doesn't exist.",
    "new_payment_link": "Same card/order can't be reused — issuing a fresh payable artifact instead.",
    "registration_link": "This is a subscription/mandate context: Razorpay's own auto-retry schedule already governs the charge and there's no API to force a retry — driving re-authorization is the actionable lever.",
    "invoice_reminder": "Overdue receivable — nudging via the existing invoice's reminder channel before escalating to a higher-touch channel.",
}


def _heuristic_decision(txn: dict, diagnosis: dict) -> dict:
    root_cause = diagnosis["root_cause"]
    if diagnosis["confidence"] < 0.60 or root_cause == "unknown":
        return {"chosen_action": "escalate", "reasoning_text": "Diagnosis confidence too low to act autonomously — routing to human review rather than guessing with money."}

    if txn["kind"] == "subscription_failure":
        action = "registration_link" if root_cause in _SUBSCRIPTION_RETRIABLE_ROOT_CAUSES else "escalate"
    elif txn["kind"] == "receivable":
        action = "invoice_reminder" if root_cause == "invoice_overdue" else "escalate"
    else:
        action = _PAYMENT_DEGRADATION_ACTIONS.get(root_cause, "escalate")

    reasoning = _REASONING.get(action, "No confident action mapping for this flow — escalating.")
    return {"chosen_action": action, "reasoning_text": reasoning}


class PipelineState(TypedDict, total=False):
    transaction: dict
    diagnosis: dict
    decision: dict


def _diagnose_node(state: PipelineState) -> PipelineState:
    txn = state["transaction"]
    llm_result = complete_json(
        system_prompt=(
            "You are the Diagnosis Agent in a revenue-recovery pipeline. Given a failed "
            "transaction, return JSON with exactly these keys: root_cause (short snake_case "
            "string), confidence (float 0-1), reasoning_text (one or two sentences)."
        ),
        user_prompt=f"Transaction: {txn}",
    )
    diagnosis = llm_result if llm_result and {"root_cause", "confidence", "reasoning_text"} <= llm_result.keys() else _heuristic_diagnosis(txn)
    return {"diagnosis": diagnosis}


def _decide_node(state: PipelineState) -> PipelineState:
    txn, diagnosis = state["transaction"], state["diagnosis"]
    llm_result = complete_json(
        system_prompt=(
            "You are the Decision Agent in a revenue-recovery pipeline. Given a transaction "
            "and its diagnosis, choose ONE action from: retry_order, new_payment_link, "
            "registration_link, invoice_reminder, escalate. Return JSON with exactly these "
            "keys: chosen_action, reasoning_text. Note: there is no API to force-retry a "
            "specific failed payment or a halted subscription — never choose an action that "
            "assumes one exists."
        ),
        user_prompt=f"Transaction: {txn}\nDiagnosis: {diagnosis}",
    )
    valid_actions = {"retry_order", "new_payment_link", "registration_link", "invoice_reminder", "escalate"}
    decision = (
        llm_result
        if llm_result and llm_result.get("chosen_action") in valid_actions and "reasoning_text" in llm_result
        else _heuristic_decision(txn, diagnosis)
    )
    return {"decision": decision}


_graph = StateGraph(PipelineState)
_graph.add_node("diagnose", _diagnose_node)
_graph.add_node("decide", _decide_node)
_graph.set_entry_point("diagnose")
_graph.add_edge("diagnose", "decide")
_graph.add_edge("decide", END)
compiled_pipeline = _graph.compile()


def run_pipeline(transaction_fields: dict) -> PipelineState:
    """transaction_fields: a plain dict (kind, amount, currency, failure_code, customer_id,
    customer_name) — the graph is intentionally decoupled from the Django ORM."""
    return compiled_pipeline.invoke({"transaction": transaction_fields})
