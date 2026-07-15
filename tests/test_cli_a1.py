"""FR-003 / FR-014 / AC-021 — the A1 `python -m transon_authoring` verbs —
plus the CLI halves of FR-026 (AC-026 ingress schema-error envelopes) and
FR-028 (AC-027 reserved-profile-knob rejection). SPEC §11.6 in full, §11.0
serialization, resolved OQ-014 (§15).

Every invocation goes through a real subprocess (`sys.executable -m
transon_authoring …`) except the OQ-014a internal-fault test, which calls
``main()`` in-process with a monkeypatched handler so the fault is
controllable. Engine-behavior expectations (dry-run results) are derived by
running the pinned engine via the library — never from memory (AD-018 /
NFR-001). Fingerprints always come from ``content_fingerprint()`` (OQ-015
acquisition-path rule).
"""

import copy
import json
import subprocess
import sys

import pytest

from transon_authoring import check_samples, dry_run, verify
from transon_authoring._ingress import schema_violations
from transon_authoring.examples import search_examples
from transon_authoring.samples import content_fingerprint

#: Template with input-dependent behavior under the pinned engine (see
#: tests/test_verify.py): {"x": v} → v, {} → NO_CONTENT, non-dict → error.
ATTR_X = {"$": "attr", "name": "x"}

#: Statically invalid template: unknown rule → engine DefinitionError.
BAD_TEMPLATE = {"$": "no_such_rule_xyz"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "transon_authoring", *args],
        capture_output=True,
        timeout=120,
    )


