"""FR-017 / NFR-010 / OQ-017 — eval harness tool loop (scripted fake provider).

`scripts/eval_harness.py` is the raw provider-API tool loop of SPEC §11.8
(OQ-017): verbatim-SKILL.md system prompt plus fixed preamble (OQ-017a),
exactly three tools with workspace path confinement (OQ-017b), tool-budget and
no-submit outcomes as bucket-failures — never infra (OQ-017c) — provider
exceptions as `infra_error` (OQ-016d), and a lazily-imported provider SDK so
the module works without the optional `[evals]` extra (OQ-017d).

All tests drive `run_fixture` with a scripted FakeProvider (OQ-017e); the real
Anthropic SDK is never exercised.
"""

import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "eval_harness.py"


def load_harness(name="eval_harness_script"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    module = importlib.util.module_from_spec(spec)
    # Register before exec: dataclass processing on 3.12 resolves the module
    # through sys.modules.
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


harness = load_harness()

#: Tiny runner cfg (shape per OQ-017f); only tool_budget drives run_fixture.
RUNNER_CFG = {"tool_budget": 8}

#: Trivially valid template for the pinned engine (`validate` exits 0 on it).
TRIVIAL_TEMPLATE = json.dumps({"$": "attr", "name": "a"})

#: A submitted-refusal AuthoringResult (§11.5 shape is scored elsewhere; the
#: harness records the submission verbatim).
AUTHORING_RESULT = {
    "schema_version": "1.0",
    "ok": False,
    "status": "need-samples",
    "explanation": "no SampleSet provided",
}


class FakeProvider:
    """Scripted provider: pops one Turn per create_turn call (OQ-017e)."""

    def __init__(self, turns):
        self.turns = list(turns)
        self.systems = []
        self.message_log = []

    def create_turn(self, system, messages, tools):
        self.systems.append(system)
        self.message_log = copy.deepcopy(messages)
        assert [t["name"] for t in tools] == [
            "write_file",
            "transon_authoring",
            "submit_result",
        ]  # OQ-017b: exactly three tools
        if not self.turns:
            return harness.Turn(text="nothing more to do")
        return self.turns.pop(0)


def tool_turn(name, tool_input, tool_id="tu-1"):
    return harness.Turn(
        tool_uses=[harness.ToolUse(id=tool_id, name=name, input=tool_input)]
    )


def spy_workspace(monkeypatch):
    """Record the temp workspace run_fixture creates (it is removed in finally)."""
    created = {}
    real_mkdtemp = tempfile.mkdtemp

    def recording_mkdtemp(*args, **kwargs):
        path = real_mkdtemp(*args, **kwargs)
        created["dir"] = path
        return path

    monkeypatch.setattr(harness.tempfile, "mkdtemp", recording_mkdtemp)
    return created


def latest_tool_results(provider):
    results = [
        block
        for message in provider.message_log
        if message["role"] == "user" and isinstance(message["content"], list)
        for block in message["content"]
        if block["type"] == "tool_result"
    ]
    return [
        (block["tool_use_id"], json.loads(block["content"]), block["is_error"])
        for block in results
    ]


def test_fr_017_oq_017_tool_loop_write_run_submit(monkeypatch):
    # FR-017/OQ-017b — write_file → transon_authoring → submit_result, with
    # the transon_authoring tool actually shelling out to the pinned CLI.
    created = spy_workspace(monkeypatch)
    provider = FakeProvider(
        [
            tool_turn("write_file", {"path": "t.json", "content": TRIVIAL_TEMPLATE}, "w1"),
            tool_turn(
                "transon_authoring", {"argv": ["validate", "--template", "t.json"]}, "r1"
            ),
            tool_turn("submit_result", {"result": AUTHORING_RESULT}, "s1"),
        ]
    )
    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "read attribute a"}, RUNNER_CFG, provider, REPO_ROOT
    )

    assert episode["outcome"] == "submitted"
    assert episode["submitted"] == AUTHORING_RESULT  # round-trips verbatim
    assert episode["tool_calls"] == 3
    assert episode["error"] is None

    results = dict((tid, payload) for tid, payload, _ in latest_tool_results(provider))
    assert results["w1"] == {"ok": True, "path": "t.json"}
    # Real subprocess exit code from `python -m transon_authoring validate`.
    assert results["r1"]["exit_code"] == 0
    assert json.loads(results["r1"]["stdout"])["ok"] is True
    # Workspace is cleaned up after the episode.
    assert not Path(created["dir"]).exists()


