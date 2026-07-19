"""NFR-007 / AC-005 + NFR-012 / AC-032 — `check_parity` gate.

Parity half (NFR-007 / AC-005): exactly one `SKILL.md` in the shipped surface
(repo root; any adapter-side copy is red), the Claude/Cursor `adapter.json`
files ship the same `files` list, every scope/capability difference is a
documented exclusion (non-empty `reason`) in the narrower adapter, and every
`python -m transon_authoring <sub>` recipe in the shipped files names a real
module subcommand.

Self-sufficiency half (NFR-012 / AC-032): the rendered text of `SKILL.md` and
every file under `adapters/` (HTML comments stripped first — the NFR-012
comment exemption) carries no unshipped repo paths (`docs/`, `harness/`,
`scripts/`, `evals/`, `tests/`, `src/`, `resources/` — sole exact-string
exemption `docs/SPECIFICATION.md`), no `SPEC.md` / `§`-section references,
and no requirement-ID citations.

The gate is run via subprocess so exit codes are observed exactly as CI
would see them. Pure offline text/tree scan — deterministic output.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK = REPO_ROOT / "scripts" / "check_parity.py"

SKILL_BODY = """\
# transon-authoring

<!-- authority: AD-018 / NFR-001 -->

Ground every operator against the engine `docs/SPECIFICATION.md` for the
pinned version. Run `python -m transon_authoring verify --template t.json
--samples s.json` and `python -m transon_authoring metadata` as needed.
"""

CLAUDE_ADAPTER = {
    "schema_version": "1.0",
    "tool": "claude",
    "scopes": ["project", "personal"],
    "files": ["SKILL.md"],
    "exclusions": [],
}

CURSOR_ADAPTER = {
    "schema_version": "1.0",
    "tool": "cursor",
    "scopes": ["project"],
    "files": ["SKILL.md"],
    "exclusions": [
        {
            "capability": "personal scope",
            "reason": "Cursor is project-only in v1 (install table)",
        }
    ],
}


def run_check(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--root", str(root)],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def shipped_tree(tmp_path: Path) -> Path:
    """A minimal green shipped surface: root SKILL.md + both adapters."""
    (tmp_path / "SKILL.md").write_text(SKILL_BODY, encoding="utf-8")
    for tool, adapter in (("claude", CLAUDE_ADAPTER), ("cursor", CURSOR_ADAPTER)):
        adapter_dir = tmp_path / "adapters" / tool
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "adapter.json").write_text(
            json.dumps(adapter, indent=2) + "\n", encoding="utf-8"
        )
        (adapter_dir / "README.md").write_text(
            f"# {tool} adapter\n\nInstalls the canonical root skill file.\n",
            encoding="utf-8",
        )
    return tmp_path


# --- Parity half: NFR-007 / AC-005 ---------------------------------------


def test_ac005_parity_green_on_repo():
    # NFR-007 / AC-005 — the real repo shipped surface passes the gate.
    result = run_check(REPO_ROOT)
    assert result.returncode == 0, result.stderr
    assert "FAIL" not in result.stderr


def test_ac005_fixture_tree_green(shipped_tree: Path):
    # NFR-007 / AC-005 — sanity: the minimal fixture surface is green.
    result = run_check(shipped_tree)
    assert result.returncode == 0, result.stderr


def test_ac005_red_on_adapter_skill_copy(shipped_tree: Path):
    # NFR-007 / AC-005 — a second SKILL.md under adapters/ breaks the
    # single-source rule (exactly one SKILL.md, at the repo root).
    copy = shipped_tree / "adapters" / "claude" / "SKILL.md"
    copy.write_text(SKILL_BODY, encoding="utf-8")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "adapters/claude/SKILL.md" in result.stderr


def test_ac005_red_on_unknown_subcommand_recipe(shipped_tree: Path):
    # NFR-007 / AC-005 — a shipped recipe naming a subcommand outside the
    # module CLI's closed set is red.
    skill = shipped_tree / "SKILL.md"
    skill.write_text(
        skill.read_text(encoding="utf-8")
        + "\nAlso run `python -m transon_authoring frobnicate` daily.\n",
        encoding="utf-8",
    )
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "frobnicate" in result.stderr


def test_ac005_red_on_undocumented_scope_difference(shipped_tree: Path):
    # NFR-007 / AC-005 — Cursor lacks the personal scope; dropping its
    # documented exclusion leaves an undocumented capability difference.
    cursor = shipped_tree / "adapters" / "cursor" / "adapter.json"
    adapter = json.loads(cursor.read_text(encoding="utf-8"))
    adapter["exclusions"] = []
    cursor.write_text(json.dumps(adapter, indent=2) + "\n", encoding="utf-8")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "personal" in result.stderr


def test_ac005_red_on_files_list_mismatch(shipped_tree: Path):
    # NFR-007 / AC-005 — the adapters must ship the same files list.
    claude = shipped_tree / "adapters" / "claude" / "adapter.json"
    adapter = json.loads(claude.read_text(encoding="utf-8"))
    adapter["files"] = ["SKILL.md", "EXTRA.md"]
    claude.write_text(json.dumps(adapter, indent=2) + "\n", encoding="utf-8")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "files" in result.stderr


# --- Self-sufficiency half: NFR-012 / AC-032 -----------------------------


def append_to_skill(root: Path, text: str) -> None:
    skill = root / "SKILL.md"
    skill.write_text(skill.read_text(encoding="utf-8") + text, encoding="utf-8")


def test_ac032_red_on_unshipped_path(shipped_tree: Path):
    # NFR-012 / AC-032 — a reference to an unshipped repo path is red.
    append_to_skill(shipped_tree, "\nSee `harness/skills/hygiene.md` first.\n")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "harness/skills/hygiene.md" in result.stderr


def test_ac032_red_on_other_docs_path(shipped_tree: Path):
    # NFR-012 / AC-032 — the exemption is the exact string
    # docs/SPECIFICATION.md; any other docs/ path trips the lint.
    append_to_skill(shipped_tree, "\nSee docs/traceability.md for status.\n")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "docs/traceability.md" in result.stderr


def test_ac032_red_on_spec_section_ref(shipped_tree: Path):
    # NFR-012 / AC-032 — a `§`-section reference into the (unshipped) spec
    # is red, as is naming SPEC.md itself.
    append_to_skill(shipped_tree, "\nStatuses are listed in §11.5 of SPEC.md.\n")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "§" in result.stderr


def test_ac032_red_on_id_citation_outside_comment(shipped_tree: Path):
    # NFR-012 / AC-032 — requirement-ID citations in rendered text are red.
    append_to_skill(shipped_tree, "\nThis step enforces AD-004 strictly.\n")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "AD-004" in result.stderr


def test_ac032_red_on_id_in_adapter_readme(shipped_tree: Path):
    # NFR-012 / AC-032 — adapter files are scanned too.
    readme = shipped_tree / "adapters" / "cursor" / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nParity per NFR-007.\n",
        encoding="utf-8",
    )
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "NFR-007" in result.stderr


def test_ac032_green_on_specification_md_exemption(shipped_tree: Path):
    # NFR-012 / AC-032 — the engine's own docs/SPECIFICATION.md (external
    # authority) is exempt; § on the same line as SPECIFICATION.md is too.
    append_to_skill(
        shipped_tree,
        "\nConsult §3 of the engine `docs/SPECIFICATION.md` when unsure.\n",
    )
    result = run_check(shipped_tree)
    assert result.returncode == 0, result.stderr


def test_ac032_green_on_id_inside_html_comment(shipped_tree: Path):
    # NFR-012 / AC-032 — the comment exemption: IDs (and anything else)
    # inside <!-- --> markdown comments never trip the lint, including
    # multi-line comment spans.
    append_to_skill(
        shipped_tree,
        "\n<!-- verify gate: AD-004 / AC-013\nsee docs/SPEC.md §11.5 -->\n",
    )
    result = run_check(shipped_tree)
    assert result.returncode == 0, result.stderr


def test_ac032_repo_skill_and_adapters_lint_green():
    # NFR-012 / AC-032 — the real root SKILL.md + adapters/ pass the
    # self-sufficiency lint (shipped surface is standalone).
    result = run_check(REPO_ROOT)
    assert result.returncode == 0, result.stderr


def test_ac032_findings_are_deterministically_ordered(shipped_tree: Path):
    # NFR-012 / AC-032 — findings are sorted by file path then line number
    # (deterministic gate output).
    append_to_skill(shipped_tree, "\nPer AD-004.\nSee tests/fixtures/x.\n")
    readme = shipped_tree / "adapters" / "claude" / "README.md"
    readme.write_text(
        readme.read_text(encoding="utf-8") + "\nPer NFR-012.\n",
        encoding="utf-8",
    )
    first = run_check(shipped_tree)
    second = run_check(shipped_tree)
    assert first.returncode == 1
    assert first.stderr == second.stderr
    lines = [line for line in first.stderr.splitlines() if "FAIL" in line]
    assert len(lines) == 3
    # Sorted by path ("SKILL.md" < "adapters/..." in ASCII), then by line.
    assert "AD-004" in lines[0]
    assert "tests/" in lines[1]
    assert "adapters/claude/README.md" in lines[2]
