"""AC-036 / OQ-027 / AD-024 — real-host eval driver + host→EpisodeResult adapter.

All offline and credential-free: the real Claude Agent SDK host is never
constructed or invoked. We test the pure adapter (`to_episode_result`), the
driver's `run_fixture` with an injected fake `Host`, and the `check_evals`
driver-selection seam (`_build_host`). The scorer, targets, baseline and lint
semantics are unchanged by this migration (AD-024) — the adapter is proved
score-equivalent to the demoted raw loop for the engine-free outcome classes.
"""

import json
import re
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
        # Every EpisodeResult carries the full §11.8 shape the scorer reads,
        # plus the additive FR-035 telemetry (cost_usd, messages) the run
        # artifacts consume — never scored (AC-034).
        assert set(episode) == {
            "submitted",
            "outcome",
            "tool_calls",
            "error",
            "tool_call_log",
            "tokens",
            "cost_usd",
            "messages",
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


def test_fr_035_serialize_messages_reproduces_turn_stream():
    """FR-035 / AC-038 — the whole-episode serializer reproduces the host turn
    stream: message class + subtype + ordered content blocks (text/thinking/
    tool_use/tool_result), each payload bounded. Duck-typed, so it runs offline
    on SimpleNamespace stand-ins for the SDK message objects."""
    from types import SimpleNamespace as NS

    # Named stand-ins so the serialized `type` is the SDK message class name.
    class AssistantMessage(NS):
        pass

    class UserMessage(NS):
        pass

    class ResultMessage(NS):
        pass

    msgs = [
        AssistantMessage(content=[
            NS(thinking="let me draft the template"),
            NS(text="Here is the template for your approval."),
            NS(name="Bash", input={"command": "python -m transon_authoring result"}, id="tu1"),
        ]),
        UserMessage(content=[NS(tool_use_id="tu1", content="matched\n" + "y" * 10)]),
        ResultMessage(subtype="success", content=None),
    ]
    out = host_harness._serialize_messages(msgs)
    assert [m["type"] for m in out] == [
        "AssistantMessage", "UserMessage", "ResultMessage"
    ]
    assert out[0]["subtype"] is None and out[2]["subtype"] == "success"
    # Assistant blocks are serialized in order with their kinds.
    assert out[0]["content"] == [
        {"type": "thinking", "thinking": "let me draft the template"},
        {"type": "text", "text": "Here is the template for your approval."},
        {"type": "tool_use", "name": "Bash",
         "input": {"command": "python -m transon_authoring result"}},
    ]
    # tool_result content is captured (and bounded via _tool_result_value).
    assert out[1]["content"] == [
        {"type": "tool_result", "tool_use_id": "tu1", "result": "matched\n" + "y" * 10}
    ]
    # A bare-string content turn and a None-content terminal are handled.
    assert out[2]["content"] is None
    assert host_harness._serialize_content("plain str") == "plain str"

    # Payloads are length-bounded so a huge tool result can't blow up the file.
    big = "z" * (host_harness._TOOL_RESULT_MAX + 50)
    huge = [UserMessage(content=[NS(tool_use_id="t", content=big)])]
    bounded = host_harness._serialize_messages(huge)[0]["content"][0]["result"]
    assert len(bounded) < len(big) and "chars)" in bounded


def test_fr_035_classify_terminal_carries_cost():
    """FR-035 — the host-reported episode cost (SDK total_cost_usd) rides through
    the classifier onto the outcome for every terminal class; additive telemetry,
    never touching the status decision (AC-034)."""
    cl = host_harness._classify_terminal
    env = {"schema_version": "1.0", "ok": True, "status": "matched"}
    assert cl("success", env, None, None, 0.19).cost_usd == 0.19
    assert cl("success", None, "nope", None, 0.02).cost_usd == 0.02  # no_submit
    assert cl("error_max_turns", None, None, None, 0.5).cost_usd == 0.5  # budget
    assert cl("error_during_execution", None, None, None, 0.01).cost_usd == 0.01  # infra
    # Cost is optional — a host that reports none leaves it None (additive identity).
    assert cl("success", env, None).cost_usd is None


def test_fr_035_to_episode_result_carries_cost_and_messages():
    """FR-035 / AC-038 — the adapter forwards the additive cost + whole-transcript
    telemetry from the HostOutcome into the EpisodeResult the run artifacts read;
    absent telemetry defaults to None / []."""
    serialized = [{"type": "AssistantMessage", "subtype": None, "content": None}]
    rich = HostOutcome(
        status=STATUS_RESULT,
        result={"ok": True, "status": "matched"},
        cost_usd=0.19,
        messages=serialized,
    )
    ep = to_episode_result(rich)
    assert ep["cost_usd"] == 0.19
    assert ep["messages"] == serialized
    # Defaults when the host exposes no cost/message telemetry.
    bare = to_episode_result(HostOutcome(status=STATUS_NO_RESULT))
    assert bare["cost_usd"] is None and bare["messages"] == []


def _zero_tokens():
    return {"input": 0, "output": 0, "cache_read": 0, "cache_creation": 0, "turns": 1}


def test_oq_016d_auth_fault_is_infra_error_not_no_submit():
    """OQ-016d — a provider/credential fault the host dresses up as a `success`
    turn must score infra_error, NEVER no_submit.

    Regression from a real capture: with an invalid key the Claude Code CLI emits
    two `api_retry` system messages, then the assistant text "Invalid API key ·
    Fix external API key", then ends `subtype: "success"` with no usage. The old
    classifier called that no_submit — a MODEL failure counted against the
    authoring target — so a dead/rate-limited key would score as the skill failing
    every episode, corrupting the rates, failure_modes and any accepted baseline.
    infra_error is instead excluded from the bucket denominator (capped at 10%)."""
    messages = [  # exactly the shape the FR-035 whole-transcript artifact captured
        {"type": "SystemMessage", "subtype": "init", "content": None},
        {"type": "SystemMessage", "subtype": "api_retry", "content": None},
        {"type": "SystemMessage", "subtype": "api_retry", "content": None},
        {"type": "AssistantMessage", "subtype": None,
         "content": [{"type": "text", "text": "Invalid API key · Fix external API key"}]},
        {"type": "ResultMessage", "subtype": "success", "content": None},
    ]
    hint = host_harness._infra_hint(messages, _zero_tokens())
    assert hint and "provider/credential fault" in hint

    outcome = host_harness._classify_terminal(
        "success", None, None, _zero_tokens(), 0.0, hint
    )
    assert outcome.status == STATUS_INFRA
    episode = to_episode_result(outcome)
    assert episode["outcome"] == "infra_error"  # NOT no_submit

    # And it scores as infra (excluded), not as a failed authoring fixture.
    matched = _load("matched")
    assert check_evals.score_episode(matched, episode) == "infra"


def test_oq_016d_zero_token_turn_is_infra_even_without_a_marker():
    """OQ-016d — the general rule, independent of any error wording: a `success`
    turn that consumed ZERO model tokens never ran (a real turn always burns input
    tokens), so it is a transport/provider fault, not a model failure."""
    silent = [{"type": "ResultMessage", "subtype": "success", "content": None}]
    hint = host_harness._infra_hint(silent, _zero_tokens())
    assert hint and "no model tokens" in hint
    assert host_harness._classify_terminal(
        "success", None, None, _zero_tokens(), 0.0, hint
    ).status == STATUS_INFRA
    # Missing usage entirely is treated the same way.
    assert host_harness._infra_hint(silent, None) is not None


def test_oq_016d_real_model_turn_without_envelope_stays_no_submit():
    """OQ-016d — the fix must NOT launder genuine model failures into infra. A turn
    that burned tokens and produced prose instead of an AuthoringResult is a real
    bucket failure and stays no_submit."""
    tokens = {"input": 120, "output": 900, "cache_read": 4000,
              "cache_creation": 0, "turns": 1}
    messages = [
        {"type": "AssistantMessage", "subtype": None,
         "content": [{"type": "text", "text": "I wrote flatten.js instead."}]},
        {"type": "ResultMessage", "subtype": "success", "content": None},
    ]
    assert host_harness._infra_hint(messages, tokens) is None
    outcome = host_harness._classify_terminal(
        "success", None, "I wrote flatten.js instead.", tokens, 0.02,
        host_harness._infra_hint(messages, tokens),
    )
    assert outcome.status == STATUS_NO_RESULT
    assert to_episode_result(outcome)["outcome"] == "no_submit"

    # A real envelope is never overridden by an infra hint either.
    env = {"schema_version": "1.0", "ok": True, "status": "matched"}
    assert host_harness._classify_terminal(
        "success", env, None, _zero_tokens(), 0.0, "some infra hint"
    ).status == STATUS_RESULT


def test_fr_030_review_approval_prompt_mandates_result_verbatim():
    """FR-030 (rev 2026-07-14) / FR-034 — the driver's review-approval message
    tells the model to emit by RUNNING the `result` command and returning its
    stdout verbatim, and forbids hand-re-typing the envelope. The real-host probe
    showed a bare 'emit the envelope as your response' prompt makes the small
    model re-type (and corrupt) large envelopes on the post-approval turn."""
    prompt = host_harness._REVIEW_APPROVAL.lower()
    assert "transon_authoring result" in prompt, (
        "approval prompt does not tell the model to run the `result` command"
    )
    assert "verbatim" in prompt, "approval prompt does not require verbatim stdout"
    assert re.search(r"(do not|don't|never)\b[^.]*\b(retype|reconstruct|by hand)", prompt), (
        "approval prompt does not forbid hand-re-typing the envelope"
    )


def test_oq_027_review_followup_is_neutral_and_allows_refusal():
    """OQ-027 — the review-follow-up must NOT fabricate approval of a template that
    was never presented. On the full-gate the old 'Approved — the template is
    correct, run `result`' derailed EVERY refuse fixture: turn 1 produced no
    envelope, so the driver 'approved' a non-existent template and the model went
    hunting for template/samples files it could not find (no_submit → adversarial
    rate 0.000). The message must instead be neutral about a template existing,
    state the session is non-interactive, and offer the REFUSAL exit (§2) as well
    as the matched-emit exit — without asking for files."""
    prompt = host_harness._REVIEW_APPROVAL.lower()
    # No fabricated approval of a correct template.
    assert "the template is correct" not in prompt
    assert "approved" not in prompt
    # Non-interactive framing that counters the observed "ask for the files / prior
    # session" derailment.
    assert "non-interactive" in prompt
    assert re.search(r"do not ask.*files|assume prior", prompt), (
        "follow-up does not forbid asking for files / assuming prior work"
    )
    # BOTH exits are offered: matched-emit (protects the authoring bucket) AND
    # refusal (fixes the adversarial bucket).
    assert "transon_authoring result" in prompt and "verbatim" in prompt
    assert "refusal" in prompt and 'status: "aborted"' in host_harness._REVIEW_APPROVAL


def test_fr_035_add_cost_is_none_identity():
    """FR-035 — multi-turn episode cost sums across turns with None as the
    additive identity (an all-None episode stays None, not 0.0)."""
    add = host_harness._add_cost
    assert add(None, None) is None
    assert add(0.1, None) == 0.1
    assert add(None, 0.2) == 0.2
    assert add(0.1, 0.2) == pytest.approx(0.3)
