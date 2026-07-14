"""AC-036 / OQ-027 / AD-024 — real-host eval driver + host→EpisodeResult adapter.

All offline and credential-free: the real Claude Agent SDK host is never
constructed or invoked. We test the pure adapter (`to_episode_result`), the
driver's `run_fixture` with an injected fake `Host`, and the `check_evals`
driver-selection seam (`_build_host`). The scorer, targets, baseline and lint
semantics are unchanged by this migration (AD-024) — the adapter is proved
score-equivalent to the demoted raw loop for the engine-free outcome classes.
"""

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CASES = REPO_ROOT / "evals" / "cases"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_evals  # noqa: E402
import eval_harness  # noqa: E402  (the demoted raw loop, OQ-027d)
import host_harness  # noqa: E402
from host_harness import (  # noqa: E402
    STATUS_BUDGET,
    STATUS_INFRA,
    STATUS_NO_RESULT,
    STATUS_RESULT,
    HostOutcome,
    to_episode_result,
)

RUNNER_CFG = {
    "schema_version": "1.0",
    "provider": "anthropic",
    "model_id": "claude-haiku-4-5-20251001",
    "max_output_tokens": 8192,
    "tool_budget": 32,
    "runs_per_fixture": 3,
    "pass_rule": "majority",
    "seed": None,
    "harness": {"kind": "agent-sdk", "version": "0.2.116"},
}


def _load(expect: str) -> dict:
    """First committed fixture with the given expect bucket."""
    for path in sorted(CASES.glob("*.json")):
        fixture = json.loads(path.read_text(encoding="utf-8"))
        if fixture["expect"] == expect:
            return fixture
    raise AssertionError(f"no committed fixture with expect={expect!r}")


# A matched fixture + the AC-001 template that verifies matched against its
# SampleSet under the pinned engine — used to exercise the matched-PASS branch
# (the OQ-016a independent re-verify) through the adapter.
FLATTEN_FIXTURE = json.loads(
    (CASES / "seed-matched-flatten-orders.json").read_text(encoding="utf-8")
)
CORRECT_TEMPLATE = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "ac001" / "template.json").read_text(
        encoding="utf-8"
    )
)


def _matched_result(template: dict) -> dict:
    """A schema-valid AuthoringResult claiming matched (OQ-016a shape)."""
    return {
        "schema_version": "1.0",
        "ok": True,
        "status": "matched",
        "explanation": "verified matched",
        "template": template,
        "verdict": {
            "schema_version": "1.0",
            "ok": True,
            "assurance": "matched",
            "errors": [],
        },
    }


class FakeHost:
    """Injected `Host` that returns a scripted outcome and records what the
    driver handed it (so we can assert workspace isolation, OQ-027f(i))."""

    def __init__(self, outcome: HostOutcome):
        self._outcome = outcome
        self.seen: dict = {}

    def run_episode(self, *, skill_md, prompt, workspace, runner_cfg):
        self.seen = {
            "prompt": prompt,
            "skill_installed": (
                workspace / ".claude" / "skills" / "transon-authoring" / "SKILL.md"
            ).is_file(),
            "samples_present": (workspace / "samples.json").is_file(),
            "workspace": workspace,
            "workspace_existed": workspace.is_dir(),
        }
        return self._outcome


# --- the pure adapter (OQ-027e / AC-036b) ------------------------------------


def test_ac_036_oq_027_adapter_maps_all_outcomes():
    # OQ-027e status→outcome mapping is total over the four host statuses.
    result_payload = {"ok": True, "status": "matched"}
    cases = [
        (HostOutcome(status=STATUS_RESULT, result=result_payload), "submitted"),
        (HostOutcome(status=STATUS_NO_RESULT), "no_submit"),
        (HostOutcome(status=STATUS_BUDGET), "budget_exceeded"),
        (HostOutcome(status=STATUS_INFRA, error="boom"), "infra_error"),
    ]
    for outcome, expected in cases:
        episode = to_episode_result(outcome)
        assert episode["outcome"] == expected, (outcome.status, episode)
        # submitted is the returned object only for the RESULT status; None else.
        if outcome.status == STATUS_RESULT:
            assert episode["submitted"] == result_payload
        else:
            assert episode["submitted"] is None
        # Every EpisodeResult carries the full §11.8 shape the scorer reads.
        assert set(episode) == {
            "submitted",
            "outcome",
            "tool_calls",
            "error",
            "tool_call_log",
            "tokens",
        }

    # Defensive: an unknown host status degrades to infra_error, never a crash.
    assert to_episode_result(HostOutcome(status="???"))["outcome"] == "infra_error"


