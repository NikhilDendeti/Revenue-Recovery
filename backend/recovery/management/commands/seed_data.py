import random
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.db.models import ProtectedError

from recovery.models import Action, AuditLogEntry, ContactCooldown, Decision, Diagnosis, GuardrailEvent, ScheduledAction, Transaction

FIRST_NAMES = ["Aarav", "Vivaan", "Diya", "Ananya", "Ishaan", "Priya", "Rohan", "Kavya", "Arjun", "Meera", "Karthik", "Sneha"]
LAST_NAMES = ["Sharma", "Verma", "Iyer", "Reddy", "Nair", "Gupta", "Menon", "Rao", "Kapoor", "Joshi"]

PAYMENT_FAILURE_CODES = [
    ("insufficient_funds", 0.28),
    ("card_declined", 0.22),
    ("card_declined_expired", 0.12),
    ("network_timeout", 0.14),
    ("", 0.10),  # no code at all — deliberately ambiguous, exercises the confidence floor
    ("issuer_unavailable_timeout", 0.14),
]
SUBSCRIPTION_FAILURE_CODES = [
    ("mandate_charge_failed", 0.45),
    ("card_declined_mandate", 0.25),
    ("insufficient_funds", 0.20),
    ("", 0.10),
]


def _weighted_choice(pairs):
    codes, weights = zip(*pairs)
    return random.choices(codes, weights=weights, k=1)[0]


def _customer():
    name = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
    return {
        "customer_id": f"cust_{uuid.uuid4().hex[:10]}",
        "customer_name": name,
        "customer_phone": f"+91{random.randint(7000000000, 9999999999)}",
    }


class Command(BaseCommand):
    help = "Seed 50+ synthetic records across the three RecoverAI flows with realistic distributions."

    def add_arguments(self, parser):
        parser.add_argument("--payment", type=int, default=22, help="payment_degradation records")
        parser.add_argument("--subscription", type=int, default=16, help="subscription_failure records")
        parser.add_argument("--receivable", type=int, default=16, help="B2B receivable records")
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

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(created)} transactions:"))
        self.stdout.write(f"  payment_degradation:  {opts['payment']}")
        self.stdout.write(f"  subscription_failure: {opts['subscription']}")
        self.stdout.write(f"  receivable:           {opts['receivable']}")
        total_at_risk = sum(t.amount for t in created)
        self.stdout.write(f"  total at risk:        ₹{total_at_risk:,.0f}")
        self.stdout.write("Run 'python manage.py replay_batch' or POST /api/batch/replay/ to process them live.")

    def _seed_payment_degradation(self, n):
        out = []
        for _ in range(n):
            code = _weighted_choice(PAYMENT_FAILURE_CODES)
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
