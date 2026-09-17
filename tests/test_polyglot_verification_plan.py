from pathlib import Path

from hashmarks.codemap import CodeMap


def test_node_test_verification_plan_is_bounded(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "ember.test.js").write_text(
        "import test from 'node:test';\nimport assert from 'node:assert/strict';\n",
        encoding="utf-8",
    )
    with CodeMap(tmp_path) as codemap:
        plan = codemap.verification_plan("tests/ember.test.js")
    assert plan["available"] is True
    assert plan["runner"] == "node-test"
    assert plan["argv"] == ["node", "--test", "tests/ember.test.js"]


def test_typescript_verification_plan_uses_existing_tsconfig(tmp_path: Path) -> None:
    (tmp_path / "tsconfig.json").write_text('{"compilerOptions":{"strict":true}}\n', encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "ember.test.ts").write_text("export const expected: 'ember' = 'ember';\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        plan = codemap.verification_plan("tests/ember.test.ts")
    assert plan["available"] is True
    assert plan["runner"] == "typescript-compiler"
    assert plan["argv"] == ["tsc", "--noEmit", "-p", "tsconfig.json"]


def test_local_vitest_takes_precedence_for_typescript(tmp_path: Path) -> None:
    (tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    (tmp_path / "node_modules" / ".bin" / "vitest").write_text("", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "ember.test.ts").write_text("test('ember', () => {});\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        plan = codemap.verification_plan("tests/ember.test.ts")
    assert plan["available"] is True
    assert plan["runner"] == "vitest"
    assert plan["argv"] == ["node_modules/.bin/vitest", "run", "tests/ember.test.ts"]


def test_go_test_file_is_classified_as_verification_surface(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.local/demo\n\ngo 1.23\n", encoding="utf-8")
    (tmp_path / "route").mkdir()
    (tmp_path / "route" / "route.go").write_text("package route\nfunc Ember731() string { return \"old\" }\n", encoding="utf-8")
    (tmp_path / "route" / "route_test.go").write_text("package route\nimport \"testing\"\nfunc TestEmber731(t *testing.T) {}\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        brief = codemap.task_action_brief("Change Ember731 accepted response")
    assert brief["verify"] == ["go", "test", "./route"]


def test_javascript_test_file_is_classified_as_verification_surface(tmp_path: Path) -> None:
    (tmp_path / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    (tmp_path / "src").mkdir(); (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "ember.js").write_text("export function Ember731(){ return 'old' }\n", encoding="utf-8")
    (tmp_path / "tests" / "ember.test.js").write_text("import test from 'node:test';\n// Ember731\n", encoding="utf-8")
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        brief = codemap.task_action_brief("Change Ember731 accepted response")
    assert brief["verify"] == ["node", "--test", "tests/ember.test.js"]
