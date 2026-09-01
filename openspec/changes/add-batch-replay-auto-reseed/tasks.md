## 1. Extract seed-data generation into a shared, reusable module

- [x] 1.1 Create `backend/recovery/seed_data_helpers.py` (or equivalent module name) containing the current per-kind generation functions from `seed_data.py`'s `Command` class (`_seed_payment_degradation`, `_seed_subscription_failure`, `_seed_receivable`, `_seed_checkout_dropoff`) and their shared dependencies (`_customer`, `_weighted_choice`, the `*_FAILURE_CODES`/`HIGH_VALUE_CART_INR`-style constant tables), as plain module-level functions rather than `Command` methods. Verify by importing the new module in a Django shell and calling each function directly against the local dev database, confirming it creates `Transaction` rows identical in shape to today's `seed_data` output.
- [x] 1.2 Update `backend/recovery/management/commands/seed_data.py`'s `Command.handle()` to import and call the extracted functions instead of its own methods, with zero change to the command's CLI behavior (same arguments, same defaults, same `--flush` semantics, same stdout messages). Verify with `python manage.py seed_data --flush` producing output identical to before this change.
- [x] 1.3 Run the full backend test suite and confirm `backend/recovery/tests/test_seed_data.py` still passes unmodified — this extraction must not change `seed_data`'s own observable behavior.

## 2. Make `BatchReplayView` seed before queuing

- [x] 2.1 In `backend/recovery/views.py`, update `BatchReplayView.post()` to call the extracted per-kind seed functions (same default counts as `seed_data`'s CLI defaults: 22/16/16/14) before calling `replay_batch.delay()`, so the newly-created rows are `OPEN` and already committed by the time `replay_batch` queries for them.
- [x] 2.2 Update the response body to include a count of newly-seeded transactions (e.g. `{"queued": True, "task_id": ..., "seeded": 68}`) so the frontend can reflect an accurate number rather than a generic "queued" message. Confirm this doesn't break the existing `{"queued": True, ...}` shape any current test asserts against — check `backend/recovery/tests/test_api.py` for `BatchReplayView` coverage first.
- [x] 2.3 Update `BatchReplayView`'s docstring to describe the new seed-then-replay behavior, replacing the now-inaccurate "Idempotent... calling this twice mid-flight is harmless" framing (still true in the sense that it's still safe to call repeatedly, but for a different reason now — every call is a fresh append, not a query that happens to return nothing on a second call).

## 3. Test coverage for the new behavior

- [x] 3.1 Add a test asserting that calling `BatchReplayView`'s endpoint (or the underlying seed-then-queue logic directly) when zero transactions exist creates new `OPEN` transactions and queues them.
- [x] 3.2 Add a test asserting that calling it again immediately after a prior batch is fully resolved (all transactions moved to a terminal status) still creates a new, nonzero set of `OPEN` transactions — this is the core scenario the spec delta requires and the one manually verified missing before this change.
- [x] 3.3 Add a test asserting that a transaction from a prior batch already in a terminal state is untouched (status, `Action`/`GuardrailEvent` history unchanged) after a later trigger.
- [x] 3.4 Add a test asserting that a transaction still `OPEN` from an earlier, unfinished trigger is included in a subsequent trigger's replay dispatch (not skipped, not duplicated into a second row).
- [x] 3.5 Run the full backend suite and confirm everything passes, including the existing `replay_batch`/`BatchReplayView` tests updated for the new response shape from task 2.2.

## 4. Frontend copy update

- [x] 4.1 Update the in-progress label in `frontend/src/components/Hero.jsx` (currently `"Replaying batch…"`) and `frontend/src/components/Header.jsx` (currently `"Batch replay in progress"`) to reflect that seeding also happens on this trigger (e.g. "Seeding & replaying…"). Keep the idle-state label "Trigger batch replay" as-is — it remains accurate.
- [x] 4.2 If the frontend surfaces the response body anywhere (toast, inline message), consider showing the `seeded` count from task 2.2 for a more informative confirmation — optional polish, not required for the core fix.
- [x] 4.3 Run `npm run build` and `npm run lint` to confirm no regressions from the copy change.

## 5. Manual verification

- [x] 5.1 Locally: run a full local stack, click "Trigger batch replay" until the batch is fully resolved (or use `--sync` for speed), then click it again and confirm new transactions appear and the ticker shows fresh activity — the exact scenario this change exists to fix.
- [x] 5.2 Confirm via `/api/summary/` that `total_count` increases by the seeded amount on each trigger, and `processed_count` climbs again after having previously plateaued.
