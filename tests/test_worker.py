"""FR-028 — sandboxed dry-run worker subprocess + host (SPEC §11.2 stage 3,
§11.3 profile table AD-015/AD-017, §11.0 ``enc``; AC-028 timeout; resolved
OQ-011/012/014 in §15; NFR-003 groundwork).

Worker protocol and error-mapping tests. Sandbox-invariant tests (AC-015)
live in ``tests/test_sandbox.py``.

Engine-behavior expectations are derived by *running* the pinned engine
(``transon==0.1.7``) in-process, never from memory (AD-018 / NFR-001).
"""

import json
import subprocess
import sys
import time

import transon_authoring.verify as verify_module
from transon_authoring import dry_run
from transon_authoring.verify import DRY_RUN_TIMEOUT_SECONDS, run_dry_run_case

TAG_KEY = "$transon_authoring"

#: Genuinely-slow template for timeout tests: quadratic work — `set` the root
#: list as a variable, then for each of the N items `chain` back to the root
#: and `map` over all N of it (N^2 walk steps). Empirically on the pinned
#: engine: N=1000 ≈ 1.15s, N=1500 ≈ 2.6s, N=2500 ≈ 7.6s in-process.
SLOW_TEMPLATE = [
    {"$": "set", "name": "root"},
    {
        "$": "map",
        "item": {
            "$": "chain",
            "funcs": [
                {"$": "get", "name": "root"},
                {"$": "map", "item": 1},
                {"$": "get", "name": "nothing"},
            ],
        },
    },
]
SLOW_INPUT = list(range(2500))


def _engine_exception(template, input_value):
    """Run the pinned engine in-process and capture the verbatim exception
    (AD-018: the running engine is the only authority for messages)."""
    from transon.transformers import Transformer

    transformer = Transformer(template)
    try:
        transformer.transform(input_value, no_content=Transformer.NO_CONTENT)
    except Exception as exc:  # noqa: BLE001 — the engine leaks non-engine types
        return type(exc).__name__, str(exc)
    raise AssertionError("engine did not raise for this fixture")


# ---------------------------------------------------------------------------
# Success envelope (§11.6 dry-run shape, OQ-014b)
# ---------------------------------------------------------------------------


def test_fr_028_echo_template_round_trip():
    input_value = {"a": [1, 2.5, "x", None, True], "b": {"nested": []}}
    envelope = dry_run({"$": "this"}, input_value)
    assert envelope == {
        "ok": True,
        "result": input_value,
        "writes": {},
        "errors": [],
    }


def test_fr_028_no_content_result_encodes_as_no_content_ref():
    # Engine-verified fixture: `attr` on a missing key yields the NO_CONTENT
    # sentinel (probed against the pinned engine; §11.0 enc → NoContentRef).
    from transon.transformers import Transformer

    engine_result = Transformer({"$": "attr", "name": "missing"}).transform(
        {}, no_content=Transformer.NO_CONTENT
    )
    assert engine_result is Transformer.NO_CONTENT  # AD-018 grounding

    envelope = dry_run({"$": "attr", "name": "missing"}, {})
    assert envelope["ok"] is True
    assert envelope["result"] == {TAG_KEY: "NO_CONTENT"}
    assert envelope["errors"] == []


def test_fr_028_worker_module_runs_directly():
    # The worker is runnable as `python -m transon_authoring._worker`:
    # one JSON request on stdin, one JSON response on stdout, exit 0.
    request = {"template": {"$": "this"}, "input": 42, "includes": {}}
    completed = subprocess.run(
        [sys.executable, "-m", "transon_authoring._worker"],
        input=json.dumps(request).encode("utf-8"),
        capture_output=True,
        timeout=60,
    )
    assert completed.returncode == 0
    response = json.loads(completed.stdout.decode("utf-8"))
    assert response == {"ok": True, "result": 42, "writes": {}, "errors": []}


def test_fr_028_fresh_worker_process_per_case(monkeypatch):
    # NFR-002 groundwork: one fresh interpreter per case — two calls, two
    # distinct worker processes.
    spawned = []
    real_popen = subprocess.Popen

    def capturing_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        spawned.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", capturing_popen)
    assert dry_run({"$": "this"}, 1)["ok"] is True
    assert dry_run({"$": "this"}, 2)["ok"] is True
    assert len(spawned) == 2
    assert spawned[0].pid != spawned[1].pid


# ---------------------------------------------------------------------------
# Error mapping (§11.2 EngineError, OQ-014c)
# ---------------------------------------------------------------------------


def test_fr_028_definition_error_verbatim():
    template = {"$": "nosuchrule"}
    engine_type, message = _engine_exception(template, {})
    assert engine_type == "DefinitionError"

    envelope = dry_run(template, {})
    assert envelope["ok"] is False
    assert "result" not in envelope and "writes" not in envelope
    (error,) = envelope["errors"]
    assert error["type"] == "DefinitionError"
    assert error["engine_type"] == "DefinitionError"
    assert error["message"] == message  # verbatim str(exc), never paraphrased
    assert "case_id" not in error  # OQ-011: the stage runner attaches case_id


def test_fr_028_leaked_value_error_maps_to_transformation_error():
    # OQ-014c: the pinned engine leaks ValueError from `call int` on "abc";
    # bucket → TransformationError, engine_type = actual class, verbatim text.
    template = {"$": "call", "name": "int"}
    engine_type, message = _engine_exception(template, "abc")
    assert engine_type == "ValueError"

    envelope = dry_run(template, "abc")
    assert envelope["ok"] is False
    (error,) = envelope["errors"]
    assert error["type"] == "TransformationError"
    assert error["engine_type"] == "ValueError"
    assert error["message"] == message


