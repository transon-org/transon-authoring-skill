#!/usr/bin/env python3
"""Stop hook (Claude Code adapter for `.cursor/hooks/handoff-memory.py`).

Nudges the agent to refresh `docs/current-state.md` before finishing when
watched files changed and the handoff was left untouched. Signal logic is
single-sourced in `harness/scripts/update_memory.handoff_nudge`. Fail-open.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "harness" / "scripts"))


def main() -> int:
    try:
        loaded = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        loaded = {}
    payload = loaded if isinstance(loaded, dict) else {}

    if payload.get("stop_hook_active"):
        print("{}")
        return 0

    try:
        from update_memory import handoff_nudge

        msg = handoff_nudge()
    except Exception as exc:  # fail-open: never block the agent on hook faults
        print(f"handoff-memory: {exc}", file=sys.stderr)
        print("{}")
        return 0

    if not msg:
        print("{}")
        return 0

    print(
        json.dumps(
            {
                "decision": "block",
                "reason": msg,
                "hookSpecificOutput": {
                    "hookEventName": "Stop",
                    "additionalContext": msg,
                },
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
