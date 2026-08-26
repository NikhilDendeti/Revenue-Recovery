"""Clock and randomness adapters — the two ambient dependencies in the money path.

Both are trivial. Both were previously unmockable without patching a global, which is why
the clamp in the outcome rule and the next-day rollover in the compliance rule had no
direct tests.
"""

import random

from django.conf import settings
from django.utils import timezone

from ..interfaces.ports import ClockInterface, RandomnessInterface


class DjangoClock(ClockInterface):
    """Reaches time through `timezone.now()` rather than `datetime.now(tz)` deliberately:
    three tests patch `recovery.guardrails.timezone.now`, and that only works if every
    caller goes through the module attribute."""

    def now(self):
        return timezone.now()

    def local_hour(self, at):
        return timezone.localtime(at).hour

    def local_window_start(self, at, hour):
        """The local wall-clock `hour` on `at`'s own local day. Deliberately does NOT roll
        forward to tomorrow when that instant has already passed — that bump is a business
        rule and lives in `guardrails.rules.compliance_hours`, where it can be tested."""
        return timezone.localtime(at).replace(hour=hour, minute=0, second=0, microsecond=0)


class SystemRandomness(RandomnessInterface):
    """A uniform draw, optionally reproducible.

    The seed is combined with the caller's key (in practice, the transaction id) rather
    than used to build one stream. Seeding a single `random.Random(seed)` looks right and
    is badly wrong here: the composition root builds its dependencies fresh per task
    invocation, so every transaction would draw the *first* value of a freshly seeded
    stream — `random.Random(7).random()` is 0.3238 every single time — and every
    transaction whose confidence exceeds that constant would resolve as recovered. A
    seeded replay would silently become a ~100% recovery rate.

    Keying by transaction id also makes reproducibility independent of processing order,
    which matters because the replay staggers work across however many workers Celery
    happens to be running.
    """

    def __init__(self, seed=None):
        self._seed = settings.RECOVERY_OUTCOME_SEED if seed is None else seed

    def uniform(self, key):
        if self._seed is None:
            return random.random()
        return random.Random(f"{self._seed}:{key}").random()
