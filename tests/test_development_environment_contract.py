from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAKEFILE = (ROOT / "Makefile").read_text(encoding="utf-8")
README = (ROOT / "README.md").read_text(encoding="utf-8")


def _recipe(target: str) -> str:
    lines = MAKEFILE.splitlines()
    start = lines.index(f"{target}:") + 1
    recipe: list[str] = []
    for line in lines[start:]:
        if line.startswith("\t"):
            recipe.append(line)
            continue
        if recipe:
            break
    return "\n".join(recipe)


def test_source_development_sync_includes_mcp_extra() -> None:
    assert "DEV_SYNC := $(UV_SYNC) --extra mcp --group test" in MAKEFILE
    for target in ("lock", "init", "bootstrap"):
        assert "$(DEV_SYNC)" in _recipe(target)


def test_readme_documents_direct_mcp_development_sync() -> None:
    assert "uv sync --frozen --extra mcp --group test" in README
