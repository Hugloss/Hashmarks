from __future__ import annotations

import argparse
import asyncio
import logging
import tempfile
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from hashmarks._command_output import log_command_output

logger = logging.getLogger(__name__)

_EXPECTED_TOOLS = [
    "repository_context",
    "find",
    "task_evidence",
    "change_impact",
    "correlate_evidence",
    "dependency_codemap",
    "repository_declarations",
    "post_change",
]


def _fixture(root: Path) -> Path:
    repo = root / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "feature.py").write_text(
        "def flare041(value: int) -> int:\n    return value + 1\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_feature.py").write_text(
        "from src.feature import flare041\n\n"
        "def test_flare041():\n    assert flare041(1) == 2\n",
        encoding="utf-8",
    )
    (repo / "runtime-a.txt").write_text("3.12\n", encoding="utf-8")
    (repo / "runtime-b.txt").write_text("3.12\n", encoding="utf-8")
    return repo


async def _exercise(executable: Path, repo: Path, state_dir: Path) -> None:
    params = StdioServerParameters(
        command=str(executable),
        args=[
            "--workspace",
            str(repo),
            "--state-dir",
            str(state_dir),
            "mcp",
        ],
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            initialized = await session.initialize()
            assert initialized.server_info.name == "Hashmarks"
            assert (await session.list_prompts()).prompts == []
            assert (await session.list_resources()).resources == []

            tools = await session.list_tools()
            assert [tool.name for tool in tools.tools] == _EXPECTED_TOOLS

            found = await session.call_tool(
                "find", arguments={"query": "flare041", "limit": 5}
            )
            assert found.is_error is not True
            assert found.structured_content is not None
            assert found.structured_content["schema"] == "hashmarks.mcp-find.v1"
            assert any(
                row["path"] == "src/feature.py"
                for row in found.structured_content["results"]
            )

            declarations = await session.call_tool(
                "repository_declarations",
                arguments={
                    "groups": [
                        {
                            "group_id": "runtime",
                            "concept": {"kind": "runtime", "identity": "python"},
                            "scope": {},
                            "correspondence": {
                                "state": "declared",
                                "basis": {"provider": "installed-smoke"},
                            },
                            "declarations": [
                                {
                                    "declaration_id": "a",
                                    "value_state": "resolved",
                                    "value": "3.12",
                                    "producer": {"kind": "fixture"},
                                    "evidence": [
                                        {
                                            "path": "runtime-a.txt",
                                            "start_line": 1,
                                            "end_line": 1,
                                        }
                                    ],
                                },
                                {
                                    "declaration_id": "b",
                                    "value_state": "resolved",
                                    "value": "3.12",
                                    "producer": {"kind": "fixture"},
                                    "evidence": [
                                        {
                                            "path": "runtime-b.txt",
                                            "start_line": 1,
                                            "end_line": 1,
                                        }
                                    ],
                                },
                            ],
                            "coverage": {
                                "state": "complete",
                                "truncation": "complete",
                                "expected_declaration_ids": ["a", "b"],
                                "scope": {},
                                "provenance": {"provider": "installed-smoke"},
                            },
                        }
                    ]
                },
            )
            assert declarations.is_error is not True
            assert declarations.structured_content is not None
            assert (
                declarations.structured_content["schema"]
                == "hashmarks.repository-declarations.v1"
            )
            assert (
                declarations.structured_content["groups"][0]["comparison"]["state"]
                == "equivalent"
            )

            invalid = await session.call_tool(
                "find", arguments={"query": "", "limit": 5}
            )
            assert invalid.is_error is True
            text = "\n".join(getattr(block, "text", "") for block in invalid.content)
            assert "query must not be empty" in text
            assert "Traceback" not in text


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Smoke the installed Hashmarks MCP console script through the official SDK."
    )
    parser.add_argument("--hashmarks", required=True)
    args = parser.parse_args(argv)
    executable = Path(args.hashmarks).absolute()
    if not executable.is_file():
        raise SystemExit(f"installed hashmarks console script not found: {executable}")
    with tempfile.TemporaryDirectory(prefix="hashmarks-mcp-installed-") as raw:
        root = Path(raw)
        asyncio.run(_exercise(executable, _fixture(root), root / "state"))
    log_command_output(logger, "Hashmarks installed MCP artifact smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
