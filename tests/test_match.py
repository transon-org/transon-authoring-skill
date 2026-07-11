"""FR-005 matching half — SPEC §11.4 rules 1-8 over the encoded domain, with
the §11.2 "Diff construction (normative)" / "Array order (normative)" walk
(resolved OQ-011/OQ-012/OQ-013 in §15). Covers AC-023 and AC-024.

Engine-behavior expectations (sentinel-producing results) are derived by
*running* the pinned engine (``transon==0.1.7``), never from memory
(AD-018 / NFR-001). Actual values handed to the matcher are always already in
the encoded domain (§11.0 ``enc``), exactly as the verify worker supplies them.
"""

import subprocess
import sys

from transon_authoring._tags import encode_engine_value
from transon_authoring.match import match_all, match_case

TAG_KEY = "$transon_authoring"
NO_CONTENT_REF = {TAG_KEY: "NO_CONTENT"}


def _transform(template, data):
    """Run the pinned engine — the only authority for engine values (AD-018).

    Mirrors the normative §11.2 dry-run call: ``no_content`` is passed so a
    root NO_CONTENT surfaces as the sentinel (the engine default maps it to
    ``None``, which is exactly the confusion AC-023 guards against).
    """
    from transon.transformers import Transformer

    return Transformer(template).transform(data, no_content=Transformer.NO_CONTENT)


def _encoded_sentinel():
    """enc of a real engine NO_CONTENT result (grounded, not hand-written)."""
    return encode_engine_value(_transform({"$": "attr", "name": "missing"}, {}))


# ---------------------------------------------------------------------------
# AC-023 — engine NO_CONTENT is its own type, never null/false/0/""
# ---------------------------------------------------------------------------


def test_ac_023_no_content_not_null():
    # §11.4 rule 1: the sentinel (encoded as NoContentRef) matches only an
    # expected NoContentRef ...
    actual = _encoded_sentinel()
    assert actual == NO_CONTENT_REF  # enc grounding (§11.0)
    assert match_case("c", {TAG_KEY: "NO_CONTENT"}, actual) == []

    # ... and does NOT match null, false, 0, or "" — each is a type_mismatch
    # (§11.2: NoContentRef counts as its own type), root path "".
    for lookalike in (None, False, 0, ""):
        diff = match_case("c", lookalike, actual)
        assert len(diff) == 1
        entry = diff[0]
        assert entry["kind"] == "type_mismatch"
        assert entry["path"] == ""
        assert entry["case_id"] == "c"
        assert entry["expected"] == lookalike
        assert entry["actual"] == NO_CONTENT_REF

        # Reverse direction: expected NoContentRef vs a plain scalar actual.
        reverse = match_case("c", {TAG_KEY: "NO_CONTENT"}, lookalike)
        assert len(reverse) == 1
        assert reverse[0]["kind"] == "type_mismatch"
        assert reverse[0]["expected"] == NO_CONTENT_REF
        assert reverse[0]["actual"] == lookalike


def test_ac_023_nested_no_content_matches_real_engine_result():
    # OQ-012: nested sentinels are reachable — plain container template nodes
    # pass NO_CONTENT through. dec/enc recursion must line up at depth.
    result = _transform(["a", {"x": {"$": "attr", "name": "missing"}}], {})
    actual = encode_engine_value(result)
    expected = ["a", {"x": {TAG_KEY: "NO_CONTENT"}}]
    assert match_case("c", expected, actual) == []


def test_ac_023_lit_ref_of_no_content_shape_matches_only_literal_lookalike():
    # §11.4 rule 1: expected LitRef whose value IS the NoContentRef-shaped
    # object matches only that literal JSON object from the engine result,
    # not the sentinel.
    expected = {TAG_KEY: "lit", "value": {TAG_KEY: "NO_CONTENT"}}

    # A template that is plain data: the engine echoes the lookalike object.
    literal_actual = encode_engine_value(_transform({TAG_KEY: "NO_CONTENT"}, {}))
    assert match_case("c", expected, literal_actual) == []

    # The sentinel does not satisfy the LitRef expectation ...
    diff = match_case("c", expected, _encoded_sentinel())
    assert len(diff) == 1
    assert diff[0]["kind"] == "type_mismatch"  # NoContentRef is its own type

    # ... and the literal lookalike does not satisfy a bare NoContentRef.
    diff = match_case("c", {TAG_KEY: "NO_CONTENT"}, literal_actual)
    assert len(diff) == 1
    assert diff[0]["kind"] == "type_mismatch"


