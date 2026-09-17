from __future__ import annotations

import argparse
import json
from pathlib import Path

from hashmarks.consumer_conformance import consumer_conformance_vectors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Emit deterministic Hashmarks downstream-consumer conformance vectors."
    )
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    vectors = consumer_conformance_vectors(Path(args.root).resolve())
    payload = {
        "schema": "hashmarks.consumer-conformance-suite.v1",
        "vectors": list(vectors),
        "execution_authority": "external",
        "result_authority": "external",
        "certification_authority": "external",
    }
    print(json.dumps(payload, indent=2, sort_keys=True))  # noqa: T201 - intentional command output
    return (
        0
        if all(row["result"]["valid"] == row["expected_valid"] for row in vectors)
        else 2
    )


if __name__ == "__main__":
    raise SystemExit(main())
