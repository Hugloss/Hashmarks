"""Observe authored Python/uv declarations beside supplied, separately bound lock evidence."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast

from hashmarks.adapters import uv_lock_dependency_observation
from hashmarks.codemap import CodeMap, PythonUvManifestDeclarations

_LOCK = b"""version = 1
revision = 3
[[package]]
name = "demo-app"
version = "0.1.0"
source = {virtual = "."}
dependencies = [{name = "shared-lib"}]
[[package]]
name = "shared-lib"
version = "2.0.0"
source = {registry = "https://example.invalid/simple"}
"""


def _repository_inputs(declarations: dict[str, object]) -> list[dict[str, object]]:
    providers = cast("list[dict[str, object]]", declarations["providers"])
    inputs = cast("list[dict[str, object]]", providers[0]["inputs"])
    return [
        {"path": row["path"], "member_revision": row["member_revision"]}
        for row in inputs
        if row["state"] == "known-present"
    ]


def run_example(workspace: Path) -> dict[str, object]:
    """Keep authored requirements, selected versions and source change distinct."""
    member = workspace / "packages" / "demo" / "pyproject.toml"
    member.parent.mkdir(parents=True, exist_ok=True)
    (workspace / "pyproject.toml").write_text(
        '[project]\nname="demo-app"\nversion="0.1.0"\n'
        'dependencies=["shared-lib>=1"]\n'
        '[tool.uv.workspace]\nmembers=["packages/*"]\n',
        encoding="utf-8",
    )
    member_source = (
        '[project]\nname="demo-tool"\nversion="0.1.0"\n'
        'dependencies=["shared-lib<3"]\n'
        '[project.scripts]\ndemo="demo_package.cli:main"\n'
    )
    member.write_text(member_source, encoding="utf-8")
    (workspace / "uv.lock").write_bytes(_LOCK)
    provider = PythonUvManifestDeclarations(
        paths=("pyproject.toml", "packages/demo/pyproject.toml")
    )
    with CodeMap(workspace) as repository:
        repository.index.sync()
        before = repository.declarations.discover([provider])
        lock_member, lock_bytes = repository.source.member(
            "uv.lock", include_bytes=True
        )
        if lock_member["state"] != "known-present" or lock_bytes is None:
            raise ValueError("the selected lock bytes are unavailable")
        inputs = _repository_inputs(before)
        inputs.append(
            {"path": "uv.lock", "member_revision": lock_member["member_revision"]}
        )
        # These nominated inputs establish source correspondence, not that uv ran
        # against them or that a requirement is satisfied by the supplied lock.
        dependency_claims = uv_lock_dependency_observation(
            lock=lock_bytes, repository_inputs=inputs
        )
        dependencies = repository.dependencies.observe(dependency_claims)
        member.write_text(
            member_source.replace("cli:main", "cli:inspect"), encoding="utf-8"
        )
        repository.index.sync(["packages/demo/pyproject.toml"])
        after = repository.declarations.discover(
            [provider], previous_observation=before
        )
        changed_binding = repository.dependencies.observe(dependency_claims)
    return {
        "before": before,
        "after": after,
        "dependencies": dependencies,
        "dependencies_with_previous_inputs": changed_binding,
    }


def main() -> None:
    with TemporaryDirectory(prefix="hashmarks-manifest-example-") as directory:
        result = run_example(Path(directory))
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
