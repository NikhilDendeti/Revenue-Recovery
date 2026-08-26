## Context

`backend/recovery/` is ~1,190 lines of production code plus ~220 in `backend/agents/`. The
suite is 80 collected tests (`79 passed, 1 skipped`; the skip is
`test_contact_cap_race_only_one_of_two_concurrent_contacts_clears`, guarded by
`connection.features.has_select_for_update`, which is False on SQLite).

This is a small codebase, and the layering is deliberately **not** applied uniformly. The
governing rule is written into `recovery/interactors/__init__.py` as the module docstring:

> **THE RULE.** Apply the interactor stack only to a code path that changes the world:
> it writes a row, calls an external system, branches on a business rule, or is reachable
> from more than one transport. A path that only reads and serialises does not get an
> interactor — DRF's `ReadOnlyModelViewSet` + serializer is already the right shape for it.

Under that rule, `tasks.py` qualifies four times over (HTTP webhook, Celery worker, Beat
sweep, and `manage.py replay_batch --sync` all reach it), and the seven read-only viewsets
do not qualify at all.

## Goals / Non-Goals

**Goals**
- Business rules testable with no database and no patching.
- One mechanically-enforced answer to "where does this code go?".
- The audit-log and guardrail invariants enforced by structure, not by convention.
- Every phase independently shippable with the suite green.

**Non-Goals**
- Rebuilding DRF. Pagination, filtering and URL routing stay with the framework.
- Relocating the WebSocket stack. `consumers.py`, `routing.py`, `auth_middleware.py` and
  `config/asgi.py` are untouched; moving them buys nothing and risks Daphne not booting.
- A `core/` package outside the Django app. Considered and rejected: ~23 files of verbatim
  relocation that moves no coupling.
- Splitting `AuditLogEntry` into its own app. That would rename `recovery_auditlogentry`
  and invalidate the raw per-vendor trigger SQL in migration `0002`, requiring a
  `SeparateDatabaseAndState` dance to preserve the guarantee the split was meant to protect.

## Decisions

### The outcome draw: split entropy from rule

`tasks.py:169` is `random.random() < min(0.95, max(0.05, diagnosis_confidence))`. The clamp
is a business rule (never fully certain in either direction); the draw is entropy. They
separate:

```python
# recovery/domain_rules.py — pure, stdlib only
def resolve_outcome(confidence: float, draw: float) -> bool:
    return draw < min(0.95, max(0.05, confidence))
```

The clamp stays in tested domain code rather than hiding inside an adapter, and assertions
become possible that could not be written before:
`resolve_outcome(0.0, 0.049) is True`, `resolve_outcome(1.0, 0.951) is False`.

**Seeding is per-transaction, not per-process.** A naive `random.Random(seed)` built inside
the wiring factory would be constructed fresh on every task invocation and therefore return
the *first* value of the stream every time — `random.Random(7).random()` is `0.3238` on
every call, which resolves as recovered for essentially every confidence the heuristic
produces, pinning a replay at ~100% recovery. A process-lifetime singleton fixes that only
if the worker runs serially, which `--concurrency > 1` does not guarantee. So the draw is
derived from the transaction id:

```python
random.Random(f"{seed}:{transaction_id}").random()
```

Reproducible across runs, independent of task ordering and worker concurrency. Unset, the
adapter uses `random.random()` and behaviour is unchanged. A test asserts that a seeded run
across many ids still produces a *distribution*, not a constant — the failure mode that a
"run it twice, compare counts" check cannot catch.

### The contact-cap row lock stays one atomic unit

Today `_log(txn, "contact_frequency_cap", ...)` executes **inside** the `atomic()` +
`select_for_update()` block: consuming the customer's 24-hour slot and recording why are
one unit. A storage method that reserves the slot and returns, leaving the interactor to
log afterwards in its own autocommit, would let a crash between the two consume a slot with
no audit-visible reason.

Therefore `RecoveryStorage.reserve_contact_slot()` writes the `GuardrailEvent` inside the
same transaction. The rule function stays pure by returning the decision *and* the detail
string; the storage persists both together.

### The clock is read once

`guardrails.py:42` binds `now = timezone.now()` once, and rules 4, 5 and 6 all compare
against that single instant. A `ClockInterface` whose `local_hour()` and
`local_window_start()` each re-read the clock would give three distinct instants, so
`max(hold_until, next_window)` would start mixing bases. `EnforceGuardrailsInteractor`
binds `now` once and passes that instant in as an argument.

**The next-day rollover belongs to the rule, not the clock.** `guardrails.py:122-124` is
`.replace(hour=start, ...)` followed by `if next_window <= now: next_window += timedelta(days=1)`.
A port that only exposes the `.replace(...)` half silently drops the bump, and at 21:00 IST
the resulting `hold_until` lands in the past — the guardrail appears to fire while
scheduling the action for a moment that has already gone. `compliance_hours` in
`guardrails/rules.py` owns the bump explicitly, and a new assertion pins
`verdict.hold_until > now`.

### Three tests patch `recovery.guardrails.timezone.now`

`test_guardrails.py` lines 178/186/193 do `patch("recovery.guardrails.timezone.now", ...)`.
That resolves the `recovery.guardrails` package, `getattr`s `timezone`, and sets `.now` on
it. So `guardrails/__init__.py` **must keep `from django.utils import timezone` bound at
module level**, and the clock adapter must reach time via `timezone.now()` rather than
`datetime.now(tz)`. One line; without it three tests die for a reason that looks unrelated.

### Guardrail events keep six individual INSERTs