# ---------------------------------------------------------------------------
# FR-005 §11.4 rules 3-4 — bool is not a number; int and float are distinct
# ---------------------------------------------------------------------------


def test_fr_005_int_float_distinct():
    # §11.4 rule 4: 1 != 1.0 — int matches only int, float only float; the
    # walk reports differing types as type_mismatch (§11.2).
    assert match_case("c", 1, 1) == []
    assert match_case("c", 1.0, 1.0) == []

    for expected, actual in ((1, 1.0), (1.0, 1), (0, 0.0), (0.0, 0)):
        diff = match_case("c", expected, actual)
        assert len(diff) == 1
        assert diff[0]["kind"] == "type_mismatch"
        assert diff[0]["expected"] == expected
        assert diff[0]["actual"] == actual

    # Same type, different value -> value_mismatch.
    diff = match_case("c", 1, 2)
    assert diff[0]["kind"] == "value_mismatch"
    assert (diff[0]["expected"], diff[0]["actual"]) == (1, 2)


def test_fr_005_bool_is_not_number():
    # §11.4 rule 3: booleans match only booleans — guard against Python's
    # bool/int equality (True == 1, False == 0), both directions.
    for expected, actual in ((True, 1), (1, True), (False, 0), (0, False)):
        diff = match_case("c", expected, actual)
        assert len(diff) == 1
        assert diff[0]["kind"] == "type_mismatch"
    assert match_case("c", True, True) == []
    assert match_case("c", False, False) == []
    diff = match_case("c", True, False)
    assert diff[0]["kind"] == "value_mismatch"


# ---------------------------------------------------------------------------
# AC-024 — writes matching (§11.4 rule 8)
# ---------------------------------------------------------------------------


def test_ac_024_declared_writes_matched():
    # Declared writes deep-equal the captured map, including NoContentRef
    # content and LitRef expectations (decoded per §11.0).
    expected_writes = {
        "out.txt": "hello",
        "nc": {TAG_KEY: "NO_CONTENT"},
        "lit": {TAG_KEY: "lit", "value": {TAG_KEY: "NO_CONTENT"}},
    }
    actual_writes = {
        "out.txt": "hello",
        "nc": _encoded_sentinel(),  # worker encodes sentinel content (§11.0)
        "lit": encode_engine_value({TAG_KEY: "NO_CONTENT"}),  # literal lookalike
    }
    assert match_case("c", 1, 1, expected_writes, actual_writes) == []

    # Any content difference -> exactly one writes_mismatch entry (§11.2),
    # path "", full decoded-expected and encoded-actual maps as snapshots.
    diff = match_case("c", 1, 1, expected_writes, {**actual_writes, "out.txt": "bye"})
    assert len(diff) == 1
    entry = diff[0]
    assert entry["kind"] == "writes_mismatch"
    assert entry["path"] == ""
    assert entry["case_id"] == "c"
    assert entry["expected"] == {
        "writes": {
            "out.txt": "hello",
            "nc": NO_CONTENT_REF,
            "lit": {TAG_KEY: "lit", "value": {TAG_KEY: "NO_CONTENT"}},
        }
    }
    assert entry["actual"] == {"writes": {**actual_writes, "out.txt": "bye"}}


def test_ac_024_undeclared_nonempty_actual_writes_fail_match():
    # §11.4 rule 8: case omits writes -> require captured map empty.
    assert match_case("c", 1, 1, None, {}) == []
    diff = match_case("c", 1, 1, None, {"f": "x"})
    assert len(diff) == 1
    assert diff[0]["kind"] == "writes_mismatch"
    assert diff[0]["expected"] == {"writes": {}}
    assert diff[0]["actual"] == {"writes": {"f": "x"}}


def test_ac_024_missing_and_extra_write_names():
    # Missing names and extra names each fail the writes comparison.
    diff = match_case("c", 1, 1, {"a": 1}, {})
    assert [e["kind"] for e in diff] == ["writes_mismatch"]
    diff = match_case("c", 1, 1, {"a": 1}, {"a": 1, "b": 2})
    assert [e["kind"] for e in diff] == ["writes_mismatch"]


