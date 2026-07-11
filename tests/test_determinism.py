"""NFR-002 / AC-018 — deterministic gates: same SampleSet + template + pin
=> identical ``SampleCheck`` / ``Verdict`` semantic content, under §11.0
equality (arrays ordered, object key order insignificant — resolved OQ-013,
§15; gap order §11.1, errors/diff order §11.2).

Equality strategy (legitimate because OQ-013 fixed all array orders): compare
byte-identical ``json.dumps(..., sort_keys=True)`` canonical dumps —
``sort_keys`` neutralizes exactly the one degree of freedom AC-018 declares
insignificant (object key order) and nothing else.

Three layers:

1. **In-process** — ``check_samples`` twice and ``verify`` twice on the same
   fixture objects, across a matched verdict, a dry-run-error-rich verdict,
   a diff-rich verdict (incl. ``writes_mismatch``), and a gap-rich
   ``SampleCheck``.
2. **Cross-process** — the CLI verbs run TWICE as separate subprocesses with
   two DIFFERENT ``PYTHONHASHSEED`` values: catches dict-iteration /
   hash-order dependence end-to-end, including the per-case dry-run worker
   subprocess boundary (workers inherit the seed via the environment).
3. **dry-run verb** — same template + input + includes under different hash
   seeds, on a fixture whose envelope carries ``NoContentRef`` and captured
   writes.

Engine-behavior expectations (which inputs fail ``attr``, what ``file`` /
``include`` produce) were derived by RUNNING the pinned engine via the
library (AD-018 / NFR-001), never from memory. Fingerprints always come from
``content_fingerprint()`` (OQ-015 acquisition-path rule), never hardcoded.

Deliberately NOT tested: wall-clock behavior near the 5s dry-run timeout —
inherently nondeterministic by design (AD-017; timeouts are a resource
limit, not part of the deterministic function NFR-002 promises).
"""

import copy
import json
import os
import subprocess
import sys

import pytest

from transon_authoring import check_samples, verify
from transon_authoring.samples import content_fingerprint

TAG_KEY = "$transon_authoring"
NO_CONTENT_REF = {TAG_KEY: "NO_CONTENT"}

#: Input-dependent template under the pinned engine (derived by running it):
#: {"x": v} -> v; non-dict input -> TransformationError at dry_run.
ATTR_X = {"$": "attr", "name": "x"}

#: Template that both writes (in-memory capture, AD-015) and transforms:
#: result = [NO_CONTENT (from `file`), input.x]; writes = {"out.json": input}.
TEMPLATE_WRITES = [
    {"$": "file", "name": "out.json", "content": {"$": "this"}},
    {"$": "attr", "name": "x"},
]

#: Two DIFFERENT hash seeds for the cross-process runs: if any array order or
#: envelope content depended on dict/set hash iteration order anywhere in the
#: pipeline (CLI process or dry-run worker), the two runs would diverge.
HASH_SEEDS = ("0", "12345")


# ---------------------------------------------------------------------------
# Canonical-dump equality (AC-018 / §11.0)
# ---------------------------------------------------------------------------


def canonical(document) -> bytes:
    """§11.0-equality canonical form: sort_keys neutralizes the insignificant
    object key order; array order stays significant (OQ-013)."""
    return json.dumps(
        document,
        sort_keys=True,
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    ).encode("utf-8")


def assert_deterministic(compute) -> dict:
    """Run *compute* twice; byte-identical canonical dumps; return the first."""
    first = compute()
    second = compute()
    assert canonical(first) == canonical(second)
    return first


# ---------------------------------------------------------------------------
# Fixture builders (§11.1 shapes; fingerprint via content_fingerprint, OQ-015)
# ---------------------------------------------------------------------------


