"""FR-005 — AuthoringTag encoding/decoding groundwork (SPEC §11.0 ``enc``,
§11.4 ``dec``; resolved OQ-012 in §15; feeds AC-023/AC-024).

Engine-behavior expectations here are derived by *running* the pinned engine
(``transon==0.1.7``), never from memory (AD-018 / NFR-001): nested
``NO_CONTENT`` sentinels are produced by real transforms.
"""

import subprocess
import sys

import pytest

from transon_authoring._tags import (
    NO_CONTENT_REF,
    UnencodableValueError,
    UnknownAuthoringTagError,
    decode_expected,
    encode_engine_value,
    is_lit_ref,
    is_no_content_ref,
    is_unknown_tag,
)

TAG_KEY = "$transon_authoring"


def _sentinel():
    """The engine NO_CONTENT sentinel from the pinned engine (identity-compared)."""
    from transon.transformers import Transformer

    return Transformer.NO_CONTENT


def _transform(template, data):
    """Run the pinned engine — the only authority for engine values (AD-018)."""
    from transon.transformers import Transformer

    return Transformer(template).transform(data)


# ---------------------------------------------------------------------------
# Tag predicates (§11.0 tagged shapes: exact key sets)
# ---------------------------------------------------------------------------


def test_fr_005_predicate_no_content_ref_exact_shape():
    # §11.0: NoContentRef is an object with exactly the one required key.
    assert is_no_content_ref({TAG_KEY: "NO_CONTENT"})
    assert not is_no_content_ref({TAG_KEY: "NO_CONTENT", "extra": 1})
    assert not is_no_content_ref({TAG_KEY: "lit", "value": 1})
    assert not is_no_content_ref({TAG_KEY: "no_content"})
    assert not is_no_content_ref({"other": "NO_CONTENT"})
    assert not is_no_content_ref("NO_CONTENT")
    assert not is_no_content_ref(None)


def test_fr_005_predicate_lit_ref_exact_shape():
    # §11.0: LitRef is an object with exactly the two required keys.
    assert is_lit_ref({TAG_KEY: "lit", "value": 1})
    assert is_lit_ref({TAG_KEY: "lit", "value": None})
    assert not is_lit_ref({TAG_KEY: "lit"})  # missing "value"
    assert not is_lit_ref({TAG_KEY: "lit", "value": 1, "extra": 2})
    assert not is_lit_ref({TAG_KEY: "NO_CONTENT"})
    assert not is_lit_ref([TAG_KEY, "lit"])


def test_fr_005_predicate_unknown_tag():
    # §11.0 rule 2: object containing the tag key but not a known tag shape.
    assert is_unknown_tag({TAG_KEY: "bogus"})
    assert is_unknown_tag({TAG_KEY: "NO_CONTENT", "extra": 1})
    assert is_unknown_tag({TAG_KEY: "lit"})
    assert is_unknown_tag({TAG_KEY: "lit", "value": 1, "extra": 2})
    assert is_unknown_tag({TAG_KEY: True})
    # Known tags and ordinary values are not "unknown tags".
    assert not is_unknown_tag({TAG_KEY: "NO_CONTENT"})
    assert not is_unknown_tag({TAG_KEY: "lit", "value": 1})
    assert not is_unknown_tag({"other": "bogus"})
    assert not is_unknown_tag(None)


# ---------------------------------------------------------------------------
# enc — §11.0 engine-value encoding (OQ-012)
# ---------------------------------------------------------------------------


def test_fr_005_oq_012_enc_sentinel_is_no_content_ref():
    # §11.0 enc: the engine NO_CONTENT sentinel encodes as NoContentRef.
    assert encode_engine_value(_sentinel()) == {TAG_KEY: "NO_CONTENT"}


def test_fr_005_oq_012_enc_nested_sentinel_in_list_from_real_engine():
    # OQ-012: nested sentinels are reachable in pinned-engine results — plain
    # list template nodes pass NO_CONTENT through.
    result = _transform(["a", {"$": "attr", "name": "missing"}], {})
    assert result[0] == "a"
    assert result[1] is _sentinel()  # identity, per §11.4 rule 1
    assert encode_engine_value(result) == ["a", {TAG_KEY: "NO_CONTENT"}]


