"""NFR-001 (A0 slice) — authority isolation: Transon semantics only from
AD-018 sources (SPEC §8; §17 row NFR-001 | AC-003, AC-022 | A0+).

At answer time, metadata/examples answers originate ONLY from the bundled
pinned snapshot (AD-018 source 3, ``resources/metadata-snapshot.json``) —
never from a live engine call, LLM memory, or the web. Proven here by making
the live engine unreachable (patched to raise AND blocked at the import seam)
and showing ``get_metadata()`` / ``search_examples()`` still serve the
committed snapshot verbatim, plus a cheap static guard that product modules
import no network machinery.

AC-003 (adversarial refuse) is A3 scope and intentionally NOT covered here.
"""

import json
import re
import sys
from pathlib import Path

import pytest

from transon_authoring import metadata as metadata_module
from transon_authoring.examples import search_examples
from transon_authoring.metadata import get_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "resources" / "metadata-snapshot.json"
PACKAGE_DIR = REPO_ROOT / "src" / "transon_authoring"

# Snapshot example object keys (engine metadata_version 3.0); hits may add
# at most the sidecar "nl" enrichment (AC-022).
EXAMPLE_KEYS = {"name", "doc", "template", "data", "result", "tags"}


def _committed_snapshot() -> dict:
    """The committed bundle file, parsed directly — the AD-018 source 3."""
    return json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))


def test_nfr_001_snapshot_is_sole_source(monkeypatch):
    # NFR-001 / AC-022 — answers come from the bundled pinned snapshot
    # (AD-018 source 3), never from a live engine call at answer time:
    # with the engine both raising and unimportable, the load path still
    # serves the committed file.

    def _forbidden_engine_call(*args, **kwargs):
        raise RuntimeError(
            "NFR-001 violation: live engine called at answer time"
        )

    # Patch the live engine entry point to raise (grabs the real module
    # reference before the import seam is poisoned below).
    monkeypatch.setattr(
        "transon.metadata.get_editor_metadata", _forbidden_engine_call
    )
    # Block the import seam entirely: any `import transon` from here on
    # raises ImportError (None in sys.modules halts the import).
    monkeypatch.setitem(sys.modules, "transon", None)
    monkeypatch.setitem(sys.modules, "transon.metadata", None)
    with pytest.raises(ImportError):
        import transon  # noqa: F401 — proves the seam is really blocked

    # Reset the module-level cache so get_metadata() executes its real load
    # path under the patched/blocked engine (monkeypatch restores it after).
    monkeypatch.setattr(metadata_module, "_METADATA_CACHE", None)

    # get_metadata() equals the parsed bundle file — snapshot-grounded.
    committed = _committed_snapshot()
    assert get_metadata() == committed

    # search_examples() likewise answers from the snapshot: the exact-name
    # hit is the committed docs.examples entry verbatim (modulo the optional
    # sidecar "nl" enrichment, AC-022).
    expected = next(
        e for e in committed["docs"]["examples"]
        if e["name"] == "AttrSimpleFixedName"
    )
    hits = search_examples("AttrSimpleFixedName")
    assert hits, "exact-name query must return the named snapshot example"
    first = dict(hits[0])
    first.pop("nl", None)
    assert first == expected


def test_nfr_001_hits_are_snapshot_verbatim():
    # NFR-001 / AC-022 — every hit for representative queries (exact name,
    # substring, tags-based) deep-equals some entry of the committed bundle's
    # docs.examples after removing the optional "nl" enrichment: nothing is
    # synthesized outside AD-018 source 3.
    corpus = _committed_snapshot()["docs"]["examples"]
    assert any("recipe" in e["tags"] for e in corpus), (
        "need a real tag for the tags-based representative query"
    )

    for query in ("AttrSimpleFixedName", "attr", "recipe"):
        hits = search_examples(query)
        assert hits, f"representative query {query!r} must return hits"
        for hit in hits:
            stripped = dict(hit)
            stripped.pop("nl", None)
            assert stripped in corpus, (
                f"hit {hit['name']!r} for query {query!r} is not a verbatim "
                "snapshot docs.examples entry (NFR-001/AD-018)"
            )
            assert set(hit) <= EXAMPLE_KEYS | {"nl"}


# Network/web machinery module roots forbidden in product code (NFR-001:
# never web at answer time; cheap authority guard, import statements only).
_FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(?:import|from)\s+(?:urllib|requests|http|httpx|aiohttp|socket)\b",
    re.MULTILINE,
)


def test_nfr_001_no_network_imports_in_product_code():
    # NFR-001 / AD-018 — static guard: no src/transon_authoring module
    # imports network/web machinery, so no answer path can reach beyond the
    # bundled snapshot.
    sources = sorted(PACKAGE_DIR.rglob("*.py"))
    assert sources, "expected product modules under src/transon_authoring"
    for path in sources:
        match = _FORBIDDEN_IMPORT_RE.search(path.read_text(encoding="utf-8"))
        assert match is None, (
            f"{path.relative_to(REPO_ROOT)} imports network machinery "
            f"({match.group(0).strip()!r}) — forbidden by NFR-001/AD-018"
        )
