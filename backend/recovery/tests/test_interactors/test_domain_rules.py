"""The outcome rule, tested at its boundaries.

None of these assertions were writable before: the draw and the clamp were fused into one
`random.random() < min(0.95, max(0.05, c))` expression inside a Celery task, so the only
thing a test could say about the most important line in the money path was "the status
ends up recovered or failed".
"""

import pytest

from ...domain_rules import OUTCOME_CEILING, OUTCOME_FLOOR, recovery_probability, resolve_outcome


@pytest.mark.parametrize("confidence,expected", [
    (0.0, OUTCOME_FLOOR),      # a hopeless diagnosis still gets the floor
    (0.03, OUTCOME_FLOOR),
    (0.05, OUTCOME_FLOOR),
    (0.42, 0.42),              # inside the band, passed straight through
    (0.82, 0.82),
    (0.95, OUTCOME_CEILING),
    (1.0, OUTCOME_CEILING),    # a certain diagnosis is still not a certain payment
])
def test_the_clamp_bounds_the_probability(confidence, expected):
    assert recovery_probability(confidence) == pytest.approx(expected)


def test_a_hopeless_diagnosis_can_still_recover():
    """The floor is the point: confidence 0 does not mean "never try"."""
    assert resolve_outcome(0.0, 0.049) is True
    assert resolve_outcome(0.0, 0.051) is False


def test_a_certain_diagnosis_can_still_fail():
    """The ceiling is the other half: nothing forces the customer to actually pay."""
    assert resolve_outcome(1.0, 0.949) is True
    assert resolve_outcome(1.0, 0.951) is False


def test_the_boundary_is_strictly_less_than():
    """A draw exactly equal to the probability fails, matching the original `<`."""
    assert resolve_outcome(0.7, 0.7) is False
    assert resolve_outcome(0.7, 0.6999) is True


def test_it_is_equivalent_to_the_expression_it_replaced():
    """Belt and braces: the refactor must not have moved the behaviour by an epsilon."""
    for confidence in (0.0, 0.35, 0.55, 0.6, 0.78, 0.82, 0.9, 1.0):
        for draw in (0.0, 0.049, 0.05, 0.3, 0.5, 0.82, 0.949, 0.95, 0.999):
            original = draw < min(0.95, max(0.05, confidence))
            assert resolve_outcome(confidence, draw) is original
