# CLAUDE.md

Guidance for Claude Code (and any other agent) working in this repository.

## Project

**RecoverAI** — an autonomous revenue-recovery agent built for the Razorpay AI
Buildathon, Track 03 ("AI Revenue Recovery"). It detects revenue at risk across three
flows, diagnoses the root cause, decides a bounded intervention, enforces deterministic
guardrails, executes the action, and logs every step to an append-only audit trail —
watchable live on the **Recovery Room** dashboard (a real-time ticker, a guardrail
console, and a click-through reasoning-chain viewer).

In-scope flows: payment degradation → recovery, failed subscription/mandate retry, and
a B2B receivables chaser. All three share one pipeline: **detect → diagnose → decide →
act (bounded) → track outcome → audit.**

Full setup/run instructions: [README.md](README.md).

## Repo layout

```
backend/
  config/          Django settings, ASGI/WSGI, Celery app, URL root
  recovery/         models, DRF views/serializers, Channels consumer, guardrails,
                    Razorpay client, Celery tasks, seed/replay management commands
  agents/           the LangGraph Diagnosis -> Decision pipeline (+ heuristic fallback)
frontend/
  src/components/   Login, Dashboard, Recovery Ticker, Guardrail Console, Audit Trail,
                    Chain drawer, Voice moment
  src/lib/          REST client, auth (JWT), WebSocket hook, formatting helpers
openspec/           planning artifacts — see "Planning workflow" below
render.yaml         Render Blueprint: web (Daphne) + worker + beat + Postgres + Redis
```

**Stack**: Django 5 + DRF + Django Channels + Celery + django-celery-beat on the
backend, PostgreSQL + Redis in production. **Local dev needs neither installed** —
SQLite, a filesystem-based Celery broker, and a small DB-backed relay standing in for
Channels' Redis layer are the defaults; see README.md for why and how to opt into real
Postgres/Redis locally. React + Vite + Tailwind CSS v4 on the frontend.

## Architectural invariants — do not casually violate these

- **The audit log is append-only at the database level**, on every backend it runs
  against — not just Postgres. `AuditLogEntry` has a real
  `BEFORE UPDATE OR DELETE` trigger (`backend/recovery/migrations/0002_*.py`),
  implemented per-vendor (`schema_editor.connection.vendor`), not just an ORM guard.
  Never propose a design that updates or deletes an audit log row, and never assume
  this guarantee is Postgres-only — write a new row instead, on any backend.
- **Guardrails are deterministic Python, never an LLM call** (`backend/recovery/guardrails.py`).
  Diagnosis/decision reasoning may call an LLM; compliance logic must not.
- **There is no Razorpay API to force-retry a failed payment or a halted subscription.**
  Every recovery action is a *fresh* payable artifact (Order re-attempt, Payment Link,
  Registration Link, Invoice reminder) — see `backend/recovery/razorpay_client.py` and
  the README's "what's real vs. simulated" section before assuming a retry endpoint
  exists. Known unfixed gap: `seed_data`'s synthetic IDs 404 against a real
  `retry_order`/`invoice_reminder` call when live Razorpay keys are configured.
- **Delayed/cooldown actions are `ScheduledAction` rows swept by a periodic Celery Beat
  task**, never raw multi-day Celery ETA tasks (those don't survive a worker restart).
- **Live dashboard events don't assume a shared-memory channel layer.** The Celery
  worker (publisher) and Daphne (the WebSocket server) are separate processes; when
  Redis isn't configured, `recovery/ws.py` and `RecoveryConsumer` route events through
  a polled `BroadcastEvent` database table instead — a bare in-memory channel layer
  was tried first and doesn't bridge processes. Keep this in mind before proposing any
  change to how live events are delivered.
- Nothing here requires real credentials, or even a database/broker service, to run
  locally: no LLM key → rule-based diagnosis fallback; no Razorpay keys → simulated
  API responses, clearly flagged as such; no `DATABASE_URL`/`REDIS_URL` → SQLite +
  filesystem broker + the DB-backed relay above.

## Planning workflow: OpenSpec (mandatory)

This repo uses **[OpenSpec](https://openspec.dev/)** as the planning layer for all
non-trivial work. It's installed (`@fission-ai/openspec`, CLI `openspec`, v1.10+) with
Claude Code integration already wired up: 6 slash commands under `.claude/commands/opsx/`
and matching skills under `.claude/skills/`.

**Rule: don't write or modify application code without going through a change proposal
first.** The only exceptions are genuinely trivial, zero-behavior-change edits (a typo,
a comment, a config value) — anything that changes behavior, adds a feature, touches the
data model, or changes an API/WS contract goes through `/opsx:propose` → review →
`/opsx:apply`, every time, no exceptions from here on.

### Directory structure

```
openspec/
  config.yaml        project context + per-artifact rules shown to the AI (already filled in)
  specs/             capability-organized specs — the current, agreed system behavior
  changes/           in-flight change proposals (proposal.md, design.md, tasks.md, spec deltas)
  archive/           completed changes, once their spec deltas are merged into specs/
```

Run `openspec list --specs` for the current set of capabilities (grows as changes
land — each one adds or updates the capabilities it touched). For a brand-new
capability, the first proposal that touches it establishes its baseline spec directly;
for an *existing* capability, a proposal that changes its behavior should diff against
what's already in `specs/`, not restate it from scratch.

### The workflow, step by step

1. **`/opsx:explore <topic>`** *(optional)* — a no-stakes thinking partner. Reads the
   codebase, weighs options, asks clarifying questions. Never writes code; may create
   planning artifacts if asked. Good for anything not already well-defined.
2. **`/opsx:propose "<description>"`** — creates `openspec/changes/<name>/` and
   generates every artifact the schema requires: `proposal.md` (what & why),
   `specs/<capability>/spec.md` (the delta — what must change, as scenarios),
   `design.md` (technical approach), `tasks.md` (implementation checklist). Planning
   only — it will not touch application code.
3. **Review the artifacts** — read `proposal.md`, `design.md`, the spec delta, and
   `tasks.md`. Catch misalignment here; it's cheap now, expensive after `/opsx:apply`.
4. **`/opsx:apply [change-name]`** — implements `tasks.md` one task at a time, checking
   each box off (`- [ ]` → `- [x]`) as it's genuinely (not partially) done. Pauses on
   ambiguity, blockers, or scope creep rather than guessing or silently narrowing scope.
5. **`/opsx:archive [change-name]`** — once all tasks are done, merges the spec delta
   into `openspec/specs/` (the new source of truth) and moves the change folder to
   `openspec/archive/`.
6. **`/opsx:sync [change-name]`** — merges delta specs into main specs mid-flight, if
   you need that without a full archive.
7. **`/opsx:update`** — refreshes the generated instruction files after an `openspec`
   CLI upgrade. Run this if `openspec --version` moves forward.

### CLI quick reference (outside the slash-command flow)

```bash
openspec list                    # active changes
openspec list --specs            # existing capability specs
openspec view                    # interactive dashboard of specs + changes
openspec show <name>             # show a change or spec
openspec status --change <name>  # artifact completion status for a change
openspec validate [item-name]    # validate changes/specs
openspec doctor                  # health-check the openspec/ root
```

### Project context for OpenSpec

`openspec/config.yaml` already has the tech stack, repo layout, and the architectural
invariants above filled in under `context:` — it's shown to the AI automatically on
every `/opsx:propose`/`/opsx:explore`. Keep it current if a core invariant changes.
