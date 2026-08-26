"""Use cases. Pure Python — no Django, no Celery, no channels, no requests, no random,
no agents, no langgraph. Everything from the outside world arrives injected.

THE RULE
--------
Apply the interactor stack only to a code path that changes the world: it writes a row,
calls an external system, branches on a business rule, or is reachable from more than one
transport. A path that only reads and serialises does not get an interactor — DRF's
ReadOnlyModelViewSet + serializer is already the right shape for it.

That is why `tasks.py` is layered (four transports reach it: the HTTP webhook, the Celery
worker, the Beat sweep, and `manage.py replay_batch --sync`) and the seven read-only
viewsets are not. If you are about to add a file here for something that only reads, stop:
it belongs in `views.py` with a serializer.

The banned-import list is enforced by `recovery/tests/test_layer_boundaries.py`, which
walks the AST rather than grepping strings. `agents` and `langgraph` are on that list on
purpose: it is what makes "guardrails are deterministic and never call an LLM" a checked
property instead of a promise.
"""
