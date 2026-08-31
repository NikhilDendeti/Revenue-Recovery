## Context

See `proposal.md` — Why. The current frontend is ~660 lines across 8 components plus 5 lib
modules. Relevant facts the design has to respect:

- **Tailwind CSS v4** via `@tailwindcss/vite`; the theme is defined in `src/index.css` with
  `@theme { --color-*: … }` and consumed as utilities (`bg-paper`, `text-ink-soft`). There
  is no `tailwind.config.js` — the CSS file *is* the config.
- **`useRecoveryRoom`** owns all live state: `{ summary, ticks, guardrails, voiceMoment,
  setVoiceMoment, connected, refreshSummary }`. It opens one WebSocket with the access token
  as a query param, buffers `ticker` and `guardrail` events to `MAX_FEED = 120`, and
  replaces `summary` wholesale from each ticker payload.
- **WebSocket payload shapes** (from `backend/recovery/tasks.py`) are fixed:
  - `ticker` → `{transaction_id, kind, amount, currency, customer_id, outcome, action_type, summary}` — note **`customer_id`, not `customer_name`**.
  - `guardrail` → `{transaction_id, rule_name, rule_result, detail}`.
  - `voice` → `{transaction_id, transcript, customer_response, promise_to_pay_date}`.
- **`GET /summary/`** returns `{total_count, at_risk_total, recovered_total, recovered_count,
  escalated_count, held_count, failed_count, processed_count, recovery_rate}`.
- **`GET /transactions/:id/chain/`** returns the transaction fields plus `diagnoses`,
  `decisions`, `actions`, `guardrail_events`, `audit_entries`, `scheduled_actions` — five of
  which the current drawer ignores.
- **`GET /transactions/`** may return a bare array or a paginated `{results: […]}`;
  `Dashboard` already handles both (`data.results ?? data`) and that must be kept.
- Transaction `status` ∈ `open | processing | recovered | failed | escalated | held`;
  `kind` ∈ `payment_degradation | subscription_failure | receivable`.
- `oxlint` runs with `react/rules-of-hooks: error` and
  `react/only-export-components: warn` — a module exporting a component **and** a
  non-constant value trips the warning, which constrains how context/provider modules are
  split.

## Goals / Non-Goals

**Goals**
- One design system that every screen and component draws from; zero one-off palettes.
- A cinematic, streaming-grade dark aesthetic that stays legible as an operations tool.
- A genuinely touch-designed mobile experience, not a scaled-down desktop one.
- Surface the reasoning-chain data the API already returns.
- Every interactive element has hover / focus-visible / active / disabled states, and every
  async surface has loading / empty / error states.
- WCAG-AA-grade contrast, keyboard operability, and reduced-motion support.

**Non-Goals**
- **No backend change of any kind** — no endpoint, serializer, payload, migration, or task.
- **No new npm dependency** — no icon library, animation library, router, or component kit.
- No routing. The dashboard stays a single scrolling view; "navigation" is in-page section
  navigation, which is what a single-view dashboard actually needs.
- No server-side search/filter/pagination. Filtering is client-side over the already-fetched
  transaction list; adding query params is a separate change.
- No change to auth behaviour, WebSocket lifecycle, or the mid-connection-token-expiry
  non-goal already documented in the auth change.
