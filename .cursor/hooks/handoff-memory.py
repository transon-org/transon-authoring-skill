#!/usr/bin/env python3
"""`stop` hook: nudge the agent to refresh the working handoff before finishing.

Only speaks up when the agent changed watched files *and* left
`docs/current-state.md` untouched. The signal logic is single-sourced in
`harness/scripts/update_memory.handoff_nudge`. Pure stdlib; fail-open.
"""
import json
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_DIR / "harness" / "scripts"))


def main() -> int:
    try:
        loaded = json.load(sys.stdin)
    except (json.JSONDecodeError, ValueError):
        loaded = {}
    payload = loaded if isinstance(loaded, dict) else {}

    if payload.get("status") not in (None, "completed"):
        print("{}")
        return 0

    try:
        from update_memory import handoff_nudge

        msg = handoff_nudge()
    except Exception as exc:  # fail-open: never block the agent on hook faults
        print(f"handoff-memory: {exc}", file=sys.stderr)
        print("{}")
        return 0

    print(json.dumps({"followup_message": msg}) if msg else "{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
