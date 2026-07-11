"""Strict JSON ingress + bundled JSON Schema validation (FR-026).

Private layer under the library/CLI surface (SPEC §11.0 ingress rules, §11.6):

- ``loads_strict`` / ``load_json_file`` parse JSON while rejecting duplicate
  object keys and non-finite numbers (``NaN`` / ``Infinity`` / ``-Infinity``)
  at ingress (§11.0 serialization rules).
- ``check_schema_version`` accepts only ``"1.0"`` (§11.0 schema versions).
- ``load_schema`` / ``schema_violations`` / ``validate_schema`` validate
  documents against the draft 2020-12 schemas bundled under
  ``transon_authoring/schemas/`` (OQ-014e); validator errors are sorted by
  (JSON instance path, message) for determinism (OQ-013).

All failures raise :class:`IngressError`, which carries PreflightError-shaped
``EngineError`` dicts — ``type: "PreflightError"``, stable library message,
no ``engine_type``, no ``case_id`` (OQ-011/OQ-014c) — for the CLI to wrap
into a ``CliError`` envelope with ``status: "schema-error"`` and exit 2.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from importlib import resources
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

#: The only document schema version the v1 library understands (§11.0).
SUPPORTED_SCHEMA_VERSION = "1.0"

#: Bundled §11 contract schemas (draft 2020-12), one file per document type.
SCHEMA_FILES = (
    "authoring_result.json",
    "cli_error.json",
    "project_config.json",
    "sample_check.json",
    "sample_set.json",
    "verdict.json",
)


def preflight_error(message: str, *, path: str | None = None) -> dict[str, Any]:
    """Build a PreflightError-shaped ``EngineError`` dict (§11.6, OQ-014c).

    Stable library message; ``engine_type`` omitted; ``case_id`` absent
    (OQ-011: preflight errors are never attributable to a sample case).
    """
    error: dict[str, Any] = {"type": "PreflightError", "message": message}
    if path is not None:
        error["path"] = path
    return error


class IngressError(Exception):
    """Ingress failure detected before any engine construction (§11.6).

    ``errors`` is a non-empty list of PreflightError-shaped ``EngineError``
    dicts, ready for a ``CliError`` ``schema-error`` envelope (exit 2).
    """

    def __init__(self, errors: Iterable[dict[str, Any]]):
        self.errors: list[dict[str, Any]] = list(errors)
        super().__init__("; ".join(error["message"] for error in self.errors))


class _StrictJsonError(ValueError):
    """Internal: raised from json hooks, converted to IngressError."""


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    obj: dict[str, Any] = {}
    for key, value in pairs:
        if key in obj:
            raise _StrictJsonError(
                f"duplicate object key: {json.dumps(key, ensure_ascii=False)}"
            )
        obj[key] = value
    return obj


def _reject_non_finite(constant: str) -> Any:
    # json only calls parse_constant for NaN / Infinity / -Infinity.
    raise _StrictJsonError(f"non-finite number not allowed: {constant}")


def loads_strict(text: str, *, source: str = "<input>") -> Any:
    """Parse *text* per §11.0 ingress rules.

    Rejects duplicate object keys and non-finite numbers in addition to
    ordinary JSON syntax errors. *source* labels the input in error messages
    (typically the input file path).
    """
    try:
        return json.loads(
            text,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_finite,
        )
    except _StrictJsonError as exc:
        raise IngressError([preflight_error(f"{source}: {exc}")]) from exc
    except json.JSONDecodeError as exc:
        raise IngressError([preflight_error(f"{source}: invalid JSON: {exc}")]) from exc


def load_json_file(path: str | os.PathLike[str], *, source: str | None = None) -> Any:
    """Read and strictly parse one JSON input file (§11.6 PreflightError:
    unreadable input file)."""
    label = str(path) if source is None else source
    try:
        text = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise IngressError(
            [preflight_error(f"unreadable input file {label}: {exc}")]
        ) from exc
    return loads_strict(text, source=label)


def check_schema_version(doc: Any, *, source: str = "<input>") -> None:
    """Require ``doc`` to be an object carrying ``schema_version: "1.0"``.

    FR-026: unknown/unsupported ``schema_version`` on ingress is a
    schema-error (CLI exit 2).
    """
    if not isinstance(doc, dict):
        raise IngressError(
            [
                preflight_error(
                    f"{source}: document must be a JSON object carrying"
                    f' schema_version "{SUPPORTED_SCHEMA_VERSION}"'
                )
            ]
        )
    if "schema_version" not in doc:
        raise IngressError(
            [
                preflight_error(
                    f"{source}: missing schema_version"
                    f' (supported: "{SUPPORTED_SCHEMA_VERSION}")'
                )
            ]
        )
    version = doc["schema_version"]
    if version != SUPPORTED_SCHEMA_VERSION:
        raise IngressError(
            [
                preflight_error(
                    f"{source}: unsupported schema_version"
                    f" {json.dumps(version, ensure_ascii=False)}"
                    f' (supported: "{SUPPORTED_SCHEMA_VERSION}")'
                )
            ]
        )


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    """Load a bundled draft 2020-12 schema document by file name (OQ-014e).

    Resolved through the package so it works from a source checkout and from
    the installed wheel. Callers must treat the returned object as read-only.
    """
    text = (resources.files("transon_authoring") / "schemas" / name).read_text(
        encoding="utf-8"
    )
    return json.loads(text)


@lru_cache(maxsize=None)
def _validator(name: str) -> Draft202012Validator:
    schema = load_schema(name)
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _json_pointer(parts: Iterable[Any]) -> str:
    """RFC 6901 pointer from a jsonschema error path (root = "")."""
    return "".join(
        "/" + str(part).replace("~", "~0").replace("/", "~1") for part in parts
    )


def schema_violations(instance: Any, schema_name: str) -> list[tuple[str, str]]:
    """Validate *instance* against a bundled schema; return violations as
    (JSON instance pointer, message) pairs, **sorted** by that pair for
    determinism (OQ-013 / OQ-014e). Empty list means valid.
    """
    violations = [
        (_json_pointer(error.absolute_path), error.message)
        for error in _validator(schema_name).iter_errors(instance)
    ]
    violations.sort()
    return violations


def validate_schema(instance: Any, schema_name: str, *, source: str = "<input>") -> None:
    """Raise IngressError with one sorted PreflightError per schema violation."""
    violations = schema_violations(instance, schema_name)
    if violations:
        raise IngressError(
            preflight_error(
                f"{source}: schema validation failed at"
                f" {pointer or '<root>'}: {message}",
                path=pointer,
            )
            for pointer, message in violations
        )


def load_document(
    path: str | os.PathLike[str], schema_name: str, *, source: str | None = None
) -> Any:
    """Full ingress for one enveloped input file: read, strict-parse, check
    ``schema_version``, then JSON-Schema validate. Returns the document."""
    label = str(path) if source is None else source
    doc = load_json_file(path, source=label)
    check_schema_version(doc, source=label)
    validate_schema(doc, schema_name, source=label)
    return doc
