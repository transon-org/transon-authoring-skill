"""FR-010 — authoritative example corpus + NL sidecar + ``search_examples``
(SPEC §7 FR-010; resolved OQ-022 contract in §15 is normative; AC-022).

Hits are the snapshot ``docs.examples`` objects verbatim (deep copies), plus
an ``"nl"`` string enrichment from ``resources/nl-intents.json`` when present.
"""

import copy
import json
from pathlib import Path

import pytest

from transon_authoring import examples as examples_module
from transon_authoring.examples import _load_sidecar, search_examples

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "resources" / "metadata-snapshot.json"
SIDECAR_PATH = REPO_ROOT / "resources" / "nl-intents.json"

# FR-010 / engine metadata_version 3.0: exactly these keys per corpus item.
EXAMPLE_KEYS = {"name", "doc", "template", "data", "result", "tags"}


def _corpus() -> list:
    """The committed snapshot's docs.examples, parsed from the file itself."""
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))["docs"]["examples"]


def test_fr_010_ac_022_exact_name_match_first_and_verbatim():
    # FR-010 / AC-022 — OQ-022 (a): an exact case-sensitive name match MUST be
    # in the results, ranked first; OQ-022 (d): the hit is the snapshot
    # example object verbatim.
    corpus = _corpus()
    expected = next(e for e in corpus if e["name"] == "AttrSimpleFixedName")

    results = search_examples("AttrSimpleFixedName")
    assert results, "exact-name query must return the named example"
    first = results[0]
    assert first["name"] == "AttrSimpleFixedName"
    assert first["template"] == expected["template"]
    assert first["data"] == expected["data"]
    assert first["result"] == expected["result"]
    assert first["doc"] == expected["doc"]
    assert first["tags"] == expected["tags"]
    # Content beyond the six snapshot keys is at most the "nl" enrichment.
    assert EXAMPLE_KEYS <= set(first) <= EXAMPLE_KEYS | {"nl"}


def test_fr_010_ac_022_limit_bound_and_validation():
    # FR-010 / AC-022 — OQ-022 (b): at most `limit` results; `limit >= 1`.
    assert len(search_examples("attr", limit=3)) == 3
    assert len(search_examples("attr", limit=1)) == 1
    assert len(search_examples("attr")) <= 10  # default limit

    with pytest.raises(ValueError):
        search_examples("attr", limit=0)
    with pytest.raises(ValueError):
        search_examples("attr", limit=-1)


def test_fr_010_ac_022_deterministic_and_deep_copied():
    # FR-010 / AC-022 — OQ-022 (c): pure function of (query, snapshot,
    # sidecar): same query twice yields identical lists including order.
    first = search_examples("attr", limit=7)
    second = search_examples("attr", limit=7)
    assert first == second

    # OQ-022 (d): hits are deep copies — mutating a returned hit must not
    # leak into the cached snapshot or later results.
    untouched = copy.deepcopy(second)
    first[0]["template"] = {"$": "mutated"}
    first[0]["tags"].append("mutated")
    first[1]["name"] = "Mutated"
    assert search_examples("attr", limit=7) == untouched


def test_fr_010_ac_022_multi_hit_truncated_in_corpus_order():
    # FR-010 / AC-022 — OQ-022 (b)+(c): a broad query is truncated to `limit`
    # and ties are ordered by index in snapshot docs.examples (corpus order).
    corpus = _corpus()

    def text(example):
        return " ".join(
            [example["name"], *example["tags"], example["doc"]]
        ).lower()

    matching = [e["name"] for e in corpus if "attr" in text(e)]
    assert len(matching) > 5, "need a genuinely multi-hit query for this test"

    results = search_examples("attr", limit=5)
    assert len(results) == 5
    # Single-token query => every hit ties at score 1 => pure corpus order.
    assert [hit["name"] for hit in results] == matching[:5]


def test_fr_010_ac_022_sidecar_enriches_nl_and_is_searchable(monkeypatch):
    # FR-010 / AC-022 — the NL sidecar enriches display only: the hit gains
    # exactly the "nl" key, everything else stays verbatim snapshot content;
    # OQ-022 (d): retrieval MAY match over sidecar NL text.
    corpus = _corpus()
    expected = next(e for e in corpus if e["name"] == "AttrSimpleFixedName")
    nl_text = "zorbophone lookup of a fixed attribute"
    monkeypatch.setattr(
        examples_module,
        "_load_sidecar",
        lambda: {"AttrSimpleFixedName": {"nl": nl_text, "notes": "test seam"}},
    )

    # A token occurring only in the NL text finds the example.
    results = search_examples("zorbophone")
    assert [hit["name"] for hit in results] == ["AttrSimpleFixedName"]
    hit = results[0]
    assert hit["nl"] == nl_text
    assert set(hit) == EXAMPLE_KEYS | {"nl"}
    assert {key: hit[key] for key in EXAMPLE_KEYS} == expected


def test_fr_010_ac_022_score_zero_query_returns_empty_list():
    # FR-010 / AC-022 — no token matches and no exact name => no hits.
    assert search_examples("qzxvjw-no-such-thing") == []
    assert search_examples("") == []


def test_fr_010_sidecar_loads_committed_file():
    # FR-010 — the sidecar is resources/nl-intents.json with an "intents"
    # object keyed by example name ({"nl": str, "notes"?: str} values).
    committed = json.loads(SIDECAR_PATH.read_text(encoding="utf-8"))
    assert committed["schema_version"] == "1.0"
    assert _load_sidecar() == committed["intents"]
