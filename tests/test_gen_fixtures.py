"""FR-029 / AD-021 / OQ-025 / OQ-026 — the synthetic-fixture generator core
(`scripts/gen_fixtures.py`).

Covers the FR-029 generator contract: determinism (no wall-clock, no
randomness), the AD-021 corpus pair as case 1 (re-executed through the pinned
engine and asserted against the snapshot `result` — never taken on faith),
the 3–6 case budget with the fixed drop order (OQ-026d: key deletion →
key addition → length variation → `list_singleton` → `optional_present` →
`list_many`), value-variation padding to the 3-case minimum, CI
confirmations with the OQ-015 library fingerprint and no `confirmed_at`,
the OQ-025 applicability predicates (optional keys, array scope, empirical
NO_CONTENT relevance, includes population and eligibility, writes-capable
seeds), and the OQ-026 wave-2 coverage extensions (list length variations
including the document root, root key addition/deletion variations, the
frozen NO_CONTENT probe count).

Every expected engine output is derived by running the pinned engine through
the AD-017 sandbox (`transon_authoring.verify.dry_run`) — never from memory
(AD-018 / NFR-001).
"""

import copy
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import gen_fixtures  # noqa: E402
from gen_fixtures import GeneratorError, generate  # noqa: E402

from transon_authoring import get_metadata  # noqa: E402
from transon_authoring.samples import check_samples, content_fingerprint  # noqa: E402
from transon_authoring.verify import dry_run  # noqa: E402

EXAMPLES = {e["name"]: e for e in get_metadata()["docs"]["examples"]}


def entry(name: str, template, data, result) -> dict:
    """A synthetic docs.examples-shaped entry for generator unit tests."""
    return {
        "name": name,
        "doc": f"synthetic test entry {name}",
        "template": template,
        "data": data,
        "result": result,
        "tags": [],
    }


def obligations_by_kind(fixture: dict) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for ob in fixture["samples"]["coverage"]:
        grouped.setdefault(ob["kind"], []).append(ob)
    return grouped


def case_for(fixture: dict, obligation_id: str) -> dict:
    matches = [
        c for c in fixture["samples"]["cases"] if obligation_id in c["satisfies"]
    ]
    assert matches, f"no case satisfies {obligation_id!r}"
    return matches[0]


# An identity seed with three ≥2-element arrays: happy + 3×(empty new case,
# singleton new case, many packed into case 1) = 7 distinct cases, forcing
# exactly one FR-029 budget drop.
THREE_ARRAYS = entry(
    "SyntheticThreeArrays",
    {"$": "this"},
    {"a": [1, 2], "b": [3, 4], "c": [5, 6]},
    {"a": [1, 2], "b": [3, 4], "c": [5, 6]},
)

# A root-scalar seed with no arrays, no optional keys, no NO_CONTENT
# relevance, no writes — and (OQ-026) no root key or length variations
# (the corpus data is neither an object nor an array): happy path alone,
# padded to 3 cases.
SCALAR_SEED = entry("SyntheticScalar", {"$": "this"}, 5, 5)

# An optional key (literal attr `wrap` with a `default`) whose absent
# derivation drives the template to the engine NO_CONTENT sentinel.
OPTIONAL_NO_CONTENT = entry(
    "SyntheticOptionalNoContent",
    {
        "$": "chain",
        "funcs": [
            {"$": "attr", "name": "wrap", "default": {}},
            {"$": "attr", "name": "inner"},
        ],
    },
    {"wrap": {"inner": 1}},
    1,
)


def test_fr_029_deterministic_across_runs():
    # FR-029 — no wall-clock, no randomness: two runs over the same seed
    # yield byte-identical fixture and seed documents.
    first = generate(EXAMPLES["Include"], "seed-x", "intent text")
    second = generate(EXAMPLES["Include"], "seed-x", "intent text")
    dumps = lambda doc: json.dumps(doc, sort_keys=True)  # noqa: E731
    assert dumps(first[0]) == dumps(second[0])
    assert dumps(first[1]) == dumps(second[1])


