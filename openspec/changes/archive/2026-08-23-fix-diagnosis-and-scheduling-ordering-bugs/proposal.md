## Why

The automated test suite added in `add-automated-test-suite` surfaced two small,
real correctness gaps while writing tests for existing behavior — this change fixes
both rather than leaving them merely documented.

## What Changes

- Reorder `agents/pipeline.py`'s `_DIAGNOSIS_RULES` so the more specific `"expired"`
  pattern is checked before the more general `"card_declined"` pattern. Today, a
  failure code containing both (like seed data's `card_declined_expired`) is always
  classified as a plain card decline and can never reach the `card_expired` diagnosis
  — meaning the `new_payment_link` decision path for expired cards is effectively
  unreachable from that seed code. **BREAKING** (in the narrow sense that the existing
  regression test's asserted output changes): `card_declined_expired` now diagnoses as
  `card_expired`, not `card_declined`.
- Add `ordering = ["-created_at"]` to `ScheduledAction.Meta`, matching every other
  model in the app (`Transaction`, `Diagnosis`, `Decision`, `Action`, `GuardrailEvent`,
  `AuditLogEntry` all order newest-first). Removes the `UnorderedObjectListWarning`
  DRF's paginator raises today and makes `/api/scheduled-actions/` pagination stable
  across pages.

## Capabilities

### New Capabilities
- `diagnosis-classification`: the rule-based mapping from a transaction's failure code
  to a diagnosed root cause, including how overlapping/ambiguous failure codes are
  resolved by specificity.
- `scheduled-action-listing`: the REST API's guarantee that listing scheduled actions
  returns a stable, well-defined order.

### Modified Capabilities
(none — `diagnosis-classification` and `scheduled-action-listing` have no existing
baseline spec yet; this change establishes them narrowly scoped to the behavior being
fixed, not a full backfill of the diagnosis pipeline or the scheduled-action model)

## Impact

- `backend/agents/pipeline.py`: reorder two entries in `_DIAGNOSIS_RULES`.
- `backend/recovery/models.py`: add `Meta.ordering` to `ScheduledAction`.
- New migration `backend/recovery/migrations/0003_*.py` (state-only — no schema/SQL
  change, `ordering` isn't a column).
- `backend/agents/tests/test_pipeline.py`: update the regression test that currently
  locks in the old (buggy) output for `card_declined_expired`.
