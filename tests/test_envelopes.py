"""NFR-005 / AC-026 — systematic envelope-conformance sweep (SPEC §8 NFR-005,
§9 AC-026, §11.5 conformance paragraph, §11.6 CliError, resolved OQ-014 §15).

Producer-side conformance: every envelope the A1 surface can emit — success or
failure — validates against its bundled draft 2020-12 schema (or an ad-hoc
2020-12 schema built here for the §11.6/OQ-014b envelopes that ship no schema
file: dry-run, validate, examples-search). On every failure envelope the
AC-026 invariant holds: ``ok`` is false, a status / ``failed_stage``
discriminator is present, and ``explanation`` (CliError) or ``errors`` /
``gaps`` / ``diff`` (Verdict / SampleCheck) carry actionable content.

The §11.5 AuthoringResult half is fixture-based by design: no module
subcommand emits AuthoringResult (its producer is the A3 skill), so §11.5
prescribes "unit tests that validate fixtures against the schema" — one
fixture per status value, embedding REAL Verdicts / SampleChecks produced by
the pinned engine (AD-018), plus negatives derived from the schema.

CLI envelopes are driven end-to-end through a real subprocess via the
`test_cli_a1` helpers, except the induced internal fault (OQ-014a technique:
in-process ``main()`` with a monkeypatched handler) and the dry-run
TimeoutError verdict (in-process ``verify()`` with a patched timeout
constant). Fingerprints always come from ``content_fingerprint()`` (OQ-015).
"""

import importlib
import json

import pytest
from jsonschema import Draft202012Validator

from transon_authoring import check_samples, verify
from transon_authoring._ingress import load_schema, schema_violations

from test_cli_a1 import (
    ATTR_X,
    BAD_TEMPLATE,
    make_sample_set,
    match_failure_samples,
    matched_samples,
    one_json_document,
    run_cli,
    unconfirmed_samples,
    write_json,
    write_text,
)

# §11.6 CliError.status (OQ-014a: "internal-error" is CLI-level only).
CLI_ERROR_STATUSES = {"schema-error", "profile-rejected", "internal-error"}

# §11.5 AuthoringResult.status — the full closed enum.
AUTHORING_STATUSES = (
    "matched",
    "need-samples",
    "deferred",
    "aborted",
    "repair-exhausted",
    "samples-rejected",
    "verify-failed",
    "schema-error",
    "profile-rejected",
)


# ---------------------------------------------------------------------------
# SampleSet builders beyond test_cli_a1's (fingerprints via content_fingerprint
# inside make_sample_set)
# ---------------------------------------------------------------------------


def dry_run_failure_samples():
    """Schema-valid, ok_for_verify, but the case input makes the pinned
    engine fail ATTR_X at dry-run (attr on int → TransformationError)."""
    return make_sample_set(
        [{"id": "c1", "input": 5, "output": 1, "satisfies": ["happy"]}]
    )


def incomplete_coverage_samples():
    """Confirmed but coverage-incomplete: the accepted happy_path obligation
    has no satisfying case → missing_happy_path gap (need-samples shape)."""
    return make_sample_set(
        [{"id": "c1", "input": {"x": 1}, "output": 1, "satisfies": []}]
    )


# ---------------------------------------------------------------------------
# AC-026 invariant helpers (bundled-schema conformance + actionable content)
# ---------------------------------------------------------------------------


def assert_conformant_cli_error(document, status):
    """AC-026 on a §11.6 CliError: bundled-schema valid, ok false, taxonomy
    status discriminator, actionable ``explanation``."""
    assert schema_violations(document, "cli_error.json") == []
    assert document["ok"] is False
    assert document["status"] == status
    assert status in CLI_ERROR_STATUSES
    assert isinstance(document["explanation"], str)
    assert document["explanation"].strip()