def test_fr_029_ad_021_case_1_is_corpus_pair_reexecuted():
    # FR-029 / AD-021 / OQ-024d — case 1 is always the example's own
    # data/result pair re-executed through the pinned engine; the corpus
    # result is never taken on faith.
    source = EXAMPLES["Include"]
    fixture, _seed = generate(source, "seed-include", "map each item")
    case_1 = fixture["samples"]["cases"][0]
    assert case_1["id"] == "c-1"
    assert case_1["input"] == source["data"]
    assert "ob-happy" in case_1["satisfies"]
    # Oracle: the pinned engine under the AD-017 sandbox, includes from the
    # generated SampleSet map only.
    env = dry_run(source["template"], source["data"], fixture["samples"]["includes"])
    assert env["ok"] is True
    assert case_1["output"] == env["result"] == source["result"]


def test_fr_029_oq_025_corpus_pair_assert_hard_fails():
    # FR-029 / OQ-025d — a seed whose re-executed output does not JSON-equal
    # the snapshot `result` is ineligible: hard error, never a fixture.
    doctored = copy.deepcopy(EXAMPLES["Include"])
    doctored["result"] = [{"tampered": True}]
    with pytest.raises(GeneratorError):
        generate(doctored, "seed-tampered", "intent")


def test_fr_029_budget_cap_and_fixed_drop_order():
    # FR-029 — 3–6 cases; over-budget seeds drop kinds in the fixed order
    # (`list_singleton` first). With three ≥2-element arrays the full build
    # is 7 cases; dropping list_singleton alone fits, so list_many (later in
    # the drop order, packed into case 1) MUST survive.
    fixture, _seed = generate(THREE_ARRAYS, "seed-three-arrays", "echo input")
    cases = fixture["samples"]["cases"]
    assert 3 <= len(cases) <= 6
    kinds = obligations_by_kind(fixture)
    assert "list_singleton" not in kinds, "list_singleton must be dropped first"
    assert len(kinds["list_empty"]) == 3  # never dropped
    assert len(kinds["list_many"]) == 3  # not reached in the drop order
    assert [ob["target"] for ob in kinds["list_empty"]] == ["/a", "/b", "/c"]
    # Every list_many obligation packs into the corpus-pair case (budget rule
    # prefers packing over adding cases).
    for ob in kinds["list_many"]:
        assert case_for(fixture, ob["id"])["id"] == "c-1"
    # Each list_empty case's output is the pinned engine's, not assumed.
    for ob in kinds["list_empty"]:
        case = case_for(fixture, ob["id"])
        env = dry_run(THREE_ARRAYS["template"], case["input"], {})
        assert env["ok"] and case["output"] == env["result"]


def test_fr_029_scalar_seed_pads_with_value_variations():
    # FR-029 — a scalar seed (no arrays / optional keys / NO_CONTENT /
    # writes) pads to the 3-case minimum with deterministic value-variation
    # customs from the fixed per-JSON-type substitution table.
    fixture, _seed = generate(SCALAR_SEED, "seed-scalar", "read a")
    samples = fixture["samples"]
    assert len(samples["cases"]) == 3
    kinds = obligations_by_kind(fixture)
    assert [ob["id"] for ob in kinds["custom"]] == ["ob-variation-1", "ob-variation-2"]
    for ob in kinds["custom"]:
        assert "variation" in ob["description"].lower()
        case = case_for(fixture, ob["id"])
        assert case["input"] != SCALAR_SEED["data"]
        env = dry_run(SCALAR_SEED["template"], case["input"], {})
        assert env["ok"] and case["output"] == env["result"]
    # Deterministic distinct variations.
    inputs = [json.dumps(c["input"], sort_keys=True) for c in samples["cases"]]
    assert len(set(inputs)) == 3


