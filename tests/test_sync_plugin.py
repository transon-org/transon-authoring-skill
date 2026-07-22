"""FR-037 half (a) / AC-040 — `sync-plugin` regenerates the plugin skill body
from the canonical root `SKILL.md` (SPEC §11.9 "Plugin form").

The script under test is run via subprocess with the same interpreter pytest
runs under, so exit codes are observed exactly as CI would see them.
"""

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sync_plugin.py"
PLUGIN_SKILL_REL = Path("skills") / "transon-authoring" / "SKILL.md"

CANONICAL_BODY = (
    "---\n"
    "name: transon-authoring\n"
    "description: Fixture body with a non-ASCII byte — ü — and no BOM.\n"
    "---\n"
    "\n"
    "# transon-authoring (fixture)\n"
).encode("utf-8")


def run_sync(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def test_fr037a_sync_plugin_writes_byte_identical_copy(tmp_path: Path):
    # FR-037a / AC-040 — the generated plugin body is byte-for-byte the
    # canonical root SKILL.md (NFR-007 single source by enforced identity).
    root = tmp_path / "repo"
    root.mkdir()
    (root / "SKILL.md").write_bytes(CANONICAL_BODY)

    result = run_sync(root)
    assert result.returncode == 0, result.stderr
    assert (root / PLUGIN_SKILL_REL).read_bytes() == CANONICAL_BODY


def test_fr037a_sync_plugin_is_idempotent(tmp_path: Path):
    # FR-037a / AC-040 — regeneration is deterministic: a second run leaves the
    # plugin tree byte-identical and drops no temp artifacts.
    root = tmp_path / "repo"
    root.mkdir()
    (root / "SKILL.md").write_bytes(CANONICAL_BODY)

    assert run_sync(root).returncode == 0
    first = {
        path.relative_to(root): path.read_bytes()
        for path in sorted((root / "skills").rglob("*"))
        if path.is_file()
    }
    assert run_sync(root).returncode == 0
    second = {
        path.relative_to(root): path.read_bytes()
        for path in sorted((root / "skills").rglob("*"))
        if path.is_file()
    }
    assert second == first
    assert list(first) == [PLUGIN_SKILL_REL]


def test_fr037a_sync_plugin_exit2_without_root_skill(tmp_path: Path):
    # FR-037a — no canonical body to copy is a loud config error, exit 2.
    root = tmp_path / "repo"
    root.mkdir()

    result = run_sync(root)
    assert result.returncode == 2
    assert "SKILL.md" in result.stderr
    assert not (root / "skills").exists()
