"""FR-009 — bundled pinned ``get_editor_metadata()`` snapshot as the
structural grounding catalog (SPEC §7, §10 packaging paragraph, §11.7 pin;
AC-006 / AC-022).

``get_metadata()`` must return exactly the committed
``resources/metadata-snapshot.json`` content, cached module-wide, resolved via
``importlib.resources`` with a repo-root fallback for source checkouts.
"""

import json
from pathlib import Path

from transon_authoring.metadata import _resource_bytes, get_metadata

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "resources" / "metadata-snapshot.json"

# FR-010 / engine metadata_version 3.0 (editor metadata-contract §2.7):
# flat example corpus with exactly these keys per item.
EXAMPLE_KEYS = {"name", "doc", "template", "data", "result", "tags"}


def test_fr_009_bundled_snapshot_is_grounding_catalog():
    # FR-009 / AC-006 — the library serves the committed snapshot verbatim.
    committed = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
    metadata = get_metadata()
    assert metadata == committed

    # §11.7 A0 pin: transon==0.1.7, metadata_version "3.0".
    assert metadata["metadata_version"] == "3.0"
    assert metadata["engine_version"] == "0.1.7"

    # FR-010 / AC-022 — docs.examples is the authoritative flat corpus.
    examples = metadata["docs"]["examples"]
    assert isinstance(examples, list)
    assert len(examples) == 121
    for item in examples:
        assert set(item) == EXAMPLE_KEYS
    names = [item["name"] for item in examples]
    assert len(set(names)) == len(names)


def test_fr_009_get_metadata_is_cached():
    # FR-009 / AC-006 — module-level cache: same (read-only) object each call.
    assert get_metadata() is get_metadata()


def test_fr_009_resource_bytes_match_repo_file():
    # FR-009 — §10: repo-root resources/ is the canonical source; in this
    # checkout _resource_bytes must return exactly those bytes. (Wheel-level
    # force-include packaging is checked outside A0 CI scope.)
    assert _resource_bytes("metadata-snapshot.json") == SNAPSHOT_PATH.read_bytes()


def test_fr_009_missing_resource_raises_with_sync_hint():
    # FR-009 — neither packaged nor repo-root copy → actionable error.
    try:
        _resource_bytes("no-such-resource.json")
    except FileNotFoundError as exc:
        assert "sync_metadata" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError for a missing resource")