def test_ac_036_oq_027_schema_invalid_payload_is_submitted():
    # OQ-016b / OQ-027e — a schema-invalid returned payload still maps to
    # `submitted` with the raw payload retained (so it scores as
    # invalid_submission, never infra); the scorer re-validates it (AD-004).
    garbage = {"totally": "not an AuthoringResult"}
    episode = to_episode_result(HostOutcome(status=STATUS_RESULT, result=garbage))
    assert episode["outcome"] == "submitted"
    assert episode["submitted"] == garbage
    matched = _load("matched")
    # score_episode fails it (invalid_submission) without raising (OQ-016b).
    assert check_evals.score_episode(matched, episode) == "fail"


def test_ac_036_oq_027_adapter_score_matches_raw_loop():
    # AD-024 / AC-036b — for the engine-free outcome classes the adapter's
    # EpisodeResult scores identically to the equivalent demoted-raw-loop
    # EpisodeResult, proving the migration changes no scoring.
    refuse = _load("refuse")
    matched = _load("matched")
    invalid = {"not": "valid"}
    trials = [
        (refuse, HostOutcome(status=STATUS_NO_RESULT), "no_submit"),
        (refuse, HostOutcome(status=STATUS_BUDGET), "budget_exceeded"),
        (refuse, HostOutcome(status=STATUS_INFRA, error="x"), "infra_error"),
        # matched + schema-invalid submission: engine-free (fails at schema).
        (
            matched,
            HostOutcome(status=STATUS_RESULT, result=invalid),
            "submitted",
        ),
    ]
    for fixture, outcome, raw_outcome in trials:
        host_ep = to_episode_result(outcome)
        raw_ep = eval_harness._episode_result(
            submitted=outcome.result if outcome.status == STATUS_RESULT else None,
            outcome=raw_outcome,
            tool_calls=0,
            error=outcome.error,
        )
        assert check_evals.score_episode(
            fixture, host_ep
        ) == check_evals.score_episode(fixture, raw_ep)

    # matched-PASS: a returned template that re-verifies (AD-004) flows through
    # the adapter to a genuine "pass" — identical to the raw loop, and the one
    # branch the engine-free trials above cannot reach. Exercises the real
    # OQ-016a re-verify subprocess.
    matched_env = _matched_result(CORRECT_TEMPLATE)
    host_pass = to_episode_result(
        HostOutcome(status=STATUS_RESULT, result=matched_env)
    )
    raw_pass = eval_harness._episode_result(
        submitted=matched_env, outcome="submitted", tool_calls=1
    )
    assert check_evals.score_episode(FLATTEN_FIXTURE, host_pass) == "pass"
    assert check_evals.score_episode(
        FLATTEN_FIXTURE, host_pass
    ) == check_evals.score_episode(FLATTEN_FIXTURE, raw_pass)


# --- the driver run_fixture with an injected fake host -----------------------


def test_oq_027_run_fixture_installs_skill_and_confines_workspace():
    # OQ-027f(i)/(iv) — the driver installs SKILL.md into an ephemeral
    # workspace, writes the fixture SampleSet there, hands the intent as the
    # prompt, and tears the workspace down after the episode.
    matched = _load("matched")
    host = FakeHost(HostOutcome(status=STATUS_RESULT, result={"ok": True}))
    episode = host_harness.run_fixture(matched, RUNNER_CFG, host, REPO_ROOT)

    assert episode["outcome"] == "submitted"
    assert episode["submitted"] == {"ok": True}
    assert matched["intent_nl"] in host.seen["prompt"]
    assert host.seen["skill_installed"] is True
    assert host.seen["samples_present"] is True  # matched fixture supplies samples
    # Ephemeral workspace destroyed after scoring (OQ-027f(iv)).
    assert not host.seen["workspace"].exists()


