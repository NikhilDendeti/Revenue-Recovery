from django.core.management.base import BaseCommand
from django.db import transaction as db_transaction
from django.db.models import ProtectedError

from recovery.models import Action, AuditLogEntry, ContactCooldown, Decision, Diagnosis, GuardrailEvent, ScheduledAction, Transaction
from recovery.seed_data_helpers import (
    seed_checkout_dropoff,
    seed_payment_degradation,
    seed_receivable,
    seed_subscription_failure,
)


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
        created += seed_payment_degradation(opts["payment"])
        created += seed_subscription_failure(opts["subscription"])
        created += seed_receivable(opts["receivable"])
        created += seed_checkout_dropoff(opts["checkout_dropoff"])

        self.stdout.write(self.style.SUCCESS(f"Seeded {len(created)} transactions:"))
        self.stdout.write(f"  payment_degradation:  {opts['payment']}")
        self.stdout.write(f"  subscription_failure: {opts['subscription']}")
        self.stdout.write(f"  receivable:           {opts['receivable']}")
        self.stdout.write(f"  checkout_dropoff:     {opts['checkout_dropoff']}")
        total_at_risk = sum(t.amount for t in created)
        self.stdout.write(f"  total at risk:        ₹{total_at_risk:,.0f}")
        self.stdout.write("Run 'python manage.py replay_batch' or POST /api/batch/replay/ to process them live.")
