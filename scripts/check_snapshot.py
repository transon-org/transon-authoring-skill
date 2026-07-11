#!/usr/bin/env python
"""check-snapshot — drift gate for the pinned metadata snapshot
(NFR-004 / AC-006 / OQ-021; SPEC §8, §11.7, §15).

Fails (exit 1) when the bundled snapshot no longer matches
``get_editor_metadata()`` under the pinned ``transon==<pin>`` install, when
the pin itself is not what is installed, when provenance hashes are stale, or
when the NL-intents sidecar violates the OQ-021 consistency rules. It does
NOT track unpinned newer releases (AD-007): only the pyproject pin matters.

All checks run every time; every failure is reported on stderr. ``synced_at``
in the provenance is informational only and is never compared (determinism,
FR-011).

Checks:

1. Installed ``transon`` version == the pyproject pin (textual parse, no
   ``tomllib`` — OQ-019); off-pin is red.
2. ``canonical_bytes(get_editor_metadata())`` from the installed engine is
   byte-equal to ``resources/metadata-snapshot.json`` (AC-006 drift).
3. Snapshot content: ``metadata_version == "3.0"`` and ``engine_version`` ==
   pin (SPEC §11.7 A0 pin).
4. Provenance ``resources/metadata-snapshot.md`` parses; its
   ``snapshot_sha256`` / ``sidecar_sha256`` match the actual file bytes; its
   ``engine_version`` / ``metadata_version`` match the snapshot.
5. OQ-021 sidecar: ``resources/nl-intents.json`` parses with
   ``schema_version "1.0"`` and an ``intents`` object; every intents key MUST
   name a snapshot ``docs.examples`` entry (dangling keys are failures);
   snapshot examples WITHOUT sidecar entries are allowed — the gate stays
   green but reports the uncovered count on stderr (full sorted name list
   under ``--verbose``).

Exit codes: 0 all green, 1 any check failed.
"""

from __future__ import annotations

import argparse
import json
import sys
from importlib.metadata import version as installed_version
from pathlib import Path

try:
    from transon_authoring._snapshot import (
        canonical_bytes,
        extract_pin,
        parse_provenance,
        sha256_hex,
    )
