"""One bounded source-syntax interpretation of an authored Go module directive.

This is not Go module graph resolution, workspace membership, package loading,
native tool availability, or a proof that every go.mod directive is valid.
The caller's source observer owns byte provenance and revision.
"""

from __future__ import annotations

import re

_MODULE = re.compile(
    r'module[ \t]+(?:"([^"\s]+)"|\x60([^\x60\s]+)\x60|([^\s"\x60]+))'
    r'(?:[ \t]+//.*)?\Z'
)


def declared_go_module(source: bytes) -> str | None:
    """Accept exactly one unambiguous, bounded source-level module declaration."""
    try:
        text = source.decode("utf-8")
    except UnicodeError:
        return None
    if "\x00" in text:
        return None
    modules: list[str] = []
    for line in text.splitlines():
        content = line.strip()
        if not content or content.startswith("//"):
            continue
        if not re.match(r"module(?:[ \t]|$)", content):
            continue
        matched = _MODULE.fullmatch(content)
        if matched is None:
            return None
        name = next(group for group in matched.groups() if group is not None)
        if not name or name.startswith("/") or name.endswith("/") or "//" in name:
            return None
        modules.append(name)
        if len(modules) > 1:
            return None
    return modules[0] if len(modules) == 1 else None
