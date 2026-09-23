from __future__ import annotations

import argparse
import hashlib
import json
import logging
import shutil
from pathlib import Path

from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

CATEGORIES = (
    "vocabulary-mismatch",
    "duplicate-symbol-decoy",
    "dead-code-decoy",
    "cross-layer-ownership",
    "configuration-ownership",
    "non-obvious-verification",
)
SCHEMA = "hashmarks.full-edit-agent-corpus.v1"


def _w(p: Path, t: str):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(t, encoding="utf-8")


def _digest(x):
    return (
        "sha256:"
        + hashlib.sha256(
            json.dumps(x, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def _validate_destinations(root: Path, *paths: Path) -> None:
    for path in paths:
        try:
            path.relative_to(root)
        except ValueError:
            continue
        raise ValueError("PUBLIC and SECRET must live outside worker roots")


def _case(root: Path, index: int, category: str) -> tuple[dict, dict]:
    case = {
        "task_id": f"edit-{index:03d}",
        "namespace": f"case_{index:03d}",
        "behavior": f"flare{index:03d}",
    }
    namespace = case["namespace"]
    behavior = case["behavior"]
    case.update(
        {
            "repo": root / case["task_id"],
            "owner": f"src/{namespace}/engine.py",
            "route": f"src/{namespace}/route.py",
            "legacy": f"src/{namespace}/legacy.py",
            "config": f"src/{namespace}/policy.toml",
            "verify": f"tests/{namespace}/test_behavior.py",
            "engine": f"def apply_{namespace}(value: str) -> str:\n    return value + '-old'\n",
            "route_text": f"from .engine import apply_{namespace}\n\ndef handle_{behavior}(value: str) -> str:\n    return apply_{namespace}(value)\n",
            "legacy_text": f"def handle_{behavior}(value: str) -> str:\n    return value + '-old'\n",
            "query": f"Fix the {behavior} accepted response so the active behavior returns the new contract value '-new'",
        }
    )
    case["expected_edit"] = case["owner"]
    _w(
        case["repo"] / "pyproject.toml",
        "[tool.pytest.ini_options]\ntestpaths=['tests']\n",
    )
    _w(case["repo"] / "src/__init__.py", "")
    _w(case["repo"] / f"src/{namespace}/__init__.py", "")
    if category == "duplicate-symbol-decoy":
        case["legacy_text"] += (
            f"\ndef apply_{namespace}(value: str) -> str:\n    return value + '-old'\n"
        )
    elif category == "dead-code-decoy":
        case["legacy_text"] = (
            f"# exact issue text: {case['query']}\n"
            + case["legacy_text"]
            + "\nENABLED=False\n"
        )
    elif category == "cross-layer-ownership":
        _w(
            case["repo"] / f"frontend/{namespace}/client.ts",
            f"export const {behavior}=(v:string)=>fetch('/api/{behavior}?v='+v);\n",
        )
        case["query"] = (
            f"The {behavior} frontend request still returns '-old'; fix the active "
            "behavior owner so it returns '-new'"
        )
    elif category == "configuration-ownership":
        _w(case["repo"] / case["config"], "mode = 'old'\n")
        case["engine"] = (
            "from pathlib import Path\n\n"
            + f"def apply_{namespace}(value: str) -> str:\n    mode='old' if \"mode = 'old'\" in Path(__file__).with_name('policy.toml').read_text() else 'new'\n    return value + '-' + mode\n"
        )
        case["expected_edit"] = case["config"]
        case["query"] = (
            f"Change the {behavior} active-path policy from old to new so the accepted response ends '-new'"
        )
    elif category == "non-obvious-verification":
        case["verify"] = f"checks/{namespace}/test_contract.py"
        case["query"] = (
            f"Repair {behavior} so its contract outside the default test tree accepts '-new'"
        )
    elif category == "vocabulary-mismatch":
        case["query"] = (
            f"Accepted responses for request family {behavior} must now use contract value '-new' instead of '-old'"
        )
    test_text = f"from src.{namespace}.route import handle_{behavior}\n\ndef test_{behavior}_contract():\n    assert handle_{behavior}('x') == 'x-new'\n"
    for path_key, text in (
        ("owner", case["engine"]),
        ("route", case["route_text"]),
        ("legacy", case["legacy_text"]),
        ("verify", test_text),
    ):
        _w(case["repo"] / case[path_key], text)
    return {
        "id": case["task_id"],
        "query": case["query"],
        "repo": case["task_id"],
    }, {
        "id": case["task_id"],
        "category": category,
        "expected_edit_path": case["expected_edit"],
        "expected_verify_path": case["verify"],
        "expected_old": "old",
        "expected_new": "new",
    }


def generate(
    root: Path, public_path: Path, secret_path: Path, *, cases_per_category: int = 10
):
    root = root.resolve()
    public_path = public_path.resolve()
    secret_path = secret_path.resolve()
    _validate_destinations(root, public_path, secret_path)
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    public = []
    secret = []
    idx = 0
    for cat in CATEGORIES:
        for _variant in range(cases_per_category):
            public_row, secret_row = _case(root, idx, cat)
            public.append(public_row)
            secret.append(secret_row)
            idx += 1
    pub = {"schema": SCHEMA, "tasks": public}
    sec = {"schema": SCHEMA, "tasks": secret}
    public_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(json.dumps(pub, indent=2, sort_keys=True) + "\n")
    secret_path.write_text(json.dumps(sec, indent=2, sort_keys=True) + "\n")
    return {
        "schema": "hashmarks.full-edit-agent-corpus-manifest.v1",
        "tasks": len(public),
        "categories": list(CATEGORIES),
        "public_identity": _digest(pub),
        "secret_identity": _digest(sec),
        "secret_outside_worker_roots": True,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--public", type=Path, required=True)
    ap.add_argument("--secret", type=Path, required=True)
    ap.add_argument("--cases-per-category", type=int, default=10)
    ap.add_argument("--manifest", type=Path)
    a = ap.parse_args()
    m = generate(a.root, a.public, a.secret, cases_per_category=a.cases_per_category)
    if a.manifest:
        a.manifest.write_text(json.dumps(m, indent=2, sort_keys=True) + "\n")
    log_command_output(logger, json.dumps(m, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
