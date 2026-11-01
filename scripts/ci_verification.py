"""Select Hashmarks developer tests using existing CodeMap verification evidence.

This is CI/local-test tooling only. Hashmarks produces repository observations;
this consumer chooses cadence and leaves actual execution to native pytest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = "hashmarks.development-ci-selection.v1"
BASELINE = (
    "tests/test_qualification_classification.py",
    "tests/test_verification_nomination_validation.py",
    "tests/test_verification_selection_identity.py",
)
# A change to an authority or broadly shared toolchain cannot be covered by
# a bounded source-to-test nomination. Keep the entire real suite in the PR.
BROAD_PATHS = frozenset(
    {
        "Makefile",
        "pyproject.toml",
        "uv.lock",
        "hashmarks_build.py",
        ".pre-commit-config.yaml",
        "tests/conftest.py",
        "scripts/ci_verification.py",
        "hashmarks/qualification_classification.py",
        "hashmarks/qualification_units.py",
        "hashmarks/verification_selection.py",
        "hashmarks/_development/test_shards.py",
    }
)


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.stdout.strip()


def _git_bytes(root: Path, *args: str) -> bytes:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        capture_output=True,
        timeout=30,
    ).stdout


def _safe_path(path: str) -> bool:
    candidate = Path(path)
    return (
        bool(path)
        and not candidate.is_absolute()
        and ".." not in candidate.parts
        and "\n" not in path
        and "\r" not in path
        and "\0" not in path
    )


def _diff_paths(
    root: Path, base: str, head: str, *, worktree: bool
) -> tuple[tuple[str, ...], bool]:
    args = (base,) if worktree else (base, head)
    raw = _git_bytes(
        root, "diff", "--no-ext-diff", "--name-status", "-z", "--find-renames", *args
    )
    tokens = raw.decode("utf-8").split("\0")
    changed: set[str] = set()
    broad = False
    offset = 0
    while offset < len(tokens) and tokens[offset]:
        status = tokens[offset]
        count = 2 if status.startswith(("R", "C")) else 1
        paths = tokens[offset + 1 : offset + 1 + count]
        if len(paths) != count or any(not _safe_path(path) for path in paths):
            raise ValueError("incomplete or unsafe Git change inventory")
        changed.update(paths)
        # Deletes, renames, copies and other unusual changes need the full suite.
        broad |= not status.startswith(("M", "A"))
        offset += count + 1
    if worktree:
        untracked = _git_bytes(root, "ls-files", "--others", "--exclude-standard", "-z")
        for path in filter(None, untracked.decode("utf-8").split("\0")):
            if not _safe_path(path):
                raise ValueError("unsafe untracked path")
            changed.add(path)
    return tuple(sorted(changed)), broad


def _documentation(path: str) -> bool:
    return path in {"README.md", "CHANGELOG.md", "LICENSE", "AGENTS.md"} or (
        path.startswith("docs/") and path.endswith((".md", ".txt"))
    )


def _test_file(path: str) -> bool:
    return (
        path.startswith("tests/")
        and Path(path).name.startswith("test_")
        and path.endswith(".py")
        and _safe_path(path)
    )


def _source_file(path: str) -> bool:
    return path.endswith(".py") and path.startswith(("hashmarks/", "scripts/"))


def _qualified_links(graph: Mapping[str, Any], source: str) -> tuple[str, ...] | None:
    qualification = graph.get("verification_qualification")
    if not isinstance(qualification, dict) or graph.get("stale") is not False:
        return None
    if (
        qualification.get("completeness") != "complete"
        or qualification.get("truncation") != "complete"
        or qualification.get("negative_evidence_admissible") is not True
        or qualification.get("qualified_identity_ambiguous") is True
        or qualification.get("verifier_identity_ambiguous") is True
        or qualification.get("search_bound_reasons")
        or source not in graph.get("edit_candidates", [])
    ):
        return None
    rows = graph.get("verification_owners")
    if not isinstance(rows, list):
        return None
    linked = [
        row["path"]
        for row in rows
        if isinstance(row, dict)
        and source in row.get("covers_edit_candidates", [])
        and row.get("coverage_evidence") in {"direct-reference", "bounded-indirect-reference"}
        and isinstance(row.get("path"), str)
    ]
    if not linked or len(linked) != len(rows) or not all(_test_file(path) for path in linked):
        return None
    return tuple(sorted(set(linked)))


def _source_links(root: Path, sources: tuple[str, ...]) -> dict[str, tuple[str, ...]] | None:
    """Read canonical Hashmarks evidence; never infer negative links from a bound."""
    from hashmarks.codemap import CodeMap
    from hashmarks.verification_nomination_validation import validate_verification_nomination

    linked: dict[str, tuple[str, ...]] = {}
    with CodeMap(root) as codemap:
        codemap.index.sync()
        for source in sources:
            graph = codemap.tasks.verification_ownership_graph(
                f"Verify {source}", limit=16, candidate_limit=16
            )
            paths = _qualified_links(graph, source)
            if paths is None:
                return None
            for path in paths:
                nomination = codemap.verification.nomination(path)
                if (
                    not (root / path).is_file()
                    or validate_verification_nomination(nomination)["valid"] is not True
                    or nomination.get("available") is not True
                    or nomination.get("runner_evidence") != "pytest"
                ):
                    return None
            linked[source] = paths
    return linked


def _identity(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def select(
    root: Path,
    base: str,
    *,
    worktree: bool = False,
    links: Callable[[Path, tuple[str, ...]], dict[str, tuple[str, ...]] | None] = _source_links,
) -> dict[str, Any]:
    """Build a conservative plan; unknown coverage selects the complete suite."""
    root = root.resolve()
    base_sha = _git(root, "rev-parse", "--verify", f"{base}^{{commit}}")
    head = _git(root, "rev-parse", "--verify", "HEAD^{commit}")
    _git(root, "merge-base", "--is-ancestor", base_sha, head)
    if not worktree and _git(root, "status", "--porcelain", "--untracked-files=normal"):
        raise ValueError("hosted candidate checkout must be clean")
    changed, unusual = _diff_paths(root, base_sha, head, worktree=worktree)
    full_reasons = ["unusual-git-change"] if unusual else []
    if not changed:
        full_reasons.append("empty-change-set")
    tests: set[str] = set(BASELINE)
    sources: list[str] = []
    for path in changed:
        if path in BROAD_PATHS or path.startswith(".github/"):
            full_reasons.append(f"broad-authority:{path}")
        elif _documentation(path):
            continue
        elif _test_file(path):
            tests.add(path)
        elif _source_file(path) and (root / path).is_file():
            sources.append(path)
        else:
            full_reasons.append(f"unclassified:{path}")
    if sources and not full_reasons:
        try:
            nominations = links(root, tuple(sources))
        except (OSError, ValueError, RuntimeError, KeyError, TypeError) as exc:
            nominations = None
            full_reasons.append(f"relevance-unavailable:{type(exc).__name__}")
        if nominations is None or set(nominations) != set(sources):
            full_reasons.append("unproven-verification-membership")
        else:
            for paths in nominations.values():
                tests.update(paths)
    mode = "full" if full_reasons else "focused"
    payload: dict[str, Any] = {
        "schema": SCHEMA,
        "base_sha": base_sha,
        "candidate_sha": head,
        "dirty_worktree": worktree,
        "mode": mode,
        "changed_paths": list(changed),
        "pytest_paths": ["tests"] if mode == "full" else sorted(tests),
        "reasons": sorted(set(full_reasons)) if full_reasons else ["qualified-relevant-selection"],
        "authority": "development-ci-consumer; pytest remains the execution owner",
    }
    payload["plan_identity"] = _identity(payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="A Git commit ancestor of HEAD")
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worktree", action="store_true")
    args = parser.parse_args()
    plan = select(args.root, args.base, worktree=args.worktree)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        json.dumps({key: plan[key] for key in ("mode", "reasons", "pytest_paths")}),
        file=sys.stderr,
    )
    # NUL-delimited argument transport: never use shell interpolation for test selectors.
    for path in plan["pytest_paths"]:
        sys.stdout.buffer.write(path.encode("utf-8") + b"\0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
