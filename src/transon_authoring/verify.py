"""Verification — the §11.2 ``verify()`` stage runner and dry-run machinery
(FR-004/FR-006/FR-027/FR-028; AC-013/AC-015/AC-016/AC-028).

This module provides:

* :func:`verify` — the four-stage runner ``samples`` → ``validate`` →
  ``dry_run`` → ``match`` (SPEC §11.2; AD-004/AD-019; resolved OQ-011/013);
* :func:`validate` — the AD-006 debug API for §11.2 stage 2 alone;
* :func:`dry_run` / :func:`run_dry_run_case` — the host half of the sandboxed
  dry-run worker (§11.2 stage 3, §11.3 profile table AD-015/AD-017; resolved
  OQ-011/012/014 in §15).

Each case runs in ONE FRESH worker subprocess
(``python -m transon_authoring._worker``, plain :mod:`subprocess` with one-shot
JSON over stdin/stdout): a fresh interpreter per case gives zero cross-case
state (NFR-002) and preserves the engine ``NO_CONTENT`` singleton identity
(no pickling). Cases run sequentially — sequencing is the caller's concern;
there is no parallelism in v1. The host attaches no ``case_id`` here: the
stage runner adds it when iterating SampleSet cases (OQ-011).
"""

from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from typing import Any

from .match import match_all
from .samples import check_samples

#: AD-017 / AC-028 — wall-clock budget per dry-run case, in seconds.
DRY_RUN_TIMEOUT_SECONDS = 5.0

#: Worker module spawned per case (module path passed to ``python -m``).
_WORKER_MODULE = "transon_authoring._worker"

#: Stable library texts (never engine-verbatim; SPEC §11.2 EngineError).
_TIMEOUT_MESSAGE = "dry-run case exceeded the 5s wall-clock timeout"


def _timeout_envelope() -> dict:
    return {
        "ok": False,
        "errors": [{"type": "TimeoutError", "message": _TIMEOUT_MESSAGE}],
    }


def _dead_worker_envelope(exit_code: Any) -> dict:
    # Worker died or wrote garbage: no engine result exists, stable text,
    # no engine_type (nothing was caught from the engine).
    return {
        "ok": False,
        "errors": [
            {
                "type": "TransformationError",
                "message": f"dry-run worker exited without a result"
                f" (exit code {exit_code})",
            }
        ],
    }


