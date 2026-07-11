"""Pre-A0 smoke tests: package skeleton + engine pin (AD-007).

The real A0 gates (snapshot, provenance, drift) land with milestone A0; these
only prove the harness CI loop runs against the pinned engine.
"""

from importlib.metadata import version

import transon_authoring


def test_package_importable():
    assert transon_authoring.__version__


def test_engine_pin_installed():
    # AD-007 — A0 baseline pin transon==0.1.7
    assert version("transon") == "0.1.7"


def test_engine_metadata_export_present():
    # AD-018 (3) — the pinned engine must expose the snapshot source for A0 sync-metadata
    from transon.metadata import get_editor_metadata

    metadata = get_editor_metadata()
    assert metadata["metadata_version"] == "3.0"
