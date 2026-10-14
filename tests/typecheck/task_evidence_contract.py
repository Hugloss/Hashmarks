"""Static consumer examples, checked with the configured ty and Pyright tools."""

from __future__ import annotations

from typing import assert_type

from hashmarks.codemap import CodeMap
from hashmarks.codemap.ownership_relation_types import (
    OwnershipPathHop,
    OwnershipRelationGraph,
)
from hashmarks.codemap.service import CodeMapServiceClient
from hashmarks.codemap.task_evidence_contract import (
    read_initial_projection,
    read_task_evidence,
)
from hashmarks.codemap.task_evidence_initial import (
    decode_initial_packet,
    initial_task_evidence,
)
from hashmarks.codemap.task_evidence_types import (
    DiscriminationRead,
    InitialTaskEvidenceEnvelope,
    InitialTaskEvidenceProjection,
    RetrievalLocator,
    TaskActionMap,
    TaskCandidate,
    TaskEvidencePacket,
    TaskPostChangeDelta,
)
from hashmarks.mcp_surface import HashmarksMcpSurface


def check_task_evidence_types(codemap: CodeMap, mode: str) -> None:
    action = codemap.task_action_map("change owner")
    assert_type(action, TaskActionMap)
    assert_type(action["ownership_authority"]["owner_resolved"], bool)
    assert_type(action["edit"], TaskCandidate | None)

    packet = codemap.task_evidence("change owner")
    assert_type(packet, TaskEvidencePacket)
    assert_type(packet["ownership"]["owner"], TaskCandidate | None)
    assert_type(packet["retrieval"]["results"], list[RetrievalLocator])
    assert_type(packet["retrieval"]["bounds"]["canonical_truncation"], str)
    assert_type(packet["freshness"]["state"], str)
    assert_type(
        codemap.task_evidence("change owner", result_mode="default"),
        TaskEvidencePacket,
    )
    initial = codemap.task_evidence("change owner", result_mode="initial")
    assert_type(initial, InitialTaskEvidenceEnvelope)
    decode_initial_packet(initial)
    assert_type(
        codemap.task_evidence("change owner", result_mode=mode),
        TaskEvidencePacket | InitialTaskEvidenceEnvelope,
    )
    assert_type(
        codemap._task_evidence_discrimination_next_read(action),
        DiscriminationRead | None,
    )
    assert_type(
        codemap.task_post_change_delta(
            "change owner", ["owner.py"], previous_evidence=packet
        ),
        TaskPostChangeDelta,
    )


def check_transport_consumers(
    client: CodeMapServiceClient, surface: HashmarksMcpSurface, mode: str, raw: object
) -> None:
    assert_type(client.task_action_map("change owner"), TaskActionMap)
    graph = client.ownership_relation_graph("change owner", "test_owner.py")
    assert_type(graph, OwnershipRelationGraph)
    assert_type(graph["owner_path"], list[OwnershipPathHop])
    for hop in graph["owner_path"]:
        assert_type(hop["from"], str)
        assert_type(hop["to"], str)
        assert_type(hop["relation"], str)
    packet = client.task_evidence("change owner")
    assert_type(packet, TaskEvidencePacket)
    budget = packet["ownership"]["source_budget"]
    if budget is not None:
        assert_type(budget["complete"], bool)
    source = packet["ownership"]["source_evidence"]
    if source is not None:
        assert_type(source["content"], str)
    assert_type(packet["verification"]["plan"]["available"], bool)
    assert_type(packet["provenance"]["context_identity"], str)
    assert_type(
        client.task_post_change_delta(
            "change owner", ["owner.py"], previous_evidence=packet
        ),
        TaskPostChangeDelta,
    )
    assert_type(surface.task_evidence("change owner"), TaskEvidencePacket)
    assert_type(
        surface.task_evidence("change owner", result_mode="initial"),
        InitialTaskEvidenceEnvelope,
    )
    assert_type(
        surface.task_evidence("change owner", result_mode=mode),
        TaskEvidencePacket | InitialTaskEvidenceEnvelope,
    )
    assert_type(
        surface.post_change("change owner", ["owner.py"], packet), TaskPostChangeDelta
    )
    initial = initial_task_evidence(packet)
    assert_type(initial, InitialTaskEvidenceProjection)
    assert_type(
        initial["initial_projection"]["omissions"]["collections"]["/retrieval/results"][
            "omitted"
        ],
        int,
    )
    assert_type(read_initial_projection(raw), InitialTaskEvidenceProjection)
    assert_type(read_task_evidence(raw), TaskEvidencePacket)
