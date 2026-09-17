from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from types import ModuleType


def _ensure_repository_root_importable() -> None:
    root = str(Path(__file__).resolve().parent.parent)
    if root not in sys.path:
        sys.path.insert(0, root)


def import_sibling(name: str, package: str | None = None) -> ModuleType:
    """Import one sibling through normal module ownership, never file re-execution."""
    if package:
        return importlib.import_module(f"{package}.{name}")
    _ensure_repository_root_importable()
    return importlib.import_module(f"scripts.{name}")
