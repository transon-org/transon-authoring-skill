"""AuthoringTag encoding/decoding — FR-005 groundwork (SPEC §11.0 / §11.4, OQ-012).

Private module implementing the two normative value mappings from the SPEC:

* ``encode_engine_value`` — §11.0 ``enc``, the injective engine-value encoding
  used wherever library output echoes raw engine values (``dry-run`` envelope
  ``result``/``writes`` values, ``DiffEntry.actual``).
* ``decode_expected`` — §11.4 ``dec``, applied recursively at every nesting
  level of a SampleCase expectation (``output``, ``writes`` values).

Decoded-domain design note (OQ-012, locked A1 design)
-----------------------------------------------------
Matching (§11.4) compares ``dec(expected)`` against ``enc(actual)`` in the
SAME domain, so ``dec`` returns values in the *encoded* domain:

* ``NoContentRef`` decodes to the literal ``NoContentRef`` object — the
  module-level singleton :data:`NO_CONTENT_REF` (a distinguished
  identity-comparable marker, NOT the engine sentinel; this module stays
  importable and usable for decoding without executing the engine);
* ``LitRef(value)`` decodes to ``enc(value)`` — literal data contains no
  engine sentinel, so encoding it is exactly LitRef-wrapping any nested
  ``"$transon_authoring"``-keyed objects;
* plain arrays/objects recurse; scalars pass through.

Because ``enc`` is injective (§11.0), a bare ``NoContentRef`` node in the
encoded domain always denotes the engine sentinel and a ``LitRef`` node always
wraps literal data — so the later ``match`` step is a plain structural compare
(object key order insignificant, ``int``/``float`` type-sensitive per §11.4
rule 4).

Error mapping (callers' responsibility, not this module's):

* :class:`UnencodableValueError` from ``enc`` → the affected dry-run case
  fails with a stable library-text ``EngineError``
  (``type: "TransformationError"``, ``engine_type`` omitted) per §11.0/OQ-012;
* :class:`UnknownAuthoringTagError` from ``dec`` → SampleSet ``schema_invalid``
  gap per §11.0 rule 2.
"""

from __future__ import annotations

import math
from typing import Any

TAG_KEY = "$transon_authoring"

#: Distinguished singleton marker for a decoded ``NoContentRef`` (§11.4 rule 1).
#: Identity-comparable (``decoded is NO_CONTENT_REF``) and structurally equal
#: to the §11.0 ``NoContentRef`` shape. It is NOT the engine sentinel. Treat as
#: immutable — never mutate it.
NO_CONTENT_REF: dict = {TAG_KEY: "NO_CONTENT"}


class UnencodableValueError(ValueError):
    """A raw engine value is not JSON-representable (§11.0 ``enc``, OQ-012).

    Raised for non-string object keys, non-finite numbers, and non-JSON
    Python types. Callers map this to the stable-library-text
    ``TransformationError`` EngineError for the affected dry-run case.
    """


class UnknownAuthoringTagError(ValueError):
    """Expected value contains an unknown authoring tag (§11.0 rule 2).

    Raised when an object contains the key ``"$transon_authoring"`` but is not
    exactly a known tag shape. Callers map this to a ``schema_invalid`` gap.
    """


def is_no_content_ref(v: Any) -> bool:
    """True iff ``v`` is exactly the §11.0 ``NoContentRef`` shape.

    Exactly one key: ``{"$transon_authoring": "NO_CONTENT"}``.
    """
    return (
        isinstance(v, dict)
        and len(v) == 1
        and v.get(TAG_KEY) == "NO_CONTENT"
        and isinstance(v.get(TAG_KEY), str)
    )


def is_lit_ref(v: Any) -> bool:
    """True iff ``v`` is exactly the §11.0 ``LitRef`` shape.

    Exactly two keys: ``{"$transon_authoring": "lit", "value": <JsonValue>}``.
    """
    return (
        isinstance(v, dict)
        and len(v) == 2
        and v.get(TAG_KEY) == "lit"
        and isinstance(v.get(TAG_KEY), str)
        and "value" in v
    )


def is_unknown_tag(v: Any) -> bool:
    """True iff ``v`` is an object containing ``"$transon_authoring"`` that is
    not exactly one of the two known tag shapes (§11.0 rule 2)."""
    return (
        isinstance(v, dict)
        and TAG_KEY in v
        and not is_no_content_ref(v)
        and not is_lit_ref(v)
    )


def _encode(v: Any, sentinel: Any) -> Any:
    """§11.0 ``enc`` over ``v``; ``sentinel`` is the engine ``NO_CONTENT``
    object compared by identity, or ``None`` to skip the sentinel branch
    (literal data from parsed JSON cannot contain the sentinel)."""
    if sentinel is not None and v is sentinel:
        return {TAG_KEY: "NO_CONTENT"}
    if isinstance(v, list):
        return [_encode(x, sentinel) for x in v]
    if isinstance(v, dict):
        for key in v:
            if not isinstance(key, str):
                raise UnencodableValueError(
                    "unencodable engine value: non-string object key"
                )
        members = {k: _encode(x, sentinel) for k, x in v.items()}
        if TAG_KEY in v:
            return {TAG_KEY: "lit", "value": members}
        return members
    if isinstance(v, float):
        if not math.isfinite(v):
            raise UnencodableValueError(
                "unencodable engine value: non-finite number"
            )
        return v
    if v is None or isinstance(v, (bool, int, str)):
        return v
    raise UnencodableValueError(
        "unencodable engine value: non-JSON Python type"
    )


def encode_engine_value(v: Any) -> Any:
    """Encode a raw engine value per §11.0 ``enc`` (OQ-012).

    * engine ``NO_CONTENT`` sentinel (identity check against the pinned
      engine's ``Transformer.NO_CONTENT``) → ``NoContentRef``;
    * array → element-wise recursion;
    * object containing ``"$transon_authoring"`` → ``LitRef`` wrapping the
      object with member values encoded;
    * other object → value-wise recursion;
    * scalar → as-is.

    Raises :class:`UnencodableValueError` (stable messages) for non-string
    object keys, non-finite numbers, and non-JSON Python types.

    The engine is imported lazily so this module stays importable — and
    ``decode_expected`` usable — without executing the engine.
    """
    from transon.transformers import Transformer  # lazy: engine only when encoding

    return _encode(v, Transformer.NO_CONTENT)


def decode_expected(v: Any) -> Any:
    """Decode a SampleCase expectation per §11.4 ``dec``, recursively at every
    nesting level (§11.0, rev 2026-07-11 / OQ-012), into the encoded domain:

    * ``NoContentRef`` → :data:`NO_CONTENT_REF` (module singleton marker);
    * ``LitRef(value)`` → ``enc(value)`` (literal data contains no sentinel);
    * plain array/object → recursion; scalar → as-is.

    Raises :class:`UnknownAuthoringTagError` for an object containing
    ``"$transon_authoring"`` that is not exactly a known tag (§11.0 rule 2).
    Does not import the engine.
    """
    if is_no_content_ref(v):
        return NO_CONTENT_REF
    if is_lit_ref(v):
        return _encode(v["value"], sentinel=None)
    if is_unknown_tag(v):
        raise UnknownAuthoringTagError(
            "unknown authoring tag: object contains \"$transon_authoring\" "
            "but is not a known tag shape"
        )
    if isinstance(v, list):
        return [decode_expected(x) for x in v]
    if isinstance(v, dict):
        return {k: decode_expected(x) for k, x in v.items()}
    return v
