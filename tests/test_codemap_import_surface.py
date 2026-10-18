"""Public export kinds must remain stable across ordinary module import order."""

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.parametrize("reverse", [False, True])
def test_public_exports_do_not_become_modules_after_submodule_imports(
    reverse: bool,
) -> None:
    modules = ["semantic_relationship_delta", "structural_locality_delta"]
    if reverse:
        modules.reverse()
    script = (
        "import importlib, types\n"
        f"for name in {modules!r}:\n"
        "    importlib.import_module('hashmarks.codemap.' + name)\n"
        "from hashmarks import codemap\n"
        "modules = [name for name in codemap.__all__ "
        "if isinstance(getattr(codemap, name), types.ModuleType)]\n"
        "assert modules == [], modules\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
