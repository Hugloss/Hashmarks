import ast
import subprocess
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
    assert "Locator/content identity separation" in binding
    assert "Precision/completeness separation" in binding
    assert "Evidence declaration topology" in binding
    assert "Repository generation and binding locality" in binding
    assert "Declared dependency topology and locality" in binding
    assert "Relationship scope and binding locality" in binding
    assert "Relationship comparability boundary" in binding
    assert (
        "loss of relationship comparability removes authority to claim edge change"
        in binding
    )
    assert "content equality may prove equivalence of observed bytes" in binding
    assert "never upgrades the completeness" in binding
    assert "must never collapse declared multiplicity or scope" in binding
    assert "repository authority may advance globally" in binding
    for state in ("current", "stale", "unknown"):
        assert state in binding


def test_public_docs_expose_dependency_derivation_and_endpoint_delta() -> None:
    stability = _text("docs/reference/API_STABILITY.md")
    dependency = _text("docs/reference/DEPENDENCY_EVIDENCE.md")
    state = _text("docs/reference/STATE_AND_SEMANTIC_OWNERS.md")
    guide = _text("docs/maintainers/CODEMAP.md")

    for schema in (
        "hashmarks.dependency-resolution-derivation.v1",
        "hashmarks.dependency-resolution-explain.v1",
        "hashmarks.dependency-resolution-delta.v3",
    ):
        assert schema in stability
        assert schema in dependency

    assert (
        "Repository identity and CodeMap generation are both comparison axes"
        in dependency
    )
    assert "physical_evidence_topology" in dependency
    assert "physical_evidence_content" in dependency
    assert "Dependency derivation/explain and endpoint-delta admission record" in state
    assert "dependency_resolution_derivation.py" in guide
    assert "dependency_resolution_delta.py" in guide
    assert 'result_mode="compare"' in dependency
    assert "dependency_codemap" in dependency


def test_public_docs_expose_typed_declaration_derivation() -> None:
    stability = _text("docs/reference/API_STABILITY.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")
    state = _text("docs/reference/STATE_AND_SEMANTIC_OWNERS.md")
    guide = _text("docs/maintainers/CODEMAP.md")
    plan = _text("docs/maintainers/DERIVED_AUTHORITY_AND_BOUNDED_COMPARISON_PLAN.md")

    for schema in (
        "hashmarks.repository-declaration-derivation.v1",
        "hashmarks.repository-declaration-explain.v1",
    ):
        assert schema in stability
        assert schema in declarations

    assert "Why this remains typed" in declarations
    assert "Authority-transition separation" in declarations
    assert "Provider-transition separation" in declarations
    assert "correspondence_changed" in declarations
    assert "not-detected -> collected" in declarations
    assert "repository_declaration_derivation.py" in guide
    assert "no universal provenance ontology admitted" in plan
    assert "New semantic owner introduced: NO" in state
    assert 'result_mode="explain"' in declarations
    assert "repository_declarations" in declarations
    assert "MCP `result_mode` is transport vocabulary only" in state


def test_semantic_identity_is_documented_without_repository_history_ownership() -> None:
    docs = _text("docs/README.md")
    architecture = _text("docs/reference/ARCHITECTURE.md")
    boundary = _text("docs/reference/PRODUCT_BOUNDARY.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")
    owners = _text("docs/reference/STATE_AND_SEMANTIC_OWNERS.md")
    decision = _text(
        "docs/maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md"
    )

    assert "SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md" in docs
    assert "### Semantic identity layers" in architecture
    assert "semantic_subject_identity" in declarations
    assert "semantic_namespace" in declarations
    assert "semantic_role" in declarations
    assert "semantic_declaration_identity" in declarations
    assert "semantic_subject_changed" in declarations
    assert "semantic_subjects" in declarations
    assert "semantic_declarations" in declarations
    assert "G69. Semantic-subject identity" in invariants
    assert "G70. Semantic-subject delta" in invariants
    assert "G71. Semantic declaration identity" in invariants
    assert "Declaration semantic subject identity" in owners
    assert "Declaration semantic role identity" in owners
    assert "Declaration semantic-subject delta" in owners
    assert "New semantic owner introduced: NO" in owners
    assert "Identity without ownership; compare without mutation" in boundary
    assert "semantic_namespace + concept + scope" in decision
    assert "semantic_subject_identity + semantic_role" in declarations
    assert (
        "does not invent, normalize, alias, require, or separately index roles"
        in declarations
    )
    assert "provider wrapper provenance/version" in declarations
    assert "alias or migration table" in declarations
    assert (
        "does not promote semantic identity into repository-evidence binding identity"
        in declarations
    )
    assert "removed and added rather than guessing continuity" in declarations
    assert "does not add a cross-binding alias" in declarations
    assert "Child-role admission evidence" in decision
    assert "Untagged children remain request-local" in decision
    assert "duplicate subject identities remain explicitly ambiguous" in decision
    assert "no history store and no retention layer" in decision
    for forbidden_owner in (
        "Hashmarks owns branch management",
        "Hashmarks owns merge",
        "Hashmarks owns repository history",
    ):
        assert forbidden_owner not in decision


