"""FR-015 / FR-016 (AC-007, feeding AC-009) — install/uninstall scripts per
SPEC §11.9, NFR-008 (versioned releases) and NFR-009 (install integrity).

The installers are run via subprocess with the same interpreter pytest runs
under (same style as tests/test_sync_metadata.py), against a throwaway repo
root and home built under tmp_path — the real ``~`` is never touched.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_INSTALLER = REPO_ROOT / "install" / "claude.py"
CURSOR_INSTALLER = REPO_ROOT / "install" / "cursor.py"

PYPROJECT = """\
[project]
name = "transon-authoring"
version = "0.0.1"
dependencies = [
    "transon==0.1.7",
]
"""

SKILL_BODY = "# transon-authoring skill body (fixture)\n"
SNAPSHOT_BYTES = b'{\n  "fixture_snapshot": true\n}\n'


def make_repo(tmp_path: Path, name: str = "repo", pyproject: str = PYPROJECT) -> Path:
    root = tmp_path / name
    for tool in ("claude", "cursor"):
        adapter_dir = root / "adapters" / tool
        adapter_dir.mkdir(parents=True)
        scopes = ["project", "personal"] if tool == "claude" else ["project"]
        (adapter_dir / "adapter.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "tool": tool,
                    "scopes": scopes,
                    "files": ["SKILL.md"],
                    "exclusions": [],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    (root / "resources").mkdir()
    (root / "resources" / "metadata-snapshot.json").write_bytes(SNAPSHOT_BYTES)
    (root / "pyproject.toml").write_text(pyproject, encoding="utf-8")
    (root / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    return root


def run_installer(script: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), *argv], capture_output=True, text=True
    )


def tree_bytes(root: Path) -> dict:
    """Relative-path -> exact bytes map, for byte-identical tree comparison."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_fr015_claude_project_install_paths_and_manifest(tmp_path: Path):
    # FR-015 / AC-007 — §11.9 project-scope destination + .install-manifest.json.
    repo = make_repo(tmp_path)
    result = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo))
    assert result.returncode == 0, result.stderr

    dest = repo / ".claude" / "skills" / "transon-authoring"
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == SKILL_BODY

    report = json.loads(result.stdout)
    assert report == {
        "schema_version": "1.0",
        "tool": "claude",
        "scope": "project",
        "action": "install",
        "dest": str(dest),
        "files": ["SKILL.md", ".install-manifest.json"],
    }

    manifest = json.loads((dest / ".install-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert manifest["tool"] == "claude"
    assert manifest["scope"] == "project"
    assert manifest["files"] == ["SKILL.md", ".install-manifest.json"]


def test_fr015_claude_personal_scope_uses_home_override(tmp_path: Path):
    # FR-015 / AC-007 — personal scope resolves under --home, never the real ~.
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    result = run_installer(
        CLAUDE_INSTALLER,
        "--scope",
        "personal",
        "--repo-root",
        str(repo),
        "--home",
        str(home),
    )
    assert result.returncode == 0, result.stderr

    dest = home / ".claude" / "skills" / "transon-authoring"
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == SKILL_BODY
    assert (dest / ".install-manifest.json").is_file()
    report = json.loads(result.stdout)
    assert report["scope"] == "personal"
    assert report["dest"] == str(dest)
    assert not (repo / ".claude").exists()


def test_fr015_cursor_personal_scope_exit2(tmp_path: Path):
    # FR-015 / NFR-007 — Cursor is project-only in v1 (documented exclusion,
    # §11.9 install table): personal scope is a config error, exit 2.
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    result = run_installer(
        CURSOR_INSTALLER,
        "--scope",
        "personal",
        "--repo-root",
        str(repo),
        "--home",
        str(home),
    )
    assert result.returncode == 2
    assert "personal" in result.stderr
    assert result.stdout == ""
    assert not (home / ".cursor").exists()
    assert not (repo / ".cursor").exists()

    project = run_installer(CURSOR_INSTALLER, "--repo-root", str(repo))
    assert project.returncode == 0, project.stderr
    dest = repo / ".cursor" / "skills" / "transon-authoring"
    assert (dest / "SKILL.md").is_file()
    assert json.loads(project.stdout)["tool"] == "cursor"


def test_fr015_manifest_records_nfr008_triplet(tmp_path: Path):
    # FR-015 / NFR-008 — manifest records skill version, engine pin, and
    # snapshot hash; the pin is parsed from pyproject, never hard-coded.
    repo = make_repo(tmp_path)
    result = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo))
    assert result.returncode == 0, result.stderr

    dest = repo / ".claude" / "skills" / "transon-authoring"
    manifest = json.loads((dest / ".install-manifest.json").read_text(encoding="utf-8"))
    assert manifest["skill_version"] == "0.0.1"
    assert manifest["engine_pin"] == "transon==0.1.7"
    assert manifest["snapshot_sha256"] == hashlib.sha256(SNAPSHOT_BYTES).hexdigest()

    # Different pin in pyproject => different engine_pin (proves textual parse).
    other = make_repo(
        tmp_path,
        name="other",
        pyproject=PYPROJECT.replace("transon==0.1.7", "transon==9.9.9").replace(
            'version = "0.0.1"', 'version = "1.2.3"'
        ),
    )
    other_result = run_installer(CLAUDE_INSTALLER, "--repo-root", str(other))
    assert other_result.returncode == 0, other_result.stderr
    other_manifest = json.loads(
        (other / ".claude" / "skills" / "transon-authoring" / ".install-manifest.json")
        .read_text(encoding="utf-8")
    )
    assert other_manifest["engine_pin"] == "transon==9.9.9"
    assert other_manifest["skill_version"] == "1.2.3"