def assert_conformant_failing_verdict(document, stage):
    """AC-026 on a §11.2 Verdict failure: bundled-schema valid, ok false,
    ``failed_stage`` discriminator, and the stage's payload (gaps / errors /
    diff per OQ-011) carries actionable content."""
    assert schema_violations(document, "verdict.json") == []
    assert document["ok"] is False
    assert "assurance" not in document  # only when ok (§11.2 / AC-013)
    assert document["failed_stage"] == stage
    if stage == "samples":
        assert document["gaps"]
        for gap in document["gaps"]:
            assert gap["message"].strip()
    elif stage == "match":
        # Match failures are expressed by diff alone — no EngineErrors (OQ-011).
        assert document["errors"] == []
        assert document["diff"]
        for entry in document["diff"]:
            assert entry["kind"]
            assert entry["case_id"]
    else:  # validate / dry_run
        assert document["errors"]
        for error in document["errors"]:
            assert error["message"].strip()


def assert_conformant_failing_sample_check(document):
    """AC-026 on a §11.1 SampleCheck failure: bundled-schema valid,
    ``ok_for_verify`` false, actionable gap messages."""
    assert schema_violations(document, "sample_check.json") == []
    assert document["ok_for_verify"] is False
    assert document["gaps"]
    for gap in document["gaps"]:
        assert gap["message"].strip()


# ---------------------------------------------------------------------------
# Ad-hoc draft 2020-12 schemas for envelopes WITHOUT a bundled schema file,
# encoding the §11.6 table rows + OQ-014b presence rules
# ---------------------------------------------------------------------------

_ADHOC_ENGINE_ERROR = {
    "type": "object",
    "required": ["type", "message"],
    "additionalProperties": False,
    "properties": {
        "type": {
            "enum": [
                "DefinitionError",
                "TransformationError",
                "ProfileError",
                "TimeoutError",
                "PreflightError",
            ]
        },
        "message": {"type": "string"},
        "engine_type": {"type": "string"},
        "path": {"type": "string"},
        "case_id": {"type": "string"},
    },
}

#: §11.6 row + OQ-014b: on success `result` AND `writes` both present
#: (`writes` may be {}) and `errors` empty; on failure both omitted and
#: `errors` non-empty.
DRY_RUN_ENVELOPE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "dry-run envelope (§11.6 / OQ-014b; no bundled schema file)",
    "type": "object",
    "required": ["schema_version", "ok", "errors"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "1.0"},
        "ok": {"type": "boolean"},
        "result": True,
        "writes": {"type": "object"},
        "errors": {"type": "array", "items": _ADHOC_ENGINE_ERROR},
    },
    "if": {"properties": {"ok": {"const": True}}},
    "then": {
        "required": ["result", "writes"],
        "properties": {"errors": {"maxItems": 0}},
    },
    "else": {
        "properties": {"errors": {"minItems": 1}},
        "not": {"anyOf": [{"required": ["result"]}, {"required": ["writes"]}]},
    },
}

#: §11.6 row + OQ-014b: {"schema_version":"1.0", ok, errors}; errors empty on
#: success, non-empty on failure.
VALIDATE_ENVELOPE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "validate envelope (§11.6 / OQ-014b; no bundled schema file)",
    "type": "object",
    "required": ["schema_version", "ok", "errors"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "1.0"},
        "ok": {"type": "boolean"},
        "errors": {"type": "array", "items": _ADHOC_ENGINE_ERROR},
    },
    "if": {"properties": {"ok": {"const": True}}},
    "then": {"properties": {"errors": {"maxItems": 0}}},
    "else": {"properties": {"errors": {"minItems": 1}}},
}

#: §11.6 row + OQ-014b: {"schema_version":"1.0","hits":[example objects…]};
#: hits are verbatim snapshot docs.examples objects (name/template guaranteed,
#: optional "nl" from the sidecar — AC-022), so items stay open.
EXAMPLES_SEARCH_ENVELOPE_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "examples-search envelope (§11.6 / OQ-014b; no bundled schema file)",
    "type": "object",
    "required": ["schema_version", "hits"],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "1.0"},
        "hits": {
            "type": "array",
            "items": {"type": "object", "required": ["name", "template"]},
        },
    },
}