def test_fr_017_oq_017_tool_budget_exceeded_is_bucket_failure():
    # OQ-017c — exceeding tool_budget is a bucket-failure outcome, not infra.
    endless_write = tool_turn("write_file", {"path": "loop.txt", "content": "x"})
    provider = FakeProvider([copy.deepcopy(endless_write) for _ in range(50)])
    cfg = {"tool_budget": 3}
    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "loop forever"}, cfg, provider, REPO_ROOT
    )
    assert episode["outcome"] == "budget_exceeded"
    assert episode["submitted"] is None
    assert episode["tool_calls"] == 4  # the call that crossed the budget


def test_fr_017_oq_017_no_submit_is_failure():
    # OQ-017c — ending with plain text and no tool call scores as no_submit.
    provider = FakeProvider([harness.Turn(text="here is your template: {…}")])
    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "do something"}, RUNNER_CFG, provider, REPO_ROOT
    )
    assert episode["outcome"] == "no_submit"
    assert episode["submitted"] is None
    assert episode["tool_calls"] == 0


def test_fr_017_oq_017_workspace_path_confinement(monkeypatch):
    # OQ-017b — write_file rejects absolute paths and workspace escapes; the
    # episode continues (error tool result), nothing is written outside.
    created = spy_workspace(monkeypatch)
    provider = FakeProvider(
        [
            tool_turn("write_file", {"path": "../escape.txt", "content": "x"}, "e1"),
            tool_turn("write_file", {"path": "/abs/path", "content": "x"}, "e2"),
            tool_turn("write_file", {"path": "inside.txt", "content": "ok"}, "e3"),
        ]
    )
    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "try to escape"}, RUNNER_CFG, provider, REPO_ROOT
    )

    # The episode survived all three tool calls, then ran out of script.
    assert episode["outcome"] == "no_submit"
    assert episode["tool_calls"] == 3

    results = {tid: (payload, is_err) for tid, payload, is_err in latest_tool_results(provider)}
    assert results["e1"][1] is True and "error" in results["e1"][0]
    assert results["e2"][1] is True and "error" in results["e2"][0]
    assert results["e3"][1] is False  # in-workspace writes still work

    # Nothing landed outside the (now removed) workspace.
    workspace = Path(created["dir"])
    assert not workspace.exists()
    assert not (workspace.parent / "escape.txt").exists()
    assert not Path("/abs/path").exists()


def test_fr_017_oq_017_provider_exception_is_infra_error():
    # OQ-016d — provider/transport exceptions are infra_error, never scored
    # as model behavior.
    class ExplodingProvider:
        def create_turn(self, system, messages, tools):
            raise ConnectionError("api unreachable")

    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "anything"}, RUNNER_CFG, ExplodingProvider(), REPO_ROOT
    )
    assert episode["outcome"] == "infra_error"
    assert episode["submitted"] is None
    assert "ConnectionError" in episode["error"]
    assert "api unreachable" in episode["error"]


