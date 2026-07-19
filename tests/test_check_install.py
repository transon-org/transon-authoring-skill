"""FR-019 / NFR-009 (AC-009, and AC-007's gate half) — scripts/check_install.py.

The gate is invoked via subprocess with the interpreter pytest runs under
(same style as tests/test_install.py), pointed at throwaway fixture roots
built in tmp_path — the real ``~`` and the real repo's ``.claude``/``.cursor``
are never touched (the gate rehearses inside its own temp staging).
"""

import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GATE = REPO_ROOT / "scripts" / "check_install.py"

PYPROJECT = """\
[project]
name = "transon-authoring"
version = "0.0.1"
dependencies = [
    "transon==0.1.7",
]
"""

SKILL_MD = """\
---
name: transon-authoring
description: Fixture skill body for the install-integrity gate.
---

# transon-authoring (fixture)
"""


def run_gate(*argv: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GATE), *argv], capture_output=True, text=True, env=env
    )


def make_fake_root(
    tmp_path: Path,
    *,
    name: str = "root",
    skill_md: str = SKILL_MD,
    adapter_files: list[str] | None = None,
) -> Path:
    root = tmp_path / name
    files = adapter_files if adapter_files is not None else ["SKILL.md"]
    for tool, scopes in (("claude", ["project", "personal"]), ("cursor", ["project"])):
        adapter_dir = root / "adapters" / tool
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "adapter.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "tool": tool,
                    "scopes": scopes,
                    "files": files,
                    "exclusions": [],
                }
            )
            + "\n",
            encoding="utf-8",
        )
    (root / "resources").mkdir()
    (root / "resources" / "metadata-snapshot.json").write_bytes(
        b'{\n  "fixture_snapshot": true\n}\n'
    )
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "SKILL.md").write_text(skill_md, encoding="utf-8")
    return root


def test_ac009_gate_green_on_repo():
    # AC-009 / FR-019 / NFR-009 — the shipped repo passes the full rehearsal
    # (all three tool/scope combos + OQ-010 lint + cursor runtime smoke).
    result = run_gate("--root", str(REPO_ROOT))
    assert result.returncode == 0, result.stderr
    assert "FAIL" not in result.stderr


def test_ac009_red_on_missing_frontmatter_description(tmp_path: Path):
    # AC-009 / OQ-010 — installed SKILL.md without a frontmatter description
    # fails the discoverability-precondition lint.
    root = make_fake_root(
        tmp_path,
        skill_md="---\nname: transon-authoring\n---\n\n# body\n",
    )
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "description" in result.stderr


def test_ac009_red_on_name_mismatch(tmp_path: Path):
    # AC-009 / OQ-010 — frontmatter `name` must equal the skill directory
    # name `transon-authoring`.
    root = make_fake_root(
        tmp_path,
        skill_md=(
            "---\nname: some-other-skill\n"
            "description: Fixture description.\n---\n\n# body\n"
        ),
    )
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "name" in result.stderr
    assert "some-other-skill" in result.stderr


def test_ac009_red_on_noncanonical_installed_body(tmp_path: Path):
    # AC-009 / FR-019 — a root whose adapter lists a file that does not exist
    # makes the installer fail (exit 2); the gate must surface that as red
    # rather than report a green structural install.
    root = make_fake_root(tmp_path, adapter_files=["SKILL.md", "extras/missing.md"])
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "install" in result.stderr


def test_ac009_cursor_smoke_metadata_version(tmp_path: Path):
    # AC-009 / FR-019 — cursor runtime smoke: `python -m transon_authoring
    # metadata` must exit 0, parse as JSON, and carry metadata_version "3.0".
    root = make_fake_root(tmp_path)

    # Green path (real runtime under the venv interpreter).
    green = run_gate("--root", str(root))
    assert green.returncode == 0, green.stderr
    assert "metadata_version" in green.stdout
    assert "3.0" in green.stdout

    # Red path: a shadowing fake runtime that reports the wrong
    # metadata_version must turn the gate red.
    fake_pkg = tmp_path / "fakelib" / "transon_authoring"
    fake_pkg.mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text("", encoding="utf-8")
    (fake_pkg / "__main__.py").write_text(
        textwrap.dedent(
            """\
            import json
            print(json.dumps({"metadata_version": "9.9"}))
            """
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path / "fakelib")
    red = run_gate("--root", str(root), env=env)
    assert red.returncode == 1
    assert "metadata_version" in red.stderr


def test_ac007_gate_covers_idempotent_uninstall(tmp_path: Path):
    # AC-007 / FR-019 — the green rehearsal exercises idempotent re-install
    # and the three uninstall behaviors (clean removal, stray preservation,
    # manifest-less no-op) for every tool/scope combo.
    root = make_fake_root(tmp_path)
    result = run_gate("--root", str(root))
    assert result.returncode == 0, result.stderr
    for combo in ("claude/project", "claude/personal", "cursor/project"):
        for check in (
            "re-install idempotent",
            "uninstall removes the clean destination",
            "stray file survives",
            "uninstall without manifest is a no-op",
        ):
            assert f"{combo}: {check}" in result.stdout, (combo, check)


def test_ac009_no_discoverability_claim_in_output(tmp_path: Path):
    # AC-009 / FR-019 (§16 risk) — the gate never claims host
    # "discoverability"; the word appears only as "discoverability
    # precondition(s)" (OQ-010 wording).
    root = make_fake_root(tmp_path)
    result = run_gate("--root", str(root))
    assert result.returncode == 0, result.stderr
    output = result.stdout + result.stderr
    assert "discoverability precondition" in output
    assert re.findall(r"discoverability(?! precondition)", output) == []
