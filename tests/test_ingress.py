"""FR-026 — strict JSON ingress (SPEC §11.0 ingress rules, §11.6 PreflightError).

The private ingress layer must reject malformed JSON, duplicate object keys,
non-finite numbers, unsupported ``schema_version``, and unreadable input
files, raising ``IngressError`` that carries PreflightError-shaped
``EngineError`` dicts (``type: "PreflightError"``, stable library message, no
``engine_type``, no ``case_id`` — OQ-011/OQ-014c) for the CLI to map to a
``CliError`` ``schema-error`` envelope with exit 2 (AC-021 groundwork).
"""

import json

import pytest

from transon_authoring._ingress import (
    SUPPORTED_SCHEMA_VERSION,
    IngressError,
    check_schema_version,
    load_document,
    load_json_file,
    loads_strict,
    schema_violations,
    validate_schema,
)


def assert_preflight_errors(exc: IngressError) -> None:
    """Every IngressError entry is a §11.6 PreflightError-shaped EngineError."""
    assert exc.errors, "IngressError must carry at least one error"
    for error in exc.errors:
        assert error["type"] == "PreflightError"
        assert isinstance(error["message"], str) and error["message"]
        assert "engine_type" not in error  # OQ-014c: omitted for preflight
        assert "case_id" not in error  # OQ-011: absent for preflight errors


# --- §11.0 ingress: strict JSON parsing -----------------------------------


def test_fr_026_valid_json_parses():
    assert loads_strict('{"a": 1.5, "b": [true, null, "x"]}') == {
        "a": 1.5,
        "b": [True, None, "x"],
    }


def test_fr_026_duplicate_object_keys_rejected():
    # §11.0: parsers MUST reject duplicate object keys at ingress.
    with pytest.raises(IngressError) as excinfo:
        loads_strict('{"a": 1, "a": 2}')
    assert_preflight_errors(excinfo.value)
    assert "duplicate object key" in excinfo.value.errors[0]["message"]


def test_fr_026_duplicate_keys_rejected_at_any_depth():
    with pytest.raises(IngressError) as excinfo:
        loads_strict('{"outer": [{"k": 1, "k": 2}]}')
    assert_preflight_errors(excinfo.value)


@pytest.mark.parametrize("text", ["NaN", "Infinity", "-Infinity"])
def test_fr_026_non_finite_numbers_rejected(text):
    # §11.0: parsers MUST reject non-finite numbers (NaN/Infinity) at ingress.
    with pytest.raises(IngressError) as excinfo:
        loads_strict('{"n": %s}' % text)
    assert_preflight_errors(excinfo.value)
    assert "non-finite" in excinfo.value.errors[0]["message"]


def test_fr_026_malformed_json_rejected():
    with pytest.raises(IngressError) as excinfo:
        loads_strict("{not json")
    assert_preflight_errors(excinfo.value)
    assert "invalid JSON" in excinfo.value.errors[0]["message"]


def test_fr_026_source_label_appears_in_message():
    with pytest.raises(IngressError) as excinfo:
        loads_strict("{", source="samples.json")
    assert excinfo.value.errors[0]["message"].startswith("samples.json:")


# --- file ingress ----------------------------------------------------------


def test_fr_026_unreadable_file_is_ingress_error(tmp_path):
    # §11.6 PreflightError: unreadable input file.
    with pytest.raises(IngressError) as excinfo:
        load_json_file(tmp_path / "does-not-exist.json")
    assert_preflight_errors(excinfo.value)
    assert "unreadable input file" in excinfo.value.errors[0]["message"]


def test_fr_026_directory_is_ingress_error(tmp_path):
    with pytest.raises(IngressError) as excinfo:
        load_json_file(tmp_path)
    assert_preflight_errors(excinfo.value)


def test_fr_026_load_json_file_reads_strictly(tmp_path):
    good = tmp_path / "good.json"
    good.write_text('{"schema_version": "1.0"}', encoding="utf-8")
    assert load_json_file(good) == {"schema_version": "1.0"}

    bad = tmp_path / "bad.json"
    bad.write_text('{"a": 1, "a": 2}', encoding="utf-8")
    with pytest.raises(IngressError):
        load_json_file(bad)


# --- schema_version gate (§11.0 schema versions) ---------------------------


def test_fr_026_supported_schema_version_accepted():
    assert SUPPORTED_SCHEMA_VERSION == "1.0"
    check_schema_version({"schema_version": "1.0"})  # must not raise


