from __future__ import annotations

import ast
import sys
from pathlib import Path


def _check(path: Path) -> list[str]:
    errors: list[str] = []
    data = path.read_bytes()
    if b"\r" in data:
        errors.append("contains CR/CRLF; repository text policy is LF")
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"not UTF-8: {exc}"]
    try:
        ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        location = f":{exc.lineno}:{exc.offset}" if exc.lineno else ""
        errors.append(f"invalid Python syntax{location}: {exc.msg}")
    return errors


def main(argv: list[str] | None = None) -> int:
    paths = [Path(value) for value in (sys.argv[1:] if argv is None else argv)]
    failed = False
    for path in paths:
        for error in _check(path):
            failed = True
            print(f"{path}: {error}", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
