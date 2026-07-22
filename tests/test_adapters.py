# FR-012 / AC-005: Claude and Cursor adapters share the single canonical SKILL.md.
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTERS_DIR = REPO_ROOT / "adapters"


def test_ac005_single_skill_source():
    # AC-005: single-source by construction — no SKILL.md copy under adapters/.
    assert ADAPTERS_DIR.is_dir()
    copies = [p for p in ADAPTERS_DIR.rglob("*") if p.name == "SKILL.md"]
    assert copies == [], f"adapters/ must not contain SKILL.md copies: {copies}"

    claude = json.loads((ADAPTERS_DIR / "claude" / "adapter.json").read_text())
    cursor = json.loads((ADAPTERS_DIR / "cursor" / "adapter.json").read_text())

    # Both adapters point at the same file list (the canonical repo-root SKILL.md).
    assert claude["files"] == cursor["files"]

    # NFR-007: every scope one adapter has and the other lacks must be a
    # documented exclusion with a non-empty reason on the narrower adapter.
    for wider, narrower in ((claude, cursor), (cursor, claude)):
        missing = set(wider["scopes"]) - set(narrower["scopes"])
        for scope in missing:
            documented = [
                excl
                for excl in narrower["exclusions"]
                if scope in excl.get("capability", "")
                and excl.get("reason", "").strip()
            ]
            assert documented, (
                f"{narrower['tool']} lacks scope {scope!r} without a documented "
                "exclusion carrying a non-empty reason"
            )


def test_ac005_adapters_reach_equal_scopes():
    # AC-005 / NFR-007 (FR-038) — the two adapters reach equal capability:
    # the same scope set, and no exclusion left on the Cursor side.
    claude = json.loads((ADAPTERS_DIR / "claude" / "adapter.json").read_text())
    cursor = json.loads((ADAPTERS_DIR / "cursor" / "adapter.json").read_text())

    assert set(claude["scopes"]) == set(cursor["scopes"])
    assert cursor["exclusions"] == []
