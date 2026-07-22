#!/usr/bin/env python
"""sync-plugin — regenerate the plugin skill body from the canonical root
`SKILL.md` (FR-037a / AC-040; SPEC §11.9 "Plugin form").

Behavior: copy ``<root>/SKILL.md`` verbatim to
``<root>/skills/transon-authoring/SKILL.md``. Marketplace hosts fetch the repo
tree, so that copy is committed; identity with the canonical file is what keeps
the single source (NFR-007) intact, and `check_install` is the gate.

Scope is the ``SKILL.md`` copy only. The ``.claude-plugin/`` manifests are
hand-authored: a forgotten ``plugin.json`` version bump surfaces as a red gate,
not as a silent rewrite here.

Exit codes: 0 success, 2 missing canonical ``SKILL.md``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROG = "sync-plugin"
SKILL_DIR_NAME = "transon-authoring"


def _publish(path: Path, data: bytes) -> None:
    """Atomically replace *path* with *data* (write tmp + rename), so readers
    and crashes never observe a partially written file."""
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}")
    tmp.write_bytes(data)
    os.replace(tmp, path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="sync_plugin",
        description="Regenerate skills/transon-authoring/SKILL.md from the "
        "canonical root SKILL.md (FR-037a).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repo root containing SKILL.md (default: this script's repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    canonical = root / "SKILL.md"
    if not canonical.is_file():
        print(
            f"{PROG}: no canonical SKILL.md at {canonical}; the plugin body is "
            "generated from it (SPEC §11.9).",
            file=sys.stderr,
        )
        return 2

    target_dir = root / "skills" / SKILL_DIR_NAME
    target_dir.mkdir(parents=True, exist_ok=True)
    _publish(target_dir / "SKILL.md", canonical.read_bytes())
    return 0


if __name__ == "__main__":
    sys.exit(main())
