"""FR-004 / FR-006 / FR-027 — `verify()` stage runner (SPEC §11.2; AC-013 /
AC-016; AC-001 groundwork).

Covers the §11.2 stage pipeline `samples` → `validate` → `dry_run` → `match`
(FR-006, fail-fast BETWEEN stages, every case processed WITHIN `dry_run` /
`match` — OQ-011), the AD-019 preflight (FR-027: `check_samples` gate before
any engine execution), the engine `validate` stage (FR-004), the normative
array orders (OQ-013), and the success contract `ok === true` ⇒
`assurance: "matched"` (AC-013 / AD-004).

Engine-behavior expectations (validate/transform error texts, NO_CONTENT for
a missing `attr` key) are derived by RUNNING the pinned engine
(`transon==0.1.7`) inside the test helpers — never from memory (AD-018 /
NFR-001). Fingerprints are always acquired via `content_fingerprint(...)` —
never hardcoded (OQ-015 acquisition-path rule).
"""

import copy
import importlib

import pytest

from transon_authoring import check_samples, validate, verify

# The package re-exports the `verify` FUNCTION under the same name as the
# submodule, so resolve the module itself for monkeypatching seams.
verify_module = importlib.import_module("transon_authoring.verify")
from transon_authoring._ingress import schema_violations
from transon_authoring.samples import content_fingerprint

TAG_KEY = "$transon_authoring"

#: Template used by most fixtures: input-dependent behavior under the pinned
#: engine — dict with "x" → its value; dict without "x" → NO_CONTENT
#: (AC-023 semantics); non-indexable input → TransformationError.
ATTR_X = {"$": "attr", "name": "x"}

#: Statically invalid template: unknown rule → engine DefinitionError.
BAD_TEMPLATE = {"$": "no_such_rule_xyz"}


# ---------------------------------------------------------------------------
# Pinned-engine oracles (AD-018: derive expectations by running the engine)
# ---------------------------------------------------------------------------


def engine_validate_message(template):
    """Verbatim str(DefinitionError) from the pinned engine's validate()."""
    from transon.transformers import DefinitionError, Transformer

    try:
        Transformer(template).validate()
    except DefinitionError as exc:
        return str(exc)
    raise AssertionError("template unexpectedly valid under the pinned engine")


def engine_transform_error(template, input_value):
    """(exception class name, verbatim message) from a pinned-engine run."""
    from transon.transformers import Transformer

    try:
        Transformer(template).transform(input_value, no_content=Transformer.NO_CONTENT)
    except Exception as exc:  # noqa: BLE001 — oracle mirrors OQ-014c leak rule
        return type(exc).__name__, str(exc)
    raise AssertionError("engine run unexpectedly succeeded")


# ---------------------------------------------------------------------------
# Fixture builders (§11.1 shapes)
# ---------------------------------------------------------------------------


def make_sample_set(cases, *, satisfied=True, confirmed=True, includes=None):
    """Schema-valid SampleSet with one accepted happy_path obligation."""
    ss = {
        "schema_version": "1.0",
        "coverage": [
            {
                "id": "happy",
                "kind": "happy_path",
                "description": "happy path",
                "acceptance": "accepted",
            }
        ],
        "cases": copy.deepcopy(cases),
        "waivers": [],
    }
    if includes is not None:
        ss["includes"] = includes
    if not satisfied:
        for case in ss["cases"]:
            case["satisfies"] = []
    confirmation = {
        "confirmed": confirmed,
        # §11.1: fingerprint over the canonical content subset, acquired via
        # content_fingerprint() — never hardcoded (OQ-015).
        "content_fingerprint": content_fingerprint(ss),
    }
    if confirmed:
        confirmation["confirmed_by"] = "user"
    ss["confirmation"] = confirmation
    return ss


def good_samples():
    """Confirmed complete SampleSet that MATCHES ATTR_X under the pin.

    c2 exercises AC-023 semantics: missing key → engine NO_CONTENT sentinel,
    expected via the NoContentRef AuthoringTag (§11.0 / §11.4 rule 1).
    """
    return make_sample_set(
        [
            {"id": "c1", "input": {"x": "hello"}, "output": "hello", "satisfies": ["happy"]},
            {
                "id": "c2",
                "input": {},
                "output": {TAG_KEY: "NO_CONTENT"},
                "satisfies": ["happy"],
            },
        ]
    )


def zero_cases_samples():
    return make_sample_set([])


