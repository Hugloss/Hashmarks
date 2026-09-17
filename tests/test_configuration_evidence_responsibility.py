from __future__ import annotations

from hashmarks.codemap.configuration_evidence import ConfigurationEvidenceMixin
from hashmarks.codemap.evidence_packet import TaskEvidencePacketMixin

_CONFIG_METHODS = {
    "_config_name_parts",
    "_config_task_terms",
    "_config_candidate_score",
    "_yaml_section_end",
    "_json_value_end",
    "_toml_config_candidates",
    "_json_config_candidates",
    "_yaml_config_candidates",
    "_task_evidence_config_evidence",
}


def test_configuration_projection_has_one_responsibility_owner() -> None:
    assert set(ConfigurationEvidenceMixin.__dict__) >= _CONFIG_METHODS
    assert _CONFIG_METHODS.isdisjoint(TaskEvidencePacketMixin.__dict__)
    assert issubclass(TaskEvidencePacketMixin, ConfigurationEvidenceMixin)
