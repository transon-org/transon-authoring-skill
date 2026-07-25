"""NFR-007 / AC-005 + NFR-012 / AC-032 — `check_parity` gate.

Parity half (NFR-007 / AC-005): exactly one `SKILL.md` in the repo tree, at
the canonical `skills/transon-authoring/SKILL.md` — any other copy is red
except under `.git/`, `.venv*/`, `dist/`, `build/`, `evals/_runs/` and the
install destinations `.claude/` and `.cursor/`. Plus: the Claude/Cursor
`adapter.json`
files ship the same `files` list, every scope/capability difference is a
documented exclusion (non-empty `reason`) in the narrower adapter, and every
`python -m transon_authoring <sub>` recipe in the shipped files names a real
module subcommand.

Self-sufficiency half (NFR-012 / AC-032): the rendered text of `SKILL.md` and
every file under `adapters/` (HTML comments stripped first — the NFR-012
comment exemption) carries no unshipped repo paths (`docs/`, `harness/`,
`scripts/`, `evals/`, `tests/`, `src/`, `resources/` — with NO external-file
exemption, so the engine repo's `docs/SPECIFICATION.md` is red like any other
`docs/` path per the AD-026 authority swap), no `SPEC.md` / `§`-section
references (a bare `§` is always red), and no requirement-ID citations.
Transon authority is cited only through `python -m transon_authoring` module
recipes (including the `language` subcommand).

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
SKILL_REL = Path("skills") / "transon-authoring" / "SKILL.md"

SKILL_BODY = """\
# transon-authoring

<!-- authority: AD-018 / NFR-001 -->

Ground every operator against the engine's Language Reference via
`python -m transon_authoring language --section expressions-and-calls`. Run
`python -m transon_authoring verify --template t.json --samples s.json` and
`python -m transon_authoring metadata` as needed.
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
    "scopes": ["project", "personal"],
    "files": ["SKILL.md"],
    "exclusions": [],
}


