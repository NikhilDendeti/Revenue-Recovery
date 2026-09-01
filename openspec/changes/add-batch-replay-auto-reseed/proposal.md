## Why

`BatchReplayView.post()` (`backend/recovery/views.py`) only queues `process_transaction_event`
for transactions still in `OPEN` status. Once a seeded batch is fully resolved — every
transaction recovered, escalated, held, or failed — clicking "Trigger batch replay" again is a
silent no-op (`{'queued': 0}`): nothing errors, but nothing happens either. For a live
demo/judging context where the same button may be clicked repeatedly with no operator
available to reseed data between clicks, this makes the feature effectively single-use per
deployment, which defeats its purpose as the dashboard's primary "watch it happen live" action.

## What Changes

- `BatchReplayView.post()` seeds a fresh batch of new synthetic transactions (reusing
  `seed_data`'s existing per-flow generation helpers) and queues them for replay, on every
  call — instead of only picking up whatever happens to still be `OPEN`.
- Existing transactions (including any still `OPEN` from an unfinished prior run) are left
  untouched and are included in the same replay pass rather than ignored or reset — nothing is
  deleted, reset, or reprocessed against its will.
- The frontend's trigger button/confirmation copy is updated to reflect that each click adds a
  new batch, rather than implying it replays the existing one.

## Capabilities

### New Capabilities
- `batch-replay-triggering`: defines what happens when the operator triggers a batch replay —
  that it is always a well-defined, non-empty action, and how it interacts with any transactions
  already in flight.

### Modified Capabilities
(none — `action-execution`'s scope is per-transaction outcome resolution, which is unaffected;
this change only affects what gets fed into the existing pipeline, not how the pipeline itself
resolves an action)

## Impact

- `backend/recovery/views.py::BatchReplayView.post()` — seeds before queuing.
- `backend/recovery/tasks.py::replay_batch` — unchanged in what it does (find `OPEN`, stagger,
  dispatch); the seeding step happens synchronously in the view, before this task is queued, so
  the newly-seeded rows are already `OPEN` by the time it runs.
- `backend/recovery/management/commands/seed_data.py` — its per-kind helper functions
  (`_seed_payment_degradation`, `_seed_subscription_failure`, `_seed_receivable`,
  `_seed_checkout_dropoff`) are reused directly by the view rather than duplicated; the
  management command itself is unchanged and still usable standalone.
- `frontend/src/components/Hero.jsx` (or wherever the trigger button/confirmation text lives) —
  copy update only, no behavioral change on the frontend.
- No new database migration — this reuses the existing `Transaction` model and seeding logic
  exactly as-is, just from a new call site.