def test_fr016_reinstall_idempotent_byte_identical(tmp_path: Path):
    # FR-016 / AC-007 — re-running install overwrites owned files and leaves
    # the destination tree byte-identical (upgrade = idempotent replace).
    repo = make_repo(tmp_path)
    dest = repo / ".claude" / "skills" / "transon-authoring"

    first = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo))
    assert first.returncode == 0, first.stderr
    before = tree_bytes(dest)

    second = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo))
    assert second.returncode == 0, second.stderr
    assert tree_bytes(dest) == before
    assert second.stdout == first.stdout


def test_fr016_uninstall_removes_only_manifest_paths_keeps_stray(tmp_path: Path):
    # FR-016 / AC-007 — uninstall deletes only manifest-listed paths; stray
    # user files (and therefore the directory) survive.
    repo = make_repo(tmp_path)
    dest = repo / ".claude" / "skills" / "transon-authoring"
    assert run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo)).returncode == 0
    stray = dest / "user-note.txt"
    stray.write_text("keep me\n", encoding="utf-8")

    result = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo), "--uninstall")
    assert result.returncode == 0, result.stderr
    assert stray.read_text(encoding="utf-8") == "keep me\n"
    assert not (dest / "SKILL.md").exists()
    assert not (dest / ".install-manifest.json").exists()
    assert dest.is_dir()
    report = json.loads(result.stdout)
    assert report["action"] == "uninstall"
    assert report["files"] == ["SKILL.md", ".install-manifest.json"]

    # Without strays the now-empty skill directory is removed too.
    clean = make_repo(tmp_path, name="clean")
    assert run_installer(CLAUDE_INSTALLER, "--repo-root", str(clean)).returncode == 0
    assert (
        run_installer(CLAUDE_INSTALLER, "--repo-root", str(clean), "--uninstall")
        .returncode
        == 0
    )
    assert not (clean / ".claude" / "skills" / "transon-authoring").exists()


def test_fr016_uninstall_noop_without_manifest(tmp_path: Path):
    # FR-016 — no manifest present => nothing owned => no-op, exit 0.
    repo = make_repo(tmp_path)
    result = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo), "--uninstall")
    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["action"] == "uninstall"
    assert report["files"] == []

    # Same when the directory exists but holds only user files.
    dest = repo / ".claude" / "skills" / "transon-authoring"
    dest.mkdir(parents=True)
    stray = dest / "user-note.txt"
    stray.write_text("keep me\n", encoding="utf-8")
    again = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo), "--uninstall")
    assert again.returncode == 0, again.stderr
    assert stray.is_file()