def adhoc_violations(instance, schema):
    """Draft 2020-12 validation against an ad-hoc schema, violations sorted
    like _ingress.schema_violations (OQ-013 determinism)."""
    Draft202012Validator.check_schema(schema)
    return sorted(
        (
            "".join("/" + str(part) for part in error.absolute_path),
            error.message,
        )
        for error in Draft202012Validator(schema).iter_errors(instance)
    )


# ---------------------------------------------------------------------------
# 1a. CliError failure envelopes, end-to-end through the CLI —
#     status "schema-error" for every §11.6/OQ-014c ingress-failure kind
# ---------------------------------------------------------------------------

_SCHEMA_ERROR_INVOCATIONS = {
    "malformed_json": lambda tmp: [
        "check-samples",
        "--samples",
        write_text(tmp, "bad.json", "{"),
    ],
    "duplicate_keys": lambda tmp: [
        "verify",
        "--template",
        write_text(tmp, "bad.json", '{"a": 1, "a": 2}'),
        "--samples",
        write_json(tmp, "s.json", matched_samples()),
    ],
    "unsupported_schema_version": lambda tmp: [
        "check-samples",
        "--samples",
        write_json(tmp, "bad.json", dict(matched_samples(), schema_version="9.9")),
    ],
    "unreadable_file": lambda tmp: [
        "validate",
        "--template",
        str(tmp / "does-not-exist.json"),
    ],
    "non_object_includes": lambda tmp: [
        "dry-run",
        "--template",
        write_json(tmp, "t.json", ATTR_X),
        "--input",
        write_json(tmp, "i.json", {"x": "hello"}),
        "--includes",
        write_text(tmp, "inc.json", "[1, 2]"),
    ],
}


@pytest.mark.parametrize("kind", sorted(_SCHEMA_ERROR_INVOCATIONS))
def test_nfr_005_ac_026_schema_error_cli_error_conforms(tmp_path, kind):
    result = run_cli(*_SCHEMA_ERROR_INVOCATIONS[kind](tmp_path))
    assert result.returncode == 2
    document = one_json_document(result)
    assert_conformant_cli_error(document, "schema-error")
    # OQ-014c: schema-error carries PreflightError entries with stable,
    # actionable library text; engine_type omitted (nothing engine-caught).
    assert document["errors"]
    for error in document["errors"]:
        assert error["type"] == "PreflightError"
        assert error["message"].strip()
        assert "engine_type" not in error


# ---------------------------------------------------------------------------
# 1b. CliError "profile-rejected" (FR-028 / AC-027 reserved knobs)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("knob", ["--marker", "--transformer"])
def test_nfr_005_ac_026_profile_rejected_cli_error_conforms(tmp_path, knob):
    result = run_cli(
        "validate", "--template", str(tmp_path / "does-not-exist.json"), knob, "X"
    )
    assert result.returncode == 2
    document = one_json_document(result)
    assert_conformant_cli_error(document, "profile-rejected")
    assert [error["type"] for error in document["errors"]] == ["ProfileError"]
    assert knob in document["errors"][0]["message"]


# ---------------------------------------------------------------------------
# 1c. CliError "internal-error" (OQ-014a) — induced fault, in-process main()
#     with a monkeypatched handler (the controllable exit-3 technique)
# ---------------------------------------------------------------------------


def test_nfr_005_ac_026_internal_error_cli_error_conforms(
    tmp_path, monkeypatch, capsys
):
    from transon_authoring import __main__ as cli

    def induced_fault(*_args, **_kwargs):
        raise ValueError("induced internal fault (AC-026 conformance sweep)")

    monkeypatch.setattr(cli, "check_samples", induced_fault)
    samples_path = write_json(tmp_path, "s.json", matched_samples())
    code = cli.main(["check-samples", "--samples", samples_path])
    captured = capsys.readouterr()
    assert code == 3
    document = json.loads(captured.out)
    assert_conformant_cli_error(document, "internal-error")
    # §11.6: errors may be empty for "internal-error"; the explanation still
    # names the fault ("<ExceptionClass>: <message>", OQ-014a).
    assert document["errors"] == []
    assert (
        document["explanation"]
        == "ValueError: induced internal fault (AC-026 conformance sweep)"
    )


