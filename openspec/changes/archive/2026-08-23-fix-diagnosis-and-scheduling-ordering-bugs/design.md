## Context

See proposal.md - Why. Both fixes were surfaced by the test suite added in
`add-automated-test-suite` and are small, isolated corrections with no cross-cutting
impact.

## Goals / Non-Goals

**Goals**: fix both gaps precisely, update the one existing test that currently locks
in the old diagnosis behavior, keep the rest of the diagnosis rule table and every
other model's behavior unchanged.

**Non-Goals**: a general specificity-scoring system for diagnosis rules (the fix is a
targeted reorder of two entries, not a new matching algorithm) — not warranted by two
overlapping patterns out of six.

## Decisions

**Reorder by moving `"expired"` earlier in `_DIAGNOSIS_RULES`, not by adding new
matching logic.** The list is already a first-match-wins substring scan; the bug is
purely that `"card_declined"` (a superstring match for `card_declined_expired`) sits
before `"expired"` in list order. Swapping their positions is the minimal fix and
preserves every other rule's behavior, since `"expired"` never overlaps with
`"insufficient_funds"`, `"timeout"`, `"network"`, or `"mandate"` in any of the seed
data's failure codes.

**`ScheduledAction.Meta.ordering = ["-created_at"]`, not `["run_after"]`.** Every other
orderable model in the app (`Transaction`, `Diagnosis`, `Decision`, `Action`,
`GuardrailEvent`, `AuditLogEntry`) orders newest-created-first; matching that
convention is more predictable than introducing a different one (soonest-due-first)
for just this one model. The dashboard's own scheduled-action visibility comes through
the audit trail and guardrail console, not a dedicated due-soon view, so there's no
existing UI dependency on due-date ordering to preserve.

## Risks / Trade-offs

- [The regression test that currently asserts the old, buggy output would fail after
  the fix] → update it in the same change to assert the corrected output — a stale
  test asserting wrong behavior is worse than no test.
- [`Meta.ordering` requires a migration] → state-only (`AlterModelOptions`), no SQL
  runs against existing data, safe to apply immediately in any environment.

## Migration Plan

Standard `makemigrations` + `migrate`. No data migration needed — `ordering` is
Django-side query behavior only.

## Open Questions

None.
