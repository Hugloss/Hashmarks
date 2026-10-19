"""Observe selected input identity and inventory with an installed Hashmarks build."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from tempfile import TemporaryDirectory

from hashmarks import RepositoryIdentity

logger = logging.getLogger(__name__)


def _demo() -> dict[str, object]:
    with TemporaryDirectory(prefix="hashmarks-input-example-") as temporary:
        workspace = Path(temporary) / "repository"
        workspace.mkdir()
        selected = workspace / "sample.txt"
        selected.write_bytes(b"before\n")
        with RepositoryIdentity(
            workspace, mode="local", state_dir=Path(temporary) / "state"
        ) as identity:
            before = identity.observe_inputs("sample.txt", verify=True)
            selected.write_bytes(b"after\n")
            after = identity.observe_inputs("sample.txt", verify=True)
            empty = identity.observe_inputs("missing/*.txt", require_matches=False)
        return {
            "before": before.as_dict(),
            "after": after.as_dict(),
            "change": after.snapshot.diff(before.snapshot).as_dict(),
            "empty_selected_scope": empty.as_dict(),
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "workspace", nargs="?", help="Live workspace; omit for a neutral change demo"
    )
    parser.add_argument("inputs", nargs="*", help="Workspace-relative paths or globs")
    parser.add_argument("--exclude", action="append", default=[], help="Excluded scope")
    parser.add_argument("--state-dir", help="Optional Hashmarks state directory")
    parser.add_argument(
        "--verify", action="store_true", help="Force native file hashing"
    )
    args = parser.parse_args()
    if args.workspace is None:
        if args.exclude or args.state_dir or args.verify:
            parser.error("observation options require a workspace and selected inputs")
        result = _demo()
    else:
        if not args.inputs:
            parser.error("a workspace requires at least one selected input")
        with RepositoryIdentity(
            args.workspace, mode="local", state_dir=args.state_dir
        ) as identity:
            result = identity.observe_inputs(
                *args.inputs, exclude=args.exclude, verify=args.verify
            ).as_dict()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logger.info("%s", json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
