import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_codemap_maintainer_guide_maps_internal_ownership_and_request_flows() -> None:
    docs = _text("docs/README.md")
    guide = _text("docs/maintainers/CODEMAP.md")
    assert "maintainers/CODEMAP.md" in docs
    for section in (
        "## Responsibility map",
        "## Trace common requests before reading everything",
        "### `CodeMap.sync()`",
        "### `CodeMap.repository_ownership_graph()`",
        "## How to choose where new code belongs",
        "## Reading strategy for a new maintainer",
    ):
        assert section in guide
    assert "import_resolution.py" in guide
    assert "ownership_analysis.py" in guide
    assert "decision_session.py" in guide
    assert "Execution/certification is external" in guide


def test_codemap_direct_mixins_are_named_in_maintainer_responsibility_map() -> None:
    tree = ast.parse(_text("hashmarks/codemap/engine.py"))
    imports: dict[str, str] = {}
    codemap: ast.ClassDef | None = None
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module:
            for alias in node.names:
                imports[alias.asname or alias.name] = node.module
        elif isinstance(node, ast.ClassDef) and node.name == "CodeMap":
            codemap = node
    assert codemap is not None

    guide = _text("docs/maintainers/CODEMAP.md")
    owner_modules = sorted(
        {
            imports[base.id]
            for base in codemap.bases
            if isinstance(base, ast.Name) and base.id in imports
        }
    )
    missing = [module for module in owner_modules if f"{module}.py" not in guide]
    assert missing == [], (
        "every direct CodeMap mixin is a responsibility boundary and must be "
        "named in docs/maintainers/CODEMAP.md: " + ", ".join(missing)
    )


def test_repository_state_families_have_one_discoverable_owner_map() -> None:
    docs = _text("docs/README.md")
    state = _text("docs/reference/STATE_AND_SEMANTIC_OWNERS.md")
    guide = _text("docs/maintainers/CODEMAP.md")
    template = _text(".github/PULL_REQUEST_TEMPLATE.md")

    assert "reference/STATE_AND_SEMANTIC_OWNERS.md" in docs
    for owner in (
        "observation.py::ObservationState",
        "client.py::RepositoryObservation",
        "repository_delta.py::RepositoryDeltaMixin",
        "evidence_freshness.py",
        "freshness_map.py",
    ):
        assert owner in state
    for state_family in (
        "Repository continuity",
        "Member revision",
        "Evidence availability",
        "Freshness",
        "Completeness",
        "Repository semantic delta",
        "Relationship evidence",
        "Consumer binding definition",
        "Consumer binding impact",
    ):
        assert state_family in state
    assert "reuse before adding" in state.lower()
    assert "STATE_AND_SEMANTIC_OWNERS.md" in guide
    assert "Existing semantic owner extended:" in template
    assert "New serialized state vocabulary:" in template


def test_public_docs_expose_repository_evidence_binding_contract() -> None:
    docs = _text("docs/README.md")
    readme = _text("README.md")
    stability = _text("docs/reference/API_STABILITY.md")
    observer = _text("docs/reference/OBSERVER_DELTA.md")
    binding = _text("docs/reference/REPOSITORY_EVIDENCE_BINDINGS.md")

    assert "reference/REPOSITORY_EVIDENCE_BINDINGS.md" in docs
    assert "Repository evidence bindings" in readme
    assert "repository_evidence_bindings()" in stability
    assert "hashmarks.repository-evidence-bindings.v1" in stability
    assert "## Repository evidence bindings" in observer
    for schema in (
        "hashmarks.repository-evidence-bindings.v1",
        "hashmarks.repository-evidence-binding-delta.v1",
        "hashmarks.repository-evidence-coverage.v1",
    ):
        assert schema in binding
    for state in ("current", "stale", "unknown"):
        assert state in binding


def test_public_docs_separate_current_contracts_from_history() -> None:
    docs = _text("docs/README.md")
    assert "public/current contracts" in docs
    assert "historical development evidence" in docs
    assert (ROOT / "docs/development/HISTORICAL_RELEASE_NOTES.md").is_file()
    assert (ROOT / "docs/development/HISTORICAL_OH_GOON_INTEGRATION_NOTES.md").is_file()
    assert "Historical, non-normative record." in _text(
        "docs/development/HISTORICAL_RELEASE_NOTES.md"
    )
    assert "Historical, non-normative record." in _text(
        "docs/development/HISTORICAL_OH_GOON_INTEGRATION_NOTES.md"
    )


def test_github_entry_points_exist() -> None:
    for path in (
        ".github/CONTRIBUTING.md",
        ".github/SECURITY.md",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/proposal.yml",
        ".github/workflows/ci.yml",
    ):
        assert (ROOT / path).is_file()