def incomplete_coverage_samples():
    # Accepted obligation with no satisfying case → coverage_complete false.
    return make_sample_set(
        [{"id": "c1", "input": {"x": 1}, "output": 1, "satisfies": ["happy"]}],
        satisfied=False,
    )


def unconfirmed_samples():
    return make_sample_set(
        [{"id": "c1", "input": {"x": 1}, "output": 1, "satisfies": ["happy"]}],
        confirmed=False,
    )


def fingerprint_mismatch_samples():
    ss = good_samples()
    altered = copy.deepcopy(ss)
    altered["cases"][0]["input"] = {"x": "tampered"}
    # A real fingerprint — of DIFFERENT content — so only the binding fails.
    ss["confirmation"]["content_fingerprint"] = content_fingerprint(altered)
    return ss


def dry_run_failure_samples():
    """Three cases against ATTR_X: c1 and c3 fail in the engine, c2 passes."""
    return make_sample_set(
        [
            {"id": "c1", "input": 5, "output": 0, "satisfies": ["happy"]},
            {"id": "c2", "input": {"x": 1}, "output": 1, "satisfies": ["happy"]},
            {"id": "c3", "input": [1], "output": 0, "satisfies": ["happy"]},
        ]
    )


def match_failure_samples():
    """Two cases against ATTR_X that run fine but mismatch expectations."""
    return make_sample_set(
        [
            {"id": "c1", "input": {"x": 1}, "output": 2, "satisfies": ["happy"]},
            {
                "id": "c2",
                "input": {"x": {"a": 1}},
                "output": {"a": 1, "b": 2},
                "satisfies": ["happy"],
            },
        ]
    )


# ---------------------------------------------------------------------------
# Scenario registry — one verify() run per scenario, cached, shared by the
# all-paths tests (schema conformance, root-writes ban).
# ---------------------------------------------------------------------------

SCENARIOS = {
    "samples_zero_cases": lambda: (ATTR_X, zero_cases_samples()),
    "samples_incomplete_coverage": lambda: (ATTR_X, incomplete_coverage_samples()),
    "samples_unconfirmed": lambda: (ATTR_X, unconfirmed_samples()),
    "samples_fingerprint_mismatch": lambda: (ATTR_X, fingerprint_mismatch_samples()),
    "validate_failure": lambda: (BAD_TEMPLATE, good_samples()),
    "dry_run_failure": lambda: (ATTR_X, dry_run_failure_samples()),
    "match_failure": lambda: (ATTR_X, match_failure_samples()),
    "success": lambda: (ATTR_X, good_samples()),
}

_VERDICT_CACHE: dict = {}


def scenario_verdict(name):
    """verify() output for a scenario; cached (NFR-002: deterministic) and
    returned as a deep copy so no test can poison another."""
    if name not in _VERDICT_CACHE:
        template, ss = SCENARIOS[name]()
        _VERDICT_CACHE[name] = verify(template, ss)
    return copy.deepcopy(_VERDICT_CACHE[name])


# ---------------------------------------------------------------------------
# Stage 1 — samples (FR-027 / AD-019 / AC-016)
# ---------------------------------------------------------------------------


def _forbid_engine(monkeypatch):
    """AD-019: when the samples stage rejects, NO engine execution happens —
    neither Transformer construction (validate) nor a dry-run worker."""
    import transon.transformers as engine

    def _boom(*_args, **_kwargs):
        raise AssertionError("engine must not run when the samples stage fails")

    monkeypatch.setattr(engine, "Transformer", _boom)
    monkeypatch.setattr(verify_module, "run_dry_run_case", _boom)


def assert_samples_failure(ss, expected_gap_code, monkeypatch):
    _forbid_engine(monkeypatch)
    verdict = verify(ATTR_X, ss)
    assert verdict["ok"] is False
    assert verdict["failed_stage"] == "samples"
    assert "assurance" not in verdict  # AC-016: never `matched`
    assert verdict["errors"] == []
    # Gaps carried verbatim from the SampleCheck (AD-019).
    assert verdict["gaps"] == check_samples(ss)["gaps"]
    assert expected_gap_code in [gap["code"] for gap in verdict["gaps"]]
    assert "json" not in verdict and "diff" not in verdict
    return verdict


def test_ac_016_zero_cases_fails_samples_stage(monkeypatch):
    assert_samples_failure(zero_cases_samples(), "no_cases", monkeypatch)


