from pathlib import Path

from hashmarks.codemap import CodeMap


def test_action_ambiguity_explains_plausibility_and_discriminator_without_secret(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "widget.py").write_text("def widget():\n    return 1\n")
    (tmp_path / "tests" / "test_widget.py").write_text(
        "from src.widget import widget\ndef test_widget(): assert widget() == 1\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        action = codemap.task_action_map("widget implementation test", limit=20)
    ambiguity = action["ambiguity"]
    assert ambiguity["schema"] == "hashmarks.action-ambiguity.v2"
    assert ambiguity["secret_knowledge_used"] is False
    if ambiguity["ambiguous"]:
        assert len(ambiguity["candidates"]) >= 2
        assert all(row["plausibility"] for row in ambiguity["candidates"])
        assert all(row["discriminator"] for row in ambiguity["candidates"])
        assert ambiguity["discrimination_question"]


def test_decision_packet_carries_ambiguity_only_when_scout_needs_it(
    tmp_path: Path,
) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "widget.py").write_text("def widget():\n    return 1\n")
    (tmp_path / "tests" / "test_widget.py").write_text(
        "def test_widget(): assert True\n"
    )
    with CodeMap(tmp_path) as codemap:
        codemap.sync()
        packet = codemap.task_decision_packet("widget implementation test", limit=20)
    if (
        packet["discrimination"]["needed"]
        and packet["discrimination"]["reason"] == "competing-action-roles"
    ):
        assert (
            packet["discrimination"]["ambiguity"]["schema"]
            == "hashmarks.action-ambiguity.v2"
        )
    else:
        assert packet["discrimination"]["ambiguity"] is None
