"""FR-029 / AD-021 / OQ-025 — the synthetic-fixture generator core
(`scripts/gen_fixtures.py`).

Covers the FR-029 generator contract: determinism (no wall-clock, no
randomness), the AD-021 corpus pair as case 1 (re-executed through the pinned
engine and asserted against the snapshot `result` — never taken on faith),
the 3–6 case budget with the fixed drop order (`list_singleton` →
`optional_present` → `list_many`), value-variation padding to the 3-case
minimum, CI confirmations with the OQ-015 library fingerprint and no
`confirmed_at`, and the OQ-025 applicability predicates (optional keys,
array scope, empirical NO_CONTENT relevance, includes population and
eligibility, writes-capable seeds).

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

# A scalar-leaf seed with no arrays, no optional keys, no NO_CONTENT
# relevance and no writes: happy path alone, padded to 3 cases.
SCALAR_SEED = entry(
    "SyntheticScalar", {"$": "attr", "name": "a"}, {"a": 5}, 5
)

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