def test_oq_027_run_fixture_host_fault_is_infra_error():
    # OQ-016d — a host/transport/credential fault is infra_error, never a crash
    # of the whole multi-fixture run.
    class Exploding:
        def run_episode(self, **kwargs):
            raise RuntimeError("transport down")

    episode = host_harness.run_fixture(_load("refuse"), RUNNER_CFG, Exploding(), REPO_ROOT)
    assert episode["outcome"] == "infra_error"
    assert "transport down" in episode["error"]


# --- the check_evals driver-selection seam (AC-036a) -------------------------


def test_ac_036_oq_027_driver_selected_by_harness_kind(monkeypatch):
    # AC-036a — check_evals selects the driver by runner.json.harness.kind.
    built = {}

    class FakeAgentSDKHost:
        def __init__(self, cfg):
            built["cfg"] = cfg

    monkeypatch.setattr(host_harness, "AgentSDKHost", FakeAgentSDKHost)
    host = check_evals._build_host(RUNNER_CFG)
    assert isinstance(host, FakeAgentSDKHost)
    assert built["cfg"] is RUNNER_CFG


def test_oq_027_unimplemented_harness_kind_is_config_error():
    # AC-036a / OQ-027a — an admitted-but-unimplemented kind is a config error
    # (surfaced as exit 2 by run_evals), exactly like an unsupported provider.
    cfg = dict(RUNNER_CFG, harness={"kind": "claude-code", "version": "1.0"})
    with pytest.raises(ValueError, match="claude-code"):
        check_evals._build_host(cfg)


def test_oq_027_extract_authoring_result_recovers_envelope():
    # OQ-027e — the AgentSDKHost recovers the AuthoringResult the skill emits as
    # its final text (whole JSON, fenced block, or wrapped in prose); unparseable
    # text yields None (→ the adapter scores it no_submit). Pure/offline — this
    # is the one piece of the live host path the deterministic gates can cover.
    env = {"schema_version": "1.0", "ok": True, "status": "matched"}
    # whole-text JSON
    assert host_harness._extract_authoring_result(json.dumps(env)) == env
    # fenced ```json block amid prose
    fenced = f"Here is the result:\n```json\n{json.dumps(env)}\n```\nDone."
    assert host_harness._extract_authoring_result(fenced) == env
    # prose-wrapped bare object (balanced-brace scan, envelope-shaped)
    prose = f"I finished. {json.dumps(env)} That's my answer."
    assert host_harness._extract_authoring_result(prose) == env
    # nothing parseable → None
    assert host_harness._extract_authoring_result("no json here at all") is None
    assert host_harness._extract_authoring_result(None) is None
    # A prose-wrapped FULL envelope whose nested `verdict` also has an "ok" key
    # must recover the whole envelope, not the inner verdict (top-level scan).
    full = _matched_result(CORRECT_TEMPLATE)
    assert "verdict" in full and full["verdict"].get("ok") is True
    got = host_harness._extract_authoring_result(f"Done. {json.dumps(full)} bye")
    assert got == full
    assert "template" in got and "status" in got  # not the nested verdict


def test_oq_027_classify_terminal_maps_subtypes():
    # OQ-027e / OQ-016d — the pure host-terminal classifier (the one slice of
    # the SDK path the offline gates can cover).
    cl = host_harness._classify_terminal
    STATUS = (host_harness.STATUS_RESULT, host_harness.STATUS_NO_RESULT,
              host_harness.STATUS_BUDGET, host_harness.STATUS_INFRA)
    env = {"schema_version": "1.0", "ok": True, "status": "matched"}
    # success + structured dict → submitted; success + prose envelope → submitted
    assert cl("success", env, None).status == host_harness.STATUS_RESULT
    assert cl("success", None, f"here: {json.dumps(env)}").status == host_harness.STATUS_RESULT
    # success but nothing parseable → no_submit (model's fault, a bucket failure)
    assert cl("success", None, "I wrote flatten.js instead").status == host_harness.STATUS_NO_RESULT
    # budget stop → budget_exceeded
    assert cl("error_max_turns", None, None).status == host_harness.STATUS_BUDGET
    # any other terminal subtype (or no ResultMessage) → infra_error, not no_submit
    assert cl("error_during_execution", None, None).status == host_harness.STATUS_INFRA
    assert cl(None, None, None).status == host_harness.STATUS_INFRA
    assert all(s in STATUS for s in (cl("success", env, None).status,))