- No fabricated domain concepts. The streaming-UI vocabulary ("rows", "billboard", "hover
  reveal") is a *layout* mapping onto recovery triage — no media-catalogue content is
  invented.

## Decisions

### Decision 1: Map the streaming design language onto recovery triage, not onto invented content
The reference aesthetic is a media app; this product is an operator console. The mapping is
structural, and each streaming pattern is adopted only where it earns its place:

| Streaming pattern | Recovery Room equivalent | Why it fits |
| --- | --- | --- |
| Billboard hero | Live batch spotlight: recovered value, recovery-rate meter, replay CTA | The one number an operator wants first, plus the one action they take |
| Content rows by theme | Transaction rows by **operational state** (needs attention → in flight → at risk → recovered) | Triage order; the row a user scans first is the one demanding action |
| Poster card | Transaction card: flow badge, customer, amount, failure code, status | Fixed aspect ratio gives the row its rhythm; amount is the "title" |
| Hover reveal | Root cause + "View chain" action on desktop hover | Progressive disclosure without a click |
| Detail page | Reasoning-chain dialog with tabs | The chain is genuinely the "detail view" of a transaction |
| Continue watching / progress bar | Recovery-rate meter and in-flight state on processing cards | Real progress semantics, not decoration |

**Rejected:** grouping rows by `kind` (payment / subscription / receivable) as the primary
axis. Kind is a *filter* (it answers "show me one flow"), not a triage order — an operator
scanning the page needs escalations first regardless of flow. Kind is therefore a filter
chip, and state is the row axis.

### Decision 2: Brand red is for intent; transaction status gets its own palette
Reserving one accent for actions is the whole reason the reference aesthetic reads as
premium rather than loud. So:

- **Red** (`--color-brand` `#e2101d`, hover `#ff2d3d`) is used *only* for: primary buttons,
  the active navigation indicator, the live pulse, the logo mark, and focus rings.
- **Status colours are separate and mutually distinguishable**: recovered → emerald
  `#3fdd8f`; failed → coral `#ff5f6b`; escalated → amber-orange `#ff9f45`; held → gold
  `#f2c14e`; processing → azure `#5ab0ff`; open → slate `#8f8f9c`.

**Why not use red for `failed`,** the obvious streaming-palette move? Because red would then
mean both "click me" and "this lost money", and the two appear side by side in the ticker.
Coral is far enough from brand red to stay unambiguous while still reading as negative.
Every status additionally carries a **glyph and a text label**, so the palette is a
reinforcement, never the sole channel (the "don't rely on colour alone" requirement).

### Decision 3: Tokens live in `@theme`; semantics live in one JS map
Tailwind v4 `@theme` is the single source for colour/typography/radius/shadow/motion tokens,
so utilities stay first-class. Status→(label, glyph, class) mapping stays in
`src/lib/format.js`, which already owns `OUTCOME_STYLE`/`STATUS_STYLE` — extended, not
replaced, so its existing import sites keep working.

**Rejected:** a `theme.js` object of JS constants. It would duplicate the tokens and split
the source of truth; Tailwind can't consume it, and arbitrary-value classes are unlintable.

### Decision 4: Header + bottom nav, not a hamburger drawer
Below the `lg` breakpoint the header collapses to wordmark + search toggle + operator menu,
and a **fixed bottom navigation bar** carries the four sections. (The switch sits at `lg`,
not `md`: measured at an 800px viewport, the header's own content — wordmark 139px + section
nav 300px + right-hand controls 296px — needs 806px inside a 790px track, so the section nav
has to leave before the rest of the header does. Putting the touch nav on tablets too is the
right call for a touch device anyway.) A hamburger drawer hides
navigation behind a tap and puts targets at the top of the screen, which is the far reach on
a phone. Bottom nav is thumb-reachable, always visible, and shows the active section without
opening anything. The bar takes `env(safe-area-inset-bottom)` padding, and `<main>` gets
matching bottom padding so nothing hides under it.

### Decision 5: In-page section navigation over a router
Adding React Router to a single-view dashboard buys nothing and adds a dependency (a
Non-Goal). Section navigation scrolls to `id`-anchored landmarks and tracks the active
section with one `IntersectionObserver`, which also gives the active-indicator behaviour for
free. Scrolling uses `scroll-margin-top` sized to the sticky header so anchors don't land
under it, and honours reduced-motion.

### Decision 6: The chain drawer becomes a real dialog, and gains tabs
Current markup is a `div` with an `onClick` backdrop — no role, no focus management, no
Escape, and the page behind it still scrolls. It becomes: `role="dialog"`,
`aria-modal="true"`, labelled by its heading, focus moved in on open and restored to the
invoking element on close, Tab cycling within the panel, Escape to close, and `overflow:
hidden` on `<body>` while open.

Tabs — **Timeline · Diagnosis · Decision · Actions · Guardrails · Scheduled** — surface the
five collections the endpoint already returns. Timeline stays the default so current
behaviour is what a user sees first. Raw payloads stay available but collapse behind a
disclosure instead of dominating the panel; the JSON is still rendered verbatim so nothing
is hidden from a judge inspecting the audit trail.

A tab whose collection is empty renders an empty state rather than being hidden — a
disappearing tab strip is worse than a stable one, and "no guardrail events fired" is itself
meaningful information.

### Decision 7: Surface errors; never regress to a silent catch
`Dashboard.refreshTransactions`, the voice-showcase call, and `useRecoveryRoom.refreshSummary`
currently swallow every rejection. Each gains an error path that raises a toast and, where
the surface owns data, an inline retry. `useRecoveryRoom` adds an `error` field to its return
value — **additive**, so existing destructuring is unaffected.

A dropped WebSocket is a distinct, non-error state: the header pill flips to
"Reconnecting…" and the ticker keeps its buffered history rather than clearing. **No
automatic reconnect loop is added** — that is a behaviour change and belongs in its own
proposal; this change only makes the existing state legible.

### Decision 8: Hand-authored inline SVG icons
One `Icon` component over a small inline `<svg>` path map (~16 glyphs). No icon package (a
Non-Goal), no sprite fetch, no emoji-as-icon — emoji render inconsistently across platforms
and are announced by screen readers as their CLDR name. Existing emoji glyphs are replaced
by icons with `aria-hidden` plus a real text label. The leftover `public/icons.svg` and
`public/favicon.svg` template assets are replaced with an on-brand favicon.

### Decision 9: Fluid panel heights via a clamp, replacing `h-[520px]`
`h-[520px]` overflows a short laptop viewport and dwarfs a phone. Panels use
`clamp(24rem, 52vh, 34rem)` so they scale with the viewport, with the internal feed keeping
its own scroll region. The Audit Trail's `min-w-[640px]` table is kept **only** at `md` and
above; below that the same data renders as stacked cards.

### Decision 10: Toast context split across two modules to satisfy the linter
`react/only-export-components` warns when a module exports both a component and a non-component
value. `src/lib/toastContext.js` holds the `createContext` object and the `useToast` hook (no
components); `src/components/ui/ToastProvider.jsx` holds the provider and its viewport
(components only). Neither module mixes export kinds.

## Risks / Trade-offs

- **Every frontend file changes at once.** Mitigated by the layering: tokens and primitives
  land first and are frozen before feature components are rebuilt against them, and the
  backend is untouched, so the blast radius is one directory and rollback is a revert.
- **Client-side filtering doesn't scale past the fetched page.** Accepted: the demo dataset
  is tens of rows, and server-side filtering is an explicit Non-Goal. The filter UI is built
  so the predicate can later move to query params without changing the component API.
- **Hover-reveal on cards is desktop-only** and unavailable to touch. Mitigated: everything
  the hover reveals is also reachable by tapping the card (which opens the chain dialog), so
  no information is hover-gated.
- **A tabbed chain view adds a click** to reach data the flat drawer showed inline. Accepted:
  the flat drawer only ever showed `audit_entries`, so nothing regresses — Timeline is the
  default tab and shows the same content, better formatted.
- **A denser visual system risks obscuring the demo's live moment.** Mitigated by keeping
  the ticker's insert animation and the voice moment as a high-prominence surface — the two
  things a judge is meant to notice — and by keeping motion subtle everywhere else.

## Migration Plan

Pure frontend, presentation-layer only. No migration, no data backfill, no contract change,
no new dependency, so `package.json` is untouched except for nothing at all. Verification is
`npm run lint` and `npm run build` clean, plus a manual pass over the checked surfaces at
360 / 768 / 1024 / 1440 / 1920 px with the backend running. Rollback is `git revert` of the
`frontend/` changes; the backend and its test suite are unaffected by construction.
