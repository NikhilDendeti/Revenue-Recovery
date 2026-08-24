import pytest
from django.db import connection
from django.db import transaction as db_transaction

from recovery.models import AuditLogEntry

pytestmark = pytest.mark.django_db


def test_creating_an_audit_entry_succeeds(make_transaction):
    txn = make_transaction()
    entry = AuditLogEntry.objects.create(
        transaction=txn, event_type="detected", actor=AuditLogEntry.Actor.SYSTEM, payload={"a": 1}
    )
    assert entry.pk is not None
    assert AuditLogEntry.objects.get(pk=entry.pk).payload == {"a": 1}


def test_raw_sql_update_against_audit_log_is_rejected(make_transaction):
    txn = make_transaction()
    entry = AuditLogEntry.objects.create(
        transaction=txn, event_type="detected", actor=AuditLogEntry.Actor.SYSTEM, payload={"original": True}
    )

    with pytest.raises(Exception) as excinfo:
        with db_transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE recovery_auditlogentry SET event_type = %s WHERE id = %s", ["tampered", entry.pk]
                )
    assert "append-only" in str(excinfo.value).lower()

    # the row is unchanged — the failed statement (and its whole atomic block) rolled back
    entry.refresh_from_db()
    assert entry.event_type == "detected"
    assert entry.payload == {"original": True}


def test_raw_sql_delete_against_audit_log_is_rejected(make_transaction):
    txn = make_transaction()
    entry = AuditLogEntry.objects.create(
        transaction=txn, event_type="detected", actor=AuditLogEntry.Actor.SYSTEM, payload={}
    )

    with pytest.raises(Exception) as excinfo:
        with db_transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM recovery_auditlogentry WHERE id = %s", [entry.pk])
    assert "append-only" in str(excinfo.value).lower()

    assert AuditLogEntry.objects.filter(pk=entry.pk).exists()


def test_orm_level_save_on_existing_entry_is_also_rejected(make_transaction):
    """The Python-level guard in AuditLogEntry.save() — a cheaper, separate check from
    the DB trigger, but should also hold."""
    txn = make_transaction()
    entry = AuditLogEntry.objects.create(
        transaction=txn, event_type="detected", actor=AuditLogEntry.Actor.SYSTEM, payload={}
    )
    entry.event_type = "tampered"
    with pytest.raises(PermissionError):
        entry.save()


def test_orm_level_delete_is_also_rejected(make_transaction):
    txn = make_transaction()
    entry = AuditLogEntry.objects.create(
        transaction=txn, event_type="detected", actor=AuditLogEntry.Actor.SYSTEM, payload={}
    )
    with pytest.raises(PermissionError):
        entry.delete()
