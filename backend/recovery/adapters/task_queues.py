"""Deferred work — two real implementations.

`CeleryTaskQueue` is production. `InlineTaskQueue` backs `manage.py replay_batch --sync`,
which has to run the whole pipeline with no worker and no broker at all; it is the
break-glass path when the worker dies mid-demo.

`InlineTaskQueue` takes the function it should call rather than the composition root. The
obvious alternative — handing it `wiring` so it can build what it needs — is circular
(wiring builds the queue, the queue calls wiring) and lets a batch replay re-enter itself
through its own queue instance.
"""

import time

from django.db import transaction as db_transaction

from ..interfaces.ports import TaskQueueInterface


class CeleryTaskQueue(TaskQueueInterface):
    """Tasks are imported inside each method, not at module scope: `tasks.py` imports
    `wiring`, `wiring` imports this module, and binding at import time would close that
    loop into an ImportError."""

    def enqueue_process_transaction(self, transaction_id, countdown=0):
        from ..tasks import process_transaction_event

        self._dispatch(
            lambda: process_transaction_event.apply_async(
                args=[str(transaction_id)], countdown=countdown
            )
        )

    def enqueue_dispatch_scheduled_action(self, scheduled_action_id):
        from ..tasks import dispatch_scheduled_action

        self._dispatch(lambda: dispatch_scheduled_action.delay(scheduled_action_id))

    @staticmethod
    def _dispatch(send):
        """Defer the send to commit when we're inside a transaction.

        A no-op today — the app runs in autocommit, so `WebhookView`'s create-then-enqueue
        is already safe. It costs three lines and removes the race the moment any caller
        wraps an enqueue in `atomic()`: without it the worker can pick the message up and
        query for a row that has not been committed yet.
        """
        if db_transaction.get_connection().in_atomic_block:
            db_transaction.on_commit(send)
        else:
            send()


class InlineTaskQueue(TaskQueueInterface):
    """Runs the work in-process, in order, with the same pacing the management command
    has always had. `--stagger` stays meaningful: it is what makes a `--sync` replay climb
    the dashboard ticker rather than dumping 54 rows at once."""

    def __init__(self, process_fn, dispatch_fn=None, stagger_seconds=0.0, on_progress=None):
        self._process = process_fn
        self._dispatch = dispatch_fn
        self._stagger = stagger_seconds
        self._on_progress = on_progress
        self._count = 0

    def enqueue_process_transaction(self, transaction_id, countdown=0):
        if self._count and self._stagger:
            time.sleep(self._stagger)
        self._process(str(transaction_id))
        self._count += 1
        if self._on_progress is not None:
            self._on_progress(self._count, str(transaction_id))

    def enqueue_dispatch_scheduled_action(self, scheduled_action_id):
        if self._dispatch is None:
            raise RuntimeError("InlineTaskQueue was built without a scheduled-action dispatcher")
        self._dispatch(scheduled_action_id)