# ---------------------------------------------------------------------------
# 1d. Failing SampleCheck (exit 1) end-to-end
# ---------------------------------------------------------------------------


def test_nfr_005_ac_026_failing_sample_check_envelope_conforms(tmp_path):
    result = run_cli(
        "check-samples",
        "--samples",
        write_json(tmp_path, "s.json", unconfirmed_samples()),
    )
    assert result.returncode == 1
    document = one_json_document(result)
    assert_conformant_failing_sample_check(document)
    assert "unconfirmed" in [gap["code"] for gap in document["gaps"]]


# ---------------------------------------------------------------------------
# 1e. Failing Verdict for EACH failed_stage value, end-to-end (plus the
#     TimeoutError dry_run variant in-process)
# ---------------------------------------------------------------------------

_FAILING_VERIFY_INPUTS = {
    "samples": (ATTR_X, unconfirmed_samples),
    "validate": (BAD_TEMPLATE, matched_samples),
    "dry_run": (ATTR_X, dry_run_failure_samples),
    "match": (ATTR_X, match_failure_samples),
}


@pytest.mark.parametrize("stage", sorted(_FAILING_VERIFY_INPUTS))
def test_nfr_005_ac_026_failing_verdict_envelope_conforms(tmp_path, stage):
    template, samples_factory = _FAILING_VERIFY_INPUTS[stage]
    result = run_cli(
        "verify",
        "--template",
        write_json(tmp_path, "t.json", template),
        "--samples",
        write_json(tmp_path, "s.json", samples_factory()),
    )
    assert result.returncode == 1  # semantic failure on schema-valid inputs
    document = one_json_document(result)
    assert_conformant_failing_verdict(document, stage)
    if stage == "validate":
        assert document["errors"][0]["type"] == "DefinitionError"
    if stage == "dry_run":
        # OQ-014c EngineError.type closure + OQ-011 case attribution.
        assert document["errors"][0]["type"] == "TransformationError"
        assert document["errors"][0]["case_id"] == "c1"


def test_nfr_005_ac_026_timeout_verdict_envelope_conforms(monkeypatch):
    # AC-028 shape via a patched timeout constant: 1ms is far below worker
    # interpreter startup, so the case deterministically times out. In-process
    # (importlib because the package re-exports `verify` the function over
    # `verify` the module).
    verify_module = importlib.import_module("transon_authoring.verify")
    monkeypatch.setattr(verify_module, "DRY_RUN_TIMEOUT_SECONDS", 0.001)
    verdict = verify_module.verify(ATTR_X, matched_samples())
    assert_conformant_failing_verdict(verdict, "dry_run")
    assert [error["type"] for error in verdict["errors"]] == ["TimeoutError"]
    assert verdict["errors"][0]["case_id"] == "c1"


# ---------------------------------------------------------------------------
# 2. Success envelopes validate too (NFR-005: statuses distinguishable from
#    success requires the success shapes to be schema-clean as well)
# ---------------------------------------------------------------------------


def test_nfr_005_matched_verdict_envelope_conforms(tmp_path):
    result = run_cli(
        "verify",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--samples",
        write_json(tmp_path, "s.json", matched_samples()),
    )
    assert result.returncode == 0
    document = one_json_document(result)
    assert schema_violations(document, "verdict.json") == []
    assert document["ok"] is True
    assert document["assurance"] == "matched"  # AD-004 / AC-013
    assert "failed_stage" not in document
    assert document["errors"] == []


def test_nfr_005_ok_sample_check_envelope_conforms(tmp_path):
    result = run_cli(
        "check-samples", "--samples", write_json(tmp_path, "s.json", matched_samples())
    )
    assert result.returncode == 0
    document = one_json_document(result)
    assert schema_violations(document, "sample_check.json") == []
    assert document["ok_for_verify"] is True
    assert document["gaps"] == []


def test_nfr_005_dry_run_success_envelope_conforms(tmp_path):
    result = run_cli(
        "dry-run",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--input",
        write_json(tmp_path, "i.json", {"x": "hello"}),
    )
    assert result.returncode == 0
    document = one_json_document(result)
    assert adhoc_violations(document, DRY_RUN_ENVELOPE_SCHEMA) == []
    assert document["ok"] is True


