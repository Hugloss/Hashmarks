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


def generate(repo: Path, public_path: Path, secret_path: Path, *, cases_per_category: int = 10) -> dict[str, object]:
    if cases_per_category < 1:
        raise ValueError("cases_per_category must be >= 1")
    repo = repo.resolve()
    public_path = public_path.resolve()
    secret_path = secret_path.resolve()
    for external in (public_path, secret_path):
        try:
            external.relative_to(repo)
        except ValueError:
            pass
        else:
            raise ValueError("PUBLIC and SECRET corpus files must live outside the worker repository")
    if repo.exists():
        shutil.rmtree(repo)
    repo.mkdir(parents=True)
    _write(repo / "pyproject.toml", "[tool.pytest.ini_options]\ntestpaths=['tests']\n")
    _write(repo / "README.md", "# Generated archaeology challenge\nNo benchmark answer keys live in this repository.\n")

    public: list[dict[str, str]] = []
    secret: list[dict[str, object]] = []
    index = 0
    for category in CATEGORIES:
        for variant in range(cases_per_category):
            task_id = f"hard-{index:03d}"
            ns = f"case_{index:03d}"
            behavior = f"ember{index:03d}"
            owner = f"src/{ns}/engine.py"
            route = f"src/{ns}/route.py"
            decoy = f"src/{ns}/legacy.py"
            config = f"src/{ns}/policy.toml"
            verify = f"tests/{ns}/test_behavior.py"
            query = f"Fix the {behavior} request so the active path preserves the accepted response contract"

            engine_text = (
                f"def apply_{ns}(value: str) -> str:\n"
                f"    # active implementation owner; intentionally avoids user-facing wording\n"
                f"    return value + '-active'\n"
            )
            route_text = (
                f"from .engine import apply_{ns}\n\n"
                f"def handle_{behavior}(value: str) -> str:\n"
                f"    # {behavior} request enters here, but behavior is delegated to the engine.\n"
                f"    return apply_{ns}(value)\n"
            )
            legacy_text = (
                f"def handle_{behavior}(value: str) -> str:\n"
                f"    # DEPRECATED {behavior} implementation retained as migration evidence only.\n"
                f"    return value + '-legacy'\n"
            )
            test_text = (
                f"from src.{ns}.route import handle_{behavior}\n\n"
                f"def test_{behavior}_accepted_response_contract():\n"
                f"    assert handle_{behavior}('x') == 'x-active'\n"
            )
            expected_edit = owner
            expected_contract = route

            if category == "duplicate-symbol-decoy":
                legacy_text += f"\ndef apply_{ns}(value: str) -> str:\n    return value + '-duplicate'\n"
            elif category == "dead-code-decoy":
                legacy_text = (
                    f"# exact symptom wording: {query}\n" + legacy_text +
                    "\nENABLED = False  # dead compatibility surface\n"
                )
            elif category == "cross-layer-ownership":
                _write(repo / f"frontend/{ns}/client.ts", (
                    f"export async function submit{index}(value: string) {{\n"
                    f"  // UI names {behavior}; backend owns transformation.\n"
                    f"  return fetch('/api/{behavior}?value=' + value);\n"
                    f"}}\n"
                ))
                query = f"The {behavior} frontend request returns the wrong accepted response; fix the behavior owner"
            elif category == "configuration-ownership":
                _write(repo / config, f"mode = 'active'\nfeature = '{behavior}'\n")
                engine_text = (
                    "from pathlib import Path\n\n"
                    f"def apply_{ns}(value: str) -> str:\n"
                    f"    text = (Path(__file__).with_name('policy.toml')).read_text()\n"
                    f"    return value + ('-active' if \"mode = 'active'\" in text else '-legacy')\n"
                )
                expected_edit = config
                expected_contract = config
                query = f"Change the {behavior} active-path policy so its accepted response mode is controlled correctly"
            elif category == "non-obvious-verification":
                alt = f"checks/{ns}/test_contract.py"
                verify = alt
                test_text = (
                    f"from src.{ns}.route import handle_{behavior}\n\n"
                    f"def test_{behavior}_contract():\n"
                    f"    assert handle_{behavior}('x').endswith('-active')\n"
                )
                query = f"Repair the {behavior} behavior and identify its contract verification outside the default test tree"
            elif category == "vocabulary-mismatch":
                query = f"Accepted responses are being transformed by the wrong active owner for request family {behavior}"

            _write(repo / owner, engine_text)
            _write(repo / route, route_text)
            _write(repo / decoy, legacy_text)
            _write(repo / verify, test_text)
            _write(repo / f"src/{ns}/__init__.py", "")
            _write(repo / "src/__init__.py", "")

            public.append({"id": task_id, "query": query})
            secret.append({
                "id": task_id,
                "category": category,
                "expected_edit_path": expected_edit,
                "expected_verify_path": verify,
                "expected_contract_path": expected_contract,
                "expected_safe": True,
            })
            index += 1

    public_payload = {"schema": SCHEMA, "tasks": public}
    secret_payload = {"schema": SCHEMA, "tasks": secret}
    public_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    public_path.write_text(json.dumps(public_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    secret_path.write_text(json.dumps(secret_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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
    manifest = generate(args.repo, args.public, args.secret, cases_per_category=args.cases_per_category)
    rendered = json.dumps(manifest, indent=2, sort_keys=True)
    if args.manifest:
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
