"""FR-015 / FR-016 (AC-007, feeding AC-009) — install/uninstall scripts per
SPEC §11.9, NFR-008 (versioned releases) and NFR-009 (install integrity).

The installers are run via subprocess with the same interpreter pytest runs
under (same style as tests/test_sync_metadata.py), against a throwaway repo
root and home built under tmp_path — the real ``~`` is never touched.
"""

import hashlib
import json
import os
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
    "transon==0.2.3",
]
"""

SKILL_BODY = "# transon-authoring skill body (fixture)\n"
SNAPSHOT_BYTES = b'{\n  "fixture_snapshot": true\n}\n'


def make_repo(tmp_path: Path, name: str = "repo", pyproject: str = PYPROJECT) -> Path:
    root = tmp_path / name
    for tool in ("claude", "cursor"):
        adapter_dir = root / "adapters" / tool
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "adapter.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "tool": tool,
                    "scopes": ["project", "personal"],
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
    # SPEC 11.9: adapter `files` are destination-relative names read out of the
    # canonical body directory; they land flat in the destination.
    skill_dir = root / "skills" / "transon-authoring"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
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


def test_fr038_cursor_personal_scope_uses_home_override(tmp_path: Path):
    # FR-038 / AC-041 — Cursor personal scope installs at the §11.9
    # destination under --home, with the same manifest discipline as every
    # other scope. Structural claim only (OQ-008): nothing here asserts that
    # Cursor discovered or activated the skill.
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
    assert result.returncode == 0, result.stderr

    dest = home / ".cursor" / "skills" / "transon-authoring"
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == SKILL_BODY
    report = json.loads(result.stdout)
    assert report["tool"] == "cursor"
    assert report["scope"] == "personal"
    assert report["dest"] == str(dest)
    assert not (repo / ".cursor").exists()

    manifest = json.loads((dest / ".install-manifest.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == "1.0"
    assert manifest["tool"] == "cursor"
    assert manifest["scope"] == "personal"
    assert manifest["skill_version"] == "0.0.1"
    assert manifest["engine_pin"] == "transon==0.2.3"
    assert manifest["snapshot_sha256"] == hashlib.sha256(SNAPSHOT_BYTES).hexdigest()
    assert manifest["files"] == ["SKILL.md", ".install-manifest.json"]


def test_fr038_cursor_personal_uninstall_removes_only_manifest_paths(tmp_path: Path):
    # FR-038 / AC-041 (with FR-016) — personal-scope uninstall deletes only
    # manifest-listed paths; stray user files under the destination survive.
    repo = make_repo(tmp_path)
    home = tmp_path / "home"
    home.mkdir()
    scope_argv = (
        "--scope",
        "personal",
        "--repo-root",
        str(repo),
        "--home",
        str(home),
    )
    assert run_installer(CURSOR_INSTALLER, *scope_argv).returncode == 0

    dest = home / ".cursor" / "skills" / "transon-authoring"
    stray = dest / "user-note.txt"
    stray.write_text("keep me\n", encoding="utf-8")

    result = run_installer(CURSOR_INSTALLER, *scope_argv, "--uninstall")
    assert result.returncode == 0, result.stderr
    assert stray.read_text(encoding="utf-8") == "keep me\n"
    assert not (dest / "SKILL.md").exists()
    assert not (dest / ".install-manifest.json").exists()
    assert dest.is_dir()
    report = json.loads(result.stdout)
    assert report["action"] == "uninstall"
    assert report["files"] == ["SKILL.md", ".install-manifest.json"]


def test_nfr_007_scope_absent_from_adapter_descriptor_exits_2(tmp_path: Path):
    # NFR-007 / FR-015 — the installer refuses a scope its adapter descriptor
    # does not list (SPEC §11.9 documented exclusion): exit 2, and nothing is
    # created at the destination. The narrower adapter here is **synthetic** —
    # the shipped Cursor adapter reaches both scopes since FR-038, so this is
    # the only thing driving the `adapter["scopes"]` guard in
    # install/_shared.py from tests/test_install.py.
    repo = make_repo(tmp_path)
    adapter_path = repo / "adapters" / "cursor" / "adapter.json"
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    adapter["scopes"] = ["project"]
    adapter_path.write_text(json.dumps(adapter, indent=2) + "\n", encoding="utf-8")

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
    assert result.returncode == 2, result.stdout
    assert "personal" in result.stderr
    assert not (home / ".cursor").exists()
    assert not (repo / ".cursor").exists()


def test_nfr_009_adapter_files_escaping_their_roots_exit_2(tmp_path: Path):
    # NFR-009 — the installer writes into a user's project, so an adapter
    # `files` entry that leaves the canonical body directory or the destination
    # (traversal or absolute) is refused outright, before any read or write.
    # The adapters here are **synthetic**: the shipped ones are repo-controlled
    # and linted by check_parity, so this is the only thing driving the guard.
    escapee = tmp_path / "escaped.md"
    escapee.write_text("payload\n", encoding="utf-8")
    absolute = tmp_path / "absolute.md"
    absolute.write_text("payload\n", encoding="utf-8")

    for name, entry in (
        ("traversal", "../../../escaped.md"),
        ("absolute", str(absolute)),
    ):
        repo = make_repo(tmp_path, name=f"repo-{name}")
        adapter_path = repo / "adapters" / "claude" / "adapter.json"
        adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
        adapter["files"] = [entry]
        adapter_path.write_text(json.dumps(adapter, indent=2) + "\n", encoding="utf-8")

        target = tmp_path / f"target-{name}"
        target.mkdir()
        result = run_installer(
            CLAUDE_INSTALLER, "--repo-root", str(repo), "--target-root", str(target)
        )
        assert result.returncode == 2, result.stdout
        assert entry in result.stderr

        # Nothing was written: the destination tree is empty (without the guard
        # the traversal entry lands at target/escaped.md) and the files the
        # entries point at are untouched.
        assert tree_bytes(target) == {}
        assert escapee.read_text(encoding="utf-8") == "payload\n"
        assert absolute.read_text(encoding="utf-8") == "payload\n"


def test_nfr_009_manifest_paths_escaping_dest_are_not_deleted(tmp_path: Path):
    # NFR-009 — the same guard on the uninstall side: a manifest `files` entry
    # pointing outside the destination is refused (exit 2) rather than unlinking
    # a file the installer never owned.
    repo = make_repo(tmp_path)
    result = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo))
    assert result.returncode == 0, result.stderr

    dest = repo / ".claude" / "skills" / "transon-authoring"
    outsider = repo / "victim.md"
    outsider.write_text("not ours\n", encoding="utf-8")
    manifest_path = dest / ".install-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = ["../../../victim.md", ".install-manifest.json"]
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    removal = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo), "--uninstall")
    assert removal.returncode == 2, removal.stdout
    assert outsider.read_text(encoding="utf-8") == "not ours\n"


def test_fr015_manifest_records_nfr008_triplet(tmp_path: Path):
    # FR-015 / NFR-008 — manifest records skill version, engine pin, and
    # snapshot hash; the pin is parsed from pyproject, never hard-coded.
    repo = make_repo(tmp_path)
    result = run_installer(CLAUDE_INSTALLER, "--repo-root", str(repo))
    assert result.returncode == 0, result.stderr

    dest = repo / ".claude" / "skills" / "transon-authoring"
    manifest = json.loads((dest / ".install-manifest.json").read_text(encoding="utf-8"))
    assert manifest["skill_version"] == "0.0.1"
    assert manifest["engine_pin"] == "transon==0.2.3"
    assert manifest["snapshot_sha256"] == hashlib.sha256(SNAPSHOT_BYTES).hexdigest()

    # Different pin in pyproject => different engine_pin (proves textual parse).
    other = make_repo(
        tmp_path,
        name="other",
        pyproject=PYPROJECT.replace("transon==0.2.3", "transon==9.9.9").replace(
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


def test_fr015_target_root_separates_source_and_destination(tmp_path: Path):
    # FR-015 / §11.9 — `<repo>` in the destination table is the *target
    # project root*: --target-root installs into a project distinct from the
    # source checkout; skill files are still read from --repo-root. Uninstall
    # honors the same flag. Default (other tests) stays the checkout root.
    checkout = make_repo(tmp_path, name="checkout")
    target = tmp_path / "project"
    target.mkdir()

    for script, tool_dir in (
        (CLAUDE_INSTALLER, ".claude"),
        (CURSOR_INSTALLER, ".cursor"),
    ):
        result = run_installer(
            script,
            "--repo-root",
            str(checkout),
            "--target-root",
            str(target),
        )
        assert result.returncode == 0, result.stderr
        dest = target / tool_dir / "skills" / "transon-authoring"
        assert (dest / "SKILL.md").read_text(encoding="utf-8") == SKILL_BODY
        assert (dest / ".install-manifest.json").is_file()
        assert json.loads(result.stdout)["dest"] == str(dest)
        # Nothing is created under the source checkout's tool directories.
        assert not (checkout / tool_dir).exists()

        uninstall = run_installer(
            script,
            "--repo-root",
            str(checkout),
            "--target-root",
            str(target),
            "--uninstall",
        )
        assert uninstall.returncode == 0, uninstall.stderr
        assert not dest.exists()
        report = json.loads(uninstall.stdout)
        assert report["action"] == "uninstall"
        assert report["files"] == ["SKILL.md", ".install-manifest.json"]


def test_fr015_oq020_missing_runtime_hint_still_exit_0(tmp_path: Path):
    # FR-015 / OQ-020 (§11.9 runtime-distribution paragraph) — when the
    # runtime package is not importable, the installer prints a stderr hint
    # naming `pip install transon-authoring` and still exits 0: the
    # structural install completes and is valid without the runtime.
    repo = make_repo(tmp_path)
    shadow = tmp_path / "shadow" / "transon_authoring"
    shadow.mkdir(parents=True)
    (shadow / "__init__.py").write_text(
        "raise ImportError('runtime not installed (test fixture)')\n",
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path / "shadow")

    result = subprocess.run(
        [sys.executable, str(CLAUDE_INSTALLER), "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0, result.stderr
    assert "pip install transon-authoring" in result.stderr

    dest = repo / ".claude" / "skills" / "transon-authoring"
    assert (dest / "SKILL.md").read_text(encoding="utf-8") == SKILL_BODY
    manifest = json.loads((dest / ".install-manifest.json").read_text(encoding="utf-8"))
    assert manifest["files"] == ["SKILL.md", ".install-manifest.json"]
    assert json.loads(result.stdout)["action"] == "install"


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
