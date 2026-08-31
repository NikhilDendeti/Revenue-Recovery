"""A thin, transparent Razorpay test-mode client — no SDK, just the handful of real
endpoints this product actually uses.

Razorpay has no "retry a failed payment" endpoint. Every function below reflects a real
Razorpay primitive: a fresh Order, a fresh Payment Link, a Registration Link to
re-authorize a mandate, or an Invoice reminder. Nothing here pretends to force a retry
that Razorpay itself doesn't expose.

When RAZORPAY_KEY_ID / RAZORPAY_KEY_SECRET are unset (the default for local dev), every
call short-circuits into a deterministic simulated response instead of hitting the
network — the full pipeline, ticker, and audit trail still work end-to-end without live
credentials. Set both env vars to switch to real Razorpay test-mode calls.
"""

import uuid

import requests
from django.conf import settings


class RazorpayError(Exception):
    """Carries the HTTP status alongside the message so callers can branch on it —
    notably to tell a 404 (a stale/never-created id, recoverable by issuing a fresh
    payable artifact) apart from a transient 5xx/timeout (escalate)."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def is_not_found(err: Exception) -> bool:
    """True for a resource-not-found (404) RazorpayError. A 404 on retry_order/
    invoice_reminder means the referenced order/invoice doesn't exist at Razorpay —
    the action layer falls back to a fresh payment link rather than escalating."""
    return getattr(err, "status_code", None) == 404


def _configured() -> bool:
    return bool(settings.RAZORPAY_KEY_ID and settings.RAZORPAY_KEY_SECRET)


def _post(path: str, payload: dict) -> dict:
    resp = requests.post(
        f"{settings.RAZORPAY_BASE_URL}{path}",
        json=payload,
        auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET),
        timeout=15,
    )
    if resp.status_code >= 400:
        raise RazorpayError(f"{path} -> {resp.status_code}: {resp.text}", status_code=resp.status_code)
    return resp.json()


def _simulated(kind: str, **extra) -> dict:
    return {
        "simulated": True,
        "id": f"sim_{kind}_{uuid.uuid4().hex[:14]}",
        **extra,
    }


def reopen_order_checkout(
    order_id: str | None,
    amount_paise: int,
    receipt: str,
    customer_name: str,
    customer_phone: str,
) -> dict:
    """Flow 1 primary path for a `retry_order` decision. Razorpay documents no operation
    to reopen, confirm, or re-attempt a pre-existing Order (only `PATCH /orders/{id}`,
    which updates `notes` only) — so, like `new_payment_link`, this issues a fresh
    Payment Link. `retry_order` and `new_payment_link` are behaviorally identical in
    live mode; only the `Decision.Action` label (and therefore the audit trail) tells
    them apart. `order_id`, when present, is carried through only as provenance
    metadata (`retried_order_id`) for the audit trail — it is not a lookup key."""
    if not _configured():
        return _simulated(
            "plink",
            short_url=f"https://rzp.io/l/sim{uuid.uuid4().hex[:8]}",
            amount=amount_paise,
            retried_order_id=order_id,
        )
    description = f"RecoverAI recovery — {receipt}"
    result = create_payment_link(amount_paise, description, customer_name, customer_phone)
    return {**result, "retried_order_id": order_id}


def create_payment_link(amount_paise: int, description: str, customer_name: str, customer_phone: str) -> dict:
    """Flow 1 primary path when the order can't be reopened — a brand-new payable
    artifact, not a resurrection of the failed payment."""
    if not _configured():
        return _simulated("plink", short_url=f"https://rzp.io/l/sim{uuid.uuid4().hex[:8]}", amount=amount_paise)
    return _post(
        "/payment_links",
        {
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
            "customer": {"name": customer_name, "contact": customer_phone},
            "notify": {"sms": True, "email": False},
            "reminder_enable": True,
        },
    )


def create_registration_link(
    amount_paise: int, description: str, customer_name: str, customer_phone: str, customer_email: str
) -> dict:
    """Flow 2: drive re-authorization of a dead mandate. There is no API to force a
    retry on a halted subscription — only re-authorizing future cycles is possible.

    Razorpay's e-mandate authorization flow requires the customer's email, a
    `subscription_registration` descriptor, and a zero amount on the registration
    call itself (the real outstanding amount is conveyed via `description` only —
    see `tasks.py::_call_razorpay`, which folds it into the label before calling
    here). `method`/`auth_type` below are the documented-safe combination for
    e-mandate registration as researched for this fix; not independently
    re-verified against a live test-mode call beyond this file's own
    `TestLiveMode` case — see design.md's Open Questions before building anything
    UPI-specific on top of this."""
    if not _configured():
        return _simulated("reglink", short_url=f"https://rzp.io/rl/sim{uuid.uuid4().hex[:8]}")
    if not customer_email:
        raise RazorpayError(
            "create_registration_link requires a customer email in live mode", status_code=None
        )
    return _post(
        "/subscription_registration/auth_links",
        {
            "customer": {"name": customer_name, "contact": customer_phone, "email": customer_email},
            "type": "link",
            "amount": 0,
            "currency": "INR",
            "description": description,
            "subscription_registration": {"method": "emandate", "auth_type": "netbanking"},
        },
    )


def create_invoice(amount_paise: int, description: str, customer_name: str, customer_phone: str, expire_by: int) -> dict:
    """Flow 3: a due-dated invoice — really a Payment Link with invoicing metadata."""
    if not _configured():
        return _simulated("inv", short_url=f"https://rzp.io/i/sim{uuid.uuid4().hex[:8]}")
    return _post(
        "/invoices",
        {
            "type": "invoice",
            "customer": {"name": customer_name, "contact": customer_phone},
            "line_items": [{"name": description, "amount": amount_paise, "currency": "INR", "quantity": 1}],
            "expire_by": expire_by,
            "sms_notify": 1,
            "email_notify": 0,
        },
    )


def resend_invoice(invoice_id: str, medium: str = "sms") -> dict:
    if not _configured():
        return _simulated("inv_notify", invoice_id=invoice_id, medium=medium)
    return _post(f"/invoices/{invoice_id}/notify_by/{medium}", {})