def test_semantic_identity_reappearance_remains_non_historical() -> None:
    invariants = _text("docs/reference/INVARIANTS.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")
    decision = _text(
        "docs/maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md"
    )

    assert "G72. Semantic identity reappearance" in invariants
    assert "same `semantic_declaration_identity`" in declarations
    assert "not an existence timeline" in declarations
    assert "stores no tombstone or resurrection record" in declarations
    assert "does **not** prove uninterrupted existence" in decision
    assert "it supplies that bounded packet explicitly" in decision


def test_declaration_uncertainty_axes_remain_orthogonal() -> None:
    invariants = _text("docs/reference/INVARIANTS.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")
    decision = _text(
        "docs/maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md"
    )

    assert "G73. Declaration uncertainty axes remain orthogonal" in invariants
    assert "## Uncertainty axes remain independent" in declarations
    assert (
        "candidate values are not promoted into a factual disagreement" in declarations
    )
    assert "does not manufacture known absence" in declarations
    assert 'synthetic "overall confidence" authority' in declarations
    assert "No combined confidence object" in decision
    assert "uncertainty owner is introduced" in decision


def test_provider_namespace_identity_never_infers_cross_provider_aliases() -> None:
    invariants = _text("docs/reference/INVARIANTS.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")
    owners = _text("docs/reference/STATE_AND_SEMANTIC_OWNERS.md")

    assert "Replacing one provider namespace with another" in invariants
    assert "never an inferred rename, alias, or provider migration" in invariants
    assert (
        "Provider implementation/provenance/version is not semantic identity"
        in invariants
    )
    assert "changing semantic scope changes subject identity" in invariants
    assert "does not infer a cross-provider rename, alias, migration" in declarations
    assert (
        "does not maintain a provider-alias or provider-migration table" in declarations
    )
    assert (
        "Provider build/provenance version is not identity; semantic scope is" in owners
    )


def test_cross_provider_correspondence_never_unions_source_identities() -> None:
    invariants = _text("docs/reference/INVARIANTS.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")
    owners = _text("docs/reference/STATE_AND_SEMANTIC_OWNERS.md")

    assert "G74. Cross-provider correspondence is a producer-owned claim" in invariants
    assert "not identity union" in invariants
    assert "must not rewrite source-provider identities" in invariants
    assert "third explicit producer" in declarations
    assert "does **not** merge, rename, alias" in declarations
    assert "not a global semantic edge registry or ontology layer" in declarations
    assert (
        "owns a separate namespaced claim rather than merging source identities"
        in owners
    )


def test_hashmarks_never_becomes_a_semantic_knowledge_graph() -> None:
    architecture = _text("docs/reference/ARCHITECTURE.md")
    boundary = _text("docs/reference/PRODUCT_BOUNDARY.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")
    decision = _text(
        "docs/maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md"
    )
    owners = _text("docs/reference/STATE_AND_SEMANTIC_OWNERS.md")

    assert "Semantic knowledge graph is a permanent non-goal" in architecture
    assert "must **not** generalize semantic identity or correspondence" in architecture
    assert "Not a semantic knowledge graph" in boundary
    assert "Four permanent non-goals" in boundary
    assert "global semantic graph/ontology ownership" in boundary
    assert "general knowledge graph, ontology, edge registry" in boundary
    assert "four negative questions before admission" in boundary
    assert "G75. Hashmarks is not a semantic knowledge graph" in invariants
    assert (
        "Explicit A↔B plus explicit B↔C does not authorize inferred A↔C" in invariants
    )
    assert "Correspondence is also deliberately **non-transitive**" in declarations
    assert "does not derive A↔C" in declarations
    assert "Why this is not a knowledge graph" in decision
    assert "they do not create A↔C" in decision
    assert "There is no global semantic edge/knowledge-graph owner" in owners
    assert "do not create a connected component, equivalence class" in invariants
    assert "Cycles do not strengthen correspondence authority" in declarations
    assert "do not create a semantic component, equivalence class" in _text("AGENTS.md")
    assert "connected components, cycle consensus, majority authority" in owners