def test_fr_017_oq_017_transon_authoring_argv_paths_confined():
    # OQ-017b — the transon_authoring tool confines path-bearing argv values
    # (--template/--samples/--input/--includes) to the workspace: absolute or
    # ..-escaping paths are rejected as an error tool result, no subprocess
    # spawned; confined relative paths still run.
    provider = FakeProvider(
        [
            tool_turn(
                "transon_authoring",
                {"argv": ["verify", "--template", "/etc/passwd", "--samples", "s.json"]},
                "p1",
            ),
            tool_turn(
                "transon_authoring",
                {"argv": ["check-samples", "--samples", "../outside.json"]},
                "p2",
            ),
            tool_turn(
                "transon_authoring",
                {"argv": ["verify", "--template=/etc/passwd", "--samples", "s.json"]},
                "p4",
            ),
            tool_turn(
                "transon_authoring",
                {"argv": ["verify", "--temp=/etc/passwd", "--samples", "s.json"]},
                "p5",
            ),
            tool_turn(
                "transon_authoring",
                {"argv": ["validate", "--template", "missing.json"]},
                "p3",
            ),
        ]
    )
    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "try path escapes"}, RUNNER_CFG, provider, REPO_ROOT
    )
    assert episode["outcome"] == "no_submit"
    results = {
        tid: (payload, is_err) for tid, payload, is_err in latest_tool_results(provider)
    }
    assert results["p1"][1] is True and "--template" in results["p1"][0]["error"]
    assert results["p2"][1] is True and "--samples" in results["p2"][0]["error"]
    # The argparse "--flag=value" form is confined too.
    assert results["p4"][1] is True and "--template" in results["p4"][0]["error"]
    # Abbreviated flags (--temp aliasing --template) cannot slip past the
    # confinement: the CLI runs with allow_abbrev=False and rejects them as a
    # usage error (exit 2) instead of resolving them to the path flag.
    assert results["p5"][1] is False
    assert results["p5"][0]["exit_code"] == 2
    assert "--temp" in results["p5"][0]["stderr"]
    # Confined path reaches the real CLI (exit 2 for the missing file — the
    # subprocess actually ran).
    assert results["p3"][1] is False
    assert results["p3"][0]["exit_code"] == 2


def test_fr_017_oq_016d_tool_fault_is_infra_error(monkeypatch):
    # OQ-016d — a harness fault during tool execution (e.g. subprocess
    # timeout) scores the episode infra_error instead of crashing the whole
    # multi-fixture run.
    def exploding_tool(workspace, tool_input):
        raise subprocess.TimeoutExpired(cmd="transon_authoring", timeout=300)

    monkeypatch.setattr(harness, "_tool_transon_authoring", exploding_tool)
    provider = FakeProvider([tool_turn("transon_authoring", {"argv": ["metadata"]})])
    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "anything"}, RUNNER_CFG, provider, REPO_ROOT
    )
    assert episode["outcome"] == "infra_error"
    assert episode["submitted"] is None
    assert "harness fault in transon_authoring" in episode["error"]
    assert "TimeoutExpired" in episode["error"]


def test_fr_017_oq_017_samples_written_and_skill_md_injected(monkeypatch):
    # OQ-017a — fixture samples are written to <workspace>/samples.json before
    # the first turn; the system prompt starts with the exact SKILL.md bytes
    # and the user message names the samples path.
    created = spy_workspace(monkeypatch)
    fixture = json.loads(
        (REPO_ROOT / "evals" / "cases" / "seed-matched-attr-dynamic-name.json").read_text(
            encoding="utf-8"
        )
    )
    seen = {}

    class InspectingProvider(FakeProvider):
        def create_turn(self, system, messages, tools):
            samples_path = Path(created["dir"]) / "samples.json"
            seen["samples_exists"] = samples_path.exists()
            if samples_path.exists():
                seen["samples"] = json.loads(samples_path.read_text(encoding="utf-8"))
            return super().create_turn(system, messages, tools)

    provider = InspectingProvider(
        [tool_turn("submit_result", {"result": AUTHORING_RESULT})]
    )
    episode = harness.run_fixture(fixture, RUNNER_CFG, provider, REPO_ROOT)

    assert episode["outcome"] == "submitted"
    assert seen["samples_exists"] is True
    assert seen["samples"] == fixture["samples"]

    skill_md = (REPO_ROOT / "SKILL.md").read_bytes().decode("utf-8")
    assert provider.systems[0].startswith(skill_md)  # verbatim bytes, then preamble
    assert provider.systems[0] == skill_md + harness.HARNESS_PREAMBLE
    assert "samples.json" in provider.message_log[0]["content"]
    assert fixture["intent_nl"] in provider.message_log[0]["content"]