def test_current_integration_contract_is_not_version_pinned() -> None:
    integration = _text("docs/integration/OH_GOON_INTEGRATION.md")
    assert "Interoperability transfers evidence, never authority." in integration
    assert "Hashmarks must never become Oh-Goon's execution motor." in integration
    assert "canonical Oh-Goon 1267.0.147" not in integration
    assert "## v0.10." not in integration


def test_public_release_contract_documents_stability_and_changelog() -> None:
    readme = _text("README.md")
    docs = _text("docs/README.md")
    stability = _text("docs/reference/API_STABILITY.md")
    changelog = _text("CHANGELOG.md")
    assert "Public API and stability policy" in readme
    assert "CHANGELOG.md" in readme
    assert "reference/API_STABILITY.md" in docs
    assert "supported Python API" in stability
    assert "hashmarks.__all__" in stability
    assert "## 0.14.0 — Repository-scope authority and precision closure" in changelog
    assert "## 0.13.0 — Initial public release" in changelog
    assert "agent-loop" in changelog


def test_publication_root_moves_agent_evaluation_corpora_out_of_product_surface() -> (
    None
):
    for old_root in (
        "baseline",
        "challenge",
        "failure-packets",
        "outputs",
        "packets",
        "worker-outputs",
    ):
        assert not (ROOT / old_root).exists()
    assert (ROOT / "benchmarks/agent_evaluation/retained").is_dir()
    retained = _text("benchmarks/agent_evaluation/README.md")
    assert "not installed Hashmarks product state" in retained


def test_public_onboarding_leads_with_installed_package_not_source_checkout() -> None:
    readme = _text("README.md")
    getting_started = _text("docs/GETTING_STARTED.md")
    assert "pip install hashmarks" in readme
    assert readme.index("pip install hashmarks") < readme.index("make init")
    assert "pip install hashmarks" in getting_started
    assert getting_started.index("pip install hashmarks") < getting_started.index(
        "make init"
    )
    assert "Git and `uv` are development/qualification tools" in getting_started


def test_agent_evaluation_executables_are_isolated_from_product_script_root() -> None:
    root_scripts = {path.name for path in (ROOT / "scripts").glob("*.py")}
    forbidden_fragments = (
        "agent",
        "codex",
        "worker",
        "swarm",
        "scout",
        "full_edit",
        "harness_run",
    )
    leaked = sorted(
        name
        for name in root_scripts
        if any(fragment in name for fragment in forbidden_fragments)
    )
    assert leaked == []
    evaluation_root = ROOT / "scripts" / "agent_evaluation"
    assert (evaluation_root / "metrics_agent.py").is_file()
    assert (evaluation_root / "codex_agent_economics.py").is_file()
    assert (evaluation_root / "score_agent_work.py").is_file()
    assert (evaluation_root / "ruff_debt_agent_economics_parity.py").is_file()
    readme = (evaluation_root / "README.md").read_text(encoding="utf-8")
    assert "development and measurement infrastructure" in readme
    assert "not installed as part of the `hashmarks` Python package" in readme


def test_normative_invariants_exclude_prepublic_agent_execution_history() -> None:
    current = _text("docs/reference/INVARIANTS.md")
    historical = _text("docs/development/HISTORICAL_INVARIANTS.md")
    assert "Status: non-normative development history." in historical
    for historical_term in (
        "Action-cache results are valid",
        "PASS promotion is post-run identity-bound",
        "failed-verification recovery — historical benchmark invariants",
        "selective ambiguity scout economics",
        "real Codex economics",
    ):
        assert historical_term not in current
        assert historical_term in historical
    assert (
        "PB6. Hashmarks must never become the agent or the execution motor." in current
    )
    assert "PB7. Interoperability transfers evidence, never authority." in current


def test_public_docs_expose_bounded_mcp_integration_and_apache_license() -> None:
    readme = _text("README.md")
    docs = _text("docs/README.md")
    mcp = _text("docs/integration/MCP.md")
    assert "Apache License 2.0" in readme
    assert "integration/MCP.md" in docs
    assert "only five tools" in mcp
    for tool in (
        "repository_context",
        "find",
        "task_evidence",
        "change_impact",
        "post_change",
    ):
        assert f"`{tool}`" in mcp
    assert "does not add planning, editing, shell execution" in mcp
    assert "`opencode.json`" in mcp
    assert ".mcp.json" in mcp
    assert ".codex/config.toml" in mcp
    assert "pi-mcp-adapter" in mcp
    assert "make mcp-host-status" in readme
    assert "make mcp-host-status" in mcp
    assert "make mcp-opencode-check" in readme
    assert "make mcp-opencode-check" in mcp
    assert (ROOT / "scripts/host_qualification/opencode_mcp_host_gate.py").is_file()
    assert (ROOT / "scripts/mcp_host_status.py").is_file()
    assert (ROOT / "opencode.json").is_file()
    assert (ROOT / ".mcp.json").is_file()
    assert (ROOT / ".codex" / "config.toml").is_file()
