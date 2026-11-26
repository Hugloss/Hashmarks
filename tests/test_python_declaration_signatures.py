import sys
from pathlib import Path

import pytest
from contract_assertions import assert_records

from hashmarks import CodeMap


@pytest.mark.parametrize(
    ("header", "name"),
    [
        ("class Pipeline(**settings)", "Pipeline"),
        (
            "class Worker(Base, *mixins, metaclass=Factory, **options, **extras)",
            "Worker",
        ),
    ],
)
def test_class_keyword_unpacking_survives_outline_and_source(
    tmp_path: Path, header: str, name: str
) -> None:
    (tmp_path / "api.py").write_text(header + ": pass\n")
    with CodeMap(tmp_path) as repository:
        outline = repository.source.outline("api.py")
        (row,) = assert_records(outline["symbols"])
        assert row["qualname"] == name and row["signature"] == header
        source = repository.source.read(f"api.py::{name}")
        assert source["signature"] == header and source["content"] == header + ": pass"


@pytest.mark.skipif(
    sys.version_info < (3, 12), reason="Native PEP 695 grammar required"
)
@pytest.mark.parametrize(
    ("name", "signature"),
    [
        ("Bucket", "class Bucket[T: Item, *Ts](Root[T], **options)"),
        ("invoke", "def invoke[**P, R](fn: Fn[P, R]) -> R: ..."),
        ("retain", "async def retain[T](item: T) -> T: ..."),
        pytest.param(
            "choose",
            "def choose[T: Base = Default](item: T) -> T: ...",
            marks=pytest.mark.skipif(
                sys.version_info < (3, 13),
                reason="Native type parameter defaults required",
            ),
        ),
    ],
)
def test_native_generic_parameters_survive_signature_projection(
    tmp_path: Path, name: str, signature: str
) -> None:
    source_text = signature + (": pass" if name == "Bucket" else "")
    (tmp_path / "api.pyi").write_text(source_text + "\n")
    with CodeMap(tmp_path) as repository:
        (row,) = assert_records(repository.source.outline("api.pyi")["symbols"])
        assert row["qualname"] == name and row["signature"] == signature
        source = repository.source.read(f"api.pyi::{name}")
        assert source["signature"] == signature and source["content"] == source_text
