import random
import uuid
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Transaction

FIRST_NAMES = ["Aarav", "Vivaan", "Diya", "Ananya", "Ishaan", "Priya", "Rohan", "Kavya", "Arjun", "Meera", "Karthik", "Sneha"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Reddy", "Nair", "Gupta", "Menon", "Rao", "Kapoor", "Joshi"]

PAYMENT_FAILURE_CODES = [
    ("insufficient_funds", 0.28),
    ("card_declined", 0.22),
    ("card_expired", 0.12),
    ("payment_timed_out", 0.14),
    ("", 0.10),
    ("issuer_technical_error", 0.14),
]
UPI_FAILURE_CODES = [
    ("invalid_vpa", 0.30),
    ("vpa_resolution_failed", 0.20),
    ("payment_collect_request_expired", 0.15),
    ("bank_technical_error", 0.15),
    ("payment_declined", 0.10),
    ("payment_timed_out", 0.05),
    ("payment_cancelled", 0.05),
]
UPI_SHARE = 0.3
SUBSCRIPTION_FAILURE_CODES = [
    ("reqauth_mandate_not_acknowledged", 0.20),
    ("mandate_creation_failed", 0.15),
    ("funds_blocked_by_mandate", 0.10),
    ("card_declined", 0.25),
    ("insufficient_funds", 0.20),
    ("", 0.10),
]
CHECKOUT_DROPOFF_PAYMENT_METHODS = [
    ("upi", 0.35),
    ("card", 0.30),
    ("netbanking", 0.15),
    ("wallet", 0.10),
    ("", 0.10),
]
CHECKOUT_DROPOFF_AGE_BUCKETS_HOURS = [
    (0.5, 2),
    (2, 24),
    (24, 72),
    (72, 240),
]


def weighted_choice(pairs):
    codes, weights = zip(*pairs)
    return random.choices(codes, weights=weights, k=1)[0]


def make_customer():
    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    customer_id = f"cust_{uuid.uuid4().hex[:10]}"
    return {
        "customer_id": customer_id,
        "customer_name": name,
        "customer_phone": f"+91{random.randint(7000000000, 9999999999)}",
        "customer_email": f"{customer_id}@example.test",
    }


def seed_payment_degradation(n):
    out = []
    for _ in range(n):
        pool = UPI_FAILURE_CODES if random.random() < UPI_SHARE else PAYMENT_FAILURE_CODES
        code = weighted_choice(pool)
        amount = round(random.uniform(300, 15000), 2)
        out.append(
            Transaction.objects.create(
                kind=Transaction.Kind.PAYMENT_DEGRADATION,
                amount=amount,
                failure_code=code,
                razorpay_order_id=f"order_sim_{uuid.uuid4().hex[:12]}",
                **make_customer(),
            )
        )
    return out


def seed_subscription_failure(n):
    out = []
    for _ in range(n):
        code = weighted_choice(SUBSCRIPTION_FAILURE_CODES)
        amount = round(random.choice([299, 499, 999, 1499, 2499, 4999]) * random.uniform(0.9, 1.0), 2)
        out.append(
            Transaction.objects.create(
                kind=Transaction.Kind.SUBSCRIPTION_FAILURE,
                amount=amount,
                failure_code=code,
                **make_customer(),
            )
        )
    return out


def seed_receivable(n):
    out = []
    for i in range(n):
        if i == 0:
            amount = round(random.uniform(60000, 120000), 2)
        else:
            amount = round(random.uniform(5000, 45000), 2)
        out.append(
            Transaction.objects.create(
                kind=Transaction.Kind.RECEIVABLE,
                amount=amount,
                failure_code="invoice_overdue",
                **make_customer(),
            )
        )
    return out


def seed_checkout_dropoff(n):
    out = []
    at_risk_floor = settings.CHECKOUT_DROPOFF_AT_RISK_HOURS
    ceiling = settings.GUARDRAILS["SPEND_CEILING_INR"]
    for i in range(n):
        low, high = CHECKOUT_DROPOFF_AGE_BUCKETS_HOURS[i % len(CHECKOUT_DROPOFF_AGE_BUCKETS_HOURS)]
        low = max(low, at_risk_floor)
        high = max(high, low + 0.1)
        hours_ago = random.uniform(low, high)
        checkout_initiated_at = timezone.now() - timedelta(hours=hours_ago)

        last_payment_method = "" if i == 1 else weighted_choice(CHECKOUT_DROPOFF_PAYMENT_METHODS)

        if i == 0:
            amount = round(random.uniform(ceiling + 5000, ceiling + 40000), 2)
        else:
            amount = round(random.uniform(300, 15000), 2)

        out.append(
            Transaction.objects.create(
                kind=Transaction.Kind.CHECKOUT_DROPOFF,
                amount=amount,
                failure_code="",
                razorpay_order_id=f"order_sim_{uuid.uuid4().hex[:12]}",
                checkout_initiated_at=checkout_initiated_at,
                last_payment_method=last_payment_method,
                **make_customer(),
            )
        )
    return out


def seed_all(payment=22, subscription=16, receivable=16, checkout_dropoff=14):
    """Seed all four flows in one call, returning every created Transaction.
    Shared by seed_data's management command and BatchReplayView's auto-reseed."""
    created = []
    created += seed_payment_degradation(payment)
    created += seed_subscription_failure(subscription)
    created += seed_receivable(receivable)
    created += seed_checkout_dropoff(checkout_dropoff)
    return created
