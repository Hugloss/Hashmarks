from __future__ import annotations

import argparse
import inspect

from hashmarks.codemap import CodeMap
from hashmarks.codemap.find_engine import FIND_DEFAULT_OPTIONS
from hashmarks.mcp_surface import HashmarksMcpSurface
from hashmarks.repository_cli import add_repository_cli


def test_find_default_limit_has_one_public_owner() -> None:
    defaults = FIND_DEFAULT_OPTIONS

    for owner in (
        CodeMap.find,
        CodeMap.find_packet,
        CodeMap._find_compose,
        HashmarksMcpSurface.find,
    ):
        parameters = inspect.signature(owner).parameters
        assert parameters["limit"].default == defaults.limit

    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    add_repository_cli(
        sub,
        add_common_arguments=lambda _parser, *, inherited=False: None,
    )
    args = parser.parse_args(["find", "widget"])
    assert args.limit == defaults.limit
