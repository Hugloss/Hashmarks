import ast
import tomllib
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


def test_public_readme_tracks_release_version_and_markdown_boundaries() -> None:
    readme = _text("README.md")
    project_version = tomllib.loads(_text("pyproject.toml"))["project"]["version"]

    assert f"Current package version: **{project_version}**." in readme
    assert "Hashmarks.\\n- **Evidence correlation.**" not in readme
    assert "REPOSITORY_EVIDENCE_BINDINGS.md)\\n- [Evidence correlation]" not in readme
    assert "Hashmarks.\n- **Evidence correlation.**" in readme
    assert "REPOSITORY_EVIDENCE_BINDINGS.md)\n- [Evidence correlation]" in readme


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


def test_generated_agent_evaluation_state_is_not_committed() -> None:
    for generated_root in (
        "baseline",
        "challenge",
        "failure-packets",
        "outputs",
        "packets",
        "worker-outputs",
        "benchmarks/agent_evaluation/retained",
    ):
        assert not (ROOT / generated_root).exists()
    evaluation_docs = _text("benchmarks/agent_evaluation/README.md")
    assert "not installed Hashmarks product state" in evaluation_docs
    assert (
        "Generated blind inputs, packets, worker outputs, and result files are not committed"
        in evaluation_docs
    )


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


def test_public_contract_docs_describe_current_api_and_authority() -> None:
    stability = _text("docs/reference/API_STABILITY.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    integration = _text("docs/integration/OH_GOON_INTEGRATION.md")

    assert "hashmarks.task-evidence.v2" in stability
    assert "one current documented Python/CLI surface" in stability
    assert "measurement/evidence infrastructure, not installed product API" in stability

    assert (
        "PB6. Hashmarks must never become the agent or the execution motor." in invariants
    )
    assert "PB7. Interoperability transfers evidence, never authority." in invariants
    assert "Interoperability transfers evidence, never authority." in integration
    assert "Hashmarks must never become Oh-Goon's execution motor." in integration


def test_public_docs_expose_bounded_mcp_integration_and_apache_license() -> None:
    readme = _text("README.md")
    docs = _text("docs/README.md")
    mcp = _text("docs/integration/MCP.md")
    assert "Apache License 2.0" in readme
    assert "integration/MCP.md" in docs
    assert "only six tools" in mcp
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


def test_ci_and_dev_check_enforce_ruff_debt_gate() -> None:
    workflow = _text(".github/workflows/ci.yml")
    marker = "      - name: Ruff maintainability debt gate\n"
    assert marker in workflow
    gate_block = workflow.split(marker, 1)[1].split("      - name:", 1)[0]
    assert "run: make lint-debt-gate" in gate_block
    assert "continue-on-error" not in gate_block

    makefile = _text("Makefile")
    dev_check = makefile.split("dev-check: setup", 1)[1].split("\ndev-check-batch:", 1)[
        0
    ]
    assert "Ruff debt no-growth gate" in dev_check
    assert "lint-debt-gate" in dev_check
    assert "lint-debt-summary || true" not in dev_check
    assert "Ruff debt:   PASS (no growth)" in dev_check
