from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

try:
    from scripts._module_loader import import_sibling
except ModuleNotFoundError:  # direct script execution
    from _module_loader import import_sibling

collect_suite = import_sibling("metrics_agent_suite", __package__).collect_suite

SCHEMA = "hashmarks.fresh-multi-repo-metrics.v1"
FIXTURE_SCHEMA = "hashmarks.fresh-multi-repo-fixture.v1"
FIXTURE_FAMILY = "hashmarks-v0.10.34-fresh-corpus-a"

_REPOSITORIES: dict[str, dict[str, object]] = {
    "python-orders": {
        "files": {
            "AGENTS.md": "Python order service. Validate changes with tests.\n",
            "src/orders/__init__.py": "from .service import OrderService\n",
            "src/orders/service.py": "from .storage import OrderStore\n\nclass OrderService:\n    def __init__(self, store: OrderStore):\n        self.store = store\n\n    def submit_order(self, order_id: str) -> str:\n        return self.store.save_order(order_id)\n",
            "src/orders/storage.py": "class OrderStore:\n    def save_order(self, order_id: str) -> str:\n        return f'saved:{order_id}'\n",
            "src/orders/validation.py": "def validate_order_id(order_id: str) -> bool:\n    return bool(order_id and order_id.strip())\n",
            "tests/test_orders.py": "from orders.service import OrderService\nfrom orders.storage import OrderStore\n\ndef test_submit_order():\n    assert OrderService(OrderStore()).submit_order('A1') == 'saved:A1'\n",
            "pyproject.toml": "[project]\nname='fresh-orders'\nversion='0.1.0'\nrequires-python='>=3.11'\n",
        },
        "tasks": [
            {
                "id": "py-service",
                "query": "OrderService submit_order implementation",
                "expected_files": ["src/orders/service.py"],
                "expected_symbols": ["OrderService", "submit_order"],
            },
            {
                "id": "py-storage",
                "query": "OrderStore save_order persistence",
                "expected_files": ["src/orders/storage.py"],
                "expected_symbols": ["OrderStore", "save_order"],
            },
            {
                "id": "py-validation",
                "query": "validate_order_id validation",
                "expected_files": ["src/orders/validation.py"],
                "expected_symbols": ["validate_order_id"],
            },
            {
                "id": "py-test",
                "query": "test_submit_order order test",
                "expected_files": ["tests/test_orders.py"],
                "expected_symbols": ["test_submit_order"],
            },
            {
                "id": "py-config",
                "query": "fresh-orders project pyproject configuration",
                "expected_files": ["pyproject.toml"],
                "expected_symbols": [],
            },
            {
                "id": "py-authority",
                "query": "Python order service validate changes tests AGENTS",
                "expected_files": ["AGENTS.md"],
                "expected_symbols": [],
            },
        ],
    },
    "typescript-dashboard": {
        "files": {
            "AGENTS.md": "Dashboard UI. Keep API adapters separate from presentation components.\n",
            "src/api/metrics.ts": "export async function loadMetrics(): Promise<number[]> { return [1, 2, 3]; }\n",
            "src/components/MetricsPanel.tsx": "import { loadMetrics } from '../api/metrics';\nexport async function MetricsPanel() { const values = await loadMetrics(); return values.join(','); }\n",
            "src/state/selection.ts": "export function normalizeSelection(value: string): string { return value.trim().toLowerCase(); }\n",
            "tests/MetricsPanel.test.tsx": "import { MetricsPanel } from '../src/components/MetricsPanel';\nexport async function testMetricsPanel() { return MetricsPanel(); }\n",
            "package.json": '{"name":"fresh-dashboard","scripts":{"test":"vitest run"}}\n',
            "vite.config.ts": "export default { test: { environment: 'jsdom' } };\n",
        },
        "tasks": [
            {
                "id": "ts-api",
                "query": "loadMetrics API adapter",
                "expected_files": ["src/api/metrics.ts"],
                "expected_symbols": ["loadMetrics"],
            },
            {
                "id": "ts-panel",
                "query": "MetricsPanel component loadMetrics",
                "expected_files": ["src/components/MetricsPanel.tsx"],
                "expected_symbols": ["MetricsPanel"],
            },
            {
                "id": "ts-selection",
                "query": "normalizeSelection state selection",
                "expected_files": ["src/state/selection.ts"],
                "expected_symbols": ["normalizeSelection"],
            },
            {
                "id": "ts-test",
                "query": "testMetricsPanel MetricsPanel test",
                "expected_files": ["tests/MetricsPanel.test.tsx"],
                "expected_symbols": ["testMetricsPanel"],
            },
            {
                "id": "ts-package",
                "query": "fresh-dashboard vitest package scripts",
                "expected_files": ["package.json"],
                "expected_symbols": [],
            },
            {
                "id": "ts-vite",
                "query": "jsdom vite test environment",
                "expected_files": ["vite.config.ts"],
                "expected_symbols": [],
            },
        ],
    },
    "release-contracts": {
        "files": {
            "AGENTS.md": "Release automation repository. Contracts are immutable inputs to packaging.\n",
            "contracts/release.schema.json": '{"title":"ReleaseManifest","required":["artifact","sha256"]}\n',
            "scripts/package_release.py": "from pathlib import Path\n\ndef package_release(artifact: Path) -> str:\n    return artifact.name\n",
            "scripts/verify_checksum.py": "def verify_checksum(expected: str, observed: str) -> bool:\n    return expected == observed\n",
            "tests/test_release_contract.py": "from scripts.verify_checksum import verify_checksum\n\ndef test_release_checksum_contract():\n    assert verify_checksum('a', 'a')\n",
            "Makefile": "release:\n\tpython scripts/package_release.py\nverify:\n\tpython scripts/verify_checksum.py\n",
            "config/release.toml": "[release]\nrequire_checksum=true\nmanifest='contracts/release.schema.json'\n",
        },
        "tasks": [
            {
                "id": "rel-schema",
                "query": "ReleaseManifest artifact sha256 contract schema",
                "expected_files": ["contracts/release.schema.json"],
                "expected_symbols": [],
            },
            {
                "id": "rel-package",
                "query": "package_release artifact packaging",
                "expected_files": ["scripts/package_release.py"],
                "expected_symbols": ["package_release"],
            },
            {
                "id": "rel-checksum",
                "query": "verify_checksum expected observed",
                "expected_files": ["scripts/verify_checksum.py"],
                "expected_symbols": ["verify_checksum"],
            },
            {
                "id": "rel-test",
                "query": "test_release_checksum_contract checksum contract test",
                "expected_files": ["tests/test_release_contract.py"],
                "expected_symbols": ["test_release_checksum_contract"],
            },
            {
                "id": "rel-make",
                "query": "release verify Makefile targets",
                "expected_files": ["Makefile"],
                "expected_symbols": [],
            },
            {
                "id": "rel-config",
                "query": "require_checksum release manifest configuration",
                "expected_files": ["config/release.toml"],
                "expected_symbols": [],
            },
        ],
    },
}


