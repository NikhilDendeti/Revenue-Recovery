import time

from django.core.management.base import BaseCommand

from recovery.models import Transaction
from recovery.tasks import process_transaction_event, replay_batch


class Command(BaseCommand):
    help = (
        "Replay every OPEN transaction through the pipeline. Default mode enqueues via "
        "Celery (staggered, matches the live demo). --sync runs it in-process with no "
        "worker required — useful for a quick smoke test."
    )

    def add_arguments(self, parser):
        parser.add_argument("--sync", action="store_true", help="run in-process, no Celery worker needed")
        parser.add_argument("--stagger", type=float, default=0.2, help="seconds between transactions in --sync mode")

    def handle(self, *args, **opts):
        if opts["sync"]:
            open_ids = list(
                Transaction.objects.filter(status=Transaction.Status.OPEN).order_by("created_at").values_list("id", flat=True)
            )
            self.stdout.write(f"Replaying {len(open_ids)} transactions synchronously...")
            for i, txn_id in enumerate(open_ids):
                process_transaction_event(str(txn_id))
                if i % 10 == 0:
                    self.stdout.write(f"  {i + 1}/{len(open_ids)}")
                time.sleep(opts["stagger"])
            self.stdout.write(self.style.SUCCESS("Done."))
        else:
            result = replay_batch.delay()
            self.stdout.write(self.style.SUCCESS(f"Queued replay_batch task {result.id} — watch the Celery worker log."))
