## Purpose

Defines the ordering guarantee for listing scheduled (delayed/cooldown) actions, so
paginated results are stable and consistent with every other list endpoint in the app.

## ADDED Requirements

### Requirement: Scheduled actions list in a stable, defined order
The scheduled-action list endpoint SHALL return results ordered newest-created-first,
consistently across pages, matching the ordering convention used by every other
listable model in the system.

#### Scenario: Listing scheduled actions across two pages returns no duplicates or gaps
- **WHEN** more scheduled actions exist than fit on one page and a client requests page 1 and then page 2
- **THEN** the two pages together contain every scheduled action exactly once, in newest-first order