Not batched into `bulk_create`. Batching gives the six rows near-identical `triggered_at`
values, which breaks `ordering = ["-triggered_at"]` on SQLite and would force a migration
adding an `-id` tiebreak — changing the Guardrail Console's display order. The win taken
here is the *verdict carrying its own checks* (which kills the double re-read and the magic
`[:6]`); the write batching is left alone.

### `_execute_action` survives as a delegate, and receives a DTO

`test_tasks.py:17-23` imports `_execute_action` at module level, so deleting the name fails
all 14 tests in the file at import time. It stays as a transport-level delegate. Its
callers pass a model instance, so the delegate converts:

```python
def _execute_action(txn, action_type, diagnosis_confidence):
    return wiring.build_execute_action_interactor().execute(
        _txn_dto(txn), action_type, diagnosis_confidence)
```

Passing `str(txn.id)` instead would make every subsequent attribute access an
`AttributeError` on a `str`.

### The four DI-impossible test retargets

Four tests enter through the `_execute_action` delegate or the `dispatch_scheduled_action`
task, both of which build their dependencies internally. There is no parameter to inject a
fake through. They retarget onto the module functions the adapter calls:

```python
patch("recovery.razorpay_client.reopen_order_checkout",
      side_effect=RazorpayError(..., status_code=404))
```

The adapter resolves that attribute at call time, so this works exactly like the surviving
`patch("recovery.razorpay_client.create_payment_link")` at `test_tasks.py:187`. For the
`RuntimeError` case, the same symbol is patched with `side_effect=RuntimeError` — the
adapter's translation layer catches only `RazorpayError`, so it still escapes to the safety
net as the test expects.

### `dispatch_scheduled_action` must NOT claim the OPEN guard

`process_transaction_event` guards on `status != OPEN`. `dispatch_scheduled_action`
deliberately does not — its transaction is `HELD`. The storage method that encapsulates the
guard is named `claim_open_transaction()` precisely so that calling it from the dispatch
path reads as obviously wrong; a "consistency" cleanup that added it there would deadlock
every held retry.

### No pipeline-wide `atomic()`

Three reasons, written as a comment on the interactor:

1. `test_process_transaction_event_escalates_on_unexpected_pipeline_error` asserts the
   `"detected"` audit entry *survives* a mid-pipeline `RuntimeError`. One enclosing
   transaction rolls it away.
2. In no-Redis mode `ws.push` writes `BroadcastEvent` rows that Daphne polls on a separate
   connection every 300ms. An open transaction blacks out the live ticker and loses every
   frame on rollback.
3. It would hold a database transaction open across a Razorpay HTTP call.

### `wiring` is never imported at `consumers.py` module scope

`wiring` imports the pipeline adapter, which imports `agents.pipeline`, which builds and
`.compile()`s the LangGraph `StateGraph` at import time. Reaching that from `consumers.py`
module scope would pull LangGraph into Daphne's boot — today `config/asgi.py` imports only
`recovery.routing` which imports `consumers.py`, whose app imports are `.models` and `.ws`.
An architecture test asserts `sys.modules` after `import config.asgi` contains no
`langgraph` or `agents.pipeline` key.

### Celery task names are pinned

`config/settings.py:187` hardcodes `"recovery.tasks.sweep_scheduled_actions"` in
`CELERY_BEAT_SCHEDULE`. All five tasks get `@shared_task(name="recovery.tasks.<fn>")` —
one keyword argument each — which permanently decouples the wire name from the module path
and keeps in-flight filesystem-broker messages resolvable.

### Known ISP debt, with a stated split seam

`StorageInterface` lands with ~18 methods and one implementation. That is an Interface
Segregation violation, accepted deliberately for now because splitting it early costs
navigation for no present benefit. The seam to split along, when it passes ~15 methods and
starts hurting: **pipeline state** (Transaction / Diagnosis / Decision / Action / Audit)
versus **scheduling** (ScheduledAction / ContactCooldown). Recorded here so the next person
does not have to re-derive it.

## Risks / Trade-offs

- **Indirection cost is real.** Tracing one webhook POST after this lands touches roughly
  ten files where today it is 18 lines in one. The mitigation is that this is applied only
  to the write path, so the read path — the majority of the endpoints — stays one hop.
- **`wiring.py` flattens the call graph.** "Who calls `ExecuteActionInteractor`?" has one
  answer everywhere: `wiring.py`. Jump-to-caller stops being useful across those seams.
  Accepted; the composition root has to live somewhere.
- **Phase 5 is not resumable halfway.** A half-gutted `tasks.py` is the one genuinely
  incoherent state in this plan. Finish the phase or revert the branch.
- **The money path being rewritten is days old.** `_execute_action`'s 404 fallback landed in
  `f173014` and has not yet run a full demo. Phase 4 rewrites exactly that code. If a demo
  comes first, stop after Phase 3.
- **Reverting Phase 3 on Windows needs a clean.** `guardrails.py` becomes `guardrails/`; a
  `git revert` can leave a stale `recovery/guardrails/__pycache__` so that
  `import recovery.guardrails` resolves to the package rather than the restored module.
  Run `git clean -xdf recovery/guardrails` after reverting.

## Migration Plan

Seven phases, each independently green. Phases 0–3 are individually safe resting states.
Phase 5 is not. Order and rationale are in `tasks.md`. The gate at the end of every task is
`pytest -q` reporting `79 passed, 1 skipped`.

## Open Questions

- Whether `RECOVERY_OUTCOME_SEED` should be set for a live demo. Reproducibility helps
  rehearsal; an unseeded run is more honest about the outcome model being a model. Left
  unset by default; the decision is the operator's.