def make_sample_set(cases, coverage, *, confirmed=True):
    ss = {
        "schema_version": "1.0",
        "coverage": copy.deepcopy(coverage),
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


def happy(obligation_id="happy"):
    return {
        "id": obligation_id,
        "kind": "happy_path",
        "description": "happy path",
        "acceptance": "accepted",
    }


def matched_samples():
    """(a) Matched under ATTR_X: two cases, two obligations, all met."""
    return make_sample_set(
        cases=[
            {"id": "c1", "input": {"x": "hello"}, "output": "hello", "satisfies": ["happy"]},
            {
                "id": "c2",
                "input": {"x": {"b": 2, "a": 1}},
                "output": {"a": 1, "b": 2},
                "satisfies": ["x-present"],
            },
        ],
        coverage=[
            happy(),
            {
                "id": "x-present",
                "kind": "optional_present",
                "target": "/x",
                "description": "x key present",
                "acceptance": "accepted",
            },
        ],
    )


def dry_run_failure_samples():
    """(b) Three cases whose inputs all fail ATTR_X at dry_run (non-dict
    inputs raise TransformationError under the pinned engine — derived by
    running it): a Verdict rich in per-case errors with case_ids."""
    return make_sample_set(
        cases=[
            {"id": "d1", "input": 5, "output": 0, "satisfies": ["happy"]},
            {"id": "d2", "input": "text", "output": 0, "satisfies": ["happy"]},
            {"id": "d3", "input": [1, 2], "output": 0, "satisfies": ["happy"]},
        ],
        coverage=[happy()],
    )


def match_failure_samples():
    """(c) Two cases that dry-run cleanly under TEMPLATE_WRITES but mismatch
    at match: a Verdict rich in DiffEntry kinds — value_mismatch, extra,
    missing, type_mismatch — plus a writes_mismatch per case (m1 declares
    wrong writes; m2 leaves captured writes undeclared, AC-024)."""
    return make_sample_set(
        cases=[
            {
                "id": "m1",
                "input": {"x": {"a": 2, "b": True}},
                # Actual result (pinned engine): [NO_CONTENT, {"a": 2, "b": true}].
                "output": [NO_CONTENT_REF, {"a": 1, "c": 3}],
                "writes": {"out.json": "wrong"},
                "satisfies": ["happy"],
            },
            {
                "id": "m2",
                "input": {"x": 7},
                # Actual: [NO_CONTENT, 7] and writes {"out.json": {"x": 7}}.
                "output": [NO_CONTENT_REF, "seven"],
                "satisfies": ["happy"],
            },
        ],
        coverage=[happy()],
    )


def gap_rich_samples():
    """SampleCheck rich in gaps: schema-VALID (so step 1 passes and the full
    §11.1 algorithm runs) but tripping many gap codes at once."""
    coverage = [
        happy("h"),  # accepted, never satisfied -> missing_happy_path
        {
            "id": "p",
            "kind": "optional_present",  # pointer kind, target absent
            "description": "needs target",
            "acceptance": "accepted",
        },  # -> target_required + optional_present_unmet
        {
            "id": "q",
            "kind": "list_many",
            "target": "no-leading-slash",
            "description": "bad pointer",
            "acceptance": "accepted",
        },  # -> target_invalid + list_many_unmet
        {
            "id": "r",
            "kind": "list_empty",
            "target": "/items",
            "description": "unmet structural",
            "acceptance": "accepted",
        },  # -> list_empty_unmet (no case satisfies it)
        {
            "id": "s",
            "kind": "mode_choice",
            "description": "still proposed",
            "acceptance": "proposed",
        },  # -> obligation_not_accepted
        {
            "id": "t",
            "kind": "custom",
            "description": "unmet custom",
            "acceptance": "accepted",
        },  # -> custom_unmet
        {
            "id": "dup",
            "kind": "custom",
            "description": "first of duplicate pair",
            "acceptance": "accepted",
        },
        {
            "id": "dup",
            "kind": "custom",
            "description": "second of duplicate pair",
            "acceptance": "accepted",
        },  # -> duplicate_id (coverage)
    ]
    cases = [
        {"id": "k1", "input": {"a": 1}, "output": 1, "satisfies": ["dup", "ghost"]},
        {"id": "k1", "input": {"a": 2}, "output": 2, "satisfies": ["dup", "ghost"]},
        # -> duplicate_id (cases) + case_satisfies_unknown ("ghost") per case
    ]
    ss = {
        "schema_version": "1.0",
        "coverage": coverage,
        "cases": cases,
        "waivers": [
            {
                "id": "w1",
                "clears_obligation_ids": ["nonexistent"],
                "reason": "dangling reference",
                "acceptance": "accepted",
            }  # -> waiver_invalid
        ],
        # confirmed false -> unconfirmed; deliberately wrong (but well-formed)
        # recorded fingerprint -> fingerprint_mismatch. NOT acquired from
        # content_fingerprint() precisely because a mismatch is the point.
        "confirmation": {"confirmed": False, "content_fingerprint": "0" * 64},
    }
    return ss


#: Gap codes the gap-rich fixture must trip (fixture-richness sanity check).
_EXPECTED_GAP_CODES = {
    "duplicate_id",
    "obligation_not_accepted",
    "missing_happy_path",
    "optional_present_unmet",
    "target_required",
    "target_invalid",
    "list_many_unmet",
    "list_empty_unmet",
    "custom_unmet",
    "waiver_invalid",
    "case_satisfies_unknown",
    "unconfirmed",
    "fingerprint_mismatch",
}


# ---------------------------------------------------------------------------
# 1. In-process determinism (NFR-002 / AC-018)
# ---------------------------------------------------------------------------


def test_ac_018_deterministic_verdict_matched():
    # (a) ok:true / assurance:"matched" Verdict.
    ss = matched_samples()
    verdict = assert_deterministic(lambda: verify(ATTR_X, ss))
    assert verdict["ok"] is True
    assert verdict["assurance"] == "matched"
    assert verdict["json"] == ATTR_X


def test_ac_018_deterministic_verdict_dry_run_errors():
    # (b) Verdict rich in dry-run EngineErrors: one per failing case, in
    # cases[] document order, each carrying its case_id (OQ-013 / OQ-011).
    ss = dry_run_failure_samples()
    verdict = assert_deterministic(lambda: verify(ATTR_X, ss))
    assert verdict["ok"] is False
    assert verdict["failed_stage"] == "dry_run"
    assert [error["case_id"] for error in verdict["errors"]] == ["d1", "d2", "d3"]
    assert all(error["type"] == "TransformationError" for error in verdict["errors"])


def test_ac_018_deterministic_verdict_match_diff():
    # (c) Verdict rich in DiffEntry kinds incl. writes_mismatch (AC-024).
    ss = match_failure_samples()
    verdict = assert_deterministic(lambda: verify(TEMPLATE_WRITES, ss))
    assert verdict["ok"] is False
    assert verdict["failed_stage"] == "match"
    kinds = {(entry["case_id"], entry["kind"]) for entry in verdict["diff"]}
    # m1: object diff under /1 plus declared-writes mismatch;
    # m2: scalar type mismatch plus undeclared-captured-writes mismatch.
    assert {
        ("m1", "value_mismatch"),
        ("m1", "extra"),
        ("m1", "missing"),
        ("m1", "writes_mismatch"),
        ("m2", "type_mismatch"),
        ("m2", "writes_mismatch"),
    } <= kinds
    # Grouped by case in cases[] order (OQ-013).
    case_order = [entry["case_id"] for entry in verdict["diff"]]
    assert case_order == sorted(case_order, key=["m1", "m2"].index)


@pytest.mark.parametrize(
    "builder",
    [matched_samples, dry_run_failure_samples, match_failure_samples],
    ids=["matched", "dry_run_errors", "match_diff"],
)
def test_ac_018_deterministic_sample_check(builder):
    ss = builder()
    check = assert_deterministic(lambda: check_samples(ss))
    assert check["ok_for_verify"] is True
    assert check["content_fingerprint"] == content_fingerprint(ss)


def test_ac_018_deterministic_sample_check_rich_gaps():
    # Many gap codes at once, in the normative §11.1 gap order every time.
    ss = gap_rich_samples()
    check = assert_deterministic(lambda: check_samples(ss))
    assert check["ok_for_verify"] is False
    assert check["coverage_complete"] is False
    assert check["confirmed"] is False
    assert {gap["code"] for gap in check["gaps"]} == _EXPECTED_GAP_CODES


# ---------------------------------------------------------------------------
# 2 + 3. Cross-process determinism under DIFFERENT PYTHONHASHSEED values
# ---------------------------------------------------------------------------


def run_cli_seeded(args, seed: str) -> subprocess.CompletedProcess:
    """One CLI invocation with a pinned hash seed; workers spawned by the CLI
    (one fresh subprocess per dry-run case) inherit the seed via the env."""
    env = dict(os.environ, PYTHONHASHSEED=seed)
    return subprocess.run(
        [sys.executable, "-m", "transon_authoring", *args],
        capture_output=True,
        env=env,
        timeout=120,
    )


def write_json(tmp_path, name, document) -> str:
    path = tmp_path / name
    path.write_text(
        json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8"
    )
    return str(path)


def assert_cli_deterministic_across_seeds(args, expected_exit) -> dict:
    """Run the CLI twice with two different hash seeds; parse each stdout
    envelope; equal exit codes and byte-identical canonical dumps."""
    runs = [run_cli_seeded(args, seed) for seed in HASH_SEEDS]
    for run in runs:
        assert run.returncode == expected_exit, run.stderr
    envelopes = [json.loads(run.stdout.decode("utf-8")) for run in runs]
    assert canonical(envelopes[0]) == canonical(envelopes[1])
    return envelopes[0]


def test_ac_018_cli_check_samples_deterministic_across_hash_seeds(tmp_path):
    samples_path = write_json(tmp_path, "samples.json", gap_rich_samples())
    envelope = assert_cli_deterministic_across_seeds(
        ["check-samples", "--samples", samples_path], expected_exit=1
    )
    assert envelope["ok_for_verify"] is False
    assert {gap["code"] for gap in envelope["gaps"]} == _EXPECTED_GAP_CODES


def test_ac_018_cli_verify_deterministic_across_hash_seeds(tmp_path):
    # The diff-rich fixture crosses the worker subprocess boundary twice per
    # run (two cases), so hash-order dependence in the worker, the host match
    # walk, or the envelope serialization would all surface here.
    template_path = write_json(tmp_path, "template.json", TEMPLATE_WRITES)
    samples_path = write_json(tmp_path, "samples.json", match_failure_samples())
    envelope = assert_cli_deterministic_across_seeds(
        ["verify", "--template", template_path, "--samples", samples_path],
        expected_exit=1,
    )
    assert envelope["ok"] is False
    assert envelope["failed_stage"] == "match"
    assert any(entry["kind"] == "writes_mismatch" for entry in envelope["diff"])


def test_ac_018_cli_dry_run_deterministic_across_hash_seeds(tmp_path):
    # Same template + input + includes twice under different hash seeds; the
    # envelope carries a NoContentRef (from `file`) AND captured writes, both
    # of which cross the worker JSON boundary.
    template = [
        {"$": "file", "name": "out.json", "content": {"$": "this"}},
        {"$": "include", "name": "sub"},
    ]
    input_value = {"x": {"b": 2, "a": 1}, "unused_key": [1, 2, 3]}
    includes = {"sub": {"$": "attr", "name": "x"}, "unused": {"$": "this"}}
    envelope = assert_cli_deterministic_across_seeds(
        [
            "dry-run",
            "--template",
            write_json(tmp_path, "template.json", template),
            "--input",
            write_json(tmp_path, "input.json", input_value),
            "--includes",
            write_json(tmp_path, "includes.json", includes),
        ],
        expected_exit=0,
    )
    assert envelope["ok"] is True
    # AD-018: shape derived by running the pinned engine — `file` yields the
    # NO_CONTENT sentinel, `include sub` yields input.x, `file` captures the
    # whole input in-memory (AD-015).
    assert envelope["result"] == [NO_CONTENT_REF, {"a": 1, "b": 2}]
    assert envelope["writes"] == {"out.json": input_value}
