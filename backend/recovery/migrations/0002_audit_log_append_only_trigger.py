from django.db import migrations

# This is the layer that actually matters. The model's save()/delete() overrides
# (recovery/models.py) block the Django ORM path; this trigger blocks *everything
# else* — raw SQL, a stray admin action, a future developer who forgets the ORM guard
# exists. It's what makes "append-only" a real guarantee instead of a convention.
#
# Implemented per-backend (RunPython branching on connection.vendor, not RunSQL)
# because local dev defaults to SQLite while production runs Postgres — the guarantee
# has to hold on both. SQLite has no PL/pgSQL equivalent, but its own
# `BEFORE UPDATE/DELETE ... BEGIN SELECT RAISE(ABORT, ...); END;` trigger syntax does
# the same job: reject the statement, raise an error.

POSTGRES_CREATE_SQL = """
CREATE OR REPLACE FUNCTION recovery_audit_log_append_only()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'recovery_auditlogentry is append-only: % is not permitted', TG_OP;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER audit_log_append_only
    BEFORE UPDATE OR DELETE ON recovery_auditlogentry
    FOR EACH ROW EXECUTE FUNCTION recovery_audit_log_append_only();
"""

POSTGRES_DROP_SQL = """
DROP TRIGGER IF EXISTS audit_log_append_only ON recovery_auditlogentry;
DROP FUNCTION IF EXISTS recovery_audit_log_append_only();
"""

SQLITE_CREATE_UPDATE_SQL = """
CREATE TRIGGER audit_log_append_only_update
BEFORE UPDATE ON recovery_auditlogentry
BEGIN
    SELECT RAISE(ABORT, 'recovery_auditlogentry is append-only: UPDATE is not permitted');
END;
"""

SQLITE_CREATE_DELETE_SQL = """
CREATE TRIGGER audit_log_append_only_delete
BEFORE DELETE ON recovery_auditlogentry
BEGIN
    SELECT RAISE(ABORT, 'recovery_auditlogentry is append-only: DELETE is not permitted');
END;
"""

SQLITE_DROP_UPDATE_SQL = "DROP TRIGGER IF EXISTS audit_log_append_only_update;"
SQLITE_DROP_DELETE_SQL = "DROP TRIGGER IF EXISTS audit_log_append_only_delete;"


def create_trigger(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        # params=None (not the default ()) tells Django to skip psycopg's parameter
        # substitution entirely — required because the PL/pgSQL RAISE EXCEPTION below
        # has its own literal '%' placeholder, which psycopg would otherwise try to
        # interpret as its own DB-API placeholder and fail on.
        schema_editor.execute(POSTGRES_CREATE_SQL, params=None)
    elif vendor == "sqlite":
        # sqlite3's cursor.execute() only accepts one statement per call.
        schema_editor.execute(SQLITE_CREATE_UPDATE_SQL)
        schema_editor.execute(SQLITE_CREATE_DELETE_SQL)
    else:
        raise NotImplementedError(f"append-only audit log trigger not implemented for database vendor '{vendor}'")


def drop_trigger(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        schema_editor.execute(POSTGRES_DROP_SQL)
    elif vendor == "sqlite":
        schema_editor.execute(SQLITE_DROP_UPDATE_SQL)
        schema_editor.execute(SQLITE_DROP_DELETE_SQL)


class Migration(migrations.Migration):

    dependencies = [
        ("recovery", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_trigger, reverse_code=drop_trigger),
    ]
