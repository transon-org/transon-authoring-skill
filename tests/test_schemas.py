"""FR-026 — bundled JSON Schemas for the §11 document contracts.

Every document under ``src/transon_authoring/schemas/`` is authored in JSON
Schema draft 2020-12 and faithfully encodes the §11.1 (SampleSet /
SampleCheck), §11.2 (Verdict / EngineError / DiffEntry), §11.5
(AuthoringResult) and §11.6 (CliError) shapes (OQ-011..OQ-014). AC-026
groundwork: failure envelopes always carry ``ok: false`` plus a §11.5/§11.6
``status``.
"""

import json
from importlib import resources
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from transon_authoring._ingress import (
    SCHEMA_FILES,
    IngressError,
    load_schema,
    schema_violations,
    validate_schema,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = REPO_ROOT / "src" / "transon_authoring" / "schemas"

EXPECTED_SCHEMA_FILES = {
    "sample_set.json",
    "sample_check.json",
    "verdict.json",
    "authoring_result.json",
    "cli_error.json",
    "project_config.json",  # §11.9 ProjectConfig (FR-022 / AC-014)
}

# §11.1 GapCode — full closed enum.
GAP_CODES = {
    "schema_invalid",
    "missing_happy_path",
    "optional_present_unmet",
    "optional_absent_unmet",
    "list_empty_unmet",
    "list_singleton_unmet",
    "list_many_unmet",
    "mode_choice_unmet",
    "custom_unmet",
    "obligation_not_accepted",
    "waiver_invalid",
    "unconfirmed",
    "fingerprint_mismatch",
    "no_cases",
    "case_satisfies_unknown",
    "duplicate_id",
    "target_invalid",
    "target_required",
}

# §11.2 EngineError.type — taxonomy buckets (OQ-014c closure).
ENGINE_ERROR_TYPES = {
    "DefinitionError",
    "TransformationError",
    "ProfileError",
    "TimeoutError",
    "PreflightError",
}

# §11.2 DiffEntry.kind.
DIFF_KINDS = {"missing", "extra", "value_mismatch", "type_mismatch", "writes_mismatch"}

# §11.1 CoverageObligation.kind.
OBLIGATION_KINDS = {
    "happy_path",
    "optional_present",
    "optional_absent",
    "list_empty",
    "list_singleton",
    "list_many",
    "mode_choice",
    "custom",
}

# §11.5 AuthoringResult.status.
AUTHORING_STATUSES = {
    "matched",
    "need-samples",
    "deferred",
    "aborted",
    "repair-exhausted",
    "samples-rejected",
    "verify-failed",
    "schema-error",
    "profile-rejected",
}

# §11.6 CliError.status (OQ-014a: "internal-error" is CLI-level only).
CLI_ERROR_STATUSES = {"schema-error", "profile-rejected", "internal-error"}


# --- schema documents themselves -------------------------------------------


def test_fr_026_schema_directory_contains_exactly_the_contract_schemas():
    assert {p.name for p in SCHEMA_DIR.glob("*.json")} == EXPECTED_SCHEMA_FILES
    assert set(SCHEMA_FILES) == EXPECTED_SCHEMA_FILES


def test_fr_026_schemas_load_as_package_resources():
    # §11.5 conformance: schemas live at src/transon_authoring/schemas/ and
    # must resolve through the package (they ship in the wheel).
    package_dir = resources.files("transon_authoring") / "schemas"
    for name in EXPECTED_SCHEMA_FILES:
        assert (package_dir / name).is_file(), name
        assert load_schema(name)  # parses to a non-empty schema object


@pytest.mark.parametrize("name", sorted(EXPECTED_SCHEMA_FILES))
def test_fr_026_schema_declares_draft_2020_12_and_is_well_formed(name):
    # OQ-014e: all documents authored in draft 2020-12, each declares $schema.
    document = json.loads((SCHEMA_DIR / name).read_text(encoding="utf-8"))
    assert document["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(document)


def test_fr_026_enums_faithfully_encode_spec_11():
    sample_check = load_schema("sample_check.json")
    assert set(sample_check["$defs"]["gap"]["properties"]["code"]["enum"]) == GAP_CODES

    sample_set = load_schema("sample_set.json")
    obligation = sample_set["$defs"]["coverageObligation"]
    assert set(obligation["properties"]["kind"]["enum"]) == OBLIGATION_KINDS

    verdict = load_schema("verdict.json")
    engine_error = verdict["$defs"]["engineError"]
    assert set(engine_error["properties"]["type"]["enum"]) == ENGINE_ERROR_TYPES
    diff_entry = verdict["$defs"]["diffEntry"]
    assert set(diff_entry["properties"]["kind"]["enum"]) == DIFF_KINDS
    # OQ-011: DiffEntry.case_id required; EngineError.case_id optional.
    assert "case_id" in diff_entry["required"]
    assert "case_id" not in engine_error["required"]
    # OQ-011: root Verdict.writes stays in the schema as optional/reserved.
    assert "writes" in verdict["properties"]
    assert "writes" not in verdict["required"]

    authoring_result = load_schema("authoring_result.json")
    statuses = authoring_result["properties"]["status"]["enum"]
    assert set(statuses) == AUTHORING_STATUSES

    cli_error = load_schema("cli_error.json")
    assert set(cli_error["properties"]["status"]["enum"]) == CLI_ERROR_STATUSES


# --- golden fixtures: one valid document per type ---------------------------

GOLDEN_SAMPLE_SET = {
    "schema_version": "1.0",
    "intent_nl": "flatten each order's line items with the customer name",
    "coverage": [
        {
            "id": "ob-happy",
            "kind": "happy_path",
            "description": "typical order",
            "acceptance": "accepted",
        },
        {
            "id": "ob-empty",
            "kind": "list_empty",
            "target": "/items",
            "description": "order with no line items",
            "acceptance": "accepted",
        },
        {
            "id": "ob-mode",
            "kind": "mode_choice",
            "target": "keys",
            "description": "map keys mode",
            "acceptance": "proposed",
        },
    ],
    "cases": [
        {
            "id": "case-1",
            "input": {"items": [{"sku": "a"}]},
            "output": [{"sku": "a"}],
            "satisfies": ["ob-happy"],
        },
        {
            "id": "case-2",
            "input": {"items": []},
            # AuthoringTag values are plain JSON to the schema; tag *validity*
            # is enforced procedurally (§11.0 decoding), not structurally.
            "output": {"$transon_authoring": "NO_CONTENT"},
            "writes": {
                "log": {
                    "$transon_authoring": "lit",
                    "value": {"$transon_authoring": "NO_CONTENT"},
                }
            },
            "satisfies": ["ob-empty"],
        },
    ],
    "waivers": [
        {
            "id": "w-1",
            "clears_obligation_ids": ["ob-mode"],
            "reason": "mode is fixed by the template",
            "acceptance": "proposed",
        }
    ],
    "includes": {"header": {"$": "attr", "name": "h"}},
    "confirmation": {
        "confirmed": True,
        "confirmed_by": "user",
        "confirmed_at": "2026-07-11T00:00:00Z",
        "note": "reviewed",
        "content_fingerprint": "0" * 64,
    },
}

GOLDEN_SAMPLE_CHECK = {
    "schema_version": "1.0",
    "coverage_complete": False,
    "confirmed": False,
    "ok_for_verify": False,
    "gaps": [
        {
            "code": "obligation_not_accepted",
            "message": "obligation ob-mode is still proposed",
            "obligation_id": "ob-mode",
        },
        {
            "code": "case_satisfies_unknown",
            "message": "case case-9 claims unknown obligation",
            "case_id": "case-9",
        },
        {"code": "unconfirmed", "message": "confirmation.confirmed is false"},
    ],
    "content_fingerprint": "0" * 64,
}

GOLDEN_VERDICT_MATCHED = {
    "schema_version": "1.0",
    "ok": True,
    "assurance": "matched",
    "errors": [],
    "json": {"$": "this"},
}

# validate-stage failure: single EngineError without case_id (OQ-011).
GOLDEN_VERDICT_VALIDATE_FAILED = {
    "schema_version": "1.0",
    "ok": False,
    "failed_stage": "validate",
    "errors": [
        {
            "type": "DefinitionError",
            "message": "unknown rule: attrx",
            "engine_type": "DefinitionError",
            "path": "/",
        }
    ],
}

# dry_run + match shapes: per-case attribution (OQ-011).
GOLDEN_VERDICT_MATCH_FAILED = {
    "schema_version": "1.0",
    "ok": False,
    "failed_stage": "match",
    "errors": [],
    "diff": [
        {
            "path": "/name",
            "kind": "value_mismatch",
            "expected": "Alice",
            "actual": "Bob",
            "case_id": "case-1",
        },
        {
            "path": "",
            "kind": "writes_mismatch",
            "expected": {"writes": {"out": 1}},
            "actual": {"writes": {}},
            "case_id": "case-2",
        },
    ],
}

GOLDEN_AUTHORING_RESULT_MATCHED = {
    "schema_version": "1.0",
    "ok": True,
    "status": "matched",
    "explanation": "template verified at assurance matched",
    "template": {"$": "this"},
    "verdict": GOLDEN_VERDICT_MATCHED,
    "repair_count": 0,
}

# AC-026: failure envelope carries ok: false and a §11.5 status.
GOLDEN_AUTHORING_RESULT_FAILURE = {
    "schema_version": "1.0",
    "ok": False,
    "status": "schema-error",
    "explanation": "SampleSet is not valid JSON",
    "samples_path": "samples/orders.json",
}

# AC-026: CliError always ok: false with a §11.6 status.
GOLDEN_CLI_ERROR = {
    "schema_version": "1.0",
    "ok": False,
    "status": "schema-error",
    "explanation": "input failed JSON Schema validation",
    "errors": [
        {"type": "PreflightError", "message": "samples.json: invalid JSON"}
    ],
}

GOLDEN_FIXTURES = [
    ("sample_set.json", GOLDEN_SAMPLE_SET),
    ("sample_check.json", GOLDEN_SAMPLE_CHECK),
    ("verdict.json", GOLDEN_VERDICT_MATCHED),
    ("verdict.json", GOLDEN_VERDICT_VALIDATE_FAILED),
    ("verdict.json", GOLDEN_VERDICT_MATCH_FAILED),
    ("authoring_result.json", GOLDEN_AUTHORING_RESULT_MATCHED),
    ("authoring_result.json", GOLDEN_AUTHORING_RESULT_FAILURE),
    ("cli_error.json", GOLDEN_CLI_ERROR),
]


@pytest.mark.parametrize(
    "schema_name,fixture",
    GOLDEN_FIXTURES,
    ids=[f"{name}-{i}" for i, (name, _) in enumerate(GOLDEN_FIXTURES)],
)
def test_fr_026_golden_fixture_validates(schema_name, fixture):
    validate_schema(fixture, schema_name)  # must not raise
    assert schema_violations(fixture, schema_name) == []


# --- invalid fixtures: required/optional and enum discipline ----------------


def test_fr_026_oq_011_diff_entry_requires_case_id():
    verdict = {
        "schema_version": "1.0",
        "ok": False,
        "failed_stage": "match",
        "errors": [],
        "diff": [{"path": "/name", "kind": "value_mismatch"}],
    }
    violations = schema_violations(verdict, "verdict.json")
    assert violations, "DiffEntry without case_id must be schema-invalid"
    assert any("case_id" in message for _, message in violations)


def test_fr_026_oq_011_engine_error_case_id_is_optional():
    verdict = {
        "schema_version": "1.0",
        "ok": False,
        "failed_stage": "dry_run",
        "errors": [
            {"type": "TimeoutError", "message": "case timed out", "case_id": "c1"},
            {"type": "TransformationError", "message": "division by zero",
             "engine_type": "ZeroDivisionError"},
        ],
    }
    assert schema_violations(verdict, "verdict.json") == []


def test_fr_026_ac_026_cli_error_requires_ok_false():
    # AC-026 groundwork: an envelope claiming ok: true is not a CliError.
    fixture = dict(GOLDEN_CLI_ERROR, ok=True)
    assert schema_violations(fixture, "cli_error.json")


def test_fr_026_ac_026_authoring_result_requires_status_and_ok():
    for missing in ("status", "ok"):
        fixture = {
            k: v for k, v in GOLDEN_AUTHORING_RESULT_FAILURE.items() if k != missing
        }
        assert schema_violations(fixture, "authoring_result.json")


def test_fr_026_unknown_status_rejected():
    fixture = dict(GOLDEN_AUTHORING_RESULT_FAILURE, status="internal-error")
    # OQ-014a: "internal-error" is CLI-level only, not an AuthoringResult status.
    assert schema_violations(fixture, "authoring_result.json")


def test_fr_026_unknown_gap_code_rejected():
    fixture = dict(
        GOLDEN_SAMPLE_CHECK,
        gaps=[{"code": "not_a_gap", "message": "x"}],
    )
    assert schema_violations(fixture, "sample_check.json")


def test_fr_026_unknown_top_level_field_rejected():
    # FR-026: emit/accept only the §11 shapes — closed envelopes.
    fixture = dict(GOLDEN_CLI_ERROR, extra_field=1)
    assert schema_violations(fixture, "cli_error.json")


def test_fr_026_invalid_fixture_errors_deterministically_sorted():
    # OQ-013 / OQ-014e: violations sorted by (JSON instance path, message).
    fixture = {
        "schema_version": "1.0",
        "ok": "yes",
        "status": "nope",
        "explanation": 7,
    }
    violations = schema_violations(fixture, "authoring_result.json")
    # /ok appears twice: the type violation plus the §11.5 status/ok coupling
    # (a non-"matched" status forces ok const false).
    assert len(violations) == 4
    assert [pointer for pointer, _ in violations] == [
        "/explanation",
        "/ok",
        "/ok",
        "/status",
    ]
    assert violations == sorted(violations)
    with pytest.raises(IngressError) as excinfo:
        validate_schema(fixture, "authoring_result.json")
    assert [e["path"] for e in excinfo.value.errors] == [
        "/explanation",
        "/ok",
        "/ok",
        "/status",
    ]


# ---------------------------------------------------------------------------
# FR-026 — shared $defs stay in sync across schema files (drift guard).
# The bundled schemas deliberately inline their shared definitions
# (engineError, gap, diffEntry, and the embedded verdict/sampleCheck shapes)
# instead of cross-document $refs; this test is the mechanical lockstep
# guarantee: a SPEC enum change applied to one copy fails here until every
# copy agrees. Comparison ignores "description" (doc-only) annotations.
# ---------------------------------------------------------------------------


def _strip_descriptions(node):
    if isinstance(node, dict):
        return {
            key: _strip_descriptions(value)
            for key, value in node.items()
            if key != "description"
        }
    if isinstance(node, list):
        return [_strip_descriptions(item) for item in node]
    return node


@pytest.mark.parametrize(
    ("def_name", "schema_files"),
    [
        ("engineError", ["verdict.json", "authoring_result.json", "cli_error.json"]),
        ("gap", ["verdict.json", "authoring_result.json", "sample_check.json"]),
        ("diffEntry", ["verdict.json", "authoring_result.json"]),
    ],
)
def test_fr_026_shared_defs_identical_across_schema_files(def_name, schema_files):
    shapes = [
        _strip_descriptions(load_schema(name)["$defs"][def_name])
        for name in schema_files
    ]
    assert all(shape == shapes[0] for shape in shapes[1:]), (
        f"$defs/{def_name} drifted between {schema_files}"
    )


@pytest.mark.parametrize(
    ("def_name", "standalone_file"),
    [("verdict", "verdict.json"), ("sampleCheck", "sample_check.json")],
)
def test_fr_026_embedded_document_defs_match_standalone_schemas(
    def_name, standalone_file
):
    # authoring_result.json embeds whole-document shapes; they must stay
    # structurally identical to the standalone schema's top-level shape.
    embedded = _strip_descriptions(load_schema("authoring_result.json")["$defs"][def_name])
    standalone = _strip_descriptions(
        {
            key: value
            for key, value in load_schema(standalone_file).items()
            if key not in ("$schema", "title", "$defs")
        }
    )
    assert embedded == standalone, (
        f"$defs/{def_name} drifted from {standalone_file}"
    )