def test_nfr_005_dry_run_failure_envelope_conforms(tmp_path):
    result = run_cli(
        "dry-run",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--input",
        write_json(tmp_path, "i.json", 5),  # attr on int → engine error
    )
    assert result.returncode == 1
    document = one_json_document(result)
    assert adhoc_violations(document, DRY_RUN_ENVELOPE_SCHEMA) == []
    assert document["ok"] is False
    for error in document["errors"]:
        assert error["message"].strip()


def test_nfr_005_validate_success_envelope_conforms(tmp_path):
    result = run_cli("validate", "--template", write_json(tmp_path, "t.json", ATTR_X))
    assert result.returncode == 0
    document = one_json_document(result)
    assert adhoc_violations(document, VALIDATE_ENVELOPE_SCHEMA) == []
    assert document["ok"] is True


def test_nfr_005_validate_failure_envelope_conforms(tmp_path):
    result = run_cli(
        "validate", "--template", write_json(tmp_path, "t.json", BAD_TEMPLATE)
    )
    assert result.returncode == 1
    document = one_json_document(result)
    assert adhoc_violations(document, VALIDATE_ENVELOPE_SCHEMA) == []
    assert document["ok"] is False
    for error in document["errors"]:
        assert error["message"].strip()


def test_nfr_005_examples_search_envelope_conforms():
    result = run_cli("examples", "search", "join", "--limit", "3")
    assert result.returncode == 0
    document = one_json_document(result)
    assert adhoc_violations(document, EXAMPLES_SEARCH_ENVELOPE_SCHEMA) == []
    assert document["hits"]


# Guard against vacuous ad-hoc schemas: each OQ-014b table-row rule must
# actually REJECT a violating envelope.

_DRY_RUN_SUCCESS = {
    "schema_version": "1.0",
    "ok": True,
    "result": "hello",
    "writes": {},
    "errors": [],
}
_DRY_RUN_FAILURE = {
    "schema_version": "1.0",
    "ok": False,
    "errors": [{"type": "TransformationError", "message": "boom"}],
}

_DRY_RUN_SCHEMA_NEGATIVES = {
    "success_missing_result": {k: v for k, v in _DRY_RUN_SUCCESS.items() if k != "result"},
    "success_missing_writes": {k: v for k, v in _DRY_RUN_SUCCESS.items() if k != "writes"},
    "success_with_errors": dict(
        _DRY_RUN_SUCCESS, errors=[{"type": "TransformationError", "message": "m"}]
    ),
    "failure_with_result": dict(_DRY_RUN_FAILURE, result=1),
    "failure_with_writes": dict(_DRY_RUN_FAILURE, writes={}),
    "failure_empty_errors": dict(_DRY_RUN_FAILURE, errors=[]),
    "wrong_schema_version": dict(_DRY_RUN_SUCCESS, schema_version="2.0"),
    "extra_top_level_key": dict(_DRY_RUN_SUCCESS, extra=1),
}


@pytest.mark.parametrize("kind", sorted(_DRY_RUN_SCHEMA_NEGATIVES))
def test_nfr_005_adhoc_dry_run_schema_rejects_oq_014b_violations(kind):
    assert adhoc_violations(_DRY_RUN_SCHEMA_NEGATIVES[kind], DRY_RUN_ENVELOPE_SCHEMA)


@pytest.mark.parametrize(
    "bad",
    [
        {"schema_version": "2.0", "hits": []},
        {"schema_version": "1.0", "hits": {}},
        {"schema_version": "1.0", "hits": [], "extra": 1},
        {"schema_version": "1.0", "hits": [{"doc": "no name/template"}]},
    ],
    ids=["wrong_version", "hits_not_array", "extra_key", "hit_missing_keys"],
)
def test_nfr_005_adhoc_examples_search_schema_rejects_violations(bad):
    assert adhoc_violations(bad, EXAMPLES_SEARCH_ENVELOPE_SCHEMA)