except ImportError:  # pragma: no cover - source-checkout fallback (SPEC §10)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from transon_authoring._snapshot import (
        canonical_bytes,
        extract_pin,
        parse_provenance,
        sha256_hex,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_snapshot",
        description="Fail if resources/metadata-snapshot.json drifted from the "
        "pinned transon engine, provenance hashes are stale, or the NL sidecar "
        "is inconsistent (NFR-004 / AC-006 / OQ-021).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repo root containing pyproject.toml (default: this script's repo)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="list the sorted names of snapshot examples without sidecar entries",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    failures: list[str] = []

    def fail(message: str) -> None:
        failures.append(message)

    # --- Check 1: installed engine == pyproject pin (NFR-004). -------------
    pin: str | None = None
    pyproject = root / "pyproject.toml"
    if not pyproject.is_file():
        fail(f"no pyproject.toml under {root}")
    else:
        pin = extract_pin(pyproject.read_text(encoding="utf-8"))
        if pin is None:
            fail(f"no 'transon==<version>' pin found in {pyproject}")

    live_bytes: bytes | None = None
    installed: str | None = None
    try:
        from transon.metadata import get_editor_metadata

        installed = installed_version("transon")
        live_bytes = canonical_bytes(get_editor_metadata())
    except Exception as exc:  # pragma: no cover - engine not installed
        fail(f"pinned engine unavailable: {exc}")
    if pin is not None and installed is not None and installed != pin:
        fail(
            f"installed transon=={installed} does not match the pyproject pin "
            f"transon=={pin}; the gate checks the pin only, never newer "
            "releases (NFR-004 / AD-007, SPEC §11.7)"
        )

    # --- Check 2: bundle bytes == live pinned metadata (AC-006 drift). -----
    snapshot_path = root / "resources" / "metadata-snapshot.json"
    snapshot_bytes: bytes | None = None
    if not snapshot_path.is_file():
        fail(f"missing {snapshot_path}; run scripts/sync_metadata.py")
    else:
        snapshot_bytes = snapshot_path.read_bytes()
        if live_bytes is not None and snapshot_bytes != live_bytes:
            fail(
                "resources/metadata-snapshot.json drifted: the bundle no longer "
                "matches get_editor_metadata() from the pinned engine; run "
                "scripts/sync_metadata.py to re-sync (NFR-004 / AC-006)"
            )

    # --- Check 3: snapshot content vs the A0 pin (SPEC §11.7). -------------
    snapshot: dict | None = None
    if snapshot_bytes is not None:
        try:
            loaded = json.loads(snapshot_bytes.decode("utf-8"))
            if not isinstance(loaded, dict):
                raise ValueError("snapshot must be a JSON object")
            snapshot = loaded
        except (ValueError, UnicodeDecodeError) as exc:
            fail(f"resources/metadata-snapshot.json does not parse: {exc}")
    if snapshot is not None:
        if snapshot.get("metadata_version") != "3.0":
            fail(
                "snapshot metadata_version is "
                f"{snapshot.get('metadata_version')!r}, expected '3.0' (SPEC §11.7)"
            )
        if pin is not None and snapshot.get("engine_version") != pin:
            fail(
                f"snapshot engine_version is {snapshot.get('engine_version')!r}, "
                f"expected the pyproject pin {pin!r} (SPEC §11.7)"
            )

    # --- Check 4: provenance parses and its hashes/versions are current. ---
    sidecar_path = root / "resources" / "nl-intents.json"
    sidecar_bytes: bytes | None = None
    if not sidecar_path.is_file():
        fail(f"missing {sidecar_path}; run scripts/sync_metadata.py (FR-010)")
    else:
        sidecar_bytes = sidecar_path.read_bytes()

    provenance_path = root / "resources" / "metadata-snapshot.md"
    provenance: dict | None = None
    if not provenance_path.is_file():
        fail(f"missing {provenance_path}; run scripts/sync_metadata.py (FR-011)")
    else:
        try:
            provenance = parse_provenance(provenance_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            fail(f"resources/metadata-snapshot.md does not parse: {exc}")
    if provenance is not None:
        if snapshot_bytes is not None and provenance.get(
            "snapshot_sha256"
        ) != sha256_hex(snapshot_bytes):
            fail(
                "provenance snapshot_sha256 does not match the actual snapshot "
                "bytes; run scripts/sync_metadata.py (FR-011)"
            )
        if sidecar_bytes is not None and provenance.get(
            "sidecar_sha256"
        ) != sha256_hex(sidecar_bytes):
            fail(
                "provenance sidecar_sha256 does not match the actual sidecar "
                "bytes; run scripts/sync_metadata.py (OQ-021)"
            )
        if snapshot is not None:
            for key in ("engine_version", "metadata_version"):
                if provenance.get(key) != snapshot.get(key):
                    fail(
                        f"provenance {key} {provenance.get(key)!r} does not "
                        f"match the snapshot's {snapshot.get(key)!r} (FR-011)"
                    )
        # synced_at is informational only — never compared (FR-011).

    # --- Check 5: OQ-021 sidecar consistency. ------------------------------
    intents: dict | None = None
    if sidecar_bytes is not None:
        try:
            sidecar = json.loads(sidecar_bytes.decode("utf-8"))
            if not isinstance(sidecar, dict):
                raise ValueError("sidecar must be a JSON object")
        except (ValueError, UnicodeDecodeError) as exc:
            fail(f"resources/nl-intents.json does not parse: {exc}")
        else:
            if sidecar.get("schema_version") != "1.0":
                fail(
                    "sidecar schema_version is "
                    f"{sidecar.get('schema_version')!r}, expected '1.0' (FR-010)"
                )
            if not isinstance(sidecar.get("intents"), dict):
                fail("sidecar 'intents' must be a JSON object (FR-010)")
            else:
                intents = sidecar["intents"]

    if intents is not None and snapshot is not None:
        docs = snapshot.get("docs")
        examples = docs.get("examples") if isinstance(docs, dict) else None
        if not isinstance(examples, list):
            fail("snapshot has no docs.examples list (OQ-021 checks need it)")
        else:
            example_names = {
                example.get("name")
                for example in examples
                if isinstance(example, dict)
            }
            dangling = sorted(set(intents) - example_names)
            if dangling:
                fail(
                    "sidecar intents keys with no matching snapshot "
                    "docs.examples name (OQ-021): " + ", ".join(dangling)
                )
            uncovered = sorted(name for name in example_names if name not in intents)
            # Allowed (gate stays green), but never silent (OQ-021 c).
            print(
                f"check-snapshot: note: {len(uncovered)} snapshot examples "
                "are uncovered by the NL sidecar (allowed; OQ-021)",
                file=sys.stderr,
            )
            if args.verbose:
                for name in uncovered:
                    print(f"check-snapshot:   uncovered: {name}", file=sys.stderr)

    for message in failures:
        print(f"check-snapshot: FAIL: {message}", file=sys.stderr)
    if failures:
        print(f"check-snapshot: {len(failures)} check(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