def test_ac_016_incomplete_coverage_fails_samples_stage(monkeypatch):
    assert_samples_failure(
        incomplete_coverage_samples(), "missing_happy_path", monkeypatch
    )


def test_ac_016_unconfirmed_fails_samples_stage(monkeypatch):
    assert_samples_failure(unconfirmed_samples(), "unconfirmed", monkeypatch)


def test_ac_016_fingerprint_mismatch_fails_samples_stage(monkeypatch):
    assert_samples_failure(
        fingerprint_mismatch_samples(), "fingerprint_mismatch", monkeypatch
    )


def test_fr_027_schema_invalid_sample_set_fails_samples_stage(monkeypatch):
    # §11.0 rule 2: unknown AuthoringTag in an expectation → schema_invalid.
    ss = good_samples()
    ss["cases"][0]["output"] = {TAG_KEY: "bogus_tag"}
    assert_samples_failure(ss, "schema_invalid", monkeypatch)


# ---------------------------------------------------------------------------
# Stage order (FR-006): samples → validate → dry_run → match, fail-fast
# between stages
# ---------------------------------------------------------------------------


def test_fr_006_stage_order_samples_validate_dry_run_match(monkeypatch):
    # An invalid template WITH bad samples fails at samples, not validate —
    # the samples stage short-circuits everything after it.
    verdict = assert_samples_failure(
        unconfirmed_samples(), "unconfirmed", monkeypatch
    )
    assert verdict["failed_stage"] == "samples"
    monkeypatch.undo()
    # Same invalid template with good samples reaches (and fails) validate.
    assert verify(BAD_TEMPLATE, good_samples())["failed_stage"] == "validate"


# ---------------------------------------------------------------------------
# Stage 2 — validate (FR-004)
# ---------------------------------------------------------------------------


def test_fr_004_validate_failure_verbatim_engine_error_no_case_id(monkeypatch):
    # dry_run must not be entered after a validate failure (FR-006).
    def _boom(*_args, **_kwargs):
        raise AssertionError("dry_run must not run after a validate failure")

    monkeypatch.setattr(verify_module, "run_dry_run_case", _boom)
    verdict = verify(BAD_TEMPLATE, good_samples())
    assert verdict["ok"] is False
    assert verdict["failed_stage"] == "validate"
    assert "assurance" not in verdict
    assert "gaps" not in verdict and "diff" not in verdict and "json" not in verdict
    assert verdict["errors"] == [
        {
            "type": "DefinitionError",
            # Verbatim str(exc) from the pinned engine (§11.6 Engine errors).
            "message": engine_validate_message(BAD_TEMPLATE),
            "engine_type": "DefinitionError",
        }
    ]
    assert "case_id" not in verdict["errors"][0]  # OQ-011: validate errors


def test_fr_004_validate_debug_api_shape():
    # AD-006 debug surface: {"ok", "errors"}; the CLI adds schema_version.
    ok = validate(ATTR_X)
    assert ok == {"ok": True, "errors": []}
    bad = validate(BAD_TEMPLATE)
    assert bad["ok"] is False
    assert bad["errors"] == [
        {
            "type": "DefinitionError",
            "message": engine_validate_message(BAD_TEMPLATE),
            "engine_type": "DefinitionError",
        }
    ]
    assert "schema_version" not in ok and "schema_version" not in bad


# ---------------------------------------------------------------------------
# Stage 3 — dry_run (FR-006 / OQ-011 / OQ-013; AC-028 timeout propagation)
# ---------------------------------------------------------------------------


def test_fr_006_dry_run_failures_reported_per_case_in_cases_order(monkeypatch):
    calls = []
    real = verify_module.run_dry_run_case

    def recording(template, input_value, includes=None):
        calls.append(copy.deepcopy(input_value))
        return real(template, input_value, includes)

    monkeypatch.setattr(verify_module, "run_dry_run_case", recording)
    ss = dry_run_failure_samples()
    verdict = verify(ATTR_X, ss)

    # Every case ran, sequentially, in cases[] document order (OQ-011) —
    # including c2/c3 after c1 already failed.
    assert calls == [5, {"x": 1}, [1]]
    assert verdict["ok"] is False
    assert verdict["failed_stage"] == "dry_run"
    assert "assurance" not in verdict
    # Exactly one EngineError per failing case, in cases[] order (OQ-013).
    assert [error["case_id"] for error in verdict["errors"]] == ["c1", "c3"]
    for error, failing_input in zip(verdict["errors"], (5, [1])):
        engine_type, message = engine_transform_error(ATTR_X, failing_input)
        assert engine_type == "TransformationError"
        assert error["type"] == "TransformationError"
        assert error["engine_type"] == engine_type
        assert error["message"] == message  # verbatim str(exc)
    # match not entered; passing-case results NOT included (OQ-011).
    assert set(verdict) == {"schema_version", "ok", "failed_stage", "errors"}


