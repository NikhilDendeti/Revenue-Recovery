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
    pass


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
        raise RazorpayError(f"{path} -> {resp.status_code}: {resp.text}")
    return resp.json()


def _simulated(kind: str, **extra) -> dict:
    return {
        "simulated": True,
        "id": f"sim_{kind}_{uuid.uuid4().hex[:14]}",
        **extra,
    }


def reopen_order_checkout(order_id: str | None, amount_paise: int, receipt: str) -> dict:
    """Flow 1 fallback path: a fresh attempt against the same order intent. Real Razorpay
    requires the customer present in Checkout to actually pay — this call only creates
    (or confirms) the Order server-side; the frontend is responsible for opening
    Checkout against it."""
    if not _configured():
        return _simulated("order", order_id=order_id or f"order_{uuid.uuid4().hex[:14]}", amount=amount_paise)
    if order_id:
        return _post(f"/orders/{order_id}", {})
    return _post("/orders", {"amount": amount_paise, "currency": "INR", "receipt": receipt})


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


def create_registration_link(amount_paise: int, description: str, customer_name: str, customer_phone: str) -> dict:
    """Flow 2: drive re-authorization of a dead mandate. There is no API to force a
    retry on a halted subscription — only re-authorizing future cycles is possible."""
    if not _configured():
        return _simulated("reglink", short_url=f"https://rzp.io/rl/sim{uuid.uuid4().hex[:8]}")
    return _post(
        "/subscription_registration/auth_links",
        {
            "customer": {"name": customer_name, "contact": customer_phone},
            "type": "link",
            "amount": amount_paise,
            "currency": "INR",
            "description": description,
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