def test_correspondence_provenance_never_becomes_referential_integrity() -> None:
    agents = _text("AGENTS.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")
    decision = _text(
        "docs/maintainers/SEMANTIC_IDENTITY_WITHOUT_REPOSITORY_OWNERSHIP.md"
    )
    owners = _text("docs/reference/STATE_AND_SEMANTIC_OWNERS.md")

    assert "G76. Correspondence provenance is not referential integrity" in invariants
    assert "not foreign keys" in declarations
    assert "does not cascade-delete" in declarations
    assert "no hidden referential-integrity graph" in declarations
    assert "Provider names or identifiers" in agents
    assert "are **not foreign keys**" in agents
    assert "Correspondence provenance is likewise non-referential" in decision
    assert "foreign-key joins, cascade deletion" in owners


def test_duplicate_semantic_roles_never_gain_core_precedence() -> None:
    invariants = _text("docs/reference/INVARIANTS.md")
    declarations = _text("docs/reference/REPOSITORY_DECLARATIONS.md")

    assert "Duplicate roles may not be collapsed" in invariants
    assert "apparent source specificity" in invariants
    assert "majority" in invariants
    assert "provider must resolve and expose that claim explicitly" in invariants
    assert "Core does not break duplicate-role ambiguity" in declarations
    assert (
        "repository-declaration core does not recreate native precedence"
        in declarations
    )


def test_derived_authority_economics_remains_diagnostic_only() -> None:
    makefile = _text("Makefile")
    plan = _text("docs/maintainers/DERIVED_AUTHORITY_AND_BOUNDED_COMPARISON_PLAN.md")
    economics = _text("docs/qualification/TEST_RUNTIME_ECONOMICS.md")

    assert "metrics-derived-authority:" in makefile
    assert "make metrics-derived-authority" in plan
    assert "make metrics-derived-authority" in economics
    assert "runtime diagnostics only" in economics
    assert "no retention implementation is admitted" in plan.lower()
    assert "genuine dependency dogfood fixtures" in plan
    assert "implemented baseline; saturation complete" in plan
    assert "Clean pass #2 qualified" in plan
    assert "No retention layer was admitted" in plan
    assert "Post-saturation adversarial coverage is now complete" in plan
    assert "Repository-evidence authority follow-through saturation" in plan
    assert "do not keep producing same-family micro-permutations" in plan
    assert "Bounded packet eviction/reconstruction is **not an open attack**" in plan
    assert "existing genuine uv/Maven dependency dogfood corpus" in economics
    assert "explicit-packet design is therefore the current baseline" in economics


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
    assert "REPOSITORY_EVIDENCE_BINDINGS.md)\\n" not in readme
    assert "REPOSITORY_DECLARATIONS.md)\\n" not in readme
    assert "Hashmarks.\n- **Evidence correlation.**" in readme
    assert (
        "[Repository evidence bindings](docs/reference/REPOSITORY_EVIDENCE_BINDINGS.md)"
        in readme
    )
    assert (
        "[Repository declarations](docs/reference/REPOSITORY_DECLARATIONS.md)" in readme
    )
    assert "[Evidence correlation](docs/reference/EVIDENCE_CORRELATION.md)" in readme


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
    generated_roots = (
        "baseline",
        "challenge",
        "failure-packets",
        "outputs",
        "packets",
        "worker-outputs",
        "benchmarks/agent_evaluation/retained",
    )
    tracked = subprocess.run(
        ["git", "ls-files", "-z", "--", *generated_roots],
        cwd=ROOT,
        capture_output=True,
        check=True,
    ).stdout
    assert not tracked, tracked.decode("utf-8")
    evaluation_docs = _text("benchmarks/agent_evaluation/README.md")
    assert "not installed Hashmarks product state" in evaluation_docs
    assert (
        "Generated blind inputs, packets, worker outputs, and result files are not committed"
        in evaluation_docs
    )


def test_public_onboarding_leads_with_standalone_install_not_source_checkout() -> None:
    readme = _text("README.md")
    getting_started = _text("docs/GETTING_STARTED.md")
    installer = "raw.githubusercontent.com/Hugloss/Hashmarks/main/install.sh"
    assert installer in readme
    assert readme.index(installer) < readme.index("make init")
    assert installer in getting_started
    assert getting_started.index(installer) < getting_started.index("make init")
    assert (
        "Python, Git, and `uv` are development/qualification tools" in getting_started
    )