@pytest.mark.parametrize(
    "doc",
    [
        {"schema_version": "2.0"},
        {"schema_version": "1"},
        {"schema_version": 1.0},
        {"schema_version": None},
    ],
)
def test_fr_026_unsupported_schema_version_rejected(doc):
    # FR-026: unknown/unsupported schema_version on ingress -> schema-error.
    with pytest.raises(IngressError) as excinfo:
        check_schema_version(doc)
    assert_preflight_errors(excinfo.value)
    assert "unsupported schema_version" in excinfo.value.errors[0]["message"]


def test_fr_026_missing_schema_version_rejected():
    with pytest.raises(IngressError) as excinfo:
        check_schema_version({"ok": True})
    assert_preflight_errors(excinfo.value)
    assert "schema_version" in excinfo.value.errors[0]["message"]


def test_fr_026_non_object_document_rejected():
    with pytest.raises(IngressError) as excinfo:
        check_schema_version(["not", "an", "object"])
    assert_preflight_errors(excinfo.value)


# --- JSON Schema validation helpers (OQ-014e) ------------------------------


def test_fr_026_validate_schema_passes_valid_document():
    cli_error = {
        "schema_version": "1.0",
        "ok": False,
        "status": "schema-error",
        "explanation": "input failed schema validation",
        "errors": [{"type": "PreflightError", "message": "bad input"}],
    }
    validate_schema(cli_error, "cli_error.json")  # must not raise


def test_fr_026_validator_errors_sorted_by_path_then_message():
    # OQ-013 / OQ-014e: schema_invalid / PreflightError messages derive from
    # validator errors sorted by (JSON instance path, message).
    invalid_sample_set = {
        "schema_version": "1.0",
        # instance insertion order deliberately differs from sorted pointer
        # order so the sort is observable: coverage, cases, confirmation.
        "coverage": [
            {
                "id": "ob-1",
                "kind": "not-a-kind",
                "description": "x",
                "acceptance": "accepted",
            }
        ],
        "cases": "not-an-array",
        "waivers": [],
        "confirmation": {"confirmed": "yes", "content_fingerprint": "f" * 64},
    }
    violations = schema_violations(invalid_sample_set, "sample_set.json")
    assert [pointer for pointer, _ in violations] == [
        "/cases",
        "/confirmation/confirmed",
        "/coverage/0/kind",
    ]
    assert violations == sorted(violations)

    with pytest.raises(IngressError) as excinfo:
        validate_schema(invalid_sample_set, "sample_set.json")
    assert_preflight_errors(excinfo.value)
    assert [e["path"] for e in excinfo.value.errors] == [
        "/cases",
        "/confirmation/confirmed",
        "/coverage/0/kind",
    ]
    messages = [e["message"] for e in excinfo.value.errors]
    assert messages == sorted(messages)  # path-major sort here implies both


def test_fr_026_root_violation_uses_root_pointer():
    violations = schema_violations([], "verdict.json")
    assert len(violations) == 1
    assert violations[0][0] == ""  # RFC 6901 root pointer


def test_fr_026_schema_violations_empty_for_valid_instance():
    # ok:false requires failed_stage (§11.2 ok/assurance/failed_stage coupling).
    verdict = {
        "schema_version": "1.0",
        "ok": False,
        "failed_stage": "samples",
        "errors": [],
    }
    assert schema_violations(verdict, "verdict.json") == []


# --- load_document convenience (read -> parse -> version -> schema) --------


def test_fr_026_load_document_happy_path(tmp_path):
    path = tmp_path / "cli_error.json"
    doc = {
        "schema_version": "1.0",
        "ok": False,
        "status": "internal-error",
        "explanation": "RuntimeError: boom",
        "errors": [],
    }
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert load_document(path, "cli_error.json") == doc


def test_fr_026_load_document_rejects_unsupported_version(tmp_path):
    path = tmp_path / "verdict.json"
    path.write_text(
        '{"schema_version": "9.9", "ok": true, "errors": []}', encoding="utf-8"
    )
    with pytest.raises(IngressError) as excinfo:
        load_document(path, "verdict.json")
    assert_preflight_errors(excinfo.value)
    assert "unsupported schema_version" in excinfo.value.errors[0]["message"]


def test_fr_026_load_document_rejects_schema_invalid(tmp_path):
    path = tmp_path / "verdict.json"
    path.write_text('{"schema_version": "1.0", "ok": true}', encoding="utf-8")
    with pytest.raises(IngressError) as excinfo:
        load_document(path, "verdict.json")
    assert_preflight_errors(excinfo.value)
