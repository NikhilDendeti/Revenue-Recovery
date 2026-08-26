"""The diagnosis/decision graph, behind a port.

`agents/pipeline.py` is already ORM-decoupled — `run_pipeline` takes a plain dict and
returns plain dicts — so this adapter is thin by design. It exists for two reasons that
have nothing to do with swapping implementations:

1. Importing `agents.pipeline` builds and compiles a LangGraph `StateGraph` at module
   scope. Keeping that behind one named module makes it obvious what drags LangGraph into
   a process, which matters because Daphne must not.
2. It gives use-case tests a seam. The alternative is `patch("recovery.tasks.run_pipeline")`,
   which is what the suite does today — coupling a test to a private import in another
   module.
"""

from ..interfaces.ports import DiagnosisPipelineInterface


class LangGraphPipeline(DiagnosisPipelineInterface):
    def run(self, transaction_fields):
        from agents.pipeline import run_pipeline

        return run_pipeline(transaction_fields)
