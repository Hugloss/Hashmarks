from __future__ import annotations

import sys
from pathlib import Path

# Research scripts are intentionally importable modules as well as CLI entrypoints.
# Put the source checkout root on sys.path once for the test process so ordinary
# imports retain one normal sys.modules/cache owner instead of per-test file execs.
ROOT = Path(__file__).parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest  # noqa: E402 - import follows standalone script path setup


@pytest.fixture(scope="session")
def repository_qualification_plan():
    """One immutable repository qualification snapshot for read-only contract tests."""
    from hashmarks.qualification_units import qualification_owner_plan

    return qualification_owner_plan(ROOT)


@pytest.fixture(scope="session")
def repository_qualification_handoff(repository_qualification_plan):
    """Project the shared qualification snapshot without rescanning repository source."""
    from hashmarks.qualification_units import _native_qualification_handoff_from_plan

    return _native_qualification_handoff_from_plan(repository_qualification_plan)


def _constrained_host_capabilities() -> dict[str, bool]:
    import importlib.util
    import os

    name = "hashmarks.exe" if os.name == "nt" else "hashmarks"
    return {
        "host_mcp_sdk": importlib.util.find_spec("mcp") is not None,
        "host_console_script": Path(sys.executable).with_name(name).is_file(),
        "host_git": __import__("shutil").which("git") is not None,
    }


def pytest_collection_modifyitems(config, items):
    """Make constrained-host capability absence explicit without weakening normal tests."""
    import os

    if os.environ.get("HASHMARKS_CONSTRAINED_HOST") != "1":
        return
    capabilities = _constrained_host_capabilities()
    mandatory_skip = {
        "certification": "native/release authority is excluded from hosted diagnostics",
        "host_dns": "external DNS/network is excluded from hosted diagnostics",
        "slow": "slow tests are excluded from hosted diagnostics",
        "scale": "scale tests are excluded from hosted diagnostics",
    }
    for item in items:
        for marker, reason in mandatory_skip.items():
            if item.get_closest_marker(marker) is not None:
                item.add_marker(pytest.mark.skip(reason=reason))
        for marker, available in capabilities.items():
            if not available and item.get_closest_marker(marker) is not None:
                item.add_marker(
                    pytest.mark.skip(
                        reason=f"constrained host lacks capability: {marker}"
                    )
                )
