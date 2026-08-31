# recovery-room-ui Specification

## Purpose

Defines the presentation and interaction contract for the Recovery Room operator dashboard:
its design system, navigation model, live panels, transaction browsing, reasoning-chain
detail view, asynchronous states, responsive behaviour, and accessibility guarantees. This
capability governs how the dashboard looks and behaves; it governs no server behaviour.

## Requirements

### Requirement: A single design system governs every surface
The dashboard SHALL derive its colour, typography, spacing, radius, elevation, and motion
values from one shared token layer. No screen or component SHALL introduce a one-off palette,
type scale, or radius that is not expressible in those tokens.

#### Scenario: A component uses shared tokens rather than ad-hoc values
- **WHEN** any dashboard component renders a surface, a text style, or an interactive control
- **THEN** its colour, radius, elevation, and motion values SHALL come from the shared token layer
- **AND** two components presenting the same kind of element SHALL present it identically

#### Scenario: No legacy surface is left on the old visual system
- **WHEN** an operator views any screen of the application, including the login screen
- **THEN** every visible component SHALL be rendered in the current design system
- **AND** no component SHALL retain a palette or style from the previous visual system

### Requirement: The accent colour is reserved for intent, and status has its own palette
The brand accent SHALL be used only to signal user intent and system liveness — primary
actions, the active navigation indicator, the live-connection indicator, the brand mark, and
focus rings. Transaction status SHALL be communicated by a separate palette in which each
state is visually distinguishable from every other state and from the brand accent.

#### Scenario: A negative outcome is not rendered in the brand accent colour
- **WHEN** a failed or escalated transaction is displayed alongside a primary action control
- **THEN** the outcome's colour SHALL be distinguishable from the brand accent
- **AND** an operator SHALL be able to tell an actionable control apart from an outcome indicator

#### Scenario: Status is never communicated by colour alone
- **WHEN** any transaction status, recovery outcome, or guardrail result is displayed
- **THEN** it SHALL carry a text label and a non-colour glyph in addition to its colour
- **AND** the status SHALL remain identifiable when colour information is unavailable

### Requirement: Navigation is designed separately for pointer and touch viewports
The dashboard SHALL present a persistent primary navigation that indicates the current
section. On pointer/desktop viewports this SHALL be a header-based navigation; on touch/small
viewports the primary navigation SHALL be a thumb-reachable bar rather than the desktop
header reduced in size.

#### Scenario: Small viewports get a touch-designed navigation
- **WHEN** the dashboard is viewed at a small (phone-class) viewport
- **THEN** primary navigation SHALL be presented in a persistent, thumb-reachable bar
- **AND** each navigation target SHALL meet the minimum touch-target size
- **AND** page content SHALL remain fully reachable without being obscured by that bar

#### Scenario: The current section is indicated
- **WHEN** the operator scrolls to or selects a dashboard section
- **THEN** the navigation SHALL indicate that section as active using the brand accent
- **AND** the indication SHALL not depend on colour alone

#### Scenario: The header does not obscure a navigated-to section
- **WHEN** the operator navigates to a section from the navigation
- **THEN** that section's heading SHALL be visible and not hidden beneath the sticky header

### Requirement: A hero surface leads with recovered value and the primary action
The dashboard SHALL open with a hero surface that states the total value recovered, gives
the batch's context, indicates live connection state, and offers the primary recovery action
as its most prominent control alongside a secondary, visually subordinate action.

#### Scenario: The hero presents the primary action prominently
- **WHEN** an authenticated operator loads the dashboard
- **THEN** the hero SHALL display the recovered total and the recovery rate
- **AND** the primary action SHALL be rendered in the brand accent as the most prominent control
- **AND** any secondary action SHALL be visually subordinate to it

#### Scenario: Hero text remains readable over its background treatment
- **WHEN** the hero renders its background treatment
- **THEN** an overlay SHALL keep hero text at readable contrast over that background

### Requirement: Transactions are browsable as state-grouped rows of cards
Transactions SHALL be presented as horizontally-scrollable rows grouped by operational
state, ordered so that states requiring operator attention appear before resolved ones. Each
transaction SHALL be rendered as a card of consistent dimensions showing its flow, customer,
amount, and status, and selecting a card SHALL open that transaction's reasoning chain.