def test_fr_028_include_depth_limit_engine_default_50():
    # FR-028 / AD-017: include depth is the engine default max_include_depth=50
    # (the worker passes NO depth argument); over-depth is an engine-verbatim
    # TransformationError naming the include chain, never a raw RecursionError.
    template = {"$": "include", "name": "loop"}
    includes = {"loop": {"$": "include", "name": "loop"}}

    envelope = dry_run(template, 1, includes)
    assert envelope["ok"] is False
    (error,) = envelope["errors"]
    assert error["type"] == "TransformationError"
    assert error["engine_type"] == "TransformationError"
    assert "include depth limit (50) exceeded" in error["message"]
    assert error["message"].count("loop") == 51  # chain of 51 names in the text


def test_fr_028_unencodable_result_int_keys_stable_library_error():
    # OQ-012: `map` key mode over a list yields int object keys — engine-real,
    # not JSON-representable. Stable library text, NO engine_type.
    from transon.transformers import Transformer

    template = {"$": "map", "key": {"$": "index"}, "value": {"$": "item"}}
    engine_result = Transformer(template).transform(
        ["a", "b"], no_content=Transformer.NO_CONTENT
    )
    assert engine_result == {0: "a", 1: "b"}  # AD-018 grounding

    envelope = dry_run(template, ["a", "b"])
    assert envelope["ok"] is False
    assert "result" not in envelope and "writes" not in envelope
    (error,) = envelope["errors"]
    assert error["type"] == "TransformationError"
    assert "engine_type" not in error
    assert error["message"] == "unencodable engine value: non-string object key"


def test_fr_028_unencodable_result_non_finite_stable_library_error():
    # OQ-012: `call float` on "inf" yields a non-finite number.
    template = {"$": "call", "name": "float"}
    envelope = dry_run(template, "inf")
    assert envelope["ok"] is False
    (error,) = envelope["errors"]
    assert error["type"] == "TransformationError"
    assert "engine_type" not in error
    assert error["message"] == "unencodable engine value: non-finite number"


def test_fr_028_unencodable_write_content_fails_case():
    # Encoding applies to every captured write as well as the result.
    template = {
        "$": "file",
        "name": "out.json",
        "content": {"$": "call", "name": "float"},
    }
    envelope = dry_run(template, "inf")
    assert envelope["ok"] is False
    (error,) = envelope["errors"]
    assert error["type"] == "TransformationError"
    assert "engine_type" not in error
    assert error["message"] == "unencodable engine value: non-finite number"


# ---------------------------------------------------------------------------
# Timeout (AC-028) and dead/garbled worker
# ---------------------------------------------------------------------------


def test_ac_028_production_timeout_is_5s():
    # AD-017 / §11.3: 5s wall clock per case.
    assert DRY_RUN_TIMEOUT_SECONDS == 5.0


def test_ac_028_timeout_kills_worker(monkeypatch):
    # Patch the module constant down so the test is fast; the template needs
    # ~7.6s in-process on the pinned engine (see SLOW_TEMPLATE note), so a
    # completed result would prove the timeout never fired.
    monkeypatch.setattr(verify_module, "DRY_RUN_TIMEOUT_SECONDS", 0.2)
    spawned = []
    real_popen = subprocess.Popen

    def capturing_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        spawned.append(proc)
        return proc

    monkeypatch.setattr(subprocess, "Popen", capturing_popen)

    start = time.monotonic()
    envelope = dry_run(SLOW_TEMPLATE, SLOW_INPUT)
    elapsed = time.monotonic() - start

    assert envelope["ok"] is False
    (error,) = envelope["errors"]
    assert error["type"] == "TimeoutError"
    assert error["message"] == "dry-run case exceeded the 5s wall-clock timeout"
    assert "engine_type" not in error
    # The worker was killed and reaped: process is dead, not lingering.
    (proc,) = spawned
    assert proc.poll() is not None
    # Well under both the template's ~7.6s runtime and the production 5s.
    assert elapsed < 5.0


def test_fr_028_dead_worker_nonzero_exit_stable_text(monkeypatch):
    # A worker that dies without a response maps to the stable exit-text error.
    monkeypatch.setattr(
        verify_module, "_WORKER_MODULE", "transon_authoring._no_such_worker"
    )
    envelope = dry_run({"$": "this"}, 1)
    assert envelope["ok"] is False
    (error,) = envelope["errors"]
    assert error["type"] == "TransformationError"
    assert "engine_type" not in error
    assert error["message"] == "dry-run worker exited without a result (exit code 1)"


def test_fr_028_garbled_worker_stdout_stable_text(monkeypatch):
    # `python -m this` exits 0 but prints non-JSON junk (the Zen of Python).
    monkeypatch.setattr(verify_module, "_WORKER_MODULE", "this")
    envelope = dry_run({"$": "this"}, 1)
    assert envelope["ok"] is False
    (error,) = envelope["errors"]
    assert error["type"] == "TransformationError"
    assert "engine_type" not in error
    assert error["message"] == "dry-run worker exited without a result (exit code 0)"


def test_fr_028_run_dry_run_case_errors_carry_no_case_id():
    # OQ-011: run_dry_run_case reports errors WITHOUT case_id; the §11.2 stage
    # runner (later task) attaches the SampleCase id.
    envelope = run_dry_run_case({"$": "nosuchrule"}, {})
    (error,) = envelope["errors"]
    assert "case_id" not in error
