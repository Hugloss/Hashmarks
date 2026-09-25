from __future__ import annotations

import hashmarks

EXPECTED_PUBLIC = {
    "__version__",
    "CodeMap",
    "Digest",
    "RepositoryIdentity",
    "RepositoryIdentityMode",
    "RepositoryDeclarationProvider",
    "RepositoryDeclarationProviderContext",
    "RepositoryDeclarationProviderError",
    "RepositoryDeclarationProviderResult",
    "IdentityCycleError",
    "IdentityGraph",
    "InputManifest",
    "InputSpec",
    "InputValue",
    "File",
    "Directory",
    "Glob",
    "Snapshot",
    "SnapshotDiff",
    "ChangeSnapshot",
    "ChangeTracker",
    "ObservationState",
    "UnstableObservationError",
    "hash_bytes",
    "hash_file",
    "resolve_inputs",
    "patterns_from_inputs",
    "validate_input_values",
}

REMOVED_BOUNDARY_DEBT = {
    "ActionCache",
    "ActionResult",
    "AgentWorkSession",
    "ExecutionCache",
    "PassPromotion",
    "StepIdentity",
    "WorkUnit",
}


def test_top_level_public_api_is_explicit_and_small() -> None:
    assert set(hashmarks.__all__) == EXPECTED_PUBLIC
    for name in EXPECTED_PUBLIC:
        assert getattr(hashmarks, name) is not None


def test_unpublished_boundary_debt_is_not_exported() -> None:
    assert not (set(hashmarks.__all__) & REMOVED_BOUNDARY_DEBT)
    for name in REMOVED_BOUNDARY_DEBT:
        assert not hasattr(hashmarks, name)