#### Scenario: Rows are ordered by operator urgency
- **WHEN** the transaction rows are rendered
- **THEN** rows representing states that need operator attention SHALL appear before rows of resolved transactions
- **AND** a row with no matching transactions SHALL NOT be rendered as an empty row

#### Scenario: A row is scrollable by pointer, keyboard, and touch
- **WHEN** a row contains more cards than fit the viewport
- **THEN** the row SHALL be scrollable by touch, by keyboard, and by on-screen controls on pointer viewports
- **AND** scrolling a row SHALL NOT cause the page itself to scroll horizontally

#### Scenario: Selecting a card opens its reasoning chain
- **WHEN** the operator activates a transaction card by click, tap, or keyboard
- **THEN** the reasoning chain for that transaction SHALL open

#### Scenario: Additional card detail is revealed without being hover-gated
- **WHEN** a pointer hovers a transaction card and additional detail is revealed
- **THEN** that same detail SHALL also be reachable on a touch viewport without hovering

### Requirement: Transactions can be searched and filtered without additional server calls
The dashboard SHALL let the operator narrow the visible transactions by free-text search and
by flow and status filters, applied to the transaction data already loaded. Filtering SHALL
NOT issue additional requests to the server, and SHALL be clearable in one action.

#### Scenario: Searching narrows the visible transactions
- **WHEN** the operator enters a search term
- **THEN** only transactions matching that term SHALL be displayed
- **AND** no additional server request SHALL be issued as a result of the search

#### Scenario: Active filters are visible and clearable
- **WHEN** one or more filters are active
- **THEN** the active filters SHALL be visibly indicated
- **AND** the operator SHALL be able to clear all of them in a single action

#### Scenario: A search matching nothing explains itself
- **WHEN** a search or filter combination matches no transactions
- **THEN** an empty state SHALL explain that the filters matched nothing and offer to clear them
- **AND** it SHALL be distinguishable from the state where no transactions exist at all

### Requirement: The audit trail adapts its presentation to the viewport
The audit trail SHALL present transactions in a tabular layout on wide viewports and as a
stacked, vertically-readable layout on narrow viewports. The dashboard SHALL NOT require
horizontal scrolling of the page at any supported viewport width.

#### Scenario: A narrow viewport gets a stacked layout, not a scrolling table
- **WHEN** the audit trail is viewed at a phone-class viewport
- **THEN** each transaction SHALL be presented as a stacked, vertically-readable entry
- **AND** reading a transaction's fields SHALL NOT require horizontal scrolling

#### Scenario: No supported viewport scrolls the page horizontally
- **WHEN** the dashboard is viewed at any supported viewport width
- **THEN** the page body SHALL NOT scroll horizontally
- **AND** any intentionally wide content SHALL scroll within its own container

### Requirement: The reasoning chain opens as an accessible dialog exposing the full chain
Selecting a transaction SHALL open its reasoning chain in a dialog that is exposed to
assistive technology as a modal dialog, manages keyboard focus, and can be dismissed by
keyboard. The dialog SHALL present the diagnosis, decision, actions, guardrail events,
scheduled actions, and audit timeline that the chain endpoint returns.

#### Scenario: The dialog manages focus and can be dismissed by keyboard
- **WHEN** the reasoning-chain dialog opens
- **THEN** it SHALL be exposed as a modal dialog with an accessible name
- **AND** keyboard focus SHALL move into the dialog and SHALL remain within it while it is open
- **AND** pressing Escape SHALL close it and return focus to the control that opened it
- **AND** content behind the dialog SHALL NOT scroll while it is open

#### Scenario: The full reasoning chain is presented, not only the audit entries
- **WHEN** the reasoning chain is displayed for a transaction
- **THEN** the diagnosis, decision, executed actions, guardrail events, and scheduled actions SHALL each be presented in a readable form
- **AND** the raw audit payloads SHALL remain inspectable verbatim

#### Scenario: A section of the chain with no records explains itself
- **WHEN** a section of the reasoning chain has no records for the transaction
- **THEN** that section SHALL remain available and SHALL state that it has no records
- **AND** it SHALL NOT be silently omitted

