"""FR-019 / NFR-009 (AC-009, AC-007's gate half, AC-040, AC-041) —
scripts/check_install.py.

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
    "transon==0.2.3",
]
"""

SKILL_MD = """\
---
name: transon-authoring
description: Fixture skill body for the install-integrity gate.
---

# transon-authoring (fixture)
"""

PLUGIN_JSON = {
    "name": "transon-authoring",
    "description": "Fixture plugin manifest. Requires the runtime: "
    "pip install transon-authoring.",
    "version": "0.0.1",
}
MARKETPLACE_JSON = {
    "name": "transon-authoring",
    "owner": {"name": "fixture-owner"},
    "plugins": [{"name": "transon-authoring", "source": "./"}],
}


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
    plugin_json: dict | None = None,
    marketplace_json: dict | None = None,
    plugin_skill_md: str | None = None,
    omit: tuple[str, ...] = (),
) -> Path:
    root = tmp_path / name
    files = adapter_files if adapter_files is not None else ["SKILL.md"]
    for tool in ("claude", "cursor"):
        adapter_dir = root / "adapters" / tool
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "adapter.json").write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "tool": tool,
                    "scopes": ["project", "personal"],
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

    plugin_dir = root / ".claude-plugin"
    plugin_dir.mkdir()
    if "plugin.json" not in omit:
        (plugin_dir / "plugin.json").write_text(
            json.dumps(plugin_json if plugin_json is not None else PLUGIN_JSON),
            encoding="utf-8",
        )
    if "marketplace.json" not in omit:
        (plugin_dir / "marketplace.json").write_text(
            json.dumps(
                marketplace_json if marketplace_json is not None else MARKETPLACE_JSON
            ),
            encoding="utf-8",
        )
    if "skill" not in omit:
        plugin_skill_dir = root / "skills" / "transon-authoring"
        plugin_skill_dir.mkdir(parents=True)
        (plugin_skill_dir / "SKILL.md").write_text(
            plugin_skill_md if plugin_skill_md is not None else skill_md,
            encoding="utf-8",
        )
    return root


def test_ac009_gate_green_on_repo():
    # AC-009 / FR-019 / NFR-009 — the shipped repo passes the full rehearsal
    # (all four tool/scope combos + OQ-010 lint + cursor runtime smoke).
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
    for combo in (
        "claude/project",
        "claude/personal",
        "cursor/project",
        "cursor/personal",
    ):
        for check in (
            "re-install idempotent",
            "uninstall removes the clean destination",
            "stray file survives",
            "uninstall without manifest is a no-op",
        ):
            assert f"{combo}: {check}" in result.stdout, (combo, check)


def test_ac041_gate_exercises_cursor_personal_combo():
    # AC-041 / FR-038 — the gate rehearses cursor/personal alongside the other
    # three combos on the shipped repo: install-table destination, canonical
    # bytes, complete manifest, OQ-010 preconditions. Structural only — no
    # claim that Cursor discovered or activated the skill (OQ-008).
    result = run_gate("--root", str(REPO_ROOT))
    assert result.returncode == 0, result.stderr
    for check in (
        "installed at the install-table destination",
        "installed files byte-identical to canonical",
        "manifest complete and correct",
        "SKILL.md frontmatter discoverability preconditions",
    ):
        assert f"cursor/personal: {check}" in result.stdout, check


def test_ac040_plugin_green_on_repo():
    # AC-040 / FR-037a — the shipped repo's plugin tree is structurally sound:
    # both manifests, the version/name agreement, the local marketplace source,
    # and the byte-identical generated SKILL.md.
    result = run_gate("--root", str(REPO_ROOT))
    assert result.returncode == 0, result.stderr
    for check in (
        "plugin: .claude-plugin/plugin.json",
        "plugin: .claude-plugin/marketplace.json",
        "plugin: skills/transon-authoring/SKILL.md",
        "plugin: SKILL.md frontmatter discoverability preconditions",
    ):
        assert check in result.stdout, check