def _sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def _tree_identity(root: Path) -> str:
    rows: list[tuple[str, str]] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if rel.parts and rel.parts[0] in {
            ".hashmarks",
            ".git",
            ".venv",
            "node_modules",
        }:
            continue
        rows.append((rel.as_posix(), _sha256_bytes(path.read_bytes())))
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return _sha256_bytes(payload)


def materialize_fixture(root: Path) -> list[tuple[str, Path, Path]]:
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    repos: list[tuple[str, Path, Path]] = []
    for name, spec in _REPOSITORIES.items():
        workspace = root / "repos" / name
        workspace.mkdir(parents=True)
        files = spec["files"]
        assert isinstance(files, dict)
        for rel, content in files.items():
            path = workspace / str(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(content), encoding="utf-8")
        corpus = root / "corpora" / f"{name}.json"
        corpus.parent.mkdir(parents=True, exist_ok=True)
        corpus.write_text(
            json.dumps(
                {"schema": "hashmarks.agent-task-corpus.v1", "tasks": spec["tasks"]},
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        repos.append((name, workspace, corpus))
    return repos


def collect_fresh(
    root: Path, *, budget: int = 1200, limit: int = 20
) -> dict[str, object]:
    repos = materialize_fixture(root)
    suite = collect_suite(repos, budget=budget, limit=limit)
    fixture_repos = []
    for name, workspace, corpus in repos:
        fixture_repos.append(
            {
                "name": name,
                "workspace_tree_identity": _tree_identity(workspace),
                "corpus_sha256": _sha256_bytes(corpus.read_bytes()),
                "tasks": len(json.loads(corpus.read_text(encoding="utf-8"))["tasks"]),
            }
        )
    fixture = {
        "schema": FIXTURE_SCHEMA,
        "family": FIXTURE_FAMILY,
        "repositories": fixture_repos,
    }
    fixture_identity = _sha256_bytes(
        json.dumps(fixture, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )
    return {
        "schema": SCHEMA,
        "fixture": fixture,
        "fixture_identity": fixture_identity,
        "suite": suite,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Materialize and run the canonical fresh multi-repository Hashmarks corpus"
    )
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--budget", type=int, default=1200)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--min-file-recall", type=float, default=1.0)
    parser.add_argument("--min-symbol-recall", type=float, default=1.0)
    parser.add_argument("--max-fallback-rate", type=float, default=0.0)
    args = parser.parse_args()
    payload = collect_fresh(args.root, budget=args.budget, limit=args.limit)
    rendered = json.dumps(payload, indent=2, sort_keys=True)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)  # noqa: T201 - intentional command output
    summary = payload["suite"]["summary"]  # type: ignore[index]
    if (
        float(summary["file_recall"]) < args.min_file_recall
        or float(summary["symbol_recall"]) < args.min_symbol_recall
        or float(summary["fallback_search_rate"]) > args.max_fallback_rate
    ):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
