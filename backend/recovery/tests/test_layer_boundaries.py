"""Architecture tests — the part of this refactor that has teeth.

A layering that is only a directory convention decays the first time someone is in a hurry.
These tests fail the build instead. They walk the AST rather than grepping strings, so
`import django.db` and `from django import db` are both caught and a mention inside a
docstring is not a false positive.
"""

import ast
import re
import subprocess
import sys
from pathlib import Path

import pytest

RECOVERY = Path(__file__).resolve().parent.parent
BACKEND = RECOVERY.parent

BANNED_TOP_LEVEL = {
    "django", "rest_framework", "celery", "channels", "requests",
    "random", "agents", "langgraph",
}

GUARDED_PATHS = [
    RECOVERY / "interactors",
    RECOVERY / "guardrails" / "rules.py",
    RECOVERY / "domain_rules.py",
]


def _python_files(target: Path):
    if not target.exists():
        return []
    if target.is_file():
        return [target]
    return sorted(p for p in target.rglob("*.py"))


def _imported_top_level_modules(path: Path):
    """Every top-level package this module imports, from the AST."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                found.add(node.module.split(".")[0])
    return found


@pytest.mark.parametrize("target", GUARDED_PATHS, ids=lambda p: p.name)
def test_pure_layers_import_nothing_impure(target):
    offenders = {}
    for path in _python_files(target):
        banned = _imported_top_level_modules(path) & BANNED_TOP_LEVEL
        if banned:
            offenders[str(path.relative_to(BACKEND))] = sorted(banned)
    assert offenders == {}, (
        f"forbidden imports in a pure layer: {offenders}. "
        "Business logic must receive these through an injected port — see "
        "recovery/interactors/__init__.py for THE RULE."
    )


AUDIT_MODEL_ALLOWED = {
    "recovery/tasks.py",
    "recovery/storages/recovery_storage.py",
}
AUDIT_MODEL_EXEMPT_PATHS = (
    "models.py", "migrations/", "admin.py", "serializers.py", "tests/", "views.py",
    "management/commands/",
)


def _repo_modules():
    for path in sorted(RECOVERY.rglob("*.py")):
        rel = path.relative_to(BACKEND).as_posix()
        if any(part in rel for part in AUDIT_MODEL_EXEMPT_PATHS):
            continue
        yield rel, path


def _references_name_in_code(path: Path, name: str) -> bool:
    """True only for a real code reference. Walking the AST means a mention in a
    docstring or a comment — which is how an interface documents *why* it has no
    mutation verb — is not a violation."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id == name:
            return True
        if isinstance(node, ast.Attribute) and node.attr == name:
            return True
        if isinstance(node, ast.ImportFrom):
            if any(a.name == name for a in node.names):
                return True
    return False


def test_only_the_storage_layer_reaches_the_audit_model():
    hits = {rel for rel, path in _repo_modules() if _references_name_in_code(path, "AuditLogEntry")}
    unexpected = hits - AUDIT_MODEL_ALLOWED
    assert unexpected == set(), (
        f"{unexpected} reference AuditLogEntry directly. The audit log is append-only; "
        "reach it through StorageInterface.append_audit so no update/delete verb exists."
    )


def test_no_queryset_level_update_against_the_audit_log():
    """`.objects.filter(...).update(...)` bypasses Model.save() entirely, so the
    PermissionError guard in AuditLogEntry.save() never runs and only the migration-0002
    database trigger would stand between a mistake and a rewritten audit row."""
    pattern = re.compile(r"AuditLogEntry\.objects[^\n]*\.update\(")
    offenders = [
        rel for rel, path in _repo_modules()
        if pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"queryset-level update against the audit log in {offenders}"


ASGI_MUST_NOT_LOAD = ("langgraph", "agents.pipeline")


def test_importing_the_asgi_app_does_not_pull_in_the_agent_graph():
    """`agents/pipeline.py` builds and compiles a LangGraph StateGraph at import time.
    If anything in the WebSocket import chain reaches `wiring`, that compile lands in
    Daphne's boot — seconds of startup for a process that never diagnoses anything.

    Runs in a subprocess because by the time this test executes, other test modules have
    already imported the agent pipeline into this interpreter's sys.modules.
    """
    script = (
        "import os, django, sys;"
        "os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings');"
        "import config.asgi;"
        "print(','.join(m for m in sys.modules if m in %r))" % (ASGI_MUST_NOT_LOAD,)
    )
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=BACKEND, capture_output=True, text=True,
    )
    assert result.returncode == 0, f"config.asgi failed to import:\n{result.stderr}"
    loaded = [m for m in result.stdout.strip().split(",") if m]
    assert loaded == [], (
        f"importing config.asgi loaded {loaded}. Do not import `wiring` at module scope "
        "from consumers.py / routing.py / ws.py — import it inside the function instead."
    )
