"""Business rules that are pure functions of their inputs. No Django, no I/O, no clock,
no randomness — just arithmetic that can be asserted on directly.

Only one rule lives here so far, but it is the most consequential line in the money path
and until now it had no test that touched its boundaries, because the draw and the rule
were fused into a single expression with no seam between them.
"""

OUTCOME_FLOOR = 0.05
OUTCOME_CEILING = 0.95


def recovery_probability(confidence: float) -> float:
    """The clamped probability a recovery lands, given the diagnosis confidence."""
    return min(OUTCOME_CEILING, max(OUTCOME_FLOOR, confidence))


def resolve_outcome(confidence: float, draw: float) -> bool:
    """True when the recovery is resolved as successful.

    `draw` is a uniform [0, 1) sample supplied by the randomness port. This is exactly
    equivalent to the original `random.random() < min(0.95, max(0.05, confidence))` — the
    only change is that the sample arrives as an argument instead of being taken inline,
    which is what makes the clamp testable.
    """
    return draw < recovery_probability(confidence)
