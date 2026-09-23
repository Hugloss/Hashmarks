from __future__ import annotations

import re
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

_INLINE_LINK_RE = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
_REFERENCE_LINK_RE = re.compile(r"^\s*\[[^\]]+\]:\s*(\S+)", re.MULTILINE)
_HTML_HREF_RE = re.compile(r"""href=["']([^"']+)["']""", re.IGNORECASE)
_SKIP_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff-venv",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
}


def _markdown_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.md")
        if not any(part in _SKIP_PARTS for part in path.relative_to(ROOT).parts)
    )


def _link_target(raw: str) -> str | None:
    target = raw.strip()
    if not target:
        return None
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]

    if target.startswith(("#", "//")):
        return None

    parsed = urlsplit(target)
    if parsed.scheme:
        return None

    path = unquote(parsed.path)
    return path or None


def _resolve_local_target(source: Path, target: str) -> Path:
    if target.startswith("/"):
        return ROOT / target.lstrip("/")
    return source.parent / target


def test_repository_local_markdown_links_resolve() -> None:
    missing: list[str] = []

    for source in _markdown_files():
        text = source.read_text(encoding="utf-8")
        raw_targets = [
            *(_INLINE_LINK_RE.findall(text)),
            *(_REFERENCE_LINK_RE.findall(text)),
            *(_HTML_HREF_RE.findall(text)),
        ]
        for raw in raw_targets:
            target = _link_target(raw)
            if target is None:
                continue
            resolved = _resolve_local_target(source, target)
            if not resolved.exists():
                missing.append(
                    f"{source.relative_to(ROOT).as_posix()}: {raw} -> "
                    f"{resolved.relative_to(ROOT).as_posix()}"
                )

    assert missing == [], "dangling repository-local Markdown links:\n" + "\n".join(
        missing
    )


def test_docs_readme_is_the_single_complete_docs_catalog() -> None:
    docs_root = (ROOT / "docs").resolve()
    index = docs_root / "README.md"

    nested_indexes = sorted(
        path.relative_to(ROOT).as_posix()
        for path in docs_root.rglob("README.md")
        if path != index
    )
    assert nested_indexes == []

    expected = sorted(
        path.relative_to(docs_root).as_posix()
        for path in docs_root.rglob("*.md")
        if path != index
    )

    text = index.read_text(encoding="utf-8")
    indexed: list[str] = []
    for raw in _INLINE_LINK_RE.findall(text):
        target = _link_target(raw)
        if target is None:
            continue
        resolved = _resolve_local_target(index, target).resolve()
        if resolved.suffix != ".md" or not resolved.is_relative_to(docs_root):
            continue
        indexed.append(resolved.relative_to(docs_root).as_posix())

    assert sorted(indexed) == expected
    assert len(indexed) == len(set(indexed))
