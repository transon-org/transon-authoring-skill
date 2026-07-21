#!/usr/bin/env python3
"""Working-memory handoff tooling for docs/current-state.md.

Regenerates the factual *At a glance* header from git + the engine pin in
``pyproject.toml``. The narrative sections below the header are hand-written.

Usage::

    update_memory.py --state     # refresh current-state.md header (create if absent)
    update_memory.py             # same as --state (state is the only mode here)

Product metadata-snapshot sync stays under ``scripts/`` (SPEC deliverable) and
is intentionally out of scope for this harness script.

Pure stdlib.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple

SCRIPTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPTS_DIR.parent.parent
DOCS = PROJECT_ROOT / "docs"
CURRENT_STATE = DOCS / "current-state.md"
PYPROJECT = PROJECT_ROOT / "pyproject.toml"

WATCHED_PREFIXES = (
    "docs/",
    "src/",
    "tests/",
    "scripts/",
    "harness/",
    "evals/",
    "resources/",
    "adapters/",
    "AGENTS.md",
    ".coderabbit.yaml",
)

STATE_BEGIN = (
    "<!-- BEGIN generated: at-a-glance · "
    "python3 harness/scripts/update_memory.py --state -->"
)
STATE_END = "<!-- END generated: at-a-glance -->"


def _git(*args: str) -> Optional[str]:
    try:
        r = subprocess.run(
            ["git", *args],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    # rstrip only — leading-space porcelain lines (` M path`) must keep the XY
    # column so `_changed_paths` can slice at index 3.
    return r.stdout.rstrip("\n") if r.returncode == 0 else None


def _changed_paths() -> List[str]:
    out = _git("status", "--porcelain")
    if not out:
        return []
    paths = []
    for line in out.splitlines():
        if not line:
            continue
        path = line[3:].strip().strip('"') if len(line) > 3 else line.strip().strip('"')
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def _engine_pin() -> str:
    """Read the pinned ``transon==…`` dependency from pyproject.toml."""
    if not PYPROJECT.exists():
        return "_pyproject.toml missing_"
    text = PYPROJECT.read_text(encoding="utf-8")
    match = re.search(r'"transon==([^"]+)"', text)
    if match:
        return f"`transon=={match.group(1)}` (see [pyproject.toml](../pyproject.toml))"
    return "_no transon pin found in pyproject.toml_"


def _state_block() -> str:
    head = _git("rev-parse", "--short", "HEAD") or "unknown"
    subject = _git("log", "-1", "--pretty=%s") or "unknown"
    branch = _git("rev-parse", "--abbrev-ref", "HEAD") or "unknown"
    return (
        f"{STATE_BEGIN}\n"
        f"| | |\n|---|---|\n"
        f"| Repo HEAD | `{head}` — {subject} |\n"
        f"| Branch | `{branch}` |\n"
        f"| Engine pin | {_engine_pin()} |\n"
        f"{STATE_END}"
    )


STATE_TEMPLATE = """# Current state — working handoff

> **Non-authoritative working memory.** A session-to-session handoff, not part of the
> contract. Where this and the contract docs (`SPEC.md`, `traceability.md`, `AGENTS.md`)
> disagree, **they win**. Update the narrative below at the end of a work session;
> regenerate the header with `python3 harness/scripts/update_memory.py --state`.

{block}

## Last action

_(Record what landed in this session.)_

## Status by milestone

Authoritative milestone DoDs live in [`ROADMAP.md` §14](ROADMAP.md). This is the living read.

- See ROADMAP §14 for A0–A5 definitions of done.

## Next steps (ordered)

1. _(Record the next concrete step.)_

## Open blockers / waiting-on

- None.

## Do-not-relitigate (pointers, not copies)

- Product contract → [`SPEC.md`](SPEC.md).
- Coverage matrix → [`traceability.md`](traceability.md).
- Golden rules → [`AGENTS.md`](../AGENTS.md).
"""


def write_state() -> Tuple[bool, str]:
    block = _state_block()
    if not CURRENT_STATE.exists():
        CURRENT_STATE.write_text(STATE_TEMPLATE.format(block=block), encoding="utf-8")
        return True, "current-state.md created"
    text = CURRENT_STATE.read_text(encoding="utf-8")
    if STATE_BEGIN in text and STATE_END in text:
        pre = text.split(STATE_BEGIN, 1)[0]
        post = text.split(STATE_END, 1)[1]
        CURRENT_STATE.write_text(pre + block + post, encoding="utf-8")
        return True, "current-state.md header refreshed"
    return False, (
        "current-state.md present but has no generated-header markers — left unchanged"
    )


def handoff_nudge() -> Optional[str]:
    """Stop-hook signal: watched files changed but the handoff was left untouched."""
    changed = _changed_paths()
    watched = [
        p
        for p in changed
        if p.startswith(WATCHED_PREFIXES) or p in WATCHED_PREFIXES
    ]
    if not watched:
        return None
    if "docs/current-state.md" in changed:
        return None
    return (
        "You changed tracked files but didn't update the working handoff. Before finishing, "
        "refresh `docs/current-state.md` so the next session resumes cleanly: run "
        "`python3 harness/scripts/update_memory.py --state` for the header, then update "
        "**Last action** and **Next steps**. (Non-blocking; skip if this was a throwaway edit.)"
    )


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(
        description="Working-memory handoff (docs/current-state.md header)."
    )
    ap.add_argument(
        "--state",
        action="store_true",
        help="refresh current-state.md header (default when no flags given)",
    )
    args = ap.parse_args(argv)

    # State is the only mode; --state is accepted for parity with blockly's CLI.
    _ = args.state
    ok, msg = write_state()
    print(("OK: " if ok else "WARN: ") + msg)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
