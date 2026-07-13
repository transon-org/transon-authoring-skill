"""FR-029 / AD-021 — the v1 synthetic fixture wave (milestone A3).

The v1 scope commits a tagged subset of `docs.examples` seeds covering every
tag family (the distinct prefixes before the first `:` across all example
tags), one seed per family (OQ-024c). Whether a family is covered by a
dedicated fixture or by another family's seed whose example also carries its
tag (dedup) is an author curation decision, not SPEC text; this test asserts
only the normative part — every family is covered. Coverage is established
through the
committed `evals/seeds/` provenance (FR-029): each seed's `source_example`
names its snapshot entry, whose tags say which families the fixture covers.

Deterministic and provider-free: only the committed corpus and the pinned
snapshot are consulted.
"""

import json
from pathlib import Path

from transon_authoring import get_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
SEEDS_DIR = REPO_ROOT / "evals" / "seeds"
CASES_DIR = REPO_ROOT / "evals" / "cases"


def tag_family(tag: str) -> str:
    return tag.split(":", 1)[0]


def test_fr_029_v1_wave_covers_all_tag_families():
    # FR-029 / AD-021 / OQ-024c — every tag family in the pinned snapshot's
    # docs.examples is covered by some committed synthetic fixture's source
    # example, established via the evals/seeds/ provenance docs.
    examples = {e["name"]: e for e in get_metadata()["docs"]["examples"]}
    snapshot_families = {
        tag_family(tag) for entry in examples.values() for tag in entry["tags"]
    }
    assert snapshot_families, "pinned snapshot carries no example tags"

    covered_families: set[str] = set()
    seed_paths = sorted(SEEDS_DIR.glob("*.json"))
    assert seed_paths, "no committed evals/seeds/ provenance docs (FR-029)"
    for seed_path in seed_paths:
        seed = json.loads(seed_path.read_text(encoding="utf-8"))
        if "origin" in seed:
            # AD-023 / FR-033 constructed real-world-pack seed — not part of the
            # FR-029 synthetic v1 wave (no docs.examples source_example).
            continue
        # Provenance chain: seed -> snapshot entry (FR-029a) and seed ->
        # committed fixture (AC-030 pairing).
        source = seed["source_example"]
        assert source in examples, (
            f"{seed_path.name}: source_example {source!r} is not in the "
            "pinned snapshot docs.examples (FR-029 / AD-021)"
        )
        assert (CASES_DIR / seed_path.name).is_file(), (
            f"{seed_path.name}: seed has no committed fixture (FR-029/AC-030)"
        )
        covered_families |= {tag_family(t) for t in examples[source]["tags"]}

    missing = sorted(snapshot_families - covered_families)
    assert not missing, (
        "tag families with no committed synthetic fixture (FR-029 v1 scope, "
        f"AD-021 / OQ-024c): {missing}"
    )
