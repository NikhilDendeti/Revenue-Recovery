## Context

`BatchReplayView.post()` (`backend/recovery/views.py:114-121`) currently does exactly one thing:
`replay_batch.delay()`. `replay_batch` (`backend/recovery/tasks.py`) finds every `Transaction`
with `status=OPEN`, orders by `created_at`, and staggers `process_transaction_event` dispatch by
`REPLAY_STAGGER_SECONDS` (default 1.5s) per transaction. Once a batch is fully resolved, this
query returns nothing, and `replay_batch` returns `{'queued': 0}` — a documented, deliberate
no-op today (`test_sweep_scheduled_actions_only_dispatches_due_items`-style idempotency), not a
bug in the existing behavior. The problem is purely that this makes the button a **one-shot**
demo action rather than a repeatable one, which matters for a judged/live-demo context where the
button needs to work correctly no matter how many times it's clicked, by anyone, with no operator
re-seeding data in between.

`seed_data.py`'s command already has exactly the generation logic needed
(`_seed_payment_degradation`, `_seed_subscription_failure`, `_seed_receivable`,
`_seed_checkout_dropoff`, each a plain function taking a count and returning created rows) —
these are Command methods today, not free functions, so calling them from a view requires either
instantiating the command or extracting them to a shared module-level helper.

## Goals / Non-Goals

**Goals:**
- Every click of "Trigger batch replay" results in a nonzero, visible batch of new activity,
  regardless of what state any prior batch is in.
- Never touch, reset, or reprocess a transaction from a prior batch — new click, new rows.
- Reuse `seed_data`'s existing generation logic rather than duplicating it.

**Non-Goals:**
- Deleting or archiving old transactions. The audit trail's append-only philosophy extends
  here: old batches' data stays exactly as it was, forever, alongside new ones. A dashboard
  showing an ever-growing transaction count across repeated demo triggers is the correct,
  honest behavior for this app, not a cleanup problem to solve.
- Changing `seed_data`'s management command itself. It remains usable standalone exactly as
  today (e.g. for local dev's initial seed, or `--flush` resets), untouched by this change.
- Rate-limiting or capping how many times the endpoint can be triggered. Out of scope; if this
  becomes a real concern (e.g. unbounded database growth from an unattended demo left running),
  it's a separate, later change.

## Decisions

### 1. Extract `seed_data`'s per-kind helpers to a shared module, don't duplicate them

**Decision:** Move `_seed_payment_degradation`, `_seed_subscription_failure`, `_seed_receivable`,
`_seed_checkout_dropoff`, and the `_customer()`/`_weighted_choice()` helpers they depend on, out
of `seed_data.py`'s `Command` class and into a new module-level location
(`backend/recovery/seed_data_helpers.py`, or similar — exact naming is an implementation detail
for tasks.md) that both `seed_data.py`'s `Command.handle()` and `BatchReplayView.post()` import
from. `seed_data.py` becomes a thin CLI wrapper around the same functions the view calls.

**Alternative considered:** Have the view shell out to the management command
(`call_command("seed_data", ...)`). Rejected — noisier (stdout writes meant for a CLI operator,
not a request), and `call_command` inside a request-handling code path is an unusual pattern this
codebase doesn't use elsewhere.

### 2. Seed the same default distribution every time (22/16/16/14), not a smaller count

**Decision:** Reuse the exact same per-flow counts `seed_data`'s command defaults to today —
22 payment_degradation, 16 subscription_failure, 16 receivable, 14 checkout_dropoff (68 total).

**Why:** These counts are already tuned to produce a demo that visibly exercises all four flows'
distinct diagnosis paths and a realistic spread of guardrail outcomes (per this session's own
verified batch runs: ~60% recovery rate, a mix of held/escalated/failed). A smaller count would
risk an unlucky draw where one flow's more interesting outcomes (e.g. a mandate-sequence
follow-up, which only shows on some fraction of subscription_failure transactions) doesn't appear
in a given click. Consistency with the existing, already-validated default beats inventing a new
number with no evidence behind it.

**Trade-off accepted:** Each click adds a full 68 rows, so the transaction list grows by 68 every
time the button is pressed. Explicitly a Non-Goal to manage this (see above) — for a demo/judging
window, unbounded growth over a handful of clicks is not a real problem.

### 3. Change the existing endpoint's behavior directly, not an additive new endpoint/flag

**Decision:** `POST /api/batch/replay/` seeds-then-replays unconditionally. No new endpoint, no
opt-in query param or body flag to get the old "replay whatever's pending" behavior back.

**Why:** The endpoint has exactly one consumer — the dashboard's own trigger button
(`frontend/src/lib/api.js::replayBatch`) — confirmed by a repo-wide search finding no other
caller. There's no existing integration relying on the old semantics that a behavior change
would break. Keeping both behaviors alive behind a flag would be speculative flexibility for a
consumer that doesn't exist.

**Alternative considered:** A distinct `POST /api/batch/reseed-and-replay/` endpoint, leaving the
original endpoint's old behavior in place. Rejected as unnecessary API surface for a single-page
dashboard with one button wired to one action — this would just mean updating the frontend to
call a different URL for no behavioral benefit.

### 4. Update the button/status copy to describe what actually happens now

**Decision:** In `frontend/src/components/Hero.jsx:92` and
`frontend/src/components/Header.jsx:193`, the label stays "Trigger batch replay" (still an
accurate imperative — the button still triggers a replay), but the in-progress label changes
from "Replaying batch…" / "Batch replay in progress" to something that reflects seeding also
happening, e.g. "Seeding & replaying…" — exact copy is an implementation-time detail, not a
spec-level concern, left to tasks.md.

## Risks / Trade-offs

- **[Risk] The view now does synchronous DB writes (seeding ~68 rows) inside the request/response
  cycle**, before returning `202`, adding latency to what was previously an instant
  `.delay()` call. → **Mitigation:** seeding is plain Django ORM `bulk`-free `.create()` calls
  (matching `seed_data.py`'s existing pattern) — the same operation already runs in well under a
  second locally per the batch-seed timings observed this session; not moved into the async task
  because the transactions must exist and be committed before `replay_batch.delay()` queries for
  `OPEN` rows, so this ordering is required, not incidental.
- **[Risk] Unbounded transaction-table growth over many demo clicks** (see Non-Goals) →
  **Mitigation:** explicitly accepted as out of scope; a future change can add a cap or a
  scheduled cleanup if this becomes a real operational concern outside a demo window.
- **[Trade-off] Losing the ability to "just replay what's pending without adding more data"** —
  the exact scenario this change removes support for. Accepted per Decision 3: no real consumer
  needs it today, and `python manage.py replay_batch --sync` remains available as a separate,
  explicit no-Celery-needed path for anyone who does want the old pending-only behavior locally.

## Migration Plan

Purely additive at the data layer (no schema change). Rollback is a straight revert of
`BatchReplayView.post()` back to its current one-liner — no data written by the new behavior is
incompatible with the old code path, since it's still just ordinary `Transaction` rows.
