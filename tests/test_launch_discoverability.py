from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_readme_launch_surface_is_descriptive_before_internal_detail() -> None:
    readme = _text("README.md")
    assert readme.startswith(
        "# Hashmarks — Repository intelligence and a local MCP server for coding agents\n"
    )
    above_fold = readme[:2200].lower()
    for phrase in (
        "repository intelligence",
        "coding agents",
        "model context protocol (mcp) server",
        "codebase search for agents",
        "change impact analysis",
        "raw.githubusercontent.com/hugloss/hashmarks/main/install.sh",
    ):
        assert phrase in above_fold
    assert readme.index("## Quick start") < readme.index("## Core architecture")
    assert readme.index("## MCP server for coding agents") < readme.index(
        "## Core architecture"
    )


def test_readme_names_supported_agent_hosts_without_comparison_marketing() -> None:
    readme = _text("README.md")
    for host in ("Claude Code", "Codex", "OpenCode", "Pi"):
        assert f"### {host} MCP server" in readme
    lowered = readme.lower()
    for forbidden in ("enola", "better than", "beats ", "versus enola", "vs. enola"):
        assert forbidden not in lowered


def test_package_metadata_carries_high_intent_discovery_terms() -> None:
    metadata = tomllib.loads(_text("pyproject.toml"))["project"]
    description = metadata["description"].lower()
    for phrase in (
        "repository intelligence",
        "mcp server",
        "coding agents",
        "codebase search",
    ):
        assert phrase in description

    keywords = set(metadata["keywords"])
    expected = {
        "repository-intelligence",
        "mcp",
        "mcp-server",
        "model-context-protocol",
        "coding-agents",
        "codebase-search",
        "code-navigation",
        "change-impact",
        "impact-analysis",
        "dependency-analysis",
        "repository-context",
        "codebase-context",
    }
    assert expected <= keywords


def test_search_facing_document_titles_are_specific() -> None:
    assert _text("docs/GETTING_STARTED.md").startswith(
        "# Getting started with Hashmarks repository intelligence\n"
    )
    assert _text("docs/integration/MCP.md").startswith(
        "# Hashmarks MCP server for coding agents\n"
    )
    assert _text("docs/README.md").startswith(
        "# Hashmarks repository intelligence documentation\n"
    )


def test_readme_has_search_facing_workflows_without_keyword_stuffing() -> None:
    readme = _text("README.md")
    for heading in (
        "### Codebase search for coding agents",
        "### Repository context for a large codebase",
        "### Change impact analysis before editing",
        "### Fresh repository evidence after changes",
    ):
        assert heading in readme
    assert readme.count("repository intelligence") < 25
    assert readme.count("MCP server") < 20


def test_readme_answers_high_intent_search_questions() -> None:
    readme = _text("README.md")
    for heading in (
        "### Is Hashmarks an MCP server?",
        "### Does Hashmarks work with Claude Code, Codex, OpenCode, and Pi?",
        "### Does Hashmarks send my source code to a cloud service?",
        "### What is the difference between repository intelligence and ordinary code search?",
    ):
        assert heading in readme
    for phrase in (
        "repository context",
        "AI coding agents",
        "local read-only stdio MCP server",
    ):
        assert phrase in readme
