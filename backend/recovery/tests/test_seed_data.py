"""Seed-data coverage for checkout_dropoff (design.md Decision 2/3 of
add-checkout-dropoff-recovery) — the first test file for any of seed_data.py's seeding
functions; the other three kinds have none yet.
"""

from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

import pytest

from recovery.models import Transaction

pytestmark = pytest.mark.django_db


def _seed_checkout_dropoff_only(n=14):
    call_command("seed_data", "--payment", 0, "--subscription", 0, "--receivable", 0, "--checkout-dropoff", n)
    return Transaction.objects.filter(kind=Transaction.Kind.CHECKOUT_DROPOFF)


def test_seeded_checkout_dropoff_rows_have_no_failure_code():
    qs = _seed_checkout_dropoff_only()
    assert qs.count() == 14
    assert not qs.exclude(failure_code="").exists()


def test_seeded_checkout_dropoff_rows_are_all_past_the_at_risk_window():
    qs = _seed_checkout_dropoff_only()
    now = timezone.now()
    at_risk_floor = settings.CHECKOUT_DROPOFF_AT_RISK_HOURS
    for txn in qs:
        assert txn.checkout_initiated_at is not None
        age_hours = (now - txn.checkout_initiated_at).total_seconds() / 3600
        assert age_hours >= at_risk_floor, (
            f"transaction {txn.id} is only {age_hours:.2f}h old — below the "
            f"{at_risk_floor}h at-risk floor"
        )


def test_seeded_checkout_dropoff_has_at_least_one_row_above_spend_ceiling():
    qs = _seed_checkout_dropoff_only()
    ceiling = settings.GUARDRAILS["SPEND_CEILING_INR"]
    assert qs.filter(amount__gt=ceiling).exists()


def test_seeded_checkout_dropoff_last_payment_method_spans_populated_and_blank():
    qs = _seed_checkout_dropoff_only()
    assert qs.filter(last_payment_method="").exists()
    assert qs.exclude(last_payment_method="").exists()
