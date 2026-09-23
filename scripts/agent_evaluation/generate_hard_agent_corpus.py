from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

SCHEMA = "hashmarks.hard-agent-corpus.v1"
CATEGORIES = (
    "vocabulary-mismatch",
    "duplicate-symbol-decoy",
    "dead-code-decoy",
    "cross-layer-ownership",
    "configuration-ownership",
    "non-obvious-verification",
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def _validate_destinations(repo: Path, *external_paths: Path) -> None:
    for external in external_paths:
        try:
            external.relative_to(repo)
        except ValueError:
            continue
        raise ValueError(
            "PUBLIC and SECRET corpus files must live outside the worker repository"
        )


def _case(
    repo: Path, index: int, category: str
) -> tuple[dict[str, str], dict[str, object]]:
    case = {
        "task_id": f"hard-{index:03d}",
        "namespace": f"case_{index:03d}",
        "behavior": f"ember{index:03d}",
    }
    namespace = case["namespace"]
    behavior = case["behavior"]
    case.update(
        {
            "owner": f"src/{namespace}/engine.py",
            "route": f"src/{namespace}/route.py",
            "decoy": f"src/{namespace}/legacy.py",
            "config": f"src/{namespace}/policy.toml",
            "verify": f"tests/{namespace}/test_behavior.py",
            "query": f"Fix the {behavior} request so the active path preserves the accepted response contract",
            "engine_text": f"def apply_{namespace}(value: str) -> str:\n    # active implementation owner; intentionally avoids user-facing wording\n    return value + '-active'\n",
            "route_text": f"from .engine import apply_{namespace}\n\ndef handle_{behavior}(value: str) -> str:\n    # {behavior} request enters here, but behavior is delegated to the engine.\n    return apply_{namespace}(value)\n",
            "legacy_text": f"def handle_{behavior}(value: str) -> str:\n    # DEPRECATED {behavior} implementation retained as migration evidence only.\n    return value + '-legacy'\n",
            "test_text": f"from src.{namespace}.route import handle_{behavior}\n\ndef test_{behavior}_accepted_response_contract():\n    assert handle_{behavior}('x') == 'x-active'\n",
        }
    )
    case["expected_edit"] = case["owner"]
    case["expected_contract"] = case["route"]
    if category == "duplicate-symbol-decoy":
        case["legacy_text"] += (
            f"\ndef apply_{namespace}(value: str) -> str:\n"
            "    return value + '-duplicate'\n"
        )
    elif category == "dead-code-decoy":
        case["legacy_text"] = (
            f"# exact symptom wording: {case['query']}\n"
            + case["legacy_text"]
            + "\nENABLED = False  # dead compatibility surface\n"
        )
    elif category == "cross-layer-ownership":
        _write(
            repo / f"frontend/{namespace}/client.ts",
            f"export async function submit{index}(value: string) {{\n  // UI names {behavior}; backend owns transformation.\n  return fetch('/api/{behavior}?value=' + value);\n}}\n",
        )
        case["query"] = (
            f"The {behavior} frontend request returns the wrong accepted response; "
            "fix the behavior owner"
        )
    elif category == "configuration-ownership":
        _write(repo / case["config"], f"mode = 'active'\nfeature = '{behavior}'\n")
        case["engine_text"] = (
            "from pathlib import Path\n\n"
            f"def apply_{namespace}(value: str) -> str:\n"
            "    text = (Path(__file__).with_name('policy.toml')).read_text()\n"
            "    return value + ('-active' if \"mode = 'active'\" in text else '-legacy')\n"
        )
        case["expected_edit"] = case["config"]
        case["expected_contract"] = case["config"]
        case["query"] = (
            f"Change the {behavior} active-path policy so its accepted response mode "
            "is controlled correctly"
        )
    elif category == "non-obvious-verification":
        case["verify"] = f"checks/{namespace}/test_contract.py"
        case["test_text"] = (
            f"from src.{namespace}.route import handle_{behavior}\n\ndef test_{behavior}_contract():\n    assert handle_{behavior}('x').endswith('-active')\n"
        )
        case["query"] = (
            f"Repair the {behavior} behavior and identify its contract verification "
            "outside the default test tree"
        )
    elif category == "vocabulary-mismatch":
        case["query"] = (
            "Accepted responses are being transformed by the wrong active owner for "
            f"request family {behavior}"
        )

    for path_key, text_key in (
        ("owner", "engine_text"),
        ("route", "route_text"),
        ("decoy", "legacy_text"),
        ("verify", "test_text"),
    ):
        _write(repo / case[path_key], case[text_key])
    _write(repo / f"src/{namespace}/__init__.py", "")
    _write(repo / "src/__init__.py", "")
    return {"id": case["task_id"], "query": case["query"]}, {
        "id": case["task_id"],
        "category": category,
        "expected_edit_path": case["expected_edit"],
        "expected_verify_path": case["verify"],
        "expected_contract_path": case["expected_contract"],
        "expected_safe": True,
    }


def generate(
    repo: Path, public_path: Path, secret_path: Path, *, cases_per_category: int = 10
) -> dict[str, object]:
    if cases_per_category < 1:
        raise ValueError("cases_per_category must be >= 1")
    repo = repo.resolve()
    public_path = public_path.resolve()
    secret_path = secret_path.resolve()
    _validate_destinations(repo, public_path, secret_path)
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    _write(repo / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    _write(
        repo / "README.md",
        "# Generated archaeology challenge\nNo benchmark answer keys live in this repository.\n",
    )

    public: list[dict[str, str]] = []
    secret: list[dict[str, object]] = []
    index = 0
    for category in CATEGORIES:
        for _variant in range(cases_per_category):
            public_row, secret_row = _case(repo, index, category)
            public.append(public_row)
            secret.append(secret_row)
            index += 1

    public_payload = {"schema": SCHEMA, "tasks": public}
    secret_payload = {"schema": SCHEMA, "tasks": secret}
    public_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(
        json.dumps(public_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    secret_path.write_text(
        json.dumps(secret_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "schema": "hashmarks.hard-agent-corpus-manifest.v1",
        "tasks": len(public),
        "categories": list(CATEGORIES),
        "cases_per_category": cases_per_category,
        "public_identity": _digest(public_payload),
        "secret_identity": _digest(secret_payload),
        "answer_key_inside_worker_repo": False,
    }
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--public", type=Path, required=True)
    parser.add_argument("--secret", type=Path, required=True)
    parser.add_argument("--cases-per-category", type=int, default=10)
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args()
    manifest = generate(
        args.repo, args.public, args.secret, cases_per_category=args.cases_per_category
    )
    rendered = json.dumps(manifest, indent=2, sort_keys=True)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)  # noqa: T201 - intentional command output


if __name__ == "__main__":
    main()