# ---------------------------------------------------------------------------
# 3. AuthoringResult §11.5 conformance — fixture per status (the producer is
#    the A3 skill; §11.5 prescribes fixture unit tests), real engine-derived
#    Verdicts / SampleChecks embedded (AD-018)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def real_documents():
    """Real building blocks from the pinned engine / library — never
    hand-written Verdicts (AD-018; fingerprints via content_fingerprint)."""
    return {
        "matched_verdict": verify(ATTR_X, matched_samples()),
        "validate_failed_verdict": verify(BAD_TEMPLATE, matched_samples()),
        "match_failed_verdict": verify(ATTR_X, match_failure_samples()),
        "ok_sample_check": check_samples(matched_samples()),
        "incomplete_sample_check": check_samples(incomplete_coverage_samples()),
        "unconfirmed_sample_check": check_samples(unconfirmed_samples()),
    }


def authoring_result_fixtures(docs):
    """One §11.5 AuthoringResult fixture per status value, shaped per the
    §11.5 table (ok true only for "matched"; AC-026 on every failure)."""
    return {
        "matched": {
            "schema_version": "1.0",
            "ok": True,
            "status": "matched",
            "explanation": "template verified at assurance matched",
            "template": ATTR_X,
            "verdict": docs["matched_verdict"],
            "repair_count": 0,
        },
        "need-samples": {
            "schema_version": "1.0",
            "ok": False,
            "status": "need-samples",
            "explanation": "coverage incomplete: the happy_path obligation has"
            " no satisfying case; more samples needed",
            "sample_check": docs["incomplete_sample_check"],
            "gaps": docs["incomplete_sample_check"]["gaps"],
            "samples_path": "samples/orders.json",
        },
        "deferred": {
            "schema_version": "1.0",
            "ok": False,
            "status": "deferred",
            "explanation": "user chose to defer authoring",
            "sample_check": docs["ok_sample_check"],
            "samples_path": "samples/orders.json",
        },
        "aborted": {
            "schema_version": "1.0",
            "ok": False,
            "status": "aborted",
            "explanation": "user chose to abort authoring",
        },
        "repair-exhausted": {
            "schema_version": "1.0",
            "ok": False,
            "status": "repair-exhausted",
            "explanation": "all repair attempts consumed without a matched verdict",
            "verdict": docs["match_failed_verdict"],
            "last_candidate": ATTR_X,
            "repair_count": 2,
        },
        "samples-rejected": {
            "schema_version": "1.0",
            "ok": False,
            "status": "samples-rejected",
            "explanation": "verify failed at the samples stage:"
            " SampleSet is unconfirmed",
            "sample_check": docs["unconfirmed_sample_check"],
            "gaps": docs["unconfirmed_sample_check"]["gaps"],
        },
        "verify-failed": {
            "schema_version": "1.0",
            "ok": False,
            "status": "verify-failed",
            "explanation": "verify failed at the validate stage; skill stopped"
            " without scheduling another repair",
            "verdict": docs["validate_failed_verdict"],
            "last_candidate": BAD_TEMPLATE,
            "repair_count": 0,
        },
        "schema-error": {
            "schema_version": "1.0",
            "ok": False,
            "status": "schema-error",
            "explanation": "SampleSet file is not valid JSON",
            "samples_path": "samples/orders.json",
        },
        "profile-rejected": {
            "schema_version": "1.0",
            "ok": False,
            "status": "profile-rejected",
            "explanation": "non-default marker requested; v1 always runs the"
            " AD-017 default profile, stopping without calling verify",
        },
    }


def test_nfr_005_fixture_set_covers_the_full_status_enum(real_documents):
    # Fixture-per-status sweep is exhaustive against both the SPEC list and
    # the bundled schema's enum (they must agree — OQ-014a keeps
    # "internal-error" out of both).
    schema_enum = load_schema("authoring_result.json")["properties"]["status"]["enum"]
    assert set(authoring_result_fixtures(real_documents)) == set(AUTHORING_STATUSES)
    assert set(schema_enum) == set(AUTHORING_STATUSES)