def test_fr_005_oq_012_enc_nested_sentinel_in_dict_from_real_engine():
    # OQ-012: plain dict template nodes pass NO_CONTENT through too.
    result = _transform({"x": {"$": "attr", "name": "missing"}, "y": 1}, {})
    assert result["x"] is _sentinel()
    assert encode_engine_value(result) == {"x": {TAG_KEY: "NO_CONTENT"}, "y": 1}


def test_fr_005_oq_012_enc_wraps_tag_keyed_object_as_lit_ref():
    # §11.0 enc: any object containing "$transon_authoring" is wrapped as
    # LitRef with *member values encoded*.
    raw = {TAG_KEY: "whatever", "n": _sentinel()}
    assert encode_engine_value(raw) == {
        TAG_KEY: "lit",
        "value": {TAG_KEY: "whatever", "n": {TAG_KEY: "NO_CONTENT"}},
    }


def test_fr_005_oq_012_enc_injective_sentinel_vs_lookalike_dict():
    # §11.0: enc is injective — a raw dict that *looks like* NoContentRef is
    # LitRef-wrapped, so a bare NoContentRef always denotes the sentinel.
    enc_sentinel = encode_engine_value(_sentinel())
    enc_lookalike = encode_engine_value({TAG_KEY: "NO_CONTENT"})
    assert enc_sentinel == {TAG_KEY: "NO_CONTENT"}
    assert enc_lookalike == {TAG_KEY: "lit", "value": {TAG_KEY: "NO_CONTENT"}}
    assert enc_sentinel != enc_lookalike


def test_fr_005_enc_scalars_pass_through_with_type_preserved():
    # §11.0 enc: scalar -> v; §11.4 rule 4: int and float are distinct types.
    for scalar in (None, True, False, 0, 1, -7, 1.5, 0.0, "", "héllo"):
        out = encode_engine_value(scalar)
        assert out == scalar
        assert type(out) is type(scalar)
    assert isinstance(encode_engine_value(1), int)
    assert isinstance(encode_engine_value(1.0), float)


def test_fr_005_enc_recurses_plain_containers():
    value = {"a": [1, {"b": None}], "c": {"d": "e"}}
    assert encode_engine_value(value) == value


def test_fr_005_oq_012_enc_rejects_non_finite_float():
    # OQ-012: non-finite numbers (reachable via `call float`) are not
    # JSON-representable -> typed error with a stable message.
    for bad in (float("inf"), float("-inf"), float("nan")):
        with pytest.raises(UnencodableValueError, match="non-finite number"):
            encode_engine_value(bad)
    with pytest.raises(UnencodableValueError, match="non-finite number"):
        encode_engine_value(["ok", {"k": float("inf")}])


def test_fr_005_oq_012_enc_rejects_non_string_dict_key():
    # OQ-012: non-string object keys (reachable via `map` key mode).
    with pytest.raises(UnencodableValueError, match="non-string object key"):
        encode_engine_value({1: "x"})
    with pytest.raises(UnencodableValueError, match="non-string object key"):
        encode_engine_value({TAG_KEY: "lit", 2: "y"})  # tag-keyed branch too


def test_fr_005_oq_012_enc_rejects_non_json_python_type():
    # OQ-012: non-JSON Python types -> typed error.
    for bad in ({"a", "b"}, object(), (1, 2), b"bytes"):
        with pytest.raises(UnencodableValueError, match="non-JSON Python type"):
            encode_engine_value(bad)


# ---------------------------------------------------------------------------
# dec — §11.4 decoding of expected values (recursive at every nesting level)
# ---------------------------------------------------------------------------


def test_fr_005_oq_012_dec_no_content_ref_is_singleton_marker():
    # §11.4 dec: NoContentRef maps to itself in the encoded domain; the module
    # returns a distinguished module-level singleton (identity-comparable),
    # NOT the engine sentinel.
    decoded = decode_expected({TAG_KEY: "NO_CONTENT"})
    assert decoded is NO_CONTENT_REF
    assert decoded == {TAG_KEY: "NO_CONTENT"}
    assert decoded is not _sentinel()