def test_fr_006_timeout_error_propagates_with_case_id(monkeypatch):
    # AC-028 path: the host timeout envelope (worker killed) flows through the
    # stage runner and gains the failing case's case_id (OQ-011).
    timeout_message = "dry-run case exceeded the 5s wall-clock timeout"

    def fake(template, input_value, includes=None):
        if input_value == {"x": "slow"}:
            return {
                "ok": False,
                "errors": [{"type": "TimeoutError", "message": timeout_message}],
            }
        return {"ok": True, "result": "hello", "writes": {}, "errors": []}

    monkeypatch.setattr(verify_module, "run_dry_run_case", fake)
    ss = make_sample_set(
        [
            {"id": "c1", "input": {"x": "hello"}, "output": "hello", "satisfies": ["happy"]},
            {"id": "c2", "input": {"x": "slow"}, "output": "never", "satisfies": ["happy"]},
        ]
    )
    verdict = verify(ATTR_X, ss)
    assert verdict["ok"] is False
    assert verdict["failed_stage"] == "dry_run"
    assert verdict["errors"] == [
        {"type": "TimeoutError", "message": timeout_message, "case_id": "c2"}
    ]


# ---------------------------------------------------------------------------
# Stage 4 — match (FR-006 / §11.4 / OQ-013)
# ---------------------------------------------------------------------------


def test_fr_006_match_failure_diff_in_normative_order_errors_empty():
    verdict = scenario_verdict("match_failure")
    assert verdict["ok"] is False
    assert verdict["failed_stage"] == "match"
    assert "assurance" not in verdict
    assert verdict["errors"] == []  # OQ-011: match produces no EngineErrors
    assert "json" not in verdict
    # §11.2 normative order: cases in cases[] order; output entries walk the
    # union of keys code-point ascending.
    assert verdict["diff"] == [
        {
            "path": "",
            "kind": "value_mismatch",
            "expected": 2,
            "actual": 1,
            "case_id": "c1",
        },
        {"path": "/b", "kind": "missing", "expected": 2, "case_id": "c2"},
    ]


# ---------------------------------------------------------------------------
# Success (AC-013 / AD-004; AC-001 groundwork)
# ---------------------------------------------------------------------------


def test_ac_013_success_requires_matched():
    verdict = scenario_verdict("success")
    assert verdict == {
        "schema_version": "1.0",
        "ok": True,
        "assurance": "matched",
        "errors": [],
        # Candidate template echoed verbatim (§11.2 `json`).
        "json": {"$": "attr", "name": "x"},
    }


def test_ac_013_success_json_does_not_alias_caller_template():
    template = copy.deepcopy(ATTR_X)
    verdict = verify(template, good_samples())
    assert verdict["json"] == template
    verdict["json"]["name"] = "mutated"
    assert template == ATTR_X  # caller's template untouched


# ---------------------------------------------------------------------------
# All paths: no root-level writes (OQ-011) + Verdict schema conformance
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_fr_004_verdict_never_has_root_writes(name):
    # OQ-011: Verdict.writes is reserved and never emitted in v1.
    assert "writes" not in scenario_verdict(name)


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_fr_006_every_verdict_validates_against_bundled_schema(name):
    # FR-026 output discipline: every produced Verdict conforms to the
    # bundled §11.2 schema on every stage outcome.
    assert schema_violations(scenario_verdict(name), "verdict.json") == []


@pytest.mark.parametrize("name", sorted(SCENARIOS))
def test_fr_006_assurance_only_when_ok(name):
    # §11.2: ok === true iff all stages pass; then assurance is "matched".
    verdict = scenario_verdict(name)
    if verdict["ok"]:
        assert verdict["assurance"] == "matched"
        assert "failed_stage" not in verdict
    else:
        assert "assurance" not in verdict
        assert verdict["failed_stage"] in {"samples", "validate", "dry_run", "match"}