@pytest.mark.parametrize("status", AUTHORING_STATUSES)
def test_nfr_005_ac_026_authoring_result_fixture_conforms(real_documents, status):
    fixture = authoring_result_fixtures(real_documents)[status]
    assert schema_violations(fixture, "authoring_result.json") == []
    assert fixture["status"] == status
    # AC-026 / NFR-005: every non-matched status is a failure envelope with
    # ok false and an actionable explanation; success is "matched" alone.
    assert fixture["ok"] is (status == "matched")
    assert fixture["explanation"].strip()


def test_nfr_005_embedded_matched_verdict_is_really_matched(real_documents):
    # The success fixture embeds a REAL pinned-engine verdict (AD-004): never
    # report success unless ok && assurance "matched".
    verdict = real_documents["matched_verdict"]
    assert verdict["ok"] is True
    assert verdict["assurance"] == "matched"


# --- negatives: what the bundled schema MUST reject --------------------------


def test_nfr_005_oq_014a_internal_error_status_rejected(real_documents):
    # OQ-014a: "internal-error" is CLI-level only — never AuthoringResult.
    fixture = dict(
        authoring_result_fixtures(real_documents)["aborted"], status="internal-error"
    )
    assert schema_violations(fixture, "authoring_result.json")


@pytest.mark.parametrize(
    "mutation",
    [
        "unknown_status",
        "missing_explanation",
        "ok_not_boolean",
        "wrong_schema_version",
        "extra_top_level_key",
        "corrupt_embedded_verdict",
        "corrupt_embedded_sample_check",
        "corrupt_gap_code",
    ],
)
def test_nfr_005_ac_026_authoring_result_negative_rejected(real_documents, mutation):
    fixtures = authoring_result_fixtures(real_documents)
    if mutation == "unknown_status":
        fixture = dict(fixtures["aborted"], status="gave-up")
    elif mutation == "missing_explanation":
        fixture = {k: v for k, v in fixtures["aborted"].items() if k != "explanation"}
    elif mutation == "ok_not_boolean":
        fixture = dict(fixtures["aborted"], ok="false")
    elif mutation == "wrong_schema_version":
        fixture = dict(fixtures["aborted"], schema_version="2.0")
    elif mutation == "extra_top_level_key":
        fixture = dict(fixtures["aborted"], surprise=1)
    elif mutation == "corrupt_embedded_verdict":
        verdict = {
            k: v for k, v in fixtures["matched"]["verdict"].items() if k != "errors"
        }
        fixture = dict(fixtures["matched"], verdict=verdict)
    elif mutation == "corrupt_embedded_sample_check":
        check = {
            k: v
            for k, v in fixtures["samples-rejected"]["sample_check"].items()
            if k != "content_fingerprint"
        }
        fixture = dict(fixtures["samples-rejected"], sample_check=check)
    else:  # corrupt_gap_code
        fixture = dict(
            fixtures["need-samples"], gaps=[{"code": "not_a_gap", "message": "x"}]
        )
    assert schema_violations(fixture, "authoring_result.json")


# --- documented schema-looser-than-spec finding ------------------------------


def test_nfr_005_report_schema_gap_ok_true_with_non_matched_status_accepted(
    real_documents,
):
    """FINDING (reported, not fixed here): §11.5's status table implies
    ``ok: true`` occurs only with ``status: "matched"`` (AC-026 pins the
    failure side only), but authoring_result.json carries no ok/status
    coupling — the document below VALIDATES. Same family: ``template`` with
    ``ok: false`` also validates ("template?: only when ok" is prose-only).
    Tightening the schema is an FR-026 spec/schema change for spec-review,
    not something this conformance sweep may invent (AGENTS.md rule 1); this
    test documents the current accepted-by-schema behavior and must be
    updated if the schema is tightened."""
    fixtures = authoring_result_fixtures(real_documents)
    ok_true_aborted = dict(fixtures["aborted"], ok=True)
    assert schema_violations(ok_true_aborted, "authoring_result.json") == []
    template_with_failure = dict(fixtures["aborted"], template={"$": "this"})
    assert schema_violations(template_with_failure, "authoring_result.json") == []