def test_fr_029_ci_confirmation_no_confirmed_at_fingerprint_from_library():
    # FR-029 — generated confirmations are exactly {confirmed: true,
    # confirmed_by: "ci", content_fingerprint: <OQ-015 acquisition path>}
    # with NO confirmed_at (determinism).
    fixture, _seed = generate(SCALAR_SEED, "seed-scalar", "read a")
    samples = fixture["samples"]
    confirmation = samples["confirmation"]
    assert set(confirmation) == {"confirmed", "confirmed_by", "content_fingerprint"}
    assert confirmation["confirmed"] is True
    assert confirmation["confirmed_by"] == "ci"
    # The fingerprint is the library's (OQ-015) — check_samples agrees and
    # the SampleSet is fully ok_for_verify (lint check 4 relies on this).
    assert confirmation["content_fingerprint"] == content_fingerprint(samples)
    check = check_samples(samples)
    assert check["confirmed"] is True
    assert check["ok_for_verify"] is True


def test_fr_029_oq_025_writes_capable_seed_gets_writes_case():
    # FR-029 / OQ-025e — FileWriteViaMap (verified present in the pinned
    # snapshot) contains a `file` rule: the seed is writes-capable, gets the
    # `writes` custom obligation, and the satisfying case declares the
    # sandbox-captured writes map.
    source = EXAMPLES["FileWriteViaMap"]
    fixture, _seed = generate(source, "seed-file-write", "write each item")
    kinds = obligations_by_kind(fixture)
    writes_obs = [
        ob for ob in kinds["custom"] if ob["id"] == "ob-writes"
    ]
    assert len(writes_obs) == 1
    assert "target" not in writes_obs[0]
    case = case_for(fixture, "ob-writes")
    env = dry_run(source["template"], case["input"], {})
    assert env["ok"] and env["writes"]  # non-empty captured writes
    assert case["writes"] == env["writes"]
    # Case 1 carries the corpus pair; its writes are declared too (AC-024:
    # undeclared non-empty writes would fail match under the seed template).
    case_1 = fixture["samples"]["cases"][0]
    env_1 = dry_run(source["template"], source["data"], {})
    assert case_1["output"] == env_1["result"] == source["result"]
    assert case_1["writes"] == env_1["writes"]


def test_fr_029_oq_025_include_seed_populates_includes_transitively():
    # FR-029 / OQ-025d — literal include names resolve transitively from
    # snapshot docs.examples into SampleSet.includes.
    source = EXAMPLES["Include"]
    fixture, _seed = generate(source, "seed-include", "map each item")
    includes = fixture["samples"]["includes"]
    assert includes == {"MapListsToDict": EXAMPLES["MapListsToDict"]["template"]}


def test_fr_029_oq_025_ineligible_include_seed_errors():
    # FR-029 / OQ-025d — IncludeWithDefault is ineligible under the pinned
    # engine/corpus: the generator errors instead of minting a fixture.
    with pytest.raises(GeneratorError):
        generate(EXAMPLES["IncludeWithDefault"], "seed-iwd", "fallback intent")


def test_fr_029_seed_doc_shape():
    # FR-029 — seed provenance doc: exactly {source_example, template
    # (verbatim snapshot template), generator: {version}}; no schema_version
    # (OQ-025 tail: validated structurally, not by the §11.0 ingress).
    source = EXAMPLES["Include"]
    _fixture, seed = generate(source, "seed-include", "map each item")
    assert seed == {
        "source_example": "Include",
        "template": source["template"],
        "generator": {"version": gen_fixtures.GENERATOR_VERSION},
    }
    assert seed["template"] == source["template"]


def test_fr_029_fixture_doc_shape_and_no_seed_template_field():
    # FR-029 / §11.8 — the fixture is an ordinary EvalFixture: expect
    # matched, redacted false, no consent, notes citing the source example
    # and AD-021, and the seed template NEVER inside the fixture object.
    source = EXAMPLES["Include"]
    fixture, _seed = generate(source, "seed-include", "map each item")
    assert fixture["schema_version"] == "1.0"
    assert fixture["id"] == "seed-include"
    assert fixture["expect"] == "matched"
    assert fixture["intent_nl"] == "map each item"
    assert fixture["redacted"] is False
    assert "consent" not in fixture
    assert "template" not in fixture and "seed_template" not in fixture
    assert "Include" in fixture["notes"] and "AD-021" in fixture["notes"]


