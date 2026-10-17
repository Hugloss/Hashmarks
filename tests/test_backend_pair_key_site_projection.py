"""C05-C08: literal site pairing is bounded syntax, never runtime compatibility."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from hashmarks import CodeMap
from hashmarks.codemap.static_python_interface_declarations import (
    StaticPythonInterfaceDeclarations,
)
from hashmarks.evidence_presentation import present_repository_evidence
from hashmarks.evidence_presentation_conformance import validate_evidence_presentation

PAIRS = (("api.py", "serve", "client.py", "render", "response"),)


def _repo(root: Path) -> None:
    (root / "api.py").write_text(
        '@router.get("/items")\n'
        "def serve():\n"
        "    if flag:\n"
        '        return {"id": 1}\n'
        '    return {"name": "Ada", "age": 2}\n',
        encoding="utf-8",
    )
    (root / "client.py").write_text(
        "def render(response):\n"
        '    value = response["name"]\n'
        '    other = payload["id"]\n'
        '    response["id"] = 5\n'
        "    def nested():\n"
        '        return response["nested"]\n'
        "    return value\n",
        encoding="utf-8",
    )


def _provider(*, projected: bool) -> StaticPythonInterfaceDeclarations:
    return StaticPythonInterfaceDeclarations(
        paths=("api.py", "client.py"),
        consumer_pairs=PAIRS,
        include_pair_key_site_projection=projected,
    )


def _observe(root: Path, *, projected: bool) -> dict:
    with CodeMap(root) as cm:
        cm.index.sync()
        return cm.discover_repository_declarations([_provider(projected=projected)])


def _paired_group(packet: dict) -> dict:
    (group,) = [
        group
        for group in packet["declarations"]["groups"]
        if group["concept"]["kind"] == "nominated-python-interface-syntax-pair"
    ]
    return group


def _key_site_projection(packet: dict) -> dict:
    group = _paired_group(packet)
    (consumer,) = [
        value
        for value in group["declarations"]
        if value["declaration_id"] == "consumer-subscript-read-syntax"
    ]
    return consumer["value"]["literal_key_site_projection"]


def test_c05_literal_match_is_only_per_return_site_syntax(tmp_path: Path) -> None:
    _repo(tmp_path)
    packet = _observe(tmp_path, projected=True)
    group = _paired_group(packet)
    summary = _key_site_projection(packet)
    assert summary["state"] == "bounded-direct-literal-site-projection"
    assert summary["coverage"] == "incomplete"
    assert summary["producer_consumer_correspondence"] == "unresolved"
    assert summary["runtime_response_shape"] == "unknown"
    assert summary["runtime_consumer_binding"] == "unknown"
    assert summary["runtime_compatibility"] == "not-asserted"
    assert summary["missing_field_conclusion"] == "not-admissible"
    assert summary["negative_evidence_admissible"] is False
    assert summary["consumer_read_sites_observed"] == 1
    assert summary["producer_return_sites_observed"] == 2
    (row,) = summary["observations"]
    assert row["consumer_site"] == {
        "path": "client.py",
        "start_line": 2,
        "end_line": 2,
    }
    assert row["consumer_literal_key"] == "name"
    assert row["producer_return_sites"] == [
        {
            "path": "api.py",
            "start_line": 4,
            "end_line": 4,
            "syntax_relation": "different-literal-key-at-site",
        },
        {
            "path": "api.py",
            "start_line": 5,
            "end_line": 5,
            "syntax_relation": "same-literal-key-at-site",
        },
    ]
    assert group["comparison"]["state"] == "ambiguous"
    assert group["correspondence"]["state"] == "unresolved"
    assert group["absence"]["state"] == "unknown"
    projected = present_repository_evidence(packet["declarations"], format="compact")
    assert projected["supported"] is True
    assert (
        validate_evidence_presentation(packet["declarations"], projected)["valid"]
        is True
    )


def test_c06_unresolved_returns_do_not_make_absence_claims(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "api.py").write_text(
        '@router.get("/items")\n'
        "def serve():\n"
        "    if flag:\n"
        "        return factory()\n"
        "    return {'id': 3}\n",
        encoding="utf-8",
    )
    summary = _key_site_projection(_observe(tmp_path, projected=True))
    relations = [
        site["syntax_relation"]
        for site in summary["observations"][0]["producer_return_sites"]
    ]
    assert relations == [
        "producer-return-syntax-unresolved",
        "different-literal-key-at-site",
    ]
    assert summary["missing_field_conclusion"] == "not-admissible"
    assert summary["runtime_compatibility"] == "not-asserted"


def test_c07_site_omissions_are_explicit_and_deterministic(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "api.py").write_text(
        "@router.get('/items')\ndef serve():\n"
        + "".join(
            f"    if value == {i}:\n        return {{'field{i}': {i}}}\n"
            for i in range(12)
        ),
        encoding="utf-8",
    )
    (tmp_path / "client.py").write_text(
        "def render(response):\n"
        + "".join(f'    value_{i} = response["field{i}"]\n' for i in range(12)),
        encoding="utf-8",
    )
    first = _key_site_projection(_observe(tmp_path, projected=True))
    second = _key_site_projection(_observe(tmp_path, projected=True))
    assert first == second
    assert first["producer_return_sites_observed"] == 12
    assert first["producer_return_sites_retained"] == 8
    assert first["producer_return_sites_omitted"] == 4
    assert first["consumer_read_sites_observed"] == 12
    assert first["consumer_read_sites_retained"] == 8
    assert first["consumer_read_sites_omitted"] == 4
    assert len(first["observations"]) == 8
    assert all(len(row["producer_return_sites"]) == 8 for row in first["observations"])
    assert first["negative_evidence_admissible"] is False


def test_c08_explicit_opt_in_preserves_prior_pair_packet_and_identity(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        prior = cm.discover_repository_declarations(
            [
                StaticPythonInterfaceDeclarations(
                    paths=("api.py", "client.py"), consumer_pairs=PAIRS
                )
            ]
        )
        off = cm.discover_repository_declarations([_provider(projected=False)])
        on = cm.discover_repository_declarations([_provider(projected=True)])
    assert prior == off
    assert "pair_key_site_projection" not in prior["providers"][0]["provenance"]
    assert prior["observation_identity"] != on["observation_identity"]
    assert "literal_key_site_projection" not in json.dumps(prior)
    assert _key_site_projection(on)["state"] == "bounded-direct-literal-site-projection"


@pytest.mark.parametrize("invalid", [None, 1, "true", [], {}, 0])
def test_c08_option_type_is_rejected_before_source_reads(invalid: object) -> None:
    with pytest.raises(ValueError, match="include_pair_key_site_projection"):
        StaticPythonInterfaceDeclarations(
            paths=("api.py", "client.py"),
            consumer_pairs=PAIRS,
            include_pair_key_site_projection=invalid,  # type: ignore[arg-type]
        )


def test_c08_pair_is_required_for_opt_in() -> None:
    with pytest.raises(ValueError, match="requires consumer_pairs"):
        StaticPythonInterfaceDeclarations(
            paths=("api.py",),
            include_pair_key_site_projection=True,
        )


def test_c08_named_receiver_scope_and_missing_candidate_are_unknown(
    tmp_path: Path,
) -> None:
    _repo(tmp_path)
    (tmp_path / "client.py").write_text(
        "def render(response):\n"
        '    x = other["id"]\n'
        '    response["id"] = 3\n'
        "    def nested():\n"
        '        return response["secret"]\n'
        "    return x\n",
        encoding="utf-8",
    )
    packet = _observe(tmp_path, projected=True)
    summary = _key_site_projection(packet)
    assert summary["consumer_read_sites_observed"] == 0
    assert summary["observations"] == []
    assert summary["coverage"] == "incomplete"
    assert _paired_group(packet)["absence"]["state"] == "unknown"


def test_c08_mutation_rebinds_literal_sites_on_new_revision(tmp_path: Path) -> None:
    _repo(tmp_path)
    with CodeMap(tmp_path) as cm:
        cm.index.sync()
        original = cm.discover_repository_declarations([_provider(projected=True)])
        source = tmp_path / "client.py"
        source.write_text(
            source.read_text(encoding="utf-8").replace(
                'response["name"]', 'response["id"]'
            ),
            encoding="utf-8",
        )
        cm.index.sync(["client.py"])
        changed = cm.discover_repository_declarations(
            [_provider(projected=True)],
            previous_observation=original,
        )
    assert original["observation_identity"] != changed["observation_identity"]
    assert (
        _key_site_projection(changed)["observations"][0]["consumer_literal_key"] == "id"
    )
    assert (
        _key_site_projection(original)["observations"][0]["consumer_literal_key"]
        == "name"
    )


def test_c08_denied_consumer_never_leaks_keys(tmp_path: Path) -> None:
    _repo(tmp_path)
    (tmp_path / "client.py").write_text(
        'def render(response):\n    return response["CONFIDENTIAL_FIELD"]\n',
        encoding="utf-8",
    )
    (tmp_path / ".hashmarks-context.toml").write_text(
        '[[rule]]\npattern = "client.py"\nvisibility = "deny"\n',
        encoding="utf-8",
    )
    from hashmarks.codemap.repository_declaration_provider import (
        RepositoryDeclarationProviderError,
    )

    with pytest.raises(RepositoryDeclarationProviderError) as caught:
        _observe(tmp_path, projected=True)
    assert "CONFIDENTIAL_FIELD" not in str(caught.value)
