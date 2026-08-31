import random
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.db.models import ProtectedError
from django.utils import timezone

from recovery.models import Action, AuditLogEntry, ContactCooldown, Decision, Diagnosis, GuardrailEvent, ScheduledAction, Transaction

FIRST_NAMES = ["Aarav", "Vivaan", "Diya", "Ananya", "Ishaan", "Priya", "Rohan", "Kavya", "Arjun", "Meera", "Karthik", "Sneha"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Reddy", "Nair", "Gupta", "Menon", "Rao", "Kapoor", "Joshi"]

# Real Razorpay reason codes (card-flavored) — see agents/pipeline.py's _CODE_DIAGNOSES
# for how each of these resolves to a root cause and action.
PAYMENT_FAILURE_CODES = [
    ("insufficient_funds", 0.28),
    ("card_declined", 0.22),
    ("card_expired", 0.12),
    ("payment_timed_out", 0.14),
    ("", 0.10),  # no code at all — deliberately ambiguous, exercises the confidence floor
    ("issuer_technical_error", 0.14),
]
# Real Razorpay reason codes (UPI-flavored) — folded into _seed_payment_degradation
# alongside PAYMENT_FAILURE_CODES so seeded data can exercise a UPI failure path too.
UPI_FAILURE_CODES = [
    ("invalid_vpa", 0.30),
    ("vpa_resolution_failed", 0.20),
    ("payment_collect_request_expired", 0.15),
    ("bank_technical_error", 0.15),
    ("payment_declined", 0.10),
    ("payment_timed_out", 0.05),
    ("payment_cancelled", 0.05),
]
# Share of seeded payment_degradation transactions drawn from the UPI pool rather than
# the card pool above.
UPI_SHARE = 0.3
SUBSCRIPTION_FAILURE_CODES = [
    ("reqauth_mandate_not_acknowledged", 0.20),
    ("mandate_creation_failed", 0.15),
    ("funds_blocked_by_mandate", 0.10),
    ("card_declined", 0.25),
    ("insufficient_funds", 0.20),
    ("", 0.10),
]
# Last payment method attempted before a checkout_dropoff — free text like failure_code,
# not a closed vocabulary (agents/pipeline.py's diagnosis tree only cares whether this is
# blank). The blank share stands in for "never attempted a payment method at all" (browse
# abandonment, per design.md Decision 3 of add-checkout-dropoff-recovery).
CHECKOUT_DROPOFF_PAYMENT_METHODS = [
    ("upi", 0.35),
    ("card", 0.30),
    ("netbanking", 0.15),
    ("wallet", 0.10),
    ("", 0.10),  # never attempted a payment method at all
]
# Age buckets (hours-ago range) a seeded checkout_dropoff row is drawn from, cycled across
# the seeded set so every bucket in agents/pipeline.py's decision tree (fresh/short-window/
# aging/cold) is represented, not just the happy-path recent one. Each row's draw is still
# clamped to at least CHECKOUT_DROPOFF_AT_RISK_HOURS old at seed time (design.md Decision 2).
CHECKOUT_DROPOFF_AGE_BUCKETS_HOURS = [
    (0.5, 2),     # fresh
    (2, 24),      # short-window
    (24, 72),     # aging
    (72, 240),    # cold
]


def _weighted_choice(pairs):
    codes, weights = zip(*pairs)
    return random.choices(codes, weights=weights, k=1)[0]


def _customer():
    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    customer_id = f"cust_{uuid.uuid4().hex[:10]}"
    return {
        "customer_id": customer_id,
        "customer_name": name,
        "customer_phone": f"+91{random.randint(7000000000, 9999999999)}",
        "customer_email": f"{customer_id}@example.test",
    }


class Command(BaseCommand):
    help = "Seed 50+ synthetic records across the three RecoverAI flows with realistic distributions."

    def add_arguments(self, parser):
        parser.add_argument("--payment", type=int, default=22, help="payment_degradation records")
        parser.add_argument("--subscription", type=int, default=16, help="subscription_failure records")
        parser.add_argument("--receivable", type=int, default=16, help="B2B receivable records")
        parser.add_argument("--checkout-dropoff", type=int, default=14, help="checkout_dropoff records")
        parser.add_argument("--flush", action="store_true", help="wipe existing data before seeding")

    def handle(self, *args, **opts):
        if opts["flush"]:
            # AuditLogEntry is deliberately untouched: it's protected by a DB-level
            # trigger (migration 0002), not just the model's save()/delete() guards, so
            # even a bulk queryset .delete() from here would be rejected outright.
            # That's the point — for a genuinely clean slate, recreate the database
            # (delete backend/db.sqlite3, or drop/recreate it if pointed at Postgres,
            # then migrate again), don't fight the trigger from application code.
            self.stdout.write("Flushing existing transactions (audit log is immutable and left intact)...")
            try:
                with db_transaction.atomic():
                    GuardrailEvent.objects.all().delete()
                    Action.objects.all().delete()
                    ScheduledAction.objects.all().delete()
                    Decision.objects.all().delete()
                    Diagnosis.objects.all().delete()
                    ContactCooldown.objects.all().delete()
                    Transaction.objects.all().delete()
            except ProtectedError:
                self.stdout.write(self.style.WARNING(
                    "Some transactions already have audit history and can't be deleted "
                    "(by design). For a fully clean slate, delete backend/db.sqlite3 "
                    "(or drop/recreate your configured database) and run migrate again."
                ))

        created = []
        created += self._seed_payment_degradation(opts["payment"])
        created += self._seed_subscription_failure(opts["subscription"])
        created += self._seed_receivable(opts["receivable"])
        created += self._seed_checkout_dropoff(opts["checkout_dropoff"])

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(created)} transactions:"))
        self.stdout.write(f"  payment_degradation:  {opts['payment']}")
        self.stdout.write(f"  subscription_failure: {opts['subscription']}")
        self.stdout.write(f"  receivable:           {opts['receivable']}")
        self.stdout.write(f"  checkout_dropoff:     {opts['checkout_dropoff']}")
        total_at_risk = sum(t.amount for t in created)
        self.stdout.write(f"  total at risk:        ₹{total_at_risk:,.0f}")
        self.stdout.write("Run 'python manage.py replay_batch' or POST /api/batch/replay/ to process them live.")

    def _seed_payment_degradation(self, n):
        out = []
        for _ in range(n):
            pool = UPI_FAILURE_CODES if random.random() < UPI_SHARE else PAYMENT_FAILURE_CODES
            code = _weighted_choice(pool)
            amount = round(random.uniform(300, 15000), 2)
            out.append(
                Transaction.objects.create(
                    kind=Transaction.Kind.PAYMENT_DEGRADATION,
                    amount=amount,
                    failure_code=code,
                    razorpay_order_id=f"order_sim_{uuid.uuid4().hex[:12]}",
                    **_customer(),
                )
            )
        return out

    def _seed_subscription_failure(self, n):
        out = []
        for _ in range(n):
            code = _weighted_choice(SUBSCRIPTION_FAILURE_CODES)
            amount = round(random.choice([299, 499, 999, 1499, 2499, 4999]) * random.uniform(0.9, 1.0), 2)
            out.append(
                Transaction.objects.create(
                    kind=Transaction.Kind.SUBSCRIPTION_FAILURE,
                    amount=amount,
                    failure_code=code,
                    **_customer(),
                )
            )
        return out

    def _seed_receivable(self, n):
        out = []
        for i in range(n):
            # Push a couple of high-value ones above the spend ceiling (escalation demo)
            # and above the voice-showcase-worthy threshold.
            if i == 0:
                amount = round(random.uniform(60000, 120000), 2)
            else:
                amount = round(random.uniform(5000, 45000), 2)
            out.append(
                Transaction.objects.create(
                    kind=Transaction.Kind.RECEIVABLE,
                    amount=amount,
                    failure_code="invoice_overdue",
                    **_customer(),
                )
            )
        return out

    def _seed_checkout_dropoff(self, n):
        out = []
        at_risk_floor = settings.CHECKOUT_DROPOFF_AT_RISK_HOURS
        ceiling = settings.GUARDRAILS["SPEND_CEILING_INR"]
        for i in range(n):
            low, high = CHECKOUT_DROPOFF_AGE_BUCKETS_HOURS[i % len(CHECKOUT_DROPOFF_AGE_BUCKETS_HOURS)]
            # Every row satisfies checkout_initiated_at <= now - CHECKOUT_DROPOFF_AT_RISK_HOURS
            # by construction (design.md Decision 2) — the bucket's own floor is raised to
            # the at-risk window when the two disagree.
            low = max(low, at_risk_floor)
            high = max(high, low + 0.1)
            hours_ago = random.uniform(low, high)
            checkout_initiated_at = timezone.now() - timedelta(hours=hours_ago)

            # Guarantee at least one "never attempted a payment method" row (i == 1) so the
            # blank share is always represented regardless of the random draw, alongside the
            # weighted-random draw (which itself usually produces a populated value).
            last_payment_method = "" if i == 1 else _weighted_choice(CHECKOUT_DROPOFF_PAYMENT_METHODS)

            if i == 0:
                # Push one above the spend ceiling for guardrail-escalation coverage,
                # mirroring _seed_receivable's high-value-outlier pattern above.
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
                    **_customer(),
                )
            )
        return out
