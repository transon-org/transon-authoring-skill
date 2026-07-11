"""Matching — FR-005 (SPEC §11.4 rules 1-8; §11.2 diff construction, OQ-013).

Pure host-side module: matching compares ``dec(expected)`` against
``enc(actual)`` over the common **encoded domain** (§11.4 / OQ-012), so it
never imports or executes the engine. Callers pass:

* **expected** values *raw from the SampleSet* (``case.output``,
  ``case.writes`` values) — this module applies §11.4 ``dec``
  (:func:`transon_authoring._tags.decode_expected`) itself;
* **actual** values *already encoded* per §11.0 ``enc`` — exactly what the
  dry-run worker emits (``result``, ``writes`` values).

Diff walk (§11.2 "Diff construction (normative)", OQ-013)
---------------------------------------------------------
* objects: visit the union of keys in Unicode code-point ascending order —
  key only in expected → ``missing``, only in actual → ``extra``, in both →
  recurse;
* arrays: indices ascending, pairwise recursion; an index beyond the shorter
  side → ``missing`` / ``extra``;
* differing node types → ``type_mismatch`` with both snapshots.
  ``NoContentRef`` counts as its own type; ``int`` and ``float`` are distinct;
  ``bool`` is not a number (§11.4 rules 3-4 — Python's ``True == 1`` never
  leaks through);
* same-type scalars that differ → ``value_mismatch``;
* an emitted entry terminates recursion at that node;
* ``path`` is the RFC 6901 pointer within the case's output document
  (root ``""``; ``~`` → ``~0``, ``/`` → ``~1`` in tokens).

Snapshot policy: ``missing`` entries carry ``expected`` only, ``extra``
entries carry ``actual`` only, ``type_mismatch`` / ``value_mismatch`` carry
both (the ``DiffEntry`` schema keys are optional). Snapshots are deep copies
in the encoded domain (AuthoringTag shapes appear as-is), so returned entries
are JSON-ready and never alias caller inputs or module state.

Writes (§11.4 rule 8, §11.2): any difference between ``dec(case.writes ?? {})``
and the worker's encoded writes map emits EXACTLY ONE entry per case —
``kind: "writes_mismatch"``, ``path: ""``, ``expected: {"writes": <decoded
expected map>}``, ``actual: {"writes": <encoded actual map>}``. A case that
omits ``writes`` requires the captured map to be empty.

Emission order (§11.2 "Array order (normative)", OQ-013): cases in ``cases[]``
document order; within a case, output entries precede the writes entry. Every
entry carries the REQUIRED ``case_id`` (OQ-011).

``dec`` may raise :class:`transon_authoring._tags.UnknownAuthoringTagError`;
by the ``match`` stage the ``samples`` stage has already rejected unknown tags
(``schema_invalid``), so this module lets it propagate.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence

from transon_authoring._tags import decode_expected, is_no_content_ref

__all__ = ["match_case", "match_all"]

# §11.2 type classes for the walk. NoContentRef is its own type; bool is
# checked before int (Python bool subclasses int); int and float are distinct.
_SCALAR_CLASSES = (
    ("null", lambda v: v is None),
    ("boolean", lambda v: isinstance(v, bool)),
    ("int", lambda v: isinstance(v, int)),
    ("float", lambda v: isinstance(v, float)),
    ("string", lambda v: isinstance(v, str)),
)


def _type_of(v: Any) -> str:
    """§11.2 node type of an encoded-domain value."""
    if is_no_content_ref(v):
        return "no_content"
    for name, check in _SCALAR_CLASSES:
        if check(v):
            return name
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    raise TypeError(f"non-JSON value in match walk: {type(v).__name__!s}")


def _escape(token: str) -> str:
    """RFC 6901 reference-token escaping (order matters: ``~`` first)."""
    return token.replace("~", "~0").replace("/", "~1")


_OMIT = object()


def _entry(
    path: str, kind: str, case_id: str, *, expected: Any = _OMIT, actual: Any = _OMIT
) -> dict:
    """Build one JSON-ready DiffEntry (§11.2); snapshots are deep-copied."""
    entry: dict = {"path": path, "kind": kind}
    if expected is not _OMIT:
        entry["expected"] = deepcopy(expected)
    if actual is not _OMIT:
        entry["actual"] = deepcopy(actual)
    entry["case_id"] = case_id
    return entry


def _walk(path: str, expected: Any, actual: Any, case_id: str, out: list) -> None:
    """§11.2 recursive diff walk over encoded-domain nodes; appends to ``out``."""
    expected_type = _type_of(expected)
    actual_type = _type_of(actual)
    if expected_type != actual_type:
        out.append(
            _entry(path, "type_mismatch", case_id, expected=expected, actual=actual)
        )
        return
    if expected_type == "no_content":
        return  # NoContentRef is a single-valued type: same type => equal
    if expected_type == "object":
        for key in sorted(set(expected) | set(actual)):  # code-point ascending
            child = f"{path}/{_escape(key)}"
            if key not in actual:
                out.append(_entry(child, "missing", case_id, expected=expected[key]))
            elif key not in expected:
                out.append(_entry(child, "extra", case_id, actual=actual[key]))
            else:
                _walk(child, expected[key], actual[key], case_id, out)
        return
    if expected_type == "array":
        for index in range(max(len(expected), len(actual))):  # indices ascending
            child = f"{path}/{index}"
            if index >= len(actual):
                out.append(_entry(child, "missing", case_id, expected=expected[index]))
            elif index >= len(expected):
                out.append(_entry(child, "extra", case_id, actual=actual[index]))
            else:
                _walk(child, expected[index], actual[index], case_id, out)
        return
    if expected != actual:  # same-type scalars (bool/int split by _type_of)
        out.append(
            _entry(path, "value_mismatch", case_id, expected=expected, actual=actual)
        )


def match_case(
    case_id: str,
    expected_output: Any,
    actual_output: Any,
    expected_writes: Mapping[str, Any] | None = None,
    actual_writes: Mapping[str, Any] | None = None,
) -> list[dict]:
    """Match one SampleCase per §11.4; return its ``DiffEntry`` list (§11.2).

    ``expected_output`` / ``expected_writes`` are raw SampleSet values
    (``dec`` applied here); ``actual_output`` / ``actual_writes`` are already
    in the §11.0 encoded domain (worker output). ``expected_writes=None``
    means the case omits ``writes`` (rule 8: captured map must be empty).
    Empty list means the case matched. Output entries precede the single
    optional ``writes_mismatch`` entry.
    """
    entries: list[dict] = []
    _walk("", decode_expected(expected_output), actual_output, case_id, entries)

    decoded_writes = {
        name: decode_expected(value) for name, value in (expected_writes or {}).items()
    }
    captured_writes = dict(actual_writes or {})
    probe: list[dict] = []
    _walk("", decoded_writes, captured_writes, case_id, probe)
    if probe:
        entries.append(
            _entry(
                "",
                "writes_mismatch",
                case_id,
                expected={"writes": decoded_writes},
                actual={"writes": captured_writes},
            )
        )
    return entries


def match_all(
    cases: Sequence[Mapping[str, Any]], results: Sequence[Mapping[str, Any]]
) -> list[dict]:
    """Match every case (§11.2 ``match`` stage); return the ``diff[]`` array.

    ``cases``: SampleSet ``cases[]`` in document order (each mapping carries
    ``id``, ``output``, optional ``writes``). ``results``: the parallel
    per-case dry-run worker results, each carrying ``result`` (encoded output)
    and optional ``writes`` (encoded map; absent means no writes captured).
    Lengths must agree — the verify runner only enters ``match`` when every
    case ran (OQ-011). Entries are grouped by case in ``cases[]`` order.
    """
    diff: list[dict] = []
    for case, result in zip(cases, results, strict=True):
        diff.extend(
            match_case(
                case["id"],
                case["output"],
                result["result"],
                case.get("writes"),
                result.get("writes"),
            )
        )
    return diff
