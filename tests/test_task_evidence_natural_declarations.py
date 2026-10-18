"""Natural-language disclosure retains exact declarations without edit authority."""

from pathlib import Path

from contract_assertions import assert_object, assert_records

from hashmarks.codemap import CodeMap
from hashmarks.codemap.task_evidence_initial import decode_initial_packet
from hashmarks.codemap.task_retrieval import TaskRetrievalMixin


def test_word_variants_keep_derivation_modes_separate_when_reused() -> None:
    for word in ("validation", "__VALIDATION--", "validation"):
        for mode in (False, True, False, True):
            variants = TaskRetrievalMixin._task_natural_term_variants(
                word, include_derivations=mode
            )
            assert isinstance(variants, tuple)
            assert variants == (
                ("validation", "validate", "valide") if mode else ("validation",)
            )


def _surface_identity(value: object) -> tuple[object, ...] | None:
    if value is None:
        return None
    row = assert_object(value)
    return tuple(
        row.get(field)
        for field in (
            "path",
            "qualname",
            "start_line",
            "end_line",
            "roles",
            "evidence_visibility",
        )
    )


def test_derived_query_words_find_declared_parameters_and_same_named_methods(
    tmp_path: Path,
) -> None:
    (tmp_path / "model.py").write_text(
        "class Record: pass\nclass RecordBuffer: pass\nclass Rule: pass\n"
    )
    (tmp_path / "rules.py").write_text(
        "class Validator:\n"
        "    def validate_records(self, records, *, rule_name):\n"
        "        return records\n"
        "class StringValidator(Validator):\n"
        "    def validate_records(self, records):\n"
        "        return super().validate_records(records, rule_name='default')\n"
    )
    task = "Investigate record validation failing when the backend does not supply its rule name."
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packets = [
            codemap.tasks.evidence(task),
            decode_initial_packet(codemap.tasks.evidence(task, result_mode="initial")),
        ]
    for packet in packets:
        rows = assert_records(assert_object(packet["retrieval"])["results"])
        assert {"Validator.validate_records", "StringValidator.validate_records"} <= {
            row.get("symbol") for row in rows[:3] if row["path"] == "rules.py"
        }
        assert assert_object(packet["ownership"])["owner"] == action["admitted_edit"]
        ambiguity = assert_object(assert_object(packet["ownership"])["ambiguity"])
        assert ambiguity["ambiguous"] == action["ambiguity"]["ambiguous"]
        assert ambiguity["reason"] == action["ambiguity"]["reason"]
        for field in ("candidates", "alternatives"):
            expected = assert_records(action["ambiguity"][field])
            observed = assert_records(ambiguity[field])
            assert [
                (
                    r.get("path"),
                    r.get("qualname"),
                    r.get("start_line"),
                    r.get("end_line"),
                )
                for r in observed
            ] == [
                (
                    r.get("path"),
                    r.get("qualname"),
                    r.get("start_line"),
                    r.get("end_line"),
                )
                for r in expected
            ]
        assert _surface_identity(
            assert_object(packet["verification"])["selected"]
        ) == _surface_identity(action["verify"])


def test_declaration_context_disambiguates_multiword_retrieval_hints(
    tmp_path: Path,
) -> None:
    (tmp_path / "expressions.py").write_text(
        "class RecordExpression: pass\n"
        "class aggregate_records: pass\n"
        "def raised_expression_error(): pass\n"
    )
    (tmp_path / "compiler.py").write_text(
        "class RecordCompiler:\n"
        "    def aggregate_records(self, record, *, function_name):\n"
        "        return record\n"
        "class StringRecordCompiler(RecordCompiler):\n"
        "    def aggregate_records(self, record):\n"
        '        return super().aggregate_records(record, function_name="default")\n'
    )
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests/test_expressions.py").write_text(
        "def test_aggregate_records_backend(): pass\n"
        "def test_record_expression_backend(): pass\n"
    )
    task = "Compiling a record aggregation expression fails when the backend does not supply its function name."
    with CodeMap(tmp_path) as codemap:
        codemap.index.sync()
        action = codemap.tasks.action_map(task)
        packets = [
            codemap.tasks.evidence(task),
            decode_initial_packet(codemap.tasks.evidence(task, result_mode="initial")),
        ]
    for packet in packets:
        rows = assert_records(assert_object(packet["retrieval"])["results"])
        assert {
            "RecordCompiler.aggregate_records",
            "StringRecordCompiler.aggregate_records",
        } <= {row.get("symbol") for row in rows[:3] if row["path"] == "compiler.py"}
        assert assert_object(packet["retrieval"])["ownership_authority"] is False
        assert assert_object(packet["ownership"])["owner"] == action["admitted_edit"]
        ambiguity = assert_object(assert_object(packet["ownership"])["ambiguity"])
        assert ambiguity["ambiguous"] == action["ambiguity"]["ambiguous"]
        assert ambiguity["reason"] == action["ambiguity"]["reason"]
        for field in ("candidates", "alternatives"):
            expected = assert_records(action["ambiguity"][field])
            observed = assert_records(ambiguity[field])
            assert [
                (
                    r.get("path"),
                    r.get("qualname"),
                    r.get("start_line"),
                    r.get("end_line"),
                )
                for r in observed
            ] == [
                (
                    r.get("path"),
                    r.get("qualname"),
                    r.get("start_line"),
                    r.get("end_line"),
                )
                for r in expected
            ]
        assert _surface_identity(
            assert_object(packet["verification"])["selected"]
        ) == _surface_identity(action["verify"])