def test_ac040_red_on_missing_plugin_manifest(tmp_path: Path):
    # AC-040(a) — a missing plugin.json is red.
    root = make_fake_root(tmp_path, omit=("plugin.json",))
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert ".claude-plugin/plugin.json" in result.stderr


def test_ac040_red_on_plugin_name_not_skill_dir(tmp_path: Path):
    # AC-040(a) — the plugin `name` must equal the skill directory name.
    root = make_fake_root(
        tmp_path, plugin_json={**PLUGIN_JSON, "name": "some-other-plugin"}
    )
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "some-other-plugin" in result.stderr


def test_ac040_red_on_version_mismatch_with_pyproject(tmp_path: Path):
    # AC-040(a) — plugin.json version must equal the pyproject project version.
    root = make_fake_root(tmp_path, plugin_json={**PLUGIN_JSON, "version": "9.9.9"})
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "9.9.9" in result.stderr
    assert "0.0.1" in result.stderr


def test_ac040_red_on_description_without_pip_install_string(tmp_path: Path):
    # AC-040(a) / OQ-029 — the description carries the runtime prerequisite
    # literally, so an agent reading only the manifest can acquire the runtime.
    root = make_fake_root(
        tmp_path,
        plugin_json={**PLUGIN_JSON, "description": "Fixture plugin manifest."},
    )
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "pip install transon-authoring" in result.stderr


def test_ac040_red_on_missing_marketplace_owner(tmp_path: Path):
    # AC-040(b) — marketplace.json must carry a non-empty owner.
    entry = {k: v for k, v in MARKETPLACE_JSON.items() if k != "owner"}
    root = make_fake_root(tmp_path, marketplace_json=entry)
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "owner" in result.stderr


def test_ac040_red_on_marketplace_source_outside_plugin_root(tmp_path: Path):
    # AC-040(b) — a source pointing anywhere but the plugin root fetches no
    # plugin manifest and no skill body.
    root = make_fake_root(
        tmp_path,
        marketplace_json={
            **MARKETPLACE_JSON,
            "plugins": [{"name": "transon-authoring", "source": "./docs"}],
        },
    )
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "source" in result.stderr
    assert "./docs" in result.stderr


def test_ac040_red_on_non_path_marketplace_source(tmp_path: Path):
    # AC-040(b) — the gate claims local resolution only; a non-string source
    # form (e.g. a github descriptor) is red, not silently accepted.
    root = make_fake_root(
        tmp_path,
        marketplace_json={
            **MARKETPLACE_JSON,
            "plugins": [
                {
                    "name": "transon-authoring",
                    "source": {"source": "github", "repo": "transon-org/x"},
                }
            ],
        },
    )
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "source" in result.stderr


def test_ac040_red_on_single_byte_stale_plugin_skill(tmp_path: Path):
    # AC-040(c) — the stale-regeneration case: one byte of drift is red, and
    # the finding names the regeneration command.
    root = make_fake_root(tmp_path, plugin_skill_md=SKILL_MD + "x")
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "python3 scripts/sync_plugin.py" in result.stderr


def test_ac040_red_on_plugin_skill_frontmatter_precondition(tmp_path: Path):
    # AC-040(d) / OQ-010 — the preconditions are asserted on the plugin copy
    # too. A canonical body without a description turns both the install lint
    # and the plugin lint red.
    root = make_fake_root(
        tmp_path, skill_md="---\nname: transon-authoring\n---\n\n# body\n"
    )
    result = run_gate("--root", str(root))
    assert result.returncode == 1
    assert "plugin: frontmatter description" in result.stderr


def test_ac040_no_catalog_or_discoverability_claim_in_output(tmp_path: Path):
    # AC-040 / FR-037b — packaging integrity only: the gate never claims a
    # catalog listing or host discovery.
    root = make_fake_root(tmp_path)
    result = run_gate("--root", str(root))
    assert result.returncode == 0, result.stderr
    output = (result.stdout + result.stderr).lower()
    for claim in ("catalog", "listed in", "discovered", "installable from"):
        assert claim not in output, claim


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