def test_fr_029_oq_025_optional_keys_and_empirical_no_content():
    # OQ-025a/c — a literal attr with default marks the key optional (pair
    # of obligations targeting the discovered pointer); the optional_absent
    # derivation empirically drives the engine to NO_CONTENT, so the
    # NO_CONTENT custom is emitted and packs onto the same case.
    fixture, _seed = generate(OPTIONAL_NO_CONTENT, "seed-onc", "unwrap inner")
    kinds = obligations_by_kind(fixture)
    present = kinds["optional_present"]
    absent = kinds["optional_absent"]
    assert [ob["target"] for ob in present] == ["/wrap"]
    assert [ob["target"] for ob in absent] == ["/wrap"]
    # `inner` has no default in the template — never optional (OQ-025a).
    assert all(ob["target"] == "/wrap" for ob in present + absent)
    # optional_present packs into the happy-path case (corpus data carries
    # the key).
    assert case_for(fixture, present[0]["id"])["id"] == "c-1"
    absent_case = case_for(fixture, absent[0]["id"])
    assert "wrap" not in absent_case["input"]
    env = dry_run(OPTIONAL_NO_CONTENT["template"], absent_case["input"], {})
    assert env["ok"] is True
    assert absent_case["output"] == env["result"]
    assert env["result"] == {"$transon_authoring": "NO_CONTENT"}
    # The empirical NO_CONTENT custom rides the same case (budget packing).
    no_content_obs = [ob for ob in kinds["custom"] if ob["id"] == "ob-no-content"]
    assert len(no_content_obs) == 1
    assert case_for(fixture, "ob-no-content")["id"] == absent_case["id"]


def test_fr_029_cli_mints_fixture_and_seed(tmp_path):
    # FR-029 — the maintainer CLI mints both documents through the SAME core
    # and refuses to return without a matched verify (AD-004).
    (tmp_path / "evals" / "cases").mkdir(parents=True)
    (tmp_path / "evals" / "seeds").mkdir(parents=True)
    rc = gen_fixtures.main(
        [
            "--example",
            "Include",
            "--fixture-id",
            "seed-include",
            "--intent-nl",
            "map each item through the included template",
            "--root",
            str(tmp_path),
        ]
    )
    assert rc == 0
    fixture_path = tmp_path / "evals" / "cases" / "seed-include.json"
    seed_path = tmp_path / "evals" / "seeds" / "seed-include.json"
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    expected_fixture, expected_seed = generate(
        EXAMPLES["Include"],
        "seed-include",
        "map each item through the included template",
    )
    assert fixture == expected_fixture
    assert seed == expected_seed
    # Overwrite refused without --force.
    assert (
        gen_fixtures.main(
            [
                "--example",
                "Include",
                "--fixture-id",
                "seed-include",
                "--intent-nl",
                "x",
                "--root",
                str(tmp_path),
            ]
        )
        == 2
    )


# ---------------------------------------------------------------------------
# OQ-026 — wave-2 coverage extensions.
# ---------------------------------------------------------------------------

# A seed whose corpus data is an object with one non-optional key and a
# defaulting-accessor name absent from the data: OQ-026b derives one key
# deletion ("a") and one key addition ("missing").
KEY_VARIATION_SEED = entry(
    "SyntheticKeyVariations",
    {"$": "attr", "name": "missing", "default": "fallback"},
    {"a": 1},
    "fallback",
)

# A seed whose only root key, when deleted, makes the dry-run error (expr
# `add` on the NO_CONTENT of a missing attr — verified against the pinned
# engine): OQ-026b key deletion is silently skipped, never ineligibility.
FAILING_DELETION_SEED = entry(
    "SyntheticFailingDeletion",
    {"$": "expr", "op": "add", "values": [{"$": "attr", "name": "a"}, 1]},
    {"a": 2},
    3,
)

