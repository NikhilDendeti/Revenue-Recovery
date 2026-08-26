"""The composition root — the one place that knows which adapter satisfies which port.

Every transport (a Celery task, a view, a management command) asks here for a fully-built
use case rather than constructing dependencies itself. That is what keeps the injection
honest: if a transport could reach an adapter directly, the ports would be decoration.

The trade-off is real and worth stating: after this exists, "who calls
ExecuteActionInteractor?" has one answer everywhere — this file — so jump-to-caller stops
being useful across those seams. A composition root has to live somewhere, and the
alternative (each transport wiring its own graph) duplicates the graph and lets the two
copies drift.

Nothing here may be imported at module scope from `consumers.py`, `routing.py` or `ws.py`:
this module reaches `adapters.langgraph_pipeline`, which imports `agents.pipeline`, which
compiles a LangGraph StateGraph at import time. That belongs in the Celery worker, not in
Daphne's boot. `test_layer_boundaries.py` asserts it stays out.
"""

from .adapters.langgraph_pipeline import LangGraphPipeline
from .adapters.razorpay_gateway import RazorpayGateway
from .adapters.runtime import DjangoClock, SystemRandomness
from .adapters.task_queues import CeleryTaskQueue


def build_gateway():
    return RazorpayGateway()


def build_pipeline():
    return LangGraphPipeline()


def build_clock():
    return DjangoClock()


def build_randomness():
    return SystemRandomness()


def build_task_queue():
    return CeleryTaskQueue()