### Requirement: Every asynchronous surface has loading, empty, and error states
Every surface that depends on a network response SHALL present a distinct loading state
before data arrives, a designed empty state when there is no data, and a visible error state
when the request fails. A failed request SHALL NOT be silently discarded.

#### Scenario: A pending surface shows a loading state
- **WHEN** a surface is awaiting its first data
- **THEN** it SHALL present a loading state that reflects the shape of the content to come
- **AND** it SHALL NOT present a blank area or a misleading empty state

#### Scenario: A failed request is surfaced to the operator
- **WHEN** a dashboard data request or operator-triggered action fails
- **THEN** the failure SHALL be surfaced visibly with a plain-language message
- **AND** where the surface owns data, a retry SHALL be offered
- **AND** the failure SHALL NOT be silently swallowed

#### Scenario: A dropped live connection is distinguishable from an error
- **WHEN** the live event connection drops
- **THEN** the connection state SHALL be indicated as disconnected rather than as a request failure
- **AND** already-received live events SHALL remain visible

#### Scenario: An operator action confirms that it was accepted
- **WHEN** the operator triggers a recovery action such as a batch replay
- **THEN** the interface SHALL confirm that the action was accepted
- **AND** the triggering control SHALL indicate its in-progress state and SHALL NOT be re-triggerable while pending

### Requirement: Every interactive element exposes its full set of states
Every interactive element SHALL present a distinct hover, keyboard-focus, active, and — where
applicable — disabled state. Keyboard focus SHALL be visible on every focusable element.

#### Scenario: Keyboard focus is always visible
- **WHEN** the operator moves focus through the interface using the keyboard
- **THEN** every focused element SHALL display a visible focus indicator
- **AND** the indicator SHALL be discernible against the surface behind it

#### Scenario: A disabled control communicates that it is unavailable
- **WHEN** a control is unavailable
- **THEN** it SHALL be visually distinct from its enabled state
- **AND** it SHALL not be activatable by pointer or keyboard

### Requirement: The interface is operable by keyboard and by assistive technology
The dashboard SHALL use semantic landmarks and headings, SHALL give every interactive
control an accessible name, SHALL offer a way to skip repeated navigation, and SHALL label
every form input.

#### Scenario: Interactive content is reachable and named
- **WHEN** the operator navigates the dashboard with a keyboard or a screen reader
- **THEN** every interactive control SHALL expose an accessible name describing its action
- **AND** the page SHALL expose landmark regions and a heading structure
- **AND** a means of skipping repeated navigation to the main content SHALL be available

#### Scenario: Form inputs are labelled and errors are explained
- **WHEN** the operator uses a form, including the login form
- **THEN** each input SHALL have an associated label
- **AND** a validation or submission error SHALL be presented in text and associated with the form

### Requirement: Motion is subtle, purposeful, and can be turned off
The dashboard SHALL use motion to reinforce state changes rather than to decorate, and SHALL
honour the operating system's reduced-motion preference by removing non-essential animation
and transition.

#### Scenario: Reduced-motion preference removes non-essential animation
- **WHEN** the operator's system requests reduced motion
- **THEN** non-essential animations and transitions SHALL be removed or reduced to an instant change
- **AND** all content and functionality SHALL remain available

#### Scenario: A newly-arrived live event is visually distinguishable
- **WHEN** a new live event arrives in a feed
- **THEN** its arrival SHALL be visually distinguishable from the entries already present

### Requirement: Existing dashboard behaviour is preserved by the redesign
The redesign SHALL be presentational. Authentication, live event handling, batch replay, the
voice showcase, and reasoning-chain retrieval SHALL continue to behave as they did before,
and the redesign SHALL introduce no new server request, request parameter, or runtime
dependency.

#### Scenario: Authentication behaviour is unchanged
- **WHEN** an operator signs in, holds an expiring session, or signs out
- **THEN** the behaviour SHALL be the same as before the redesign, including the silent token refresh and the session-expiry return to the login screen

#### Scenario: Live events and operator actions are unchanged
- **WHEN** live ticker, guardrail, or voice events arrive, or the operator triggers a batch replay or a voice showcase
- **THEN** the resulting behaviour and the requests issued SHALL be the same as before the redesign
- **AND** the redesign SHALL introduce no additional server request or request parameter