def test_fr_032_run_fixture_records_ordered_tool_call_log(monkeypatch):
    # FR-032 / AC-034 — run_fixture records tool_call_log: an ordered
    # [{seq,name,input,result}] record for every EXECUTED dispatch. tool_calls
    # stays the int call *count* (the existing scoring contract, unchanged).
    provider = FakeProvider(
        [
            tool_turn("write_file", {"path": "t.json", "content": TRIVIAL_TEMPLATE}, "w1"),
            tool_turn(
                "transon_authoring", {"argv": ["validate", "--template", "t.json"]}, "r1"
            ),
            tool_turn("submit_result", {"result": AUTHORING_RESULT}, "s1"),
        ]
    )
    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "read attribute a"}, RUNNER_CFG, provider, REPO_ROOT
    )

    assert episode["tool_calls"] == 3  # still the int call count (unchanged)

    log = episode["tool_call_log"]
    assert [r["seq"] for r in log] == [1, 2, 3]  # contiguous 1..N, in order
    assert [r["name"] for r in log] == [
        "write_file",
        "transon_authoring",
        "submit_result",
    ]
    # write_file record: verbatim input + the {ok, path} payload sent to the model.
    assert log[0]["input"] == {"path": "t.json", "content": TRIVIAL_TEMPLATE}
    assert log[0]["result"] == {"ok": True, "path": "t.json"}
    # transon_authoring record: result is the real {exit_code, stdout, stderr}.
    assert log[1]["input"] == {"argv": ["validate", "--template", "t.json"]}
    assert log[1]["result"]["exit_code"] == 0
    assert json.loads(log[1]["result"]["stdout"])["ok"] is True
    # submit_result terminal record: result is None; input carries the verbatim
    # submitted AuthoringResult payload.
    assert log[2]["result"] is None
    assert log[2]["input"] == {"result": AUTHORING_RESULT}
    assert episode["submitted"] == AUTHORING_RESULT


def test_fr_032_budget_crossing_call_not_logged():
    # FR-032 — the tool call that crosses tool_budget never executes, so it is
    # not appended to tool_call_log; the log stays contiguous over the executed
    # calls (seq 1..3 for budget 3) even though tool_calls counts the crossing.
    endless_write = tool_turn("write_file", {"path": "loop.txt", "content": "x"})
    provider = FakeProvider([copy.deepcopy(endless_write) for _ in range(50)])
    cfg = {"tool_budget": 3}
    episode = harness.run_fixture(
        {"id": "fx", "intent_nl": "loop forever"}, cfg, provider, REPO_ROOT
    )
    assert episode["outcome"] == "budget_exceeded"
    assert episode["tool_calls"] == 4  # the call that crossed the budget
    log = episode["tool_call_log"]
    assert [r["seq"] for r in log] == [1, 2, 3]  # crossing 4th call not logged
    assert all(r["name"] == "write_file" for r in log)


def test_fr_017_oq_017_module_imports_without_anthropic_sdk(monkeypatch):
    # OQ-017d — the anthropic SDK is an optional extra imported lazily inside
    # AnthropicProvider.__init__; module import must succeed without it.
    monkeypatch.setitem(sys.modules, "anthropic", None)  # `import anthropic` raises
    with pytest.raises(ImportError):
        import anthropic  # noqa: F401  (prove the blocker is effective)

    module = load_harness("eval_harness_script_no_sdk")
    assert hasattr(module, "run_fixture")
    assert hasattr(module, "AnthropicProvider")
    # Only instantiating the real provider needs the SDK.
    with pytest.raises(ImportError):
        module.AnthropicProvider(
            {"model_id": "m", "max_output_tokens": 1, "seed": None}
        )
