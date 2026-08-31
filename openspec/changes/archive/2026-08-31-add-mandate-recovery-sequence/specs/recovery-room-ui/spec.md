## ADDED Requirements

### Requirement: The reasoning chain surfaces mandate-sequence progress
When a transaction has an active or completed mandate-recovery cadence, the
reasoning-chain dialog SHALL present its progress as a current-step-of-total indicator
(for example, "step 2 of 3") alongside the step's status. A transaction with no cadence
SHALL show that section stating there is no active sequence, rather than omitting it.

#### Scenario: A sequenced transaction shows its current step
- **WHEN** the reasoning-chain dialog opens for a transaction with an active mandate-recovery cadence
- **THEN** the dialog SHALL display which step the transaction is currently on and how many steps the cadence has
- **AND** the displayed step SHALL update to reflect the transaction's latest cadence progress

#### Scenario: A non-sequenced transaction states it has no active sequence
- **WHEN** the reasoning-chain dialog opens for a transaction that never entered a mandate-recovery cadence
- **THEN** the dialog SHALL state that no sequence is active for that transaction
- **AND** it SHALL NOT omit the section or leave it blank
