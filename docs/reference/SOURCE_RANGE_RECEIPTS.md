# Exact source byte-range receipts

`CodeMap.source.range_receipt()` returns original bytes for one contiguous range
of one admitted repository member. It extends the existing Source owner and
stable member read. The direct Python component, CLI, MCP, and CodeMap service
client all return the same canonical receipt.

```python
import base64

from hashmarks import CodeMap

with CodeMap(".") as codemap:
    codemap.index.sync()
    receipt = codemap.source.range_receipt("src/example.py", start_byte=0, end_byte=12)
    if receipt["availability"] == "observed":
        original_bytes = base64.b64decode(receipt["content"]["data"], validate=True)
```

## Transport entry points

The CLI selects the range mode explicitly:

```bash
hashmarks --workspace . source-observation src/example.py \
  --result-mode range --start-byte 0 --end-byte 12
```

MCP uses the existing `source_observation` tool with one path,
`result_mode: "range"`, and
`byte_range: {"start_byte": 0, "end_byte": 12}`. The coordinates retain their
JSON scalar types, so boolean and fractional coordinates are rejected.
`CodeMapServiceClient.source_range_receipt(path, start_byte=0, end_byte=12)` is
the flat service method. Optional `max_bytes` selects the whole-member budget.
CLI and MCP also support the existing optional evidence presentations; the
original receipt remains in the presentation envelope.

CLI and MCP synchronize the requested path at their existing request boundary.
Service callers use `client.sync(...)` when they need to reconcile current source;
the receipt preserves the Source owner's generation and freshness qualifications.
The Identity daemon has a separate identity/inventory contract.

## Contract

Schema: `hashmarks.source-range-receipt.v1`.

Coordinates are **zero-based, half-open byte offsets**: `[start_byte, end_byte)`.
They do not count Unicode codepoints or physical lines. Both coordinates and
`max_bytes` must be integers; booleans are rejected. Negative offsets, reversed
ranges, and invalid budgets raise `ValueError` before a member read. An endpoint
beyond a successfully observed member also raises `ValueError`.

The byte budget covers the **whole member** needed to establish its revision,
not just the requested range. Its default is 1 MiB and maximum is 8 MiB, matching
the existing Source observation bound. An oversized or unavailable member returns
an unavailable receipt, so its range bounds cannot be established.

| Field | Meaning |
| --- | --- |
| `member` | Canonical path, full-member revision, admission/visibility and index state from Source. |
| `range` | Coordinate system and the exact requested offsets. |
| `content` | Base64-encoded original bytes, selected byte count, and `sha256:` content digest. |
| `source_byte_count` | Full member byte count from the same captured bytes. |
| `observation_identity` | Domain-separated range identity binding path, full-member revision, coordinates, full byte count, and selected content digest. |
| `generation`, `identity_generation`, `freshness` | Existing read-scope freshness authority; `current`, `stale`, or `unknown` remains distinct from content identity. |
| `completeness`, `truncation` | Complete for the exact observed range, unknown when unavailable. These fields do not describe repository-wide coverage. |

The content digest identifies just the selected bytes. The observation identity
also changes when the path, coordinates, or **any byte of the full member** changes,
even if the selected bytes are unchanged. Changing only an adequate byte budget
does not change the identity. The receipt is a point-in-time observation, not a
promise that subsequent filesystem reads will contain those bytes.

LF, CRLF, final-newline presence, BOMs, invalid UTF-8, NUL bytes, and offsets inside
a multibyte character are preserved without decoding or normalization. Source
admission and visibility still apply. A zero-length in-bounds range is observed
as empty bytes; `[0, 0)` is valid for an empty member. Empty ranges never establish
negative repository evidence.

Denied, outline-only, symlink, missing, unstable, oversized, or unreconciled indexed
members expose no content and no observation identity. Source reports the reason
in `member`. A generation change during observation marks the receipt stale;
unknown freshness is never upgraded to current. Consumers must evaluate freshness
separately from the range's byte completeness.

`source.slice()` retains its display-oriented text behavior. Consumers needing
original bytes use this receipt or the existing `source.member(include_bytes=True)`.
No second filesystem read, source cache, or repository index is introduced.

## Observer ownership

- **Observed evidence:** exact original bytes and coordinates inside an admitted member.
- **Authority source:** Source's canonical stable member capture and full-member revision.
- **Completeness/freshness:** explicit range scope, existing generation authority, unknown on unavailable evidence.
- **Existing owner extended:** `RepositorySource`.
- **Consumer responsibility:** choosing ranges, interpreting the bytes, editing, and executing remain external.
- **Decision:** OBSERVER.

Regression coverage: `tests/test_source_range_receipt.py`,
`tests/test_observation_transport_completion.py`, and
`tests/test_standalone_codemap_service_observations.py`.
