"""AC-001 / FR-004 / UC-001 — the hand-authored AC-001 path (§14 A1 DoD:
"hand AC-001 path with fixed SampleSet (no skill body)").

End-to-end demonstration of the authoring-verification path for the exact
AC-001 intent — "flatten each order's line items with the customer name" —
using the committed fixtures in tests/fixtures/ac001/ (see its README):
a hand-authored, user-confirmed, coverage-complete SampleSet and a
hand-written template, driven through BOTH the library API (`check_samples`,
`verify`; FR-003/FR-004/FR-027) and the §11.6 CLI verbs, plus a deliberately
wrong template variant proving the `match` stage really compares outputs.

Scope note: AC-001's full wording ends in "success `AuthoringResult` with
`verdict.assurance === "matched"`". The `AuthoringResult` envelope is the
skill-level §11.5 wrapper and lands with the skill body in A3; per the A1 DoD
this file covers the hand path up to the embedded Verdict — `ok: true`,
`assurance: "matched"` (AD-004/AC-013) — with no skill body involved.

All engine expectations in the fixtures were derived by running the pinned
`transon==0.1.7` at fixture-authoring time, never from memory (AD-018 /
NFR-001); the fixture fingerprint was acquired via
`transon_authoring.samples.content_fingerprint` (OQ-015 acquisition path).
"""

import json
import subprocess
import sys
from pathlib import Path

from transon_authoring import check_samples, verify
from transon_authoring._ingress import schema_violations
from transon_authoring.samples import content_fingerprint

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ac001"

SAMPLES_PATH = FIXTURES / "sample_set.json"
TEMPLATE_PATH = FIXTURES / "template.json"
WRONG_TEMPLATE_PATH = FIXTURES / "template_wrong.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "transon_authoring", *args],
        capture_output=True,
        timeout=120,
    )


def stdout_envelope(result) -> dict:
    """§11.6: stdout is exactly one JSON envelope; stderr is human-only."""
    document = json.loads(result.stdout.decode("utf-8"))
    assert b'"schema_version"' not in result.stderr
    return document


# ---------------------------------------------------------------------------
# Fixture shape — the SampleSet really is the AC-001 artifact it claims to be
# ---------------------------------------------------------------------------


def test_ac_001_fixture_is_confirmed_multi_kind_sample_set():
    # AC-001 requires a CONFIRMED COMPLETE SampleSet for the flatten intent;
    # guard the committed fixture against drive-by edits that would hollow
    # out the demonstration.
    ss = load(SAMPLES_PATH)
    assert "flatten each order's line items with the customer name" in (
        ss["intent_nl"].lower()
    )
    # Several accepted obligations spanning kinds (§11.1 table).
    kinds = {ob["kind"] for ob in ss["coverage"]}
    assert {"happy_path", "list_many", "list_empty", "optional_present",
            "optional_absent"} <= kinds
    assert all(ob["acceptance"] == "accepted" for ob in ss["coverage"])
    assert len(ss["cases"]) >= 3
    # Confirmation recorded by the fixture author acting as user (the library
    # never sets confirmed: true, §11.1); fingerprint frozen from the library
    # computation (OQ-015 acquisition path) and still current.
    assert ss["confirmation"]["confirmed"] is True
    assert ss["confirmation"]["confirmed_by"] == "user"
    assert ss["confirmation"]["content_fingerprint"] == content_fingerprint(ss)


# ---------------------------------------------------------------------------
# Library path (FR-003 / FR-004 / FR-027; AC-001 core)
# ---------------------------------------------------------------------------


def test_ac_001_fr_004_library_check_samples_ok_for_verify():
    check = check_samples(load(SAMPLES_PATH))
    assert check["ok_for_verify"] is True
    assert check["coverage_complete"] is True
    assert check["confirmed"] is True
    assert check["gaps"] == []


def test_ac_001_fr_004_library_verify_matched():
    template = load(TEMPLATE_PATH)
    verdict = verify(template, load(SAMPLES_PATH))
    # AD-004 / AC-013: success is ok && assurance === "matched", nothing less.
    assert verdict["ok"] is True
    assert verdict["assurance"] == "matched"
    assert verdict["errors"] == []
    assert "failed_stage" not in verdict
    # The verdict echoes the blessed candidate template (§11.2 Verdict.json).
    assert verdict["json"] == template
    assert schema_violations(verdict, "verdict.json") == []


# ---------------------------------------------------------------------------
# CLI path (FR-014 / AC-021 halves of UC-001: same artifacts via python -m)
# ---------------------------------------------------------------------------


def test_ac_001_fr_004_cli_check_samples_exit_0():
    result = run_cli("check-samples", "--samples", str(SAMPLES_PATH))
    assert result.returncode == 0
    document = stdout_envelope(result)
    assert document == check_samples(load(SAMPLES_PATH))
    assert document["ok_for_verify"] is True


def test_ac_001_fr_004_cli_verify_exit_0_matched_envelope():
    result = run_cli(
        "verify",
        "--template", str(TEMPLATE_PATH),
        "--samples", str(SAMPLES_PATH),
    )
    assert result.returncode == 0
    document = stdout_envelope(result)
    # Deterministic (NFR-002/AC-018): the CLI Verdict deep-equals library
    # verify() on the same committed artifacts.
    assert document == verify(load(TEMPLATE_PATH), load(SAMPLES_PATH))
    assert document["ok"] is True
    assert document["assurance"] == "matched"
    assert document["json"] == load(TEMPLATE_PATH)
    assert schema_violations(document, "verdict.json") == []


# ---------------------------------------------------------------------------
# Negative twist — verification is real, not vacuous (FR-005/§11.4 via FR-004
# path): dropping customer_name from the template fails at `match` with diffs
# attributed to exactly the cases whose outputs carry rows
# ---------------------------------------------------------------------------


def test_ac_001_wrong_template_fails_at_match_with_case_ids():
    verdict = verify(load(WRONG_TEMPLATE_PATH), load(SAMPLES_PATH))
    assert verdict["ok"] is False
    assert verdict["failed_stage"] == "match"
    assert "assurance" not in verdict
    assert "json" not in verdict
    # §11.2 stage 4: match produces no EngineErrors — diff alone (OQ-011).
    assert verdict["errors"] == []
    # Every row of every non-empty case output lost its customer_name; the
    # empty-list cases (c-no-orders, c-empty-line-items) still match and MUST
    # NOT appear. Order is normative (OQ-013): cases[] order, walk order.
    assert [
        (entry["case_id"], entry["kind"], entry["path"]) for entry in verdict["diff"]
    ] == [
        ("c-two-orders", "missing", "/0/customer_name"),
        ("c-two-orders", "missing", "/1/customer_name"),
        ("c-two-orders", "missing", "/2/customer_name"),
        ("c-note-present", "missing", "/0/customer_name"),
    ]
    assert verdict["diff"][0]["expected"] == "Ada"
    assert schema_violations(verdict, "verdict.json") == []


def test_ac_001_wrong_template_cli_verify_exit_1():
    result = run_cli(
        "verify",
        "--template", str(WRONG_TEMPLATE_PATH),
        "--samples", str(SAMPLES_PATH),
    )
    assert result.returncode == 1  # semantic verify failure on schema-valid input
    document = stdout_envelope(result)
    assert document == verify(load(WRONG_TEMPLATE_PATH), load(SAMPLES_PATH))
    assert document["failed_stage"] == "match"
    failing_cases = {entry["case_id"] for entry in document["diff"]}
    assert failing_cases == {"c-two-orders", "c-note-present"}
