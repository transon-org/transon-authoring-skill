"""Sandboxed dry-run worker subprocess (FR-028; SPEC §11.2 stage 3, §11.3).

Private module, runnable as ``python -m transon_authoring._worker``. The host
(:mod:`transon_authoring.verify`) spawns ONE FRESH PROCESS PER CASE — a fresh
interpreter gives zero cross-case state (NFR-002) and keeps the engine
``NO_CONTENT`` singleton identity intact (no pickling, unlike
``multiprocessing``).

Protocol (one-shot JSON over stdin/stdout):

* stdin — one JSON object
  ``{"template": <JsonValue>, "input": <JsonValue>, "includes": {name: template, …}}``,
  parsed strictly (§11.0 ingress: duplicate keys / non-finite numbers rejected).
  Expected outputs NEVER cross into the worker.
* stdout — one JSON object
  ``{"ok": bool, "result": <enc>, "writes": {name: <enc>, …}, "errors": [EngineError]}``
  — ``result``/``writes`` present only when ``ok`` (OQ-014b); ``errors`` carry
  no ``case_id`` (the §11.2 stage runner attaches it, OQ-011).

Sandbox (AD-015 / AD-017 profile — the engine defaults ARE the profile, so the
``Transformer`` is constructed with no marker / ``max_include_depth`` args:
base class, marker ``"$"``, depth 50):

* ``file_writer`` appends into an in-memory dict (last write wins; never the FS);
* ``template_loader`` resolves the request ``includes`` map ONLY — a hit builds
  the sub-transformer via ``IncludeContext.transformer`` (inheriting marker,
  depth guard, include stack, and this loader) with the SAME write-capture
  dict; a miss delegates to the engine's ``no_template_loader`` so the
  ``DefinitionError`` text is engine-verbatim.

Error mapping (§11.2 / OQ-014c / OQ-012):

* ``DefinitionError`` / ``TransformationError`` → ``type`` = ``engine_type`` =
  the class name, ``message`` = verbatim ``str(exc)``;
* any other exception leaked by the engine (e.g. ``ValueError`` from
  ``call int``, ``ZeroDivisionError`` from ``expr /``) →
  ``type: "TransformationError"``, ``engine_type`` = actual class name,
  verbatim message;
* :class:`~transon_authoring._tags.UnencodableValueError` while encoding the
  result or a captured write → ``type: "TransformationError"``, NO
  ``engine_type``, stable library message.

The worker always exits 0 with a response when it can. A malformed request
object (host bug) may crash it — the host maps a dead/garbled worker to the
stable exit-text error.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from transon_authoring._ingress import IngressError, loads_strict
from transon_authoring._tags import UnencodableValueError, encode_engine_value


def _failure(error_type: str, message: str, *, engine_type: str | None = None) -> dict:
    """Failure response: one EngineError, no result/writes (OQ-014b)."""
    error: dict[str, Any] = {"type": error_type, "message": message}
    if engine_type is not None:
        error["engine_type"] = engine_type
    return {"ok": False, "errors": [error]}


def run_request(request: dict) -> dict:
    """Execute one dry-run case per §11.2 stage 3 under the AD-015 sandbox."""
    # Engine import stays local: the worker process imports it exactly once,
    # and module import elsewhere never executes the engine.
    from transon.transformers import (
        DefinitionError,
        Transformer,
        TransformationError,
        no_template_loader,
    )

    template = request["template"]
    input_value = request["input"]
    includes = request.get("includes") or {}
    writes: dict[str, Any] = {}

    def file_writer(name: str, content: Any) -> None:
        # AD-015: in-memory capture, last write wins; never touches the FS.
        writes[name] = content

    def template_loader(name: str, context=None):
        # AD-017: includes resolve from the request map ONLY.
        if name in includes:
            # IncludeContext.transformer inherits marker / depth guard /
            # include stack / this loader; the explicit file_writer shares
            # the single write-capture dict across all include hops.
            return context.transformer(includes[name], file_writer=file_writer)
        # Miss → engine-verbatim DefinitionError text.
        return no_template_loader(name)

    try:
        transformer = Transformer(
            template,
            file_writer=file_writer,
            template_loader=template_loader,
            # No marker / max_include_depth args: engine defaults ARE the
            # AD-017 profile ("$", 50).
        )
        result = transformer.transform(input_value, no_content=Transformer.NO_CONTENT)
    except (DefinitionError, TransformationError) as exc:
        name = type(exc).__name__
        return _failure(name, str(exc), engine_type=name)
    except Exception as exc:  # noqa: BLE001 — OQ-014c: engine leaks non-engine types
        return _failure(
            "TransformationError", str(exc), engine_type=type(exc).__name__
        )

    try:
        encoded_result = encode_engine_value(result)
        encoded_writes = {
            name: encode_engine_value(content) for name, content in writes.items()
        }
    except UnencodableValueError as exc:
        # OQ-012: stable library text, engine_type omitted.
        return _failure("TransformationError", str(exc))

    return {"ok": True, "result": encoded_result, "writes": encoded_writes, "errors": []}


def main() -> int:
    raw = sys.stdin.read()
    try:
        request = loads_strict(raw, source="<dry-run request>")
    except IngressError as exc:
        # Host bug (the host constructs the request); still answer in-protocol.
        response: dict = {"ok": False, "errors": exc.errors}
    else:
        response = run_request(request)
    sys.stdout.write(json.dumps(response, allow_nan=False))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
