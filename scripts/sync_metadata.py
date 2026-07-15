#!/usr/bin/env python
"""sync-metadata — regenerate the metadata snapshot from the pinned engine and
record provenance (FR-011 / AC-006; SPEC §7, §10, §11.7, OQ-021).

Behavior:

1. Read the ``transon==<pin>`` dependency pin textually from
   ``<root>/pyproject.toml`` (no ``tomllib`` — Python floor is 3.10, OQ-019).
2. Exit 2 if the installed ``transon`` version differs from the pin.
3. Write ``resources/metadata-snapshot.json`` as the canonical serialization
   of ``transon.metadata.get_editor_metadata()``.
4. Create the ``resources/nl-intents.json`` sidecar skeleton only if absent —
   an existing sidecar is NEVER overwritten (FR-010/OQ-021).
5. Write ``resources/metadata-snapshot.md`` with SHA-256 provenance for both
   files. ``synced_at`` is informational only (never compared by gates).

Exit codes: 0 success, 2 pin/config error.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as installed_version
from pathlib import Path

from _shared import ensure_src

ensure_src()
from transon_authoring._snapshot import (  # noqa: E402
    canonical_bytes,
    read_pin,
    render_provenance,
    sha256_hex,
)

SIDECAR_SKELETON = {"schema_version": "1.0", "intents": {}}


def _publish(path: Path, data: bytes) -> None:
    """Atomically replace *path* with *data* (write tmp + rename), so readers
    and crashes never observe a partially written file."""
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def _publish_no_replace(path: Path, data: bytes) -> None:
    """Atomically create *path* with *data* only if it does not exist yet
    (first-writer-wins via hard link; the file is never visible partially
    written and an existing file is never touched)."""
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    try:
        os.link(tmp, path)
    except FileExistsError:
        pass
    finally:
        tmp.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sync_metadata",
        description="Regenerate resources/metadata-snapshot.json from the "
        "pinned transon engine and record provenance (FR-011).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repo root containing pyproject.toml (default: this script's repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    pin, pin_error = read_pin(root)
    if pin_error is not None:
        print(f"sync-metadata: {pin_error}", file=sys.stderr)
        return 2

    try:
        installed = installed_version("transon")
    except PackageNotFoundError:
        print(
            f"sync-metadata: pinned engine transon=={pin} is not installed; "
            "install it and re-run (SPEC §11.7).",
            file=sys.stderr,
        )
        return 2
    if installed != pin:
        print(
            f"sync-metadata: installed transon=={installed} does not match the "
            f"pyproject pin transon=={pin}; install the pinned engine and re-run "
            "(SPEC §11.7).",
            file=sys.stderr,
        )
        return 2

    from transon.metadata import get_editor_metadata

    metadata = get_editor_metadata()

    resources = root / "resources"
    resources.mkdir(parents=True, exist_ok=True)

    snapshot_path = resources / "metadata-snapshot.json"
    _publish(snapshot_path, canonical_bytes(metadata))

    # Skeleton only on first sync; atomic first-writer-wins creation so
    # authored intents are never clobbered and no reader (including a
    # concurrent sync hashing for provenance) can observe a partial file
    # (FR-010/OQ-021).
    sidecar_path = resources / "nl-intents.json"
    _publish_no_replace(sidecar_path, canonical_bytes(SIDECAR_SKELETON))

    provenance = {
        "schema_version": "1.0",
        "engine_version": metadata["engine_version"],
        "metadata_version": metadata["metadata_version"],
        "algorithm": "sha256",
        "snapshot_sha256": sha256_hex(snapshot_path.read_bytes()),
        "sidecar_sha256": sha256_hex(sidecar_path.read_bytes()),
        "synced_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    provenance_path = resources / "metadata-snapshot.md"
    _publish(provenance_path, render_provenance(provenance).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
