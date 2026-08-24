## 1. Diagnosis rule ordering fix

- [x] 1.1 In `backend/agents/pipeline.py`, move the `"expired"` entry in `_DIAGNOSIS_RULES` before the `"card_declined"` entry
- [x] 1.2 Update `backend/agents/tests/test_pipeline.py::test_diagnosis_rule_order_card_declined_beats_expired_on_overlap` to assert the corrected output (rename it to reflect the new behavior) and verify `pytest agents/tests/test_pipeline.py -v` passes — 14/14 passing

## 2. ScheduledAction ordering fix

- [x] 2.1 Add `class Meta: ordering = ["-created_at"]` to `ScheduledAction` in `backend/recovery/models.py`
- [x] 2.2 Run `python manage.py makemigrations recovery` and verify it generates a state-only migration (no `AddField`/`AlterField`, just `AlterModelOptions`), then `python manage.py migrate` — migration 0003 confirmed state-only, applied cleanly
- [x] 2.3 Verify the `UnorderedObjectListWarning` no longer appears

## 3. Full verification

- [x] 3.1 Run the entire suite (`pytest -v` from `backend/`) and verify all tests pass with no warnings from either fixed area — 64/64 passing, zero warnings
