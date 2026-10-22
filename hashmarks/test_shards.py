"""Compatibility identity for Hashmarks' developer-only test-sharding owner.

This is the same module object, not a second selector or execution publisher.
New developer tooling imports hashmarks._development.test_shards directly.
"""

from importlib import import_module as _import_module
from sys import modules as _modules

from hashmarks._development.test_shards import (  # noqa: F401
    ENVELOPE_SCHEMA,
    EXECUTION_LAYER_AUTHORITIES,
    HASHMARKS_AUTHORITIES,
    ISOLATED_NODEIDS,
    MEMBERSHIP_SCHEMA,
    SCHEMA,
    SELECTION_INPUT_SCHEMA,
    SHARD_ALGORITHM,
    developer_selection_source_identity,
    node_membership_identity,
    plan,
    repository_content_identity,
    select,
    selection_input_identity,
    selection_membership_identity,
    validate_test_shard_plan,
    validate_work_selection_envelope,
    validate_work_selection_repository_binding,
    work_selection_envelope,
)
from hashmarks._development.test_shards import __all__ as __all__

_modules[__name__] = _import_module("hashmarks._development.test_shards")

if __name__ == "__main__":
    # Preserve the historical python -m entrypoint as well as import identity.
    from hashmarks._development.test_shards import main

    raise SystemExit(main())