# `cond` with no matching arm yields NO_CONTENT under the pinned engine:
# n == 13 (value-variation index 2) is the only NO_CONTENT input, so the
# OQ-026c two-candidate probe must NOT find it; with corpus n == 11 the
# substitution table puts 13 at variation index 1 and the probe MUST find it.
_COND_13_TEMPLATE = {
    "$": "chain",
    "funcs": [
        {"$": "attr", "name": "n"},
        {
            "$": "cond",
            "cases": [{"when": {"$": "expr", "op": "!=", "value": 13}, "then": {"$": "this"}}],
        },
    ],
}


def test_fr_029_oq_026_root_array_length_variation_even_boundary():
    # OQ-026a — the document root IS an array-discovery site: the
    # FilterListByOddIndex root-array seed (excluded from `list_*` by
    # OQ-025b) gains a length-variation case whose input is the corpus
    # array with its final element removed — the even-length boundary.
    source = EXAMPLES["FilterListByOddIndex"]
    fixture, _seed = generate(source, "syn-filter-list-by-odd-index", "odd items")
    kinds = obligations_by_kind(fixture)
    length_obs = [
        ob for ob in kinds["custom"] if ob["id"] == "ob-length-variation--root"
    ]
    assert len(length_obs) == 1
    assert "target" not in length_obs[0]
    case = case_for(fixture, "ob-length-variation--root")
    assert case["input"] == source["data"][:-1]
    assert len(case["input"]) % 2 == 0  # the motivating even-length boundary
    env = dry_run(source["template"], case["input"], {})
    assert env["ok"] and case["output"] == env["result"]


def test_fr_029_oq_026_nested_array_length_variation():
    # OQ-026a — a nested corpus array (length ≥ 2) yields a length-variation
    # case: the corpus document with that array's final element removed.
    source = entry(
        "SyntheticNestedArray", {"$": "this"}, {"a": [1, 2, 3]}, {"a": [1, 2, 3]}
    )
    fixture, _seed = generate(source, "seed-nested-array", "echo")
    case = case_for(fixture, "ob-length-variation--a")
    assert case["input"] == {"a": [1, 2]}
    env = dry_run(source["template"], case["input"], {})
    assert env["ok"] and case["output"] == env["result"]


def test_fr_029_oq_026_short_array_yields_no_length_variation():
    # OQ-026a — derived only when the corpus array has length ≥ 2.
    source = entry(
        "SyntheticShortArray", {"$": "this"}, {"a": [1]}, {"a": [1]}
    )
    fixture, _seed = generate(source, "seed-short-array", "echo")
    assert not [
        ob
        for ob in fixture["samples"]["coverage"]
        if ob["id"].startswith("ob-length-variation")
    ]


def test_fr_029_oq_026_key_addition_and_deletion():
    # OQ-026b — (i) a defaulting-accessor literal name absent from the
    # corpus data yields a key-addition case (value from the substitution
    # table row keyed by the literal default's JSON type); (ii) a
    # non-optional root key yields a key-deletion case.
    fixture, _seed = generate(KEY_VARIATION_SEED, "seed-key-var", "fallback")
    kinds = obligations_by_kind(fixture)
    custom_ids = [ob["id"] for ob in kinds["custom"]]
    assert "ob-key-deletion--a" in custom_ids
    assert "ob-key-addition--missing" in custom_ids
    deletion_case = case_for(fixture, "ob-key-deletion--a")
    assert deletion_case["input"] == {}
    addition_case = case_for(fixture, "ob-key-addition--missing")
    # string default "fallback" → first entry of the string row.
    assert addition_case["input"] == {"a": 1, "missing": "variation-alpha"}
    for case in (deletion_case, addition_case):
        env = dry_run(KEY_VARIATION_SEED["template"], case["input"], {})
        assert env["ok"] and case["output"] == env["result"]
    # The motivating present-branch: the addition case exercises the key.
    assert addition_case["output"] == "variation-alpha"
    assert deletion_case["output"] == "fallback"


