#!/usr/bin/env python3
"""Cursor skill installer (FR-015/FR-016, SPEC §11.9).

Project scope only: ``<target-root>/.cursor/skills/transon-authoring/``
(``--target-root``; default: the ``--repo-root`` checkout itself).
Personal scope is a documented exclusion (Cursor is project-only in v1) and
exits 2. Copies files only; the runtime comes from
``pip install transon-authoring``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_INSTALL_DIR = str(Path(__file__).resolve().parent)
if _INSTALL_DIR not in sys.path:
    sys.path.insert(0, _INSTALL_DIR)

import _shared


def main(argv=None) -> int:
    return _shared.run("cursor", argv)


if __name__ == "__main__":
    raise SystemExit(main())