def run_check(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--root", str(root)],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def shipped_tree(tmp_path: Path) -> Path:
    """A minimal green shipped surface: the canonical SKILL.md + adapters."""
    (tmp_path / SKILL_REL).parent.mkdir(parents=True)
    (tmp_path / SKILL_REL).write_text(SKILL_BODY, encoding="utf-8")
    for tool, adapter in (("claude", CLAUDE_ADAPTER), ("cursor", CURSOR_ADAPTER)):
        adapter_dir = tmp_path / "adapters" / tool
        adapter_dir.mkdir(parents=True)
        (adapter_dir / "adapter.json").write_text(
            json.dumps(adapter, indent=2) + "\n", encoding="utf-8"
        )
        (adapter_dir / "README.md").write_text(
            f"# {tool} adapter\n\nInstalls the canonical skill file.\n",
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
    # single-source rule (exactly one SKILL.md, at the canonical path).
    copy = shipped_tree / "adapters" / "claude" / "SKILL.md"
    copy.write_text(SKILL_BODY, encoding="utf-8")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "adapters/claude/SKILL.md" in result.stderr


def test_ac005_red_on_recreated_root_skill_copy(shipped_tree: Path):
    # NFR-007 / AC-005 — single source is by ABSENCE of a second copy
    # (AD-005 / FR-037a), so a body re-created at the old repo-root path is
    # red; nothing else in the tree would notice it.
    copy = shipped_tree / "SKILL.md"
    copy.write_text(SKILL_BODY, encoding="utf-8")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "second SKILL.md at the repo root" in result.stderr


def test_ac005_red_on_stray_skill_copy_outside_shipped_surface(shipped_tree: Path):
    # NFR-007 / AC-005 — the scan covers the whole repo tree, not just the
    # root and adapters/: a body anywhere else is a second copy and is red.
    for rel in ("docs/SKILL.md", "resources/SKILL.md",
                "skills/transon-authoring-v2/SKILL.md"):
        copy = shipped_tree / rel
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(SKILL_BODY, encoding="utf-8")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    for rel in ("docs/SKILL.md", "resources/SKILL.md",
                "skills/transon-authoring-v2/SKILL.md"):
        assert rel in result.stderr


def test_ac005_green_on_excluded_skill_copies(shipped_tree: Path):
    # NFR-007 / AC-005 — the excluded trees are not false positives: an
    # installer run against the checkout itself writes a body under .claude/
    # and .cursor/, and version-control/build/eval-run trees carry copies of
    # their own.
    for rel in (
        ".claude/skills/transon-authoring/SKILL.md",
        ".cursor/skills/transon-authoring/SKILL.md",
        ".venv/lib/python3.12/site-packages/pkg/SKILL.md",
        ".venv-3.11/lib/pkg/SKILL.md",
        ".git/worktrees/x/SKILL.md",
        "dist/skills/transon-authoring/SKILL.md",
        "build/skills/transon-authoring/SKILL.md",
        "evals/_runs/run-1/SKILL.md",
    ):
        copy = shipped_tree / rel
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(SKILL_BODY, encoding="utf-8")
    result = run_check(shipped_tree)
    assert result.returncode == 0, result.stderr


def test_ac005_red_on_unknown_subcommand_recipe(shipped_tree: Path):
    # NFR-007 / AC-005 — a shipped recipe naming a subcommand outside the
    # module CLI's closed set is red.
    skill = shipped_tree / SKILL_REL
    skill.write_text(
        skill.read_text(encoding="utf-8")
        + "\nAlso run `python -m transon_authoring frobnicate` daily.\n",
        encoding="utf-8",
    )
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "frobnicate" in result.stderr


def test_ac005_red_on_undocumented_scope_difference(shipped_tree: Path):
    # NFR-007 / AC-005 — a narrower adapter is green only while it carries a
    # documented exclusion with a non-empty reason; dropping the exclusion
    # leaves an undocumented capability difference and is red. The narrower
    # adapter is synthetic: the shipped adapters reach equal scopes.
    cursor = shipped_tree / "adapters" / "cursor" / "adapter.json"
    adapter = json.loads(cursor.read_text(encoding="utf-8"))
    adapter["scopes"] = ["project"]
    adapter["exclusions"] = [
        {"capability": "personal scope", "reason": "synthetic narrower adapter"}
    ]
    cursor.write_text(json.dumps(adapter, indent=2) + "\n", encoding="utf-8")
    assert run_check(shipped_tree).returncode == 0

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


def test_ac005_red_on_missing_files_key(shipped_tree: Path):
    # NFR-007 / AC-005 — a missing/empty 'files' key must be red, never a
    # vacuous None == None pass that the installer would crash on.
    for tool in ("claude", "cursor"):
        path = shipped_tree / "adapters" / tool / "adapter.json"
        adapter = json.loads(path.read_text(encoding="utf-8"))
        del adapter["files"]
        path.write_text(json.dumps(adapter, indent=2) + "\n", encoding="utf-8")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert result.stderr.count("non-empty list") == 2


# --- Self-sufficiency half: NFR-012 / AC-032 -----------------------------


def append_to_skill(root: Path, text: str) -> None:
    skill = root / SKILL_REL
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


def test_ac032_red_on_dot_slash_prefixed_unshipped_path(shipped_tree: Path):
    # NFR-012 / AC-032 — a leading `./` must not defeat the unshipped-path
    # lint: `./docs/…` is the same repo-relative reference as `docs/…`.
    # Paths under some other prefix (e.g. `foo/docs/`) stay unmatched.
    append_to_skill(shipped_tree, "\nSee `./docs/notes.md` for details.\n")
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "docs/notes.md" in result.stderr


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


def test_ac032_red_on_specification_md_reference(shipped_tree: Path):
    # NFR-012 / AC-032 / AD-026 — the engine repo's docs/SPECIFICATION.md is a
    # maintainer-only design-time authority, never cited by the shipped skill.
    # A reference to it in rendered text is red like any other docs/ path, and a
    # bare `§` on the same line is red too (no SPECIFICATION.md allowance).
    append_to_skill(
        shipped_tree,
        "\nConsult §3 of the engine `docs/SPECIFICATION.md` when unsure.\n",
    )
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "docs/SPECIFICATION.md" in result.stderr
    assert "§" in result.stderr


def test_ac032_red_on_architecture_and_roadmap_reference(shipped_tree: Path):
    # NFR-012 / AC-032 — the contract spans SPEC.md, ARCHITECTURE.md and
    # ROADMAP.md; none is shipped, so naming any of them in rendered text is
    # red. Bare filenames (no `docs/` prefix) are not caught by the
    # unshipped-path rule, so this exercises the contract-doc rule alone.
    append_to_skill(
        shipped_tree,
        "\nDecisions live in ARCHITECTURE.md and milestones in ROADMAP.md.\n",
    )
    result = run_check(shipped_tree)
    assert result.returncode == 1
    assert "ARCHITECTURE.md" in result.stderr
    assert "ROADMAP.md" in result.stderr


def test_ac032_contract_doc_rule_does_not_match_specification_md(shipped_tree: Path):
    # NFR-012 / AC-032 — widening the contract-doc rule must not make
    # `SPECIFICATION.md` match it. That token is red via the unshipped-path
    # rule when written as `docs/SPECIFICATION.md`; a bare mention is not a
    # contract-doc finding.
    append_to_skill(shipped_tree, "\nThe engine ships SPECIFICATION.md upstream.\n")
    result = run_check(shipped_tree)
    assert result.returncode == 0, result.stderr


def test_ac032_green_on_language_recipe(shipped_tree: Path):
    # NFR-012 / AC-032 / AD-026 — the shipped authority is the engine's
    # Language Reference reached through the `language` module recipe. A body
    # whose only Transon-authority reference is
    # `python -m transon_authoring language --section <id>` lints green, and
    # `language` is a real subcommand in the recipe allowlist.
    append_to_skill(
        shipped_tree,
        "\nDiscover sections with `python -m transon_authoring language "
        "--list-sections`, then ground a specific one with "
        "`python -m transon_authoring language --section context-and-scoping`.\n",
    )
    result = run_check(shipped_tree)
    assert result.returncode == 0, result.stderr

    # `language` is in the module-recipe allowlist (SPEC §11.6 closed set), so
    # the recipe lint does not flag it as an unknown subcommand.
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    import check_parity

    assert "language" in check_parity.SUBCOMMANDS


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
    # NFR-012 / AC-032 — the real canonical SKILL.md + adapters/ pass the
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
    # Sorted by path ("adapters/..." < "skills/..." in ASCII), then by line.
    assert "adapters/claude/README.md" in lines[0]
    assert "AD-004" in lines[1]
    assert "tests/" in lines[2]
