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
import re
import sys
from datetime import datetime, timezone
from importlib.metadata import version as installed_version
from pathlib import Path

try:
    from transon_authoring._snapshot import (
        canonical_bytes,
        render_provenance,
        sha256_hex,
    )
except ImportError:  # pragma: no cover - source-checkout fallback (SPEC §10)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from transon_authoring._snapshot import (
        canonical_bytes,
        render_provenance,
        sha256_hex,
    )

# Textual pin extraction from the dependency line, e.g.
#   dependencies = ["transon==0.1.7"]
# PEP 440 version charset in the capture so quotes/brackets stay out of it.
PIN_RE = re.compile(r"transon==([0-9A-Za-z.!+*-]+)")

SIDECAR_SKELETON = {"schema_version": "1.0", "intents": {}}


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

    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        print(f"sync-metadata: no pyproject.toml under {root}", file=sys.stderr)
        return 2
    match = PIN_RE.search(pyproject.read_text(encoding="utf-8"))
    if not match:
        print(
            f"sync-metadata: no 'transon==<version>' pin found in {pyproject}",
            file=sys.stderr,
        )
        return 2
    pin = match.group(1)

    installed = installed_version("transon")
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
    snapshot_path.write_bytes(canonical_bytes(metadata))

    sidecar_path = resources / "nl-intents.json"
    if not sidecar_path.exists():
        # Skeleton only on first sync; authored intents are never clobbered.
        sidecar_path.write_bytes(canonical_bytes(SIDECAR_SKELETON))

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
    provenance_path.write_bytes(render_provenance(provenance).encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