def run_dry_run_case(
    template: Any, input_value: Any, includes: dict | None = None
) -> dict:
    """Execute ONE dry-run case in a fresh sandboxed worker subprocess.

    Returns the worker envelope ``{"ok", "result"?, "writes"?, "errors"}``
    (``result``/``writes`` only on success, values §11.0-encoded). Errors carry
    NO ``case_id`` — the §11.2 stage runner attaches it per SampleCase
    (OQ-011). Expected outputs never cross into the worker.

    Host-side failures map to stable library-text errors: exceeding
    :data:`DRY_RUN_TIMEOUT_SECONDS` kills the worker and reports a
    ``TimeoutError``; a worker that exits non-zero or writes non-JSON output
    reports the exit-text ``TransformationError``.
    """
    request = {
        "template": template,
        "input": input_value,
        "includes": includes or {},
    }
    request_bytes = json.dumps(request, allow_nan=False).encode("utf-8")

    proc = subprocess.Popen(
        [sys.executable, "-m", _WORKER_MODULE],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        stdout_bytes, _stderr = proc.communicate(
            input=request_bytes, timeout=DRY_RUN_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()  # reap the killed worker; nothing lingers (AC-028)
        return _timeout_envelope()

    if proc.returncode != 0:
        return _dead_worker_envelope(proc.returncode)
    try:
        response = json.loads(stdout_bytes.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return _dead_worker_envelope(proc.returncode)
    if not (
        isinstance(response, dict)
        and isinstance(response.get("ok"), bool)
        and isinstance(response.get("errors"), list)
    ):
        return _dead_worker_envelope(proc.returncode)
    return response


def _validate_template(template: Any) -> dict | None:
    """§11.2 stage 2: engine ``validate()`` under the AD-017 default profile.

    Runs **in-parent** (no worker, no timeout): ``validate()`` is a static,
    input-free walk of the template — AD-017's 5s budget is per dry-run case.
    The ``Transformer`` is constructed with defaults only (base class, marker
    ``"$"``, built-in registries, engine-default delegates/depth); there is no
    JSON-level custom-marker detector (§11.2 stage 2 / AC-027).

    Returns ``None`` when the template validates, else one EngineError dict:
    ``type: "DefinitionError"``, verbatim ``str(exc)``, ``engine_type``, and
    NO ``case_id`` (OQ-011: validate errors are never case-attributable).
    Non-``DefinitionError`` exceptions leaked by the pinned engine (e.g.
    ``TypeError`` for ``{"$": 5}``) map to the same "template invalid" class
    per §11.2 stage 2 (rev 2026-07-11), message kept verbatim.
    """
    # Engine import stays local so importing this module never loads the
    # engine (the samples stage must be able to reject engine-free, AD-019).
    from transon.transformers import Transformer

    try:
        Transformer(template).validate()
    except Exception as exc:
        return {
            "type": "DefinitionError",
            "message": str(exc),  # verbatim engine text (§11.6)
            "engine_type": type(exc).__name__,
        }
    return None


def validate(template: Any) -> dict:
    """Public debug API (AD-006): §11.2 stage 2 alone, no blessing path.

    Returns ``{"ok": bool, "errors": [EngineError]}`` shaped for the §11.6
    ``validate`` envelope — the CLI adds ``schema_version`` when wrapping this
    for stdout.
    """
    error = _validate_template(template)
    return {"ok": error is None, "errors": [] if error is None else [error]}


def verify(template: Any, sample_set: Any) -> dict:
    """Run the §11.2 stage pipeline; return a ``Verdict`` dict (FR-004/006/027).

    Stages run fail-fast **between** stages (FR-006): ``samples`` (AD-019
    preflight via :func:`check_samples`, requiring ``ok_for_verify``) →
    ``validate`` (in-parent engine ``validate()``) → ``dry_run`` (one sandboxed
    worker per case, sequentially in ``cases[]`` document order — every case
    runs even after earlier failures, OQ-011) → ``match`` (§11.4). Array
    orders are normative per OQ-013. Root-level ``writes`` is reserved and
    NEVER emitted (OQ-011). ``assurance`` is present only when ``ok`` — and is
    then always ``"matched"`` (AC-013 / AD-004).

    *sample_set* is an already-parsed SampleSet dict; malformed / JSON-level
    schema-invalid input handling is the CLI's job (§11.6 ``schema-error``).
    Semantic rejects (zero cases, incomplete coverage, unconfirmed,
    fingerprint mismatch, ``schema_invalid`` gaps from ``check_samples``)
    surface here as ``failed_stage: "samples"``.
    """
    # Stage 1 — samples (FR-027 / AD-019): no engine execution on reject.
    sample_check = check_samples(sample_set)
    if not sample_check["ok_for_verify"]:
        return {
            "schema_version": "1.0",
            "ok": False,
            "failed_stage": "samples",
            "errors": [],
            "gaps": sample_check["gaps"],
        }

    # Stage 2 — validate (FR-004).
    validate_error = _validate_template(template)
    if validate_error is not None:
        return {
            "schema_version": "1.0",
            "ok": False,
            "failed_stage": "validate",
            "errors": [validate_error],
        }

    # Stage 3 — dry_run: sequentially in cases[] document order; every case
    # runs even after earlier failures; one EngineError per failing case with
    # its case_id attached (OQ-011/013). The worker emits one error per
    # failure; take the first defensively.
    includes = sample_set.get("includes") or {}
    dry_run_errors: list[dict] = []
    results: list[dict] = []
    for case in sample_set["cases"]:
        envelope = run_dry_run_case(template, case["input"], includes)
        if envelope["ok"]:
            results.append(envelope)
        else:
            error = dict(envelope["errors"][0])
            error["case_id"] = case["id"]
            dry_run_errors.append(error)
    if dry_run_errors:
        # match not entered; passing-case results NOT included (OQ-011).
        return {
            "schema_version": "1.0",
            "ok": False,
            "failed_stage": "dry_run",
            "errors": dry_run_errors,
        }

    # Stage 4 — match (§11.4): compares every case; diff alone expresses the
    # failure — no EngineErrors from match (OQ-011).
    diff = match_all(sample_set["cases"], results)
    if diff:
        return {
            "schema_version": "1.0",
            "ok": False,
            "failed_stage": "match",
            "errors": [],
            "diff": diff,
        }

    # All stages passed: ok === true iff all stages pass; assurance is then
    # always "matched" (§11.2 / AC-013). Candidate echoed as `json` (deep copy
    # so the Verdict never aliases the caller's template).
    return {
        "schema_version": "1.0",
        "ok": True,
        "assurance": "matched",
        "errors": [],
        "json": deepcopy(template),
    }


def dry_run(template: Any, input_value: Any, includes: dict | None = None) -> dict:
    """Public debug API (AD-006): sandboxed dry-run of one template + input.

    Returns ``{"ok": bool, "result"?: <enc>, "writes"?: {name: <enc>}, "errors":
    [EngineError]}`` shaped for the §11.6 ``dry-run`` envelope — ``result`` and
    ``writes`` are present only on success (OQ-014b); the CLI adds
    ``schema_version`` when wrapping this for stdout. ``includes`` is the
    ``SampleSet.includes``-shaped map (include name → template JSON).
    """
    return run_dry_run_case(template, input_value, includes)