def one_json_document(result) -> dict:
    """§11.0 / §11.6 emission discipline (AC-021): stdout is exactly ONE JSON
    document — a single compact write (`ensure_ascii=False, allow_nan=False,
    separators=(",", ":")`) plus a trailing newline — and stderr never carries
    a machine envelope."""
    text = result.stdout.decode("utf-8")
    document = json.loads(text)  # a second concatenated document would fail
    assert text == (
        json.dumps(
            document, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    )
    assert b'"schema_version"' not in result.stderr  # human diagnostics only
    return document


def write_json(tmp_path, name, document) -> str:
    path = tmp_path / name
    path.write_text(
        json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    return str(path)


def write_text(tmp_path, name, text) -> str:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def assert_cli_error(result, status):
    """Common CliError contract (AC-026): ok false, §11.5 status, bundled
    schema conformance."""
    document = one_json_document(result)
    assert document["schema_version"] == "1.0"
    assert document["ok"] is False  # AC-026: failure envelopes carry ok: false
    assert document["status"] == status
    assert isinstance(document["explanation"], str)
    assert schema_violations(document, "cli_error.json") == []
    return document


# ---------------------------------------------------------------------------
# SampleSet fixture builders (§11.1 shapes; fingerprint via content_fingerprint)
# ---------------------------------------------------------------------------


def make_sample_set(cases, *, confirmed=True):
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
    confirmation = {
        "confirmed": confirmed,
        "content_fingerprint": content_fingerprint(ss),
    }
    if confirmed:
        confirmation["confirmed_by"] = "user"
    ss["confirmation"] = confirmation
    return ss


def matched_samples():
    """Confirmed, complete, and MATCHING ATTR_X under the pinned engine."""
    return make_sample_set(
        [{"id": "c1", "input": {"x": "hello"}, "output": "hello", "satisfies": ["happy"]}]
    )


def unconfirmed_samples():
    return make_sample_set(
        [{"id": "c1", "input": {"x": 1}, "output": 1, "satisfies": ["happy"]}],
        confirmed=False,
    )


def match_failure_samples():
    """Schema-valid, ok_for_verify, but expectations mismatch ATTR_X."""
    return make_sample_set(
        [{"id": "c1", "input": {"x": 1}, "output": 2, "satisfies": ["happy"]}]
    )


# ---------------------------------------------------------------------------
# examples search (FR-003 / AC-021)
# ---------------------------------------------------------------------------


def test_ac_021_examples_search_envelope_exit_0():
    result = run_cli("examples", "search", "join", "--limit", "3")
    assert result.returncode == 0
    document = one_json_document(result)
    # §11.6 row + OQ-014b: {"schema_version":"1.0","hits":[…]}.
    assert set(document) == {"schema_version", "hits"}
    assert document["schema_version"] == "1.0"
    # Deterministic function of (query, snapshot, sidecar) — deep-equal to the
    # library surface (FR-003: same operation via library and python -m).
    assert document["hits"] == search_examples("join", limit=3)
    assert 1 <= len(document["hits"]) <= 3


# ---------------------------------------------------------------------------
# metadata (A0 behavior kept verbatim; §11.6 schema_version exemption)
# ---------------------------------------------------------------------------


def test_ac_021_metadata_still_verbatim_snapshot(tmp_path):
    from pathlib import Path

    snapshot = (
        Path(__file__).resolve().parents[1] / "resources" / "metadata-snapshot.json"
    )
    result = run_cli("metadata")
    assert result.returncode == 0
    # Verbatim engine document — exempt from the schema_version envelope rule.
    assert result.stdout == snapshot.read_bytes()
    assert result.stderr == b""


# ---------------------------------------------------------------------------
# check-samples (FR-003 / FR-014 / AC-021 exit-code matrix)
# ---------------------------------------------------------------------------


def test_fr_014_check_samples_ok_exit_0(tmp_path):
    ss = matched_samples()
    result = run_cli("check-samples", "--samples", write_json(tmp_path, "s.json", ss))
    assert result.returncode == 0
    document = one_json_document(result)
    # SampleCheck envelope, deep-equal to the library result (FR-003).
    assert document == check_samples(ss)
    assert document["ok_for_verify"] is True
    assert schema_violations(document, "sample_check.json") == []


def test_fr_014_check_samples_unconfirmed_exit_1(tmp_path):
    ss = unconfirmed_samples()
    result = run_cli("check-samples", "--samples", write_json(tmp_path, "s.json", ss))
    assert result.returncode == 1  # semantic failure on schema-valid input
    document = one_json_document(result)
    assert document == check_samples(ss)
    assert document["ok_for_verify"] is False
    assert "unconfirmed" in [gap["code"] for gap in document["gaps"]]
    assert schema_violations(document, "sample_check.json") == []


# ---------------------------------------------------------------------------
# verify (FR-003 / FR-014 / AC-021; single-shot, no repair loop)
# ---------------------------------------------------------------------------


def test_fr_014_verify_matched_exit_0(tmp_path):
    ss = matched_samples()
    result = run_cli(
        "verify",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--samples",
        write_json(tmp_path, "s.json", ss),
    )
    assert result.returncode == 0
    document = one_json_document(result)
    # Deterministic (NFR-002): CLI Verdict deep-equals the library verify().
    assert document == verify(ATTR_X, ss)
    assert document["ok"] is True
    assert document["assurance"] == "matched"
    assert document["json"] == ATTR_X
    assert schema_violations(document, "verdict.json") == []


def test_fr_034_ac_037_result_command_builds_authoring_result_envelope(tmp_path):
    """FR-034 / AC-037(a) — `result` machine-builds the COMPLETE §11.5
    AuthoringResult envelope from one verify: matched → success (exit 0),
    non-matched → the verify-derived failure envelope (exit 1) with samples-
    rejected vs verify-failed by the failed stage, malformed ingress → §11.6
    schema-error CliError (exit 2). Every success/failure emission is a
    schema-valid AuthoringResult."""
    ss = matched_samples()
    samples_path = write_json(tmp_path, "s.json", ss)

    # matched → complete success envelope; deep-equals the hand-spec'd shape.
    r = run_cli("result", "--template", write_json(tmp_path, "t.json", ATTR_X),
                "--samples", samples_path)
    assert r.returncode == 0
    env = one_json_document(r)
    assert schema_violations(env, "authoring_result.json") == []
    assert env["ok"] is True and env["status"] == "matched"
    assert env["template"] == ATTR_X
    assert env["verdict"] == verify(ATTR_X, ss)   # the exact library Verdict
    assert env["repair_count"] == 0

    # valid template that does not match → verify-failed, NO template (AC-004).
    r = run_cli("result", "--template", write_json(tmp_path, "b.json", BAD_TEMPLATE),
                "--samples", samples_path)
    assert r.returncode == 1
    env = one_json_document(r)
    assert schema_violations(env, "authoring_result.json") == []
    assert env["ok"] is False and env["status"] == "verify-failed"
    assert "template" not in env
    assert env["verdict"]["ok"] is False

    # unconfirmed SampleSet → samples stage fails → samples-rejected.
    r = run_cli("result", "--template", write_json(tmp_path, "t2.json", ATTR_X),
                "--samples", write_json(tmp_path, "u.json", unconfirmed_samples()))
    assert r.returncode == 1
    env = one_json_document(r)
    assert env["ok"] is False and env["status"] == "samples-rejected"
    assert env["verdict"]["failed_stage"] == "samples"

    # malformed template ingress → §11.6 schema-error CliError, exit 2.
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    r = run_cli("result", "--template", str(bad), "--samples", samples_path)
    assert r.returncode == 2
    assert one_json_document(r)["status"] == "schema-error"


def test_fr_034_ac_037_result_refuse_builds_refusal_envelope(tmp_path):
    """FR-034 (rev 2026-07-15) / AC-037(a) — `result --refuse --status S
    --explanation T` machine-builds the template-less refusal AuthoringResult
    (`{schema_version, ok:false, status, explanation}`, exit 1) so a §2 refusal /
    review stop is emitted verbatim, not hand-written. The real-host gate saw the
    small model refuse correctly but hand-write schema-invalid envelopes (missing
    schema_version/explanation, inventing error/reason keys) — invalid_submission
    on every adversarial episode."""
    # Each template-less refusal status → a schema-valid envelope, exit 1.
    for status in ("aborted", "deferred", "need-samples", "repair-exhausted"):
        r = run_cli("result", "--refuse", "--status", status,
                    "--explanation", "No such operator 'frobnicate' in the pinned engine.")
        assert r.returncode == 1, status
        env = one_json_document(r)
        assert schema_violations(env, "authoring_result.json") == [], (status, env)
        assert env == {
            "schema_version": "1.0", "ok": False, "status": status,
            "explanation": "No such operator 'frobnicate' in the pinned engine.",
        }
        assert "template" not in env and "verdict" not in env  # AC-004

    # A status OUTSIDE the template-less refusal set (verify-derived / matched /
    # CLI-level) is a usage error, not a silently-built envelope → exit 2.
    for bad_status in ("matched", "verify-failed", "samples-rejected",
                       "schema-error", "profile-rejected", "bogus"):
        r = run_cli("result", "--refuse", "--status", bad_status, "--explanation", "x")
        assert r.returncode == 2, bad_status
        assert one_json_document(r)["status"] == "schema-error"

    # Empty / whitespace explanation → exit 2 (a refusal must explain itself).
    r = run_cli("result", "--refuse", "--status", "aborted", "--explanation", "   ")
    assert r.returncode == 2
    assert one_json_document(r)["status"] == "schema-error"

    # --refuse is mutually exclusive with the verify inputs.
    t = write_json(tmp_path, "t.json", ATTR_X)
    r = run_cli("result", "--refuse", "--status", "aborted",
                "--explanation", "x", "--template", t)
    assert r.returncode == 2
    assert one_json_document(r)["status"] == "schema-error"

    # --status/--explanation without --refuse is a usage error too.
    r = run_cli("result", "--status", "aborted", "--explanation", "x")
    assert r.returncode == 2
    assert one_json_document(r)["status"] == "schema-error"

    # Plain verify mode with neither pair nor --refuse → exit 2 (not a crash).
    assert run_cli("result").returncode == 2


def test_fr_014_verify_failed_stage_exit_1(tmp_path):
    ss = match_failure_samples()
    result = run_cli(
        "verify",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--samples",
        write_json(tmp_path, "s.json", ss),
    )
    assert result.returncode == 1  # semantic verify failure, schema-valid input
    document = one_json_document(result)
    assert document["ok"] is False
    assert document["failed_stage"] == "match"
    assert "assurance" not in document
    assert schema_violations(document, "verdict.json") == []


def test_fr_003_no_repair_flag(tmp_path):
    # §11.6 / FR-007: verify is single-shot; --repair-attempts DOES NOT EXIST,
    # so argparse itself rejects it (usage error, exit 2, nothing on stdout).
    result = run_cli(
        "verify",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--samples",
        write_json(tmp_path, "s.json", matched_samples()),
        "--repair-attempts",
        "1",
    )
    assert result.returncode == 2
    assert result.stdout == b""
    assert result.stderr != b""


# ---------------------------------------------------------------------------
# validate (FR-003 / FR-014 / AC-021)
# ---------------------------------------------------------------------------


def test_fr_014_validate_ok_exit_0(tmp_path):
    result = run_cli("validate", "--template", write_json(tmp_path, "t.json", ATTR_X))
    assert result.returncode == 0
    document = one_json_document(result)
    # OQ-014b: {"schema_version":"1.0", ok, errors}.
    assert document == {"schema_version": "1.0", "ok": True, "errors": []}


def test_fr_014_validate_invalid_template_exit_1(tmp_path):
    result = run_cli(
        "validate", "--template", write_json(tmp_path, "t.json", BAD_TEMPLATE)
    )
    assert result.returncode == 1
    document = one_json_document(result)
    assert set(document) == {"schema_version", "ok", "errors"}
    assert document["schema_version"] == "1.0"
    assert document["ok"] is False
    assert len(document["errors"]) == 1
    assert document["errors"][0]["type"] == "DefinitionError"


# ---------------------------------------------------------------------------
# dry-run (FR-003 / FR-014 / AC-021; OQ-014b result/writes presence)
# ---------------------------------------------------------------------------


def test_fr_014_dry_run_success_has_result_and_writes(tmp_path):
    result = run_cli(
        "dry-run",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--input",
        write_json(tmp_path, "i.json", {"x": "hello"}),
    )
    assert result.returncode == 0
    document = one_json_document(result)
    # AD-018: expected values derived by running the pinned engine via the
    # library, not from memory.
    expected = dry_run(ATTR_X, {"x": "hello"})
    assert expected["ok"] is True
    # OQ-014b: on success result AND writes both present (writes may be {}).
    assert document == {
        "schema_version": "1.0",
        "ok": True,
        "result": expected["result"],
        "writes": expected["writes"],
        "errors": [],
    }
    assert document["writes"] == {}


def test_fr_014_dry_run_failure_omits_result_and_writes(tmp_path):
    result = run_cli(
        "dry-run",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--input",
        write_json(tmp_path, "i.json", 5),  # non-indexable → engine error
    )
    assert result.returncode == 1
    document = one_json_document(result)
    assert document["schema_version"] == "1.0"
    assert document["ok"] is False
    # OQ-014b: on failure both omitted and errors non-empty.
    assert "result" not in document
    assert "writes" not in document
    assert len(document["errors"]) >= 1
    assert document["errors"][0]["type"] == "TransformationError"


def test_fr_014_dry_run_accepts_bare_object_includes(tmp_path):
    result = run_cli(
        "dry-run",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--input",
        write_json(tmp_path, "i.json", {"x": "hello"}),
        "--includes",
        write_json(tmp_path, "inc.json", {"inc": {"$": "attr", "name": "x"}}),
    )
    assert result.returncode == 0
    document = one_json_document(result)
    assert document["ok"] is True


@pytest.mark.parametrize("includes_doc", ["[1,2]", "3", '"x"', "null"])
def test_ac_026_dry_run_includes_non_object_exit_2(tmp_path, includes_doc):
    # OQ-014d: --includes must be a BARE JSON object (includes-map shape);
    # any other JSON value → exit 2 schema-error.
    result = run_cli(
        "dry-run",
        "--template",
        write_json(tmp_path, "t.json", ATTR_X),
        "--input",
        write_json(tmp_path, "i.json", {"x": "hello"}),
        "--includes",
        write_text(tmp_path, "inc.json", includes_doc),
    )
    assert result.returncode == 2
    document = assert_cli_error(result, "schema-error")
    assert [error["type"] for error in document["errors"]] == ["PreflightError"]


# ---------------------------------------------------------------------------
# Ingress matrix (FR-026 / AC-026): every input flag of every verb → exit 2
# CliError schema-error with PreflightError entries
# ---------------------------------------------------------------------------

_VERB_FLAGS = [
    ("check-samples", "--samples"),
    ("verify", "--template"),
    ("verify", "--samples"),
    ("validate", "--template"),
    ("dry-run", "--template"),
    ("dry-run", "--input"),
    ("dry-run", "--includes"),
]

_BAD_INPUTS = {
    "malformed_json": "{",
    "duplicate_keys": '{"a": 1, "a": 2}',
    "non_finite_number": "[NaN]",
}


def _args_with_bad_flag(tmp_path, verb, bad_flag, bad_path):
    """CLI args for *verb* with every input flag pointing at a good file
    except *bad_flag*."""
    flags = {}
    if verb in ("verify", "validate", "dry-run"):
        flags["--template"] = write_json(tmp_path, "good-t.json", ATTR_X)
    if verb in ("check-samples", "verify"):
        flags["--samples"] = write_json(tmp_path, "good-s.json", matched_samples())
    if verb == "dry-run":
        flags["--input"] = write_json(tmp_path, "good-i.json", {"x": "hello"})
    flags[bad_flag] = bad_path
    return [verb] + [part for pair in flags.items() for part in pair]


@pytest.mark.parametrize("verb,flag", _VERB_FLAGS)
@pytest.mark.parametrize("kind", sorted(_BAD_INPUTS))
def test_ac_026_ingress_failures_exit_2_cli_error(tmp_path, verb, flag, kind):
    bad_path = write_text(tmp_path, "bad.json", _BAD_INPUTS[kind])
    result = run_cli(*_args_with_bad_flag(tmp_path, verb, flag, bad_path))
    assert result.returncode == 2
    document = assert_cli_error(result, "schema-error")
    assert len(document["errors"]) >= 1
    assert all(error["type"] == "PreflightError" for error in document["errors"])
    # Not a SampleCheck / Verdict body (§11.6 schema vs semantic failures).
    assert "ok_for_verify" not in document
    assert "failed_stage" not in document


@pytest.mark.parametrize("verb,flag", _VERB_FLAGS)
def test_ac_026_unreadable_input_file_exit_2(tmp_path, verb, flag):
    missing = str(tmp_path / "does-not-exist.json")
    result = run_cli(*_args_with_bad_flag(tmp_path, verb, flag, missing))
    assert result.returncode == 2
    document = assert_cli_error(result, "schema-error")
    assert all(error["type"] == "PreflightError" for error in document["errors"])
    assert "unreadable input file" in document["errors"][0]["message"]


@pytest.mark.parametrize("verb", ["check-samples", "verify"])
def test_ac_026_unsupported_schema_version_exit_2(tmp_path, verb):
    ss = matched_samples()
    ss["schema_version"] = "9.9"
    bad_path = write_json(tmp_path, "bad-s.json", ss)
    result = run_cli(*_args_with_bad_flag(tmp_path, verb, "--samples", bad_path))
    assert result.returncode == 2
    document = assert_cli_error(result, "schema-error")
    assert all(error["type"] == "PreflightError" for error in document["errors"])
    assert "schema_version" in document["errors"][0]["message"]


@pytest.mark.parametrize("verb", ["check-samples", "verify"])
def test_ac_026_sample_set_schema_invalid_is_cli_error_not_body(tmp_path, verb):
    # §11.6: SampleSet JSON-Schema invalidity is a CLI-level exit 2 CliError —
    # NOT a SampleCheck/Verdict body (the library-level all-flags-false
    # SampleCheck applies only to embedded use).
    ss = matched_samples()
    del ss["coverage"]  # required by sample_set.json
    bad_path = write_json(tmp_path, "bad-s.json", ss)
    result = run_cli(*_args_with_bad_flag(tmp_path, verb, "--samples", bad_path))
    assert result.returncode == 2
    document = assert_cli_error(result, "schema-error")
    assert all(error["type"] == "PreflightError" for error in document["errors"])
    assert "ok_for_verify" not in document
    assert "gaps" not in document


# ---------------------------------------------------------------------------
# Reserved profile knobs (FR-028 / AC-027)
# ---------------------------------------------------------------------------

_KNOB_VERBS = {
    "verify": lambda missing: ["verify", "--template", missing, "--samples", missing],
    "validate": lambda missing: ["validate", "--template", missing],
    "dry-run": lambda missing: ["dry-run", "--template", missing, "--input", missing],
}


@pytest.mark.parametrize("verb", sorted(_KNOB_VERBS))
@pytest.mark.parametrize("knob", [["--marker", "X"], ["--transformer", "Y"]])
def test_ac_027_reserved_knobs_rejected(tmp_path, verb, knob):
    # The input paths DO NOT EXIST: rejection must come post-parse but before
    # any input file read or engine work — a file read would have produced a
    # schema-error envelope instead of profile-rejected.
    missing = str(tmp_path / "does-not-exist.json")
    result = run_cli(*_KNOB_VERBS[verb](missing), *knob)
    assert result.returncode == 2
    document = assert_cli_error(result, "profile-rejected")
    # Exactly one ProfileError with stable library text (§11.6 / AC-027).
    assert len(document["errors"]) == 1
    assert document["errors"][0]["type"] == "ProfileError"
    assert knob[0] in document["errors"][0]["message"]
    assert "engine_type" not in document["errors"][0]


def test_ac_027_rejection_is_deterministic_stable_text(tmp_path):
    missing = str(tmp_path / "does-not-exist.json")
    first = run_cli("validate", "--template", missing, "--marker", "@")
    second = run_cli("validate", "--template", missing, "--marker", "%")
    # Stable library text: not parameterized by the requested marker value.
    assert first.stdout == second.stdout


# ---------------------------------------------------------------------------
# init-config is a known §11.6 verb since A2 (FR-022; conformance lives in
# tests/test_config.py)
# ---------------------------------------------------------------------------


def test_ac_021_init_config_now_conforms(tmp_path):
    # FR-022 landed in A2: init-config is a known subcommand that emits ONE
    # JSON document (the ProjectConfig) on stdout per the §11.6 global
    # contract; full behavior is covered by tests/test_config.py.
    result = subprocess.run(
        [sys.executable, "-m", "transon_authoring", "init-config",
         "--layout", "sibling"],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        cwd=str(tmp_path),
        timeout=120,
    )
    assert result.returncode == 0
    document = one_json_document(result)
    assert document["layout"] == "sibling"


# ---------------------------------------------------------------------------
# Internal fault → exit 3 (OQ-014a)
# ---------------------------------------------------------------------------


def test_oq_014a_internal_fault_exit_3(monkeypatch, capsys):
    from transon_authoring import __main__ as cli

    def boom(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(cli, "search_examples", boom)
    code = cli.main(["examples", "search", "join"])
    captured = capsys.readouterr()
    assert code == 3
    # Best-effort CliError envelope, single write on stdout (OQ-014a).
    document = json.loads(captured.out)
    assert captured.out == (
        json.dumps(
            document, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    )
    assert document == {
        "schema_version": "1.0",
        "ok": False,
        "status": "internal-error",
        "explanation": "RuntimeError: boom",
        "errors": [],
    }
    assert schema_violations(document, "cli_error.json") == []
    # Traceback on stderr only; never the machine envelope there. (The
    # traceback may echo source lines, so check for the envelope itself.)
    assert "Traceback" in captured.err
    assert "RuntimeError: boom" in captured.err
    assert '"status":"internal-error"' not in captured.err