def test_fr_029_oq_026_key_addition_value_typing_and_order():
    # OQ-026b(i)/(d) — a default member is NOT required for
    # membership in the addition set; the addition value is the FIRST entry
    # of the table row keyed by the attr's literal default JSON type when
    # one is present (non-literal default → string row; no default at all →
    # string row); additions are emitted in template pre-order discovery
    # order.
    template = {
        "x": {"$": "attr", "name": "alpha", "default": 0},
        "y": {"$": "attr", "name": "beta", "default": {"$": "this"}},
        "z": {"$": "attr", "name": "gamma"},  # defaultless accessor
    }
    baseline = dry_run(template, {"k": "v"}, {})
    assert baseline["ok"]
    source = entry("SyntheticTypedAdds", template, {"k": "v"}, baseline["result"])
    fixture, _seed = generate(source, "seed-typed-adds", "defaults")
    addition_ids = [
        ob["id"]
        for ob in fixture["samples"]["coverage"]
        if ob["id"].startswith("ob-key-addition")
    ]
    assert addition_ids == [
        "ob-key-addition--alpha",
        "ob-key-addition--beta",
        "ob-key-addition--gamma",
    ]
    alpha_case = case_for(fixture, "ob-key-addition--alpha")
    assert alpha_case["input"]["alpha"] == 7  # number row, first entry
    beta_case = case_for(fixture, "ob-key-addition--beta")
    assert beta_case["input"]["beta"] == "variation-alpha"  # non-literal default
    gamma_case = case_for(fixture, "ob-key-addition--gamma")
    assert gamma_case["input"]["gamma"] == "variation-alpha"  # no default member
    for case in (alpha_case, beta_case, gamma_case):
        env = dry_run(template, case["input"], {})
        assert env["ok"] and case["output"] == env["result"]


def test_fr_029_oq_026_optional_root_key_not_deleted_again():
    # OQ-026b(ii) — a root key already covered by an optional_absent
    # obligation gets NO key-deletion obligation.
    fixture, _seed = generate(OPTIONAL_NO_CONTENT, "seed-onc", "unwrap inner")
    assert not [
        ob
        for ob in fixture["samples"]["coverage"]
        if ob["id"].startswith("ob-key-deletion")
    ]


def test_fr_029_oq_026_failing_key_deletion_silently_skipped():
    # OQ-026b — a root key variation whose dry-run errors is silently
    # skipped: no obligation, no case, and NEVER seed ineligibility
    # (contrast the OQ-025d structural hard-error rule).
    env = dry_run(FAILING_DELETION_SEED["template"], {}, {})
    assert env["ok"] is False  # oracle: deletion really does error
    fixture, _seed = generate(FAILING_DELETION_SEED, "seed-fail-del", "add one")
    assert not [
        ob
        for ob in fixture["samples"]["coverage"]
        if ob["id"].startswith("ob-key-deletion")
    ]
    assert len(fixture["samples"]["cases"]) >= 3  # padded, still eligible


def test_fr_029_oq_026_probe_count_frozen_at_two():
    # OQ-026c — the NO_CONTENT probe examines only the FIRST TWO
    # value-variation candidates: normative freeze of the constant…
    assert gen_fixtures.PROBE_VARIATIONS == 2
    # …and of the behavior. With corpus n == 5 the NO_CONTENT input
    # ({"n": 13}) is variation index 2 — beyond the probe: not emitted.
    beyond = entry("SyntheticCondBeyond", _COND_13_TEMPLATE, {"n": 5}, 5)
    fixture, _seed = generate(beyond, "seed-cond-beyond", "not thirteen")
    ids = [ob["id"] for ob in fixture["samples"]["coverage"]]
    assert "ob-no-content" not in ids
    # With corpus n == 11 the table puts 13 at variation index 1 — within
    # the probe: emitted, and the case really is the engine's NO_CONTENT.
    within = entry("SyntheticCondWithin", _COND_13_TEMPLATE, {"n": 11}, 11)
    fixture, _seed = generate(within, "seed-cond-within", "not thirteen")
    case = case_for(fixture, "ob-no-content")
    assert case["input"] == {"n": 13}
    assert case["output"] == {"$transon_authoring": "NO_CONTENT"}


