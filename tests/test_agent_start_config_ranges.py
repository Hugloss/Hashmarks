from pathlib import Path

from hashmarks.codemap import CodeMap


def _repo(root: Path, filename: str, content: str) -> None:
    (root / "src/case").mkdir(parents=True)
    (root / "tests/case").mkdir(parents=True)
    (root / "src/__init__.py").write_text("", encoding="utf-8")
    (root / "src/case/__init__.py").write_text("", encoding="utf-8")
    (root / "src/case/engine.py").write_text(
        "def apply_case(value: str) -> str:\n    return value + '-active'\n",
        encoding="utf-8",
    )
    (root / "src/case/route.py").write_text(
        "from .engine import apply_case\n\n"
        "def handle_ember(value: str) -> str:\n    return apply_case(value)\n",
        encoding="utf-8",
    )
    (root / "tests/case/test_behavior.py").write_text(
        "from src.case.route import handle_ember\n\n"
        "def test_ember_contract():\n    assert handle_ember('x') == 'x-active'\n",
        encoding="utf-8",
    )
    (root / f"src/case/{filename}").write_text(content, encoding="utf-8")


def _start(root: Path, query: str, *, token_budget: int = 128) -> dict[str, object]:
    with CodeMap(root) as codemap:
        codemap.sync()
        return codemap.task_evidence(query, token_budget=token_budget)


def test_toml_key_range_replaces_symbol_less_next_read(tmp_path: Path) -> None:
    _repo(tmp_path, "policy.toml", "mode='active'\nfeature='ember'\n")
    start = _start(tmp_path, "Change ember policy config accepted response mode")
    assert start["edit"] == "src/case/policy.toml"
    assert start["edit_evidence"] == {
        "symbol": "mode",
        "lines": [1, 1],
        "representation": "config-key-range",
        "content": "mode='active'",
        "estimated_tokens": 4,
        "config": {"format": "toml", "kind": "key", "name": "mode", "locator": "exact-task-key"},
    }
    assert start["next_read"] is None
    assert start["source_budget"]["complete"] is True


def test_toml_section_range_is_bounded_to_named_section(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        "policy.toml",
        "global='keep'\n\n[response]\nmode='active'\nfeature='ember'\n\n[other]\nmode='legacy'\n",
    )
    start = _start(tmp_path, "Inspect the response section in the ember policy config")
    evidence = start["edit_evidence"]
    assert evidence["representation"] == "config-key-range"
    assert evidence["config"] == {
        "format": "toml", "kind": "section", "name": "response", "locator": "exact-task-key"
    }
    assert evidence["lines"] == [3, 5]
    assert evidence["content"] == "[response]\nmode='active'\nfeature='ember'"
    assert "legacy" not in evidence["content"]


def test_json_key_range_uses_valid_json_and_one_key_line(tmp_path: Path) -> None:
    _repo(tmp_path, "policy.json", '{\n  "mode": "active",\n  "feature": "ember"\n}\n')
    start = _start(tmp_path, "Change ember policy config accepted response mode")
    evidence = start["edit_evidence"]
    assert evidence["representation"] == "config-key-range"
    assert evidence["lines"] == [2, 2]
    assert evidence["content"] == '  "mode": "active",'
    assert evidence["config"]["format"] == "json"


def test_yaml_nested_key_range_uses_task_supported_path(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        "policy.yaml",
        "response:\n  mode: active\n  feature: ember\nother:\n  mode: legacy\n",
    )
    start = _start(tmp_path, "Change ember response mode in the policy config")
    evidence = start["edit_evidence"]
    assert evidence["representation"] == "config-key-range"
    assert evidence["config"] == {
        "format": "yaml", "kind": "key", "name": "response.mode", "locator": "exact-task-key"
    }
    assert evidence["lines"] == [2, 2]
    assert evidence["content"] == "  mode: active"


def test_ambiguous_yaml_key_fails_closed_instead_of_guessing(tmp_path: Path) -> None:
    _repo(
        tmp_path,
        "policy.yaml",
        "primary:\n  mode: active\nsecondary:\n  mode: legacy\n",
    )
    start = _start(tmp_path, "Change ember policy config mode")
    assert start["edit"] == "src/case/policy.yaml"
    assert start["edit_evidence"] is None
    assert start["next_read"]["reason"] == "ambiguous-task-local-config-key"
    assert start["next_read"]["candidate_count"] == 2
    assert start["source_budget"]["complete"] is False


def test_config_range_over_budget_is_not_clipped(tmp_path: Path) -> None:
    _repo(tmp_path, "policy.toml", "mode='this-is-a-long-active-policy-value'\nfeature='ember'\n")
    start = _start(tmp_path, "Change ember policy config accepted response mode", token_budget=1)
    assert start["edit_evidence"] is None
    assert start["next_read"]["reason"] == "exact-config-range-exceeds-start-budget"
    assert start["next_read"]["lines"] == [1, 1]
    assert start["next_read"]["config"]["name"] == "mode"


def test_invalid_json_config_does_not_project_source(tmp_path: Path) -> None:
    _repo(tmp_path, "policy.json", '{\n  "mode": "active",\n}\n')
    start = _start(tmp_path, "Change ember policy config accepted response mode")
    assert start["edit_evidence"] is None
    assert start["next_read"]["reason"] == "invalid-config-syntax"