def test_fr_005_oq_012_dec_recurses_at_every_nesting_level():
    # §11.0: decoding applies recursively at every
    # nesting level of an expected value.
    expected = {
        "top": [{TAG_KEY: "NO_CONTENT"}, {"deep": {"deeper": [{TAG_KEY: "NO_CONTENT"}]}}],
        "plain": 1,
    }
    decoded = decode_expected(expected)
    assert decoded["top"][0] is NO_CONTENT_REF
    assert decoded["top"][1]["deep"]["deeper"][0] is NO_CONTENT_REF
    assert decoded["plain"] == 1


def test_fr_005_oq_012_dec_lit_ref_maps_to_enc_of_value():
    # §11.4: dec maps LitRef(value) to enc(value) — same encoded domain as
    # enc(actual), so matching is a plain structural compare.
    assert decode_expected({TAG_KEY: "lit", "value": [1, {"a": None}]}) == [1, {"a": None}]


def test_fr_005_oq_012_dec_lit_ref_of_no_content_shaped_value():
    # §11.4 rule 1: expected LitRef whose value IS the NoContentRef-shaped
    # object matches only the literal JSON object from the engine — its
    # decoding equals enc(literal lookalike), not the bare NoContentRef.
    lit = {TAG_KEY: "lit", "value": {TAG_KEY: "NO_CONTENT"}}
    decoded = decode_expected(lit)
    assert decoded == {TAG_KEY: "lit", "value": {TAG_KEY: "NO_CONTENT"}}
    # Same encoded node an engine-produced literal lookalike yields...
    assert decoded == encode_engine_value({TAG_KEY: "NO_CONTENT"})
    # ...and distinguishable from the sentinel's encoding.
    assert decoded != encode_engine_value(_sentinel())


def test_fr_005_dec_plain_values_pass_through():
    value = {"a": [1, 2.5, "s", None, True], "b": {"c": {}}}
    assert decode_expected(value) == value
    assert decode_expected(7) == 7


def test_fr_005_oq_012_dec_unknown_tag_raises():
    # §11.0 rule 2: unknown authoring tag -> typed error (callers map it to a
    # schema_invalid gap).
    for bad in (
        {TAG_KEY: "bogus"},
        {TAG_KEY: "NO_CONTENT", "extra": 1},
        {TAG_KEY: "lit"},
        {TAG_KEY: "lit", "value": 1, "extra": 2},
    ):
        with pytest.raises(UnknownAuthoringTagError, match="unknown authoring tag"):
            decode_expected(bad)
    # Nested unknown tags are found by the recursive walk.
    with pytest.raises(UnknownAuthoringTagError, match="unknown authoring tag"):
        decode_expected({"nest": [{TAG_KEY: "bogus"}]})


def test_fr_005_oq_012_dec_unknown_tag_inside_lit_ref_value_is_literal_data():
    # Inside a LitRef value everything is literal data (enc-equivalent), so a
    # tag-keyed object there is LitRef-wrapped, never an unknown-tag error.
    lit = {TAG_KEY: "lit", "value": {"inner": {TAG_KEY: "bogus"}}}
    assert decode_expected(lit) == {
        "inner": {TAG_KEY: "lit", "value": {TAG_KEY: "bogus"}}
    }


# ---------------------------------------------------------------------------
# Import isolation — module stays importable without executing the engine
# ---------------------------------------------------------------------------


def test_fr_005_tags_module_importable_without_engine():
    # Design constraint: importing _tags (and decoding expectations) must not
    # import/execute the pinned engine; enc imports it lazily.
    code = (
        "import sys\n"
        "import transon_authoring._tags as t\n"
        "assert 'transon' not in sys.modules, 'importing _tags pulled in the engine'\n"
        "t.decode_expected({'$transon_authoring': 'NO_CONTENT'})\n"
        "t.decode_expected({'$transon_authoring': 'lit', 'value': {'a': 1}})\n"
        "assert 'transon' not in sys.modules, 'decoding pulled in the engine'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
