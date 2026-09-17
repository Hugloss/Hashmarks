from hashmarks.symbolic_identity import symbolic_nomination_record, symbolic_task_terms


def test_symbolic_terms_bridge_camel_and_snake_case() -> None:
    terms = symbolic_task_terms("Fix NormalizeWidget and package.ServiceAdapter")
    assert "NormalizeWidget" in terms
    assert "normalize_widget" in terms
    assert "ServiceAdapter" in terms
    assert "service_adapter" in terms


def test_symbolic_nomination_fails_closed_on_competing_paths() -> None:
    result = symbolic_nomination_record(
        task="Fix NormalizeWidget",
        terms=("NormalizeWidget", "normalize_widget"),
        candidates=(
            {"path": "a.py", "name": "normalize_widget", "kind": "function"},
            {"path": "b.py", "name": "normalize_widget", "kind": "function"},
        ),
    )
    assert result["status"] == "ambiguous"
    assert result["authority"] == "nomination-only"
    assert result["ranking_effect"] == "none"


def test_decision_packet_exposes_nomination_without_ranking_authority(tmp_path) -> None:
    from hashmarks.codemap import CodeMap

    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "widget.py").write_text(
        "def normalize_widget(value):\n    return value.strip().lower()\n"
    )
    (tmp_path / "tests" / "test_widget.py").write_text(
        "from src.widget import normalize_widget\n"
        "def test_normalize_widget():\n"
        "    assert normalize_widget(' X ') == 'x'\n"
    )

    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet(
            "Fix NormalizeWidget implementation",
            limit=20,
        )

    nomination = packet["symbolic_nomination"]
    assert "normalize_widget" in nomination["terms"]
    assert nomination["status"] in {"resolved", "ambiguous"}
    assert any(row["name"] == "normalize_widget" for row in nomination["candidates"])
    assert nomination["authority"] == "nomination-only"
    assert nomination["ranking_effect"] == "none"
    assert packet["ranking_effect"] == "none"
