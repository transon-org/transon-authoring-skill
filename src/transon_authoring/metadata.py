"""Bundled pinned ``get_editor_metadata()`` snapshot — the structural
grounding catalog (FR-009, SPEC §7; §10 packaging; §11.7 pin).

``get_metadata()`` serves the committed ``resources/metadata-snapshot.json``
(engine ``transon==0.2.3``, ``metadata_version "3.0"``) without touching the
live engine. Resolution order (§10): the packaged copy under
``transon_authoring/resources/`` (hatchling force-include in wheels), then the
repo-root ``resources/`` for src-layout checkouts / editable installs.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path

# Read-only module-level cache for get_metadata(). Callers MUST NOT mutate
# the returned mapping — it is shared across all callers for the process
# lifetime.
_METADATA_CACHE: dict | None = None


def _resource_bytes(name: str) -> bytes:
    """Return the bytes of bundled resource *name* (e.g. ``metadata-snapshot.json``).

    Resolution order (SPEC §10):

    1. ``transon_authoring/resources/<name>`` via ``importlib.resources`` —
       present in installed wheels through the hatchling force-include;
    2. repo-root ``resources/<name>`` — the canonical, human-edited source in
       a src-layout checkout (editable install);
    3. neither → ``FileNotFoundError`` with a remediation hint.
    """
    packaged = resources.files("transon_authoring") / "resources" / name
    if packaged.is_file():
        return packaged.read_bytes()

    repo_copy = Path(__file__).resolve().parents[2] / "resources" / name
    if repo_copy.is_file():
        return repo_copy.read_bytes()

    raise FileNotFoundError(
        f"bundled resource {name!r} not found in the installed package or the "
        "repo-root resources/ directory; run scripts/sync_metadata.py to "
        "regenerate the metadata snapshot (SPEC §11.7)"
    )


def get_metadata() -> dict:
    """Return the pinned ``get_editor_metadata()`` snapshot (FR-009).

    Parsed from the bundled ``resources/metadata-snapshot.json`` and cached at
    module level: repeated calls return the same object. The result is
    **read-only** — callers must not mutate it.
    """
    global _METADATA_CACHE
    if _METADATA_CACHE is None:
        _METADATA_CACHE = json.loads(
            _resource_bytes("metadata-snapshot.json").decode("utf-8")
        )
    return _METADATA_CACHE