def test_ac_024_exactly_one_writes_entry_for_many_write_diffs():
    # §11.2: writes mismatches emit EXACTLY ONE entry per case, no matter how
    # many names/values differ.
    expected_writes = {"a": 1, "b": [1, 2], "c": "keep"}
    actual_writes = {"a": 2, "b": [1], "d": True}
    diff = match_case("c", 1, 1, expected_writes, actual_writes)
    assert len(diff) == 1
    assert diff[0]["kind"] == "writes_mismatch"

    # Writes content is type-sensitive too (§11.4 rules 3-4 apply inside).
    assert len(match_case("c", 1, 1, {"a": 1}, {"a": True})) == 1
    assert len(match_case("c", 1, 1, {"a": 1}, {"a": 1.0})) == 1


# ---------------------------------------------------------------------------
# Diff construction (§11.2 normative walk, OQ-013)
# ---------------------------------------------------------------------------


def test_fr_005_oq_013_shallowest_node_terminates_recursion():
    # An emitted entry terminates recursion at that node: a type_mismatch at a
    # parent emits no child entries.
    diff = match_case("c", {"x": {"y": 1, "z": 2}, "ok": True}, {"x": [1, 2, 3], "ok": True})
    assert len(diff) == 1
    assert diff[0] == {
        "path": "/x",
        "kind": "type_mismatch",
        "expected": {"y": 1, "z": 2},
        "actual": [1, 2, 3],
        "case_id": "c",
    }


def test_fr_005_oq_013_object_key_visit_order_is_code_point_ascending():
    # Union of keys visited in Unicode code-point ascending order:
    # "Z" (0x5A) < "a" (0x61) < "b" (0x62), regardless of insertion order.
    diff = match_case("c", {"a": 1, "Z": 1, "b": 1}, {"a": 2, "Z": 2, "b": 2})
    assert [e["path"] for e in diff] == ["/Z", "/a", "/b"]
    assert all(e["kind"] == "value_mismatch" for e in diff)


def test_fr_005_oq_013_object_missing_and_extra_keys():
    # Key only in expected -> missing (expected snapshot); only in actual ->
    # extra (actual snapshot); both -> recurse. Emission order is the sorted
    # key union.
    diff = match_case("c", {"a": 1, "Z": 1}, {"b": 2, "Z": 2})
    assert [(e["path"], e["kind"]) for e in diff] == [
        ("/Z", "value_mismatch"),
        ("/a", "missing"),
        ("/b", "extra"),
    ]
    missing, extra = diff[1], diff[2]
    assert missing["expected"] == 1 and "actual" not in missing
    assert extra["actual"] == 2 and "expected" not in extra


def test_fr_005_oq_013_array_index_missing_and_extra():
    # Arrays: indices ascending, pairwise recursion; an index beyond the
    # shorter side emits missing/extra.
    diff = match_case("c", [1, 2, 3, 4], [1, 9])
    assert [(e["path"], e["kind"]) for e in diff] == [
        ("/1", "value_mismatch"),
        ("/2", "missing"),
        ("/3", "missing"),
    ]
    assert diff[1]["expected"] == 3 and "actual" not in diff[1]

    diff = match_case("c", [1], [1, 2, 3])
    assert [(e["path"], e["kind"]) for e in diff] == [("/1", "extra"), ("/2", "extra")]
    assert diff[0]["actual"] == 2 and "expected" not in diff[0]


def test_fr_005_oq_013_root_path_is_empty_string():
    # RFC 6901: the whole document pointer is "".
    diff = match_case("c", "a", "b")
    assert diff[0]["path"] == ""
    assert diff[0]["kind"] == "value_mismatch"


def test_fr_005_oq_013_pointer_tokens_escaped_per_rfc_6901():
    # "/" -> "~1", "~" -> "~0" in reference tokens. Code-point order:
    # "a/b" (0x2F) precedes "a~b" (0x7E).
    diff = match_case("c", {"a/b": 1, "a~b": 1}, {"a/b": 2, "a~b": 2})
    assert [e["path"] for e in diff] == ["/a~1b", "/a~0b"]
    # Nested tokens compose.
    diff = match_case("c", {"a/b": {"c~d": 1}}, {"a/b": {"c~d": 2}})
    assert diff[0]["path"] == "/a~1b/c~0d"


def test_fr_005_oq_011_case_id_on_every_entry():
    # OQ-011: DiffEntry.case_id is REQUIRED on every entry, output and writes.
    diff = match_case("case-7", {"a": 1, "b": 2}, {"a": 9, "c": 3}, {"w": 1}, {})
    assert len(diff) >= 3
    assert all(e["case_id"] == "case-7" for e in diff)


