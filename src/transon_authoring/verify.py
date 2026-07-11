"""Verification host side — dry-run machinery (FR-028, AC-015/AC-028).

This module currently provides the host half of the sandboxed dry-run worker
(SPEC §11.2 stage 3, §11.3 profile table AD-015/AD-017; resolved OQ-011/012/014
in §15). The full ``verify()`` stage runner (samples → validate → dry_run →
match, §11.2) is a later A1 task and will live here too.

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
from typing import Any

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


def dry_run(template: Any, input_value: Any, includes: dict | None = None) -> dict:
    """Public debug API (AD-006): sandboxed dry-run of one template + input.

    Returns ``{"ok": bool, "result"?: <enc>, "writes"?: {name: <enc>}, "errors":
    [EngineError]}`` shaped for the §11.6 ``dry-run`` envelope — ``result`` and
    ``writes`` are present only on success (OQ-014b); the CLI adds
    ``schema_version`` when wrapping this for stdout. ``includes`` is the
    ``SampleSet.includes``-shaped map (include name → template JSON).
    """
    return run_dry_run_case(template, input_value, includes)
