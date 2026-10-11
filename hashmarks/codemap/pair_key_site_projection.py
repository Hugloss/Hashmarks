"""Bounded presentation of caller-nominated literal key sites, not API compatibility.

These rows project *only* the source-bound sites emitted by the single existing
handler-body syntax extractor. Matching words across files prove neither a
runtime producer/consumer link nor a complete field contract.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

MAX_PROJECTED_CONSUMER_SITES = 8
MAX_PROJECTED_RETURN_SITES = 8


def _return_relation(site: Mapping[str, object], literal: str) -> str:
    keys = site.get("literal_keys_in_source_order")
    if not isinstance(keys, list):
        return "producer-return-syntax-unresolved"
    return (
        "same-literal-key-at-site"
        if literal in keys
        else "different-literal-key-at-site"
    )


def project_pair_key_sites(
    returns: Sequence[Mapping[str, object]],
    reads: Sequence[Mapping[str, object]],
    *,
    producer_path: str,
    consumer_path: str,
) -> dict[str, object]:
    """Project direct literal spelling per observed return/read site only."""
    selected_returns = returns[:MAX_PROJECTED_RETURN_SITES]
    selected_reads = reads[:MAX_PROJECTED_CONSUMER_SITES]
    rows: list[dict[str, object]] = []
    for read in selected_reads:
        literal = str(read["literal_key"])
        rows.append(
            {
                "consumer_site": {
                    "path": consumer_path,
                    "start_line": read["line"],
                    "end_line": read["end_line"],
                },
                "consumer_literal_key": literal,
                "producer_return_sites": [
                    {
                        "path": producer_path,
                        "start_line": site["line"],
                        "end_line": site["end_line"],
                        "syntax_relation": _return_relation(site, literal),
                    }
                    for site in selected_returns
                ],
            }
        )
    return {
        "state": "bounded-direct-literal-site-projection",
        "input_authority": "caller-nominated-pair-and-source-bound-handler-sites",
        "comparison_authority": "literal-spelling-at-individual-source-sites-only",
        "producer_return_sites_observed": len(returns),
        "producer_return_sites_retained": len(selected_returns),
        "producer_return_sites_omitted": len(returns) - len(selected_returns),
        "consumer_read_sites_observed": len(reads),
        "consumer_read_sites_retained": len(selected_reads),
        "consumer_read_sites_omitted": len(reads) - len(selected_reads),
        "limits": {
            "return_sites": MAX_PROJECTED_RETURN_SITES,
            "consumer_read_sites": MAX_PROJECTED_CONSUMER_SITES,
        },
        "observations": rows,
        "producer_consumer_correspondence": "unresolved",
        "runtime_response_shape": "unknown",
        "runtime_consumer_binding": "unknown",
        "runtime_compatibility": "not-asserted",
        "missing_field_conclusion": "not-admissible",
        "coverage": "incomplete",
        "negative_evidence_admissible": False,
    }
