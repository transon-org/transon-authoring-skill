"""FR-031 / AC-033 — self-reported session trace (observability).

AD-022: an ``AuthoringResult`` MAY carry an optional ordered ``trace`` (the
§11.5 ``TraceEntry`` shape). It is **diagnostic only**: schema-validated when
present, ignored by scoring and gates, its absence never invalidates a result,
and a malformed ``trace`` fails schema validation like any other field. These
tests pin the schema shape (AC-033), prove ``trace`` changes no mechanical
scoring, and assert the SKILL.md text-contract for the FR-031 instruction.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

from transon_authoring._ingress import load_schema, schema_violations

REPO_ROOT = Path(__file__).resolve().parents[1]
SKILL_PATH = REPO_ROOT / "SKILL.md"

# The mechanical scorer lives under scripts/; import it the same way
# tests/test_check_evals.py does (offline, refuse scoring needs no re-verify).
sys.path.insert(0, str(REPO_ROOT / "scripts"))
from check_evals import score_episode  # noqa: E402


# §11.5 TraceEntry.step — the 10-value closed enum (FR-031).
TRACE_STEPS = {
    "config",
    "ground",
    "propose",
    "present-gaps",
    "confirm",
    "draft",
    "verify",
    "repair",
    "review",
    "result",
}

# A well-formed trace: one full entry (command + outcome), one minimal entry
# carrying only the three required fields.
WELL_FORMED_TRACE = [
    {
        "seq": 1,
        "step": "config",
        "summary": "read project config; repair budget 3",
        "command": "python -m transon_authoring metadata",
        "outcome": "repair_attempts: 3",
    },
    {
        "seq": 2,
        "step": "result",
        "summary": "returned refusal — capability not in the pinned snapshot",
    },
]


def refuse_result(trace=None):
    """A schema-valid refusal AuthoringResult (OQ-016b shape), optionally
    carrying a self-reported ``trace``."""
    result = {
        "schema_version": "1.0",
        "ok": False,
        "status": "aborted",
        "explanation": "cannot be grounded in the pinned metadata",
    }
    if trace is not None:
        result["trace"] = trace
    return result


def episode(submitted):
    """Minimal EpisodeResult (eval_harness shape) with a submitted envelope."""
    return {
        "submitted": submitted,
        "outcome": "submitted",
        "tool_calls": 1,
        "error": None,
    }


def test_ac_033_authoring_result_with_trace_validates():
    # AC-033 / FR-031 — a well-formed `trace` (one full entry with command +
    # outcome, one minimal entry) validates against the §11.5 TraceEntry shape.
    result = refuse_result(trace=WELL_FORMED_TRACE)
    assert schema_violations(result, "authoring_result.json") == []


def test_ac_033_authoring_result_without_trace_validates():
    # AC-033 — `trace` is optional; the same result without it stays valid
    # (absence never invalidates a result — AD-022).
    assert schema_violations(refuse_result(), "authoring_result.json") == []


def test_fr_031_trace_entry_shape_matches_spec_11_5():
    # FR-031 — the bundled schema encodes the §11.5 TraceEntry shape: the
    # 10-value closed `step` enum, seq/step/summary required, closed object.
    entry = load_schema("authoring_result.json")["$defs"]["traceEntry"]
    assert set(entry["properties"]["step"]["enum"]) == TRACE_STEPS
    assert entry["required"] == ["seq", "step", "summary"]
    assert entry["additionalProperties"] is False
    assert entry["properties"]["seq"]["type"] == "integer"


@pytest.mark.parametrize(
    "trace",
    [
        pytest.param(
            [{"seq": 1, "step": "bogus", "summary": "x"}], id="bad-step-enum"
        ),
        pytest.param([{"step": "config", "summary": "x"}], id="missing-seq"),
        pytest.param(
            [{"seq": "1", "step": "config", "summary": "x"}], id="seq-as-string"
        ),
        pytest.param(
            [{"seq": 1, "step": "config", "summary": "x", "extra": 1}],
            id="unknown-key",
        ),
    ],
)
def test_ac_033_malformed_trace_fails_schema(trace):
    # AC-033 — a malformed `trace` fails schema validation like any other field.
    assert schema_violations(refuse_result(trace=trace), "authoring_result.json")


def test_ac_033_trace_changes_no_scoring():
    # AC-033 / AD-022 — `trace` is diagnostic only and never an input to
    # scoring: a `refuse` fixture's refusal AuthoringResult scores "pass"
    # identically with or without `trace`. Refuse scoring runs no re-verify
    # subprocess, so this stays fast and offline.
    refuse_fixture = {"id": "r", "expect": "refuse"}
    without = score_episode(refuse_fixture, episode(refuse_result()))
    with_trace = score_episode(
        refuse_fixture, episode(refuse_result(trace=WELL_FORMED_TRACE))
    )
    assert without == "pass"
    assert with_trace == without


def test_fr_031_skill_body_documents_trace_diagnostic_only():
    # FR-031 / AD-022 — the skill body instructs filling `trace`, names it
    # diagnostic-only, and cites FR-031 inside an html comment (NFR-012 /
    # AC-032: requirement-ID citations live only inside markdown comments).
    body = SKILL_PATH.read_text(encoding="utf-8")
    assert re.search(r"\btrace\b", body), "SKILL.md does not mention `trace`"
    assert re.search(
        r"diagnostic", body, re.IGNORECASE
    ), "SKILL.md does not name `trace` diagnostic-only"
    assert re.search(
        r"<!--.*?FR-031.*?-->", body, re.DOTALL
    ), "FR-031 must be cited inside an html comment, not in the prose"