def test_fr_005_oq_013_multi_case_order_output_before_writes():
    # §11.2 array order: diff[] groups cases in cases[] order; within a case,
    # output entries precede the single writes entry.
    cases = [
        {"id": "c1", "input": {}, "output": {"a": 1}, "writes": {"w": 1}},
        {"id": "c2", "input": {}, "output": [1]},
    ]
    results = [
        {"result": {"a": 2}, "writes": {"w": 2}},
        {"result": [1, 5], "writes": {}},
    ]
    diff = match_all(cases, results)
    assert [(e["case_id"], e["kind"]) for e in diff] == [
        ("c1", "value_mismatch"),
        ("c1", "writes_mismatch"),
        ("c2", "extra"),
    ]


def test_fr_005_match_all_passing_cases_contribute_nothing():
    cases = [
        {"id": "c1", "input": {}, "output": {TAG_KEY: "NO_CONTENT"}},
        {"id": "c2", "input": {}, "output": 2, "writes": {"w": "x"}},
    ]
    results = [
        {"result": _encoded_sentinel()},
        {"result": 2, "writes": {"w": "x"}},
    ]
    assert match_all(cases, results) == []


def test_fr_005_deterministic_diff_lists():
    # NFR-002 / AC-018 groundwork (OQ-013 defined emission order): same inputs
    # produce identical entry lists, run after run.
    cases = [
        {"id": "c1", "input": {}, "output": {"b": [1, {"k": 2}], "a": 1}, "writes": {"w": 1}},
    ]
    results = [{"result": {"a": True, "b": [1, {"k": 3}, 4], "c": None}, "writes": {}}]
    first = match_all(cases, results)
    second = match_all(cases, results)
    assert first == second
    assert first is not second


def test_fr_005_diff_entries_conform_to_verdict_schema():
    # Every emitted entry must validate against the Verdict schema's diffEntry
    # (src/transon_authoring/schemas/verdict.json, FR-026 alignment).
    import json
    from pathlib import Path

    import jsonschema

    schema_path = (
        Path(__file__).resolve().parent.parent
        / "src"
        / "transon_authoring"
        / "schemas"
        / "verdict.json"
    )
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    entry_schema = {
        "$schema": schema["$schema"],
        "$defs": schema["$defs"],
        "$ref": "#/$defs/diffEntry",
    }
    diff = match_case(
        "c",
        {"a": 1, "b": {TAG_KEY: "NO_CONTENT"}, "d": [1]},
        {"a": 1.0, "c": 2, "d": [1, 2]},
        {"w": 1},
        {"v": 2},
    )
    kinds = {e["kind"] for e in diff}
    assert kinds == {"type_mismatch", "missing", "extra", "writes_mismatch"}
    for entry in diff:
        jsonschema.validate(entry, entry_schema)
        json.dumps(entry)  # JSON-ready, no Python-only objects


def test_fr_005_snapshots_do_not_alias_matcher_state():
    # Snapshots are deep copies: mutating a returned entry must not corrupt
    # the module's decoded NoContentRef marker or the caller's inputs.
    from transon_authoring import _tags

    expected_writes = {"nc": {TAG_KEY: "NO_CONTENT"}}
    actual_writes = {"other": 1}
    diff = match_case("c", 1, 1, expected_writes, actual_writes)
    diff[0]["expected"]["writes"]["nc"]["mutated"] = True
    diff[0]["actual"]["writes"]["other"] = 999
    assert _tags.NO_CONTENT_REF == {TAG_KEY: "NO_CONTENT"}
    assert expected_writes == {"nc": {TAG_KEY: "NO_CONTENT"}}
    assert actual_writes == {"other": 1}


def test_fr_005_match_module_importable_without_engine():
    # Locked A1 design: matching happens host-side over the encoded domain —
    # match.py never imports/executes the engine.
    code = (
        "import sys\n"
        "from transon_authoring.match import match_case, match_all\n"
        "assert 'transon' not in sys.modules, 'importing match pulled in the engine'\n"
        "diff = match_case('c', {'$transon_authoring': 'NO_CONTENT'}, None, {'w': 1}, {})\n"
        "assert [e['kind'] for e in diff] == ['type_mismatch', 'writes_mismatch']\n"
        "assert 'transon' not in sys.modules, 'matching pulled in the engine'\n"
    )
    subprocess.run([sys.executable, "-c", code], check=True)
