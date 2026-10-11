"""Retrieved lexical class members never acquire owner/runtime authority."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from hashmarks.codemap import CodeMap
from hashmarks.digest import FILE_DOMAIN, hash_file
from hashmarks.evidence_presentation import FORMATS, presentation_response


def _context(packet: dict) -> dict:
    return next(
        row["class_declarations"]
        for row in packet["retrieval"]["results"]
        if "class_declarations" in row
    )


def test_retrieved_class_exposes_exact_direct_members_in_every_format(
    tmp_path: Path,
) -> None:
    path = tmp_path / "backend.py"
    path.write_text(
        "class Base:\n    def inherited(self): pass\n"
        "class ChannelBackend(Base):\n"
        "    async def subscribe(self):\n        await self._listener()\n"
        "    class Inner:\n        def unrelated(self): pass\n"
        "    def stop(self): pass\n"
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = cm.task_evidence("Inspect ChannelBackend subscription behavior")
        initial = cm.task_evidence(
            "Inspect ChannelBackend subscription behavior", result_mode="initial"
        )
    context = _context(packet)
    assert context["declarations"] == [
        {
            "path": "backend.py",
            "symbol": "ChannelBackend.subscribe",
            "start_line": 4,
            "end_line": 5,
        },
        {
            "path": "backend.py",
            "symbol": "ChannelBackend.stop",
            "start_line": 8,
            "end_line": 8,
        },
    ]
    assert context["source_revision"] == hash_file(path, domain=FILE_DOMAIN).hash
    assert context["ownership_authority"] is False
    assert context["negative_evidence_admissible"] is False
    assert context["runtime_members"] == "not-established"
    assert _context(initial) == context
    for mode in FORMATS:
        response = presentation_response("task_evidence", packet, format=mode)
        native = response.get("result", response)
        assert isinstance(native, dict)
        assert _context(native) == context


def test_lexical_member_bound_accounts_for_omissions_without_runtime_absence(
    tmp_path: Path,
) -> None:
    (tmp_path / "backend.py").write_text(
        "class ChannelBackend:\n"
        + "".join(f"    def member_{i}(self): pass\n" for i in range(30))
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = cm.task_evidence("Inspect ChannelBackend")
    context = _context(packet)
    assert (context["observed"], context["returned"], context["omitted"]) == (
        30,
        16,
        14,
    )
    assert len(context["declarations"]) == 16
    assert context["negative_evidence_admissible"] is False


def test_reopened_stale_class_cannot_disclose_old_members_as_current(
    tmp_path: Path,
) -> None:
    path = tmp_path / "backend.py"
    path.write_text("class ChannelBackend:\n    def obsolete(self): pass\n")
    state = tmp_path / "state"
    with CodeMap(tmp_path, state_dir=state) as cm:
        cm.sync()
        cm.task_evidence("Inspect ChannelBackend")
    path.write_text("class ChannelBackend:\n    def current_member(self): pass\n")
    with CodeMap(tmp_path, state_dir=state) as cm:
        packet = cast("dict", cm.task_evidence("Inspect ChannelBackend"))
    for row in packet["retrieval"]["results"]:
        if "class_declarations" in row:
            context = row["class_declarations"]
            assert (
                context["source_revision"] == hash_file(path, domain=FILE_DOMAIN).hash
            )
            assert all(
                decl["symbol"] != "ChannelBackend.obsolete"
                for decl in context["declarations"]
            )


@pytest.mark.parametrize("visibility", ["outline", "deny"])
def test_class_disclosure_respects_source_visibility(
    tmp_path: Path, visibility: str
) -> None:
    (tmp_path / "backend.py").write_text(
        "class ChannelBackend:\n    def subscribe(self): return 'private_body_literal'\n"
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        f'[[rule]]\npattern = "backend.py"\nvisibility = "{visibility}"\n'
    )
    with CodeMap(tmp_path) as cm:
        cm.sync()
        packet = cm.task_evidence("Inspect ChannelBackend")
    assert "private_body_literal" not in json.dumps(packet)
    if visibility == "deny":
        assert "class_declarations" not in json.dumps(packet)
    else:
        assert (
            _context(packet)["declarations"][0]["symbol"] == "ChannelBackend.subscribe"
        )