def test_public_install_and_release_docs_match_github_release_authority() -> None:
    readme = _text("README.md")
    releasing = _text("docs/maintainers/RELEASING.md")

    assert 'pip install "hashmarks[mcp]"' not in readme
    assert "standalone Hashmarks executable from GitHub Releases" in readme
    assert ".github/release-request.toml" in releasing
    assert (
        "release-request merge SHA becomes the default release source authority"
        in releasing
    )
    assert "GitHub Releases" in releasing
    assert "does not automatically publish to PyPI" in releasing
    assert "PyPI Trusted Publishing" not in releasing
    assert "publication_attempt" in releasing
    assert "source_sha" in releasing


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
        "PB6. Hashmarks must never become the agent or the execution motor."
        in invariants
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
    assert "small read-only repository-intelligence tool catalog" in mcp
    for tool in (
        "repository_context",
        "find",
        "task_evidence",
        "change_impact",
        "correlate_evidence",
        "dependency_codemap",
        "repository_declarations",
        "post_change",
    ):
        assert f"`{tool}`" in mcp
    assert "does not add planning, editing, shell execution" in mcp
    assert 'result_mode="observation" | "explain" | "compare"' in mcp
    assert 'result_mode="observation" | "explain"' in mcp
    assert "The catalog stays small" in mcp
    assert 'never stores a "previous" dependency or declaration observation' in mcp
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


def test_ci_and_dev_check_enforce_current_ruff_gate() -> None:
    workflow = _text(".github/workflows/ci.yml")
    marker = "      - name: Enforce configured Ruff and zero complexity debt\n"
    assert marker in workflow
    gate_block = workflow.split(marker, 1)[1].split("      - name:", 1)[0]
    assert "run: make lint" in gate_block
    assert "continue-on-error" not in gate_block
    convergence = workflow.split("  qualification-convergence:", 1)[1]
    assert "      - formatting" in convergence
    assert "      - ruff-debt" in convergence
    assert "FORMATTING: ${{ needs.formatting.result }}" in convergence
    assert "RUFF_DEBT: ${{ needs.ruff-debt.result }}" in convergence
    assert '"FORMATTING" "$FORMATTING"' in convergence
    qualification_loop = convergence.split("for lane in", 1)[1].split("do", 1)[0]
    assert "FORMATTING" not in qualification_loop
    assert "RUFF_DEBT" in qualification_loop
    assert 'test "$failed" -eq 0' in convergence

    makefile = _text("Makefile")
    dev_check = makefile.split("dev-check: setup", 1)[1].split("\ndev-check-batch:", 1)[
        0
    ]
    assert "Current Ruff and size gates" in dev_check
    assert "--no-print-directory lint" in dev_check
    assert dev_check.index("--no-print-directory dev-check-tests") < dev_check.index(
        "--no-print-directory lint"
    )
    assert "lint-debt-summary || true" not in dev_check
    assert "Ruff:        PASS (zero debt)" in dev_check


def test_update_lifecycle_is_explicit_native_and_outside_repository_authority() -> None:
    readme = _text("README.md")
    getting_started = _text("docs/GETTING_STARTED.md")
    architecture = _text("docs/reference/ARCHITECTURE.md")
    invariants = _text("docs/reference/INVARIANTS.md")
    boundary = _text("docs/reference/PRODUCT_BOUNDARY.md")

    governing_rule = (
        "Hashmarks may discover update availability. It never owns updating itself."
    )
    assert governing_rule in readme
    assert governing_rule in getting_started
    assert governing_rule in architecture
    assert governing_rule in boundary

    for text in (readme, getting_started, architecture, invariants, boundary):
        assert "HASHMARKS_NO_UPDATE_CHECK=1" in text
        assert "MCP" in text
        assert "CI" in text

    assert "hashmarks upgrade" in readme
    assert "hashmarks upgrade" in getting_started
    assert "canonical standalone distribution" in architecture
    assert "does not determine whether that mechanism is uv, pip, pipx" in architecture
    assert "U5. Installation mutation is explicit and narrow." in invariants
    assert (
        "Skip for now** path does not resolve or preflight installer prerequisites"
        in invariants
    )
    assert "requirements are resolved once" in architecture
    assert (
        "single resolution of both installation mode and exact execution payload"
        in invariants
    )
    assert "resolved together by one optional command result" in architecture
    assert "must not transport the same upgrade inputs again" in invariants
    assert "displayed standalone command is also the execution payload" in architecture
    assert "does not preflight installer prerequisites" in getting_started
    assert "U6. Hashmarks never owns updating itself." in invariants
    assert "U7. Native package-manager state stays opaque and native." in invariants
    assert "must not reconstruct uv/pip/pipx filesystem layouts" in invariants
    assert "inspect or certify their receipts/metadata" in invariants
    assert "package-manager detector" in invariants
    assert "Those commands are examples, not Hashmarks-owned manager selection." in (
        getting_started
    )
    assert "does not detect/certify uv, pip, pipx" in boundary
    assert "package-manager detection/certification" in boundary
    assert "Narrow product-distribution lifecycle exception" in boundary
    assert "package resolver" in boundary
    assert "repository/task command execution" in boundary