def test_fr_029_oq_026_new_kinds_drop_first():
    # OQ-026d — the extended drop order: key deletion drops FIRST, before
    # list_singleton. Two 2-element arrays + two non-optional root keys is
    # 7 distinct cases; dropping key deletions alone fits the cap, so the
    # list_* kinds (and the packed length variations) all survive.
    assert gen_fixtures.DROP_ORDER == (
        "key_deletion",
        "key_addition",
        "length_variation",
        "list_singleton",
        "optional_present",
        "list_many",
    )
    source = entry(
        "SyntheticDropFirst",
        {"$": "this"},
        {"a": [1, 2], "b": [3, 4]},
        {"a": [1, 2], "b": [3, 4]},
    )
    fixture, _seed = generate(source, "seed-drop-first", "echo")
    assert len(fixture["samples"]["cases"]) <= 6
    kinds = obligations_by_kind(fixture)
    ids = [ob["id"] for ob in fixture["samples"]["coverage"]]
    assert not [i for i in ids if i.startswith("ob-key-deletion")]
    assert "list_singleton" in kinds and len(kinds["list_singleton"]) == 2
    # The length variations survive and pack onto the singleton cases
    # (FR-029 packing preference; the derived inputs coincide).
    for pointer in ("a", "b"):
        length_case = case_for(fixture, f"ob-length-variation--{pointer}")
        singleton_case = case_for(fixture, f"ob-list-singleton--{pointer}")
        assert length_case["id"] == singleton_case["id"]


def test_fr_029_oq_026_deterministic_across_runs():
    # OQ-026 / FR-029 — the wave-2 kinds preserve determinism: two runs
    # over a seed exercising length + key variations are byte-identical.
    for name in ("FilterListByOddIndex", "JoinWithStaticNoOverrides"):
        first = generate(EXAMPLES[name], "seed-x", "intent text")
        second = generate(EXAMPLES[name], "seed-x", "intent text")
        dumps = lambda doc: json.dumps(doc, sort_keys=True)  # noqa: E731
        assert dumps(first[0]) == dumps(second[0])
        assert dumps(first[1]) == dumps(second[1])


def test_fr_029_oq_026_motivating_join_default_insertion_branch():
    # OQ-026b(ii) — the JoinWithStaticNoOverrides gap: deleting the
    # non-optional root key "a" exercises the join default-insertion branch
    # ({"a": "default"} wins only when the input lacks "a").
    source = EXAMPLES["JoinWithStaticNoOverrides"]
    fixture, _seed = generate(source, "syn-join-with-static-no-overrides", "enrich")
    case = case_for(fixture, "ob-key-deletion--a")
    assert case["input"] == {"c": "d"}
    env = dry_run(source["template"], case["input"], {})
    assert env["ok"] and case["output"] == env["result"]
    assert case["output"]["a"] == "default"


def test_fr_029_oq_026_format_label_addition_derived_but_engine_skipped():
    # OQ-026b(i) — the FormatWithDefault "label" accessor
    # carries NO default member, so the amended addition set DOES derive the
    # {"other": 1, "label": "variation-alpha"} candidate. But under the
    # pinned engine the format pattern "{label}" formats against the
    # computed `value` (here the plain string), NOT the input document, so
    # the dry-run errors — oracle asserted below — and per OQ-026b the
    # derivation is silently skipped: no obligation, no case, and the seed
    # stays eligible. (The motivating label-present branch therefore remains
    # uncovered for this template: it would need a dict-shaped label. STOP
    # item, reported — never a silent special case.)
    source = EXAMPLES["FormatWithDefault"]
    env = dry_run(source["template"], {"other": 1, "label": "variation-alpha"}, {})
    assert env["ok"] is False  # engine-decided, never assumed (AD-018)
    fixture, _seed = generate(source, "syn-format-with-default", "label me")
    ids = [ob["id"] for ob in fixture["samples"]["coverage"]]
    assert "ob-key-addition--label" not in ids
    assert "ob-key-deletion--other" in ids  # the deletion still lands
    assert len(fixture["samples"]["cases"]) >= 3  # still eligible
