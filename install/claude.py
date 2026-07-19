#!/usr/bin/env python3
"""Claude Code skill installer (FR-015/FR-016, SPEC §11.9).

Project scope: ``<repo-root>/.claude/skills/transon-authoring/``.
Personal scope: ``~/.claude/skills/transon-authoring/`` (``--home`` overrides).
Copies files only; the runtime comes from ``pip install transon-authoring``.
"""

from __future__ import annotations

import sys
from pathlib import Path

_INSTALL_DIR = str(Path(__file__).resolve().parent)
if _INSTALL_DIR not in sys.path:
    sys.path.insert(0, _INSTALL_DIR)

import _shared


def main(argv=None) -> int:
    return _shared.run("claude", argv)


if __name__ == "__main__":
    raise SystemExit(main())