def test_oq_027_needs_review_followup_only_on_clean_no_envelope():
    """OQ-027 — the driver answers the §6 review 'approve' exit ONLY when the
    first turn ended cleanly with no AuthoringResult (presented the template for
    approval and stopped). A real authoring/refusal envelope, and any
    infra/budget fault, are the model's real outcome and are never overridden."""
    needs = host_harness._needs_review_followup
    HO = host_harness.HostOutcome
    RES, NO, BUDGET, INFRA = (
        host_harness.STATUS_RESULT, host_harness.STATUS_NO_RESULT,
        host_harness.STATUS_BUDGET, host_harness.STATUS_INFRA,
    )
    # Presented for review / no parseable result → follow up.
    assert needs(HO(status=NO)) is True
    # A bare transon template (no ok/status/schema_version) → follow up.
    assert needs(HO(status=RES, result={"$": "map", "funcs": []})) is True
    # A real success envelope → NO follow-up (the model already answered).
    assert needs(HO(status=RES, result={"ok": True, "status": "matched"})) is False
    # A refusal envelope (ok:false) → NO follow-up — never approve a refusal.
    assert needs(HO(status=RES, result={"ok": False, "status": "aborted"})) is False
    # Even a schema-invalid but envelope-SHAPED payload is the model's answer.
    assert needs(HO(status=RES, result={"schema_version": "1.0"})) is False
    # infra / budget faults are real failures, never a review stall.
    assert needs(HO(status=INFRA, error="boom")) is False
    assert needs(HO(status=BUDGET)) is False
    # A non-dict result payload is not envelope-shaped → follow up.
    assert needs(HO(status=RES, result="oops")) is True


def test_fr_032_tool_calls_from_messages_records_tool_use_and_result():
    """OQ-027 / FR-032 — the driver builds the transcript tool-call log from the
    SDK message stream: one closed {seq,name,input,result} per tool_use, its
    result matched from the tool_result by id; plain text messages and orphan
    results are ignored."""
    from types import SimpleNamespace as NS
    tcm = host_harness._tool_calls_from_messages
    msgs = [
        NS(content=[NS(name="Bash", input={"command": "ls"}, id="tu1"),
                    NS(name="Read", input={"file_path": "x"}, id="tu2")]),
        NS(content="a plain assistant text turn (str, not a list) — ignored"),
        NS(content=[NS(tool_use_id="tu2", content="file body"),
                    NS(tool_use_id="tu1", content="a\nb\nc")]),
        NS(content=[NS(tool_use_id="no-such-id", content="orphan")]),
    ]
    calls = tcm(msgs)
    assert [c["seq"] for c in calls] == [1, 2]
    assert calls[0] == {"seq": 1, "name": "Bash",
                        "input": {"command": "ls"}, "result": "a\nb\nc"}
    assert calls[1] == {"seq": 2, "name": "Read",
                        "input": {"file_path": "x"}, "result": "file body"}
    for call in calls:  # the closed toolCall shape (schema §11.8)
        assert set(call) == {"seq", "name", "input", "result"}


def test_fr_032_tool_result_value_bounds_large_payloads():
    """OQ-027 / FR-032 — recorded tool results are bounded so transcripts stay
    diagnosable without blow-up; non-strings are JSON-encoded."""
    val = host_harness._tool_result_value
    assert val(None) is None
    assert val("short") == "short"
    big = "x" * (host_harness._TOOL_RESULT_MAX + 100)
    out = val(big)
    assert out.startswith("x" * host_harness._TOOL_RESULT_MAX) and "chars)" in out
    assert len(out) < len(big)
    assert val({"a": 1}) == '{"a": 1}'
