from pathlib import Path

import hashmarks_build

ROOT = Path(__file__).resolve().parents[1]


def _text(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_agents_file_declares_repository_intelligence_boundary() -> None:
    text = _text("AGENTS.md")
    assert (
        "Hashmarks is not an agentic orchestrator and must not become another ChatGPT/Codex/OpenCode clone."
        in text
    )
    assert "Hashmarks owns **repository intelligence**" in text
    assert (
        "External coding agents and their harnesses own the **solution loop**" in text
    )


def test_product_profile_explicitly_rejects_agent_and_execution_motor_drift() -> None:
    agents = _text("AGENTS.md")
    boundary = _text("docs/reference/PRODUCT_BOUNDARY.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    assert (
        "Hashmarks must never be turned into either the coding agent's solution loop or Oh-Goon's execution/certification motor."
        in agents
    )
    assert "## Two permanent non-goals" in boundary
    assert "Not the agent." in boundary
    assert "Not the execution/certification motor." in boundary
    assert "Interoperability transfers evidence, never authority." in boundary
    assert (
        "PB6. Hashmarks must never become the agent or the execution motor."
        in invariants
    )
    assert "PB7. Interoperability transfers evidence, never authority." in invariants


def test_external_library_findings_do_not_expand_repository_analysis_scope() -> None:
    boundary = _text("docs/reference/PRODUCT_BOUNDARY.md")
    agents = _text("AGENTS.md")
    contributing = _text(".github/CONTRIBUTING.md")
    architecture = _text("docs/reference/ARCHITECTURE.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    for text in (boundary, agents, contributing):
        assert "Do not chase remaining findings in external libraries." in text

    assert (
        "An import is an evidence edge, not permission to recursively investigate the imported library."
        in boundary
    )
    assert "not active roadmap items" in agents
    assert "external dependency edge" in architecture
    assert (
        "PB8. Repository ownership does not transit through dependencies." in invariants
    )
    assert (
        "PB9. External-library characterization is qualification evidence, not backlog."
        in invariants
    )
    assert "Package-name suppression tables" in invariants


def test_evidence_authority_precedence_is_explicit_and_non_strengthening() -> None:
    boundary = _text("docs/reference/PRODUCT_BOUNDARY.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    architecture = _text("docs/reference/ARCHITECTURE.md")
    agents = _text("AGENTS.md")
    contributing = _text(".github/CONTRIBUTING.md")

    assert "Evidence authority precedence and non-strengthening" in boundary
    assert "may not silently strengthen, repair, override, or redefine" in boundary
    assert "not permission to invent a new global precedence engine" in boundary
    assert (
        "PB10. Derived evidence may never silently strengthen its authority source."
        in invariants
    )
    assert (
        "Authority precedence is non-strengthening, not a global score" in architecture
    )
    assert (
        "consumer/model interpretation stays outside repository authority"
        in architecture
    )
    assert "Evidence authority is non-strengthening" in agents
    assert "There is no universal confidence score" in contributing


def test_evidence_correlation_preserves_repository_truth_and_consumer_authority() -> (
    None
):
    boundary = _text("docs/reference/PRODUCT_BOUNDARY.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    contract = _text("docs/reference/EVIDENCE_CORRELATION.md")

    rule = (
        "Hashmarks establishes repository truth and correlates evidence to it. "
        "The consuming agent decides what the evidence means and what action to take."
    )
    assert rule in boundary
    assert rule in contract
    assert (
        "G68. Evidence correlation preserves claims without acquiring interpretation authority."
        in invariants
    )
    assert (
        "PB11. External observations are correlation inputs, not repository authority."
        in invariants
    )
    assert "Correlation never becomes causation" in contract
    assert "It must not infer causation" in boundary
    assert "Interpretation and action remain consumer-owned." in contract


def test_agent_boundary_keeps_solution_authority_external() -> None:
    text = _text("AGENTS.md")
    for authority in (
        "solution reasoning or autonomous planning",
        "editing source code or deciding the patch",
        "verification execution on behalf of the coding agent",
        "recovery strategy after a failed attempt",
        "task scheduling or multi-agent orchestration",
        "worktree/git lifecycle or final solution behavior",
    ):
        assert authority in text


def test_architecture_invariant_and_readme_repeat_boundary() -> None:
    invariants = _text("docs/reference/INVARIANTS.md")
    readme = _text("README.md")
    assert (
        "G25. Hashmarks is repository intelligence, not the coding-agent solution loop."
        in invariants
    )
    assert (
        "Agent-facing features that would transfer those authorities into Hashmarks are architecture regressions."
        in invariants
    )
    assert "Non-negotiable agent boundary" in readme
    assert (
        "`AGENTS.md` is the contributor/agent-facing guardrail for this boundary."
        in readme
    )
    assert (
        "G29. Post-change evidence delta is incremental invalidation, not autonomous recovery."
        in invariants
    )
    assert (
        "compact post-change evidence deltas over caller-reported changed paths"
        in _text("AGENTS.md")
    )
    assert (
        "G33. Declared cross-repository impact is provenance-bearing evidence, never coordination."
        in invariants
    )
    assert (
        "G34. Dynamic Python module loading is repository ownership evidence, not runtime authority."
        in invariants
    )
    assert "Hashmarks must not rewrite imports" in _text("AGENTS.md")
    integration = _text("docs/integration/OH_GOON_INTEGRATION.md")
    assert "Interoperability transfers evidence, never authority." in integration
    assert "Hashmarks must never become Oh-Goon's execution motor." in integration


def test_repository_carries_agent_boundary_instructions_without_shipping_them_in_sdist() -> (
    None
):
    assert (hashmarks_build.ROOT / "AGENTS.md").is_file()
    members = hashmarks_build._sdist_members()
    assert Path("AGENTS.md") not in members
    assert Path("uv.lock") not in members


def test_agents_file_freezes_hashmarks_oh_goon_execution_boundary() -> None:
    text = _text("AGENTS.md")
    assert (
        "Hashmarks defines immutable repository evidence and selection authority; Oh-Goon owns execution and certification authority."
        in text
    )
    for hashmarks_contract in (
        "hashmarks.repository-work-selection.v1",
        "hashmarks.test-shards.v3",
        "hashmarks.test-shard-membership.v1",
        "pure membership-conservation checks",
        "compact decision-authority receipts",
    ):
        assert hashmarks_contract in text
    for execution_authority in (
        "durable execution-progress ledgers",
        "deciding which chunk/shard runs next",
        "process launch, process-tree supervision",
        "retry policy, timeout-driven splitting/bisection",
        "runtime `HOME`/cache/temp/socket-path isolation",
        "classification of product failure versus controller interruption versus environment failure",
        "membership-closure certification",
    ):
        assert execution_authority in text
    assert "must never choose the refinement" in text
    assert "completed/running/remaining progress" in text


def test_exact_repository_intelligence_execution_constitution_is_frozen() -> None:
    constitution = (
        "Hashmarks is a repository observer that exposes repository intelligence, "
        "not an autonomous coding agent, policy engine, or execution engine."
    )
    assert constitution in _text("README.md")
    assert constitution in _text("docs/reference/INVARIANTS.md")


def test_modern_repository_contracts_do_not_import_consumer_runtime() -> None:
    """Hashmarks evidence contracts stay consumable without Oh-Goon/runtime packages."""
    import ast

    modern_paths = [
        ROOT / "hashmarks" / "consumer_conformance.py",
        ROOT / "hashmarks" / "repository_cli.py",
        *sorted((ROOT / "hashmarks" / "codemap").rglob("*.py")),
    ]
    forbidden_roots = {"oh_goon", "ohgoon", "goon"}
    violations: list[str] = []
    for path in modern_paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                names = [node.module or ""]
            else:
                continue
            for name in names:
                if name.split(".", 1)[0] in forbidden_roots:
                    violations.append(f"{path.relative_to(ROOT)}: {name}")
    assert violations == []


def test_agent_evaluation_compatibility_manifest_is_removed() -> None:
    assert not (ROOT / "hashmarks" / "contract_surface.py").exists()
    assert not (ROOT / "scripts" / "agent_evaluation" / "contract_surface.py").exists()



def test_repository_root_markdown_is_limited_to_entry_points() -> None:
    allowed = {"AGENTS.md", "README.md", "CHANGELOG.md"}
    root_markdown = {path.name for path in ROOT.glob("*.md")}
    assert root_markdown == allowed
    assert (ROOT / "docs" / "README.md").is_file()
    assert not (ROOT / "docs" / "development").exists()
    assert (ROOT / "docs" / "reference" / "INVARIANTS.md").is_file()
    assert (ROOT / "docs" / "integration" / "OH_GOON_INTEGRATION.md").is_file()
    assert (ROOT / "docs" / "maintainers" / "RELEASING.md").is_file()
    assert (ROOT / "docs" / "qualification" / "REPOSITORY_QUALITY.md").is_file()


def test_repository_root_has_no_historical_phase_evidence() -> None:
    root = Path(__file__).resolve().parents[1]
    historical = sorted(
        path.name
        for path in root.iterdir()
        if path.is_file()
        and path.name.startswith("HM")
        and path.suffix in {".json", ".txt", ".md"}
    )
    assert historical == []
    assert not (root / "docs" / "development").exists()
    historical_docs = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "docs").rglob("*")
        if path.is_file()
        and (path.name.startswith("HM") or "HISTORICAL" in path.name)
    )
    assert historical_docs == []
    assert "## HM" not in (root / "CHANGELOG.md").read_text(encoding="utf-8")
