#!/usr/bin/env python
"""check-parity — adapter parity + shipped self-sufficiency gate
(NFR-007 / AC-005; NFR-012 / AC-032; SPEC §13).

Pure offline text/tree scan. The text lints cover the shipped surface: the
canonical ``skills/transon-authoring/SKILL.md`` plus every file under
``adapters/``. The single-source rule walks the whole repo tree. Findings
are deterministic — sorted by file path, then line number — and reported on
stderr.

Parity half (NFR-007 / AC-005):

1. Exactly one ``SKILL.md`` in the repo, at the canonical path
   ``skills/transon-authoring/SKILL.md``. Any other file of that name is
   red, except under ``.git/``, ``.venv*/``, ``dist/``, ``build/``,
   ``evals/_runs/`` and the install destinations ``.claude/`` and
   ``.cursor/`` — an installer run against the checkout itself legitimately
   writes a body there.
2. ``adapters/claude/adapter.json`` and ``adapters/cursor/adapter.json``
   both parse; their ``files`` lists are equal; every scope/capability
   difference appears in the narrower adapter's ``exclusions`` with a
   non-empty ``reason`` (documented exclusion), else red.
3. Module-recipe lint: every ``python -m transon_authoring <sub>`` (also
   ``python3 -m``) occurrence names a subcommand from the module CLI's
   closed set (SPEC §11.6), else red.

Self-sufficiency half (NFR-012 / AC-032), applied to rendered text only —
HTML comments (``<!-- … -->``, multi-line-aware) are stripped first (the
NFR-012 comment exemption):

1. Unshipped-path rule: any token under ``docs/``, ``harness/``,
   ``scripts/``, ``evals/``, ``tests/``, ``src/``, or ``resources/`` is red;
   a leading ``./`` does not defeat the rule. There is NO external-file
   exemption — the engine repo's ``docs/SPECIFICATION.md`` is a
   maintainer-only design-time authority (AD-026 authority swap) and is red
   like any other ``docs/`` path. The shipped skill cites the engine's
   Language Reference through the ``language`` module recipe instead.
2. Contract-doc rule: the tokens ``SPEC.md``, ``ARCHITECTURE.md`` and
   ``ROADMAP.md`` are red (never false-positives on ``SPECIFICATION.md``);
   a ``§`` character is always red.
3. ID-citation rule: requirement-ID citations (``FR-``/``NFR-``/``AC-``/
   ``AD-``/``OQ-``/``UC-`` + three digits) in rendered text are red.

Exit codes: 0 all green, 1 any finding.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

from _shared import SKILL_REL, report_failures

#: The module CLI's closed subcommand set (SPEC §11.6). Lives here because
#: the shipped files cannot cite the spec section themselves (NFR-012).
SUBCOMMANDS = frozenset(
    {
        "metadata",
        "examples",
        "language",
        "check-samples",
        "verify",
        "result",
        "validate",
        "dry-run",
        "init-config",
    }
)

#: The canonical shipped body: the one editable ``SKILL.md``, sitting at the
#: plugin-native path so the plugin channel needs no copy of it (FR-037a).
CANONICAL_SKILL_REL = SKILL_REL.as_posix()

#: Directory names pruned from the single-source ``SKILL.md`` walk (AC-005).
#: ``.claude``/``.cursor`` are the install destinations: an installer aimed at
#: the checkout itself writes a body there, and that copy is the installer's
#: output, not a second source.
PRUNED_DIR_NAMES = frozenset({".git", "dist", "build", ".claude", ".cursor"})
PRUNED_DIR_GLOBS = (".venv*",)
#: Pruned only at this exact position, not by bare directory name.
PRUNED_DIR_PATHS = frozenset({"evals/_runs"})

COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
RECIPE_RE = re.compile(r"python3?\s+-m\s+transon_authoring\s+([A-Za-z0-9_-]+)")
# The optional leading `./` alternative keeps repo-relative references red
# even when spelled `./docs/…` (a `./` prefix must not defeat the lint),
# while paths under some other prefix (`foo/docs/…`, `../docs/…`) stay
# unmatched as before.
UNSHIPPED_PATH_RE = re.compile(
    r"(?:(?<![\w/.-])\./|(?<![\w/-]))"
    r"(?:docs|harness|scripts|evals|tests|src|resources)/[\w./-]*"
)
CONTRACT_MD_RE = re.compile(r"\b(?:SPEC|ARCHITECTURE|ROADMAP)\.md\b")
ID_RE = re.compile(r"\b(?:FR|NFR|AC|AD|OQ|UC)-\d{3}\b")


def strip_html_comments(text: str) -> str:
    """Blank out ``<!-- … -->`` spans (multi-line-aware), preserving line
    structure so line numbers keep pointing at the original file."""

    def blank(match: re.Match) -> str:
        return re.sub(r"[^\n]", " ", match.group(0))

    return COMMENT_RE.sub(blank, text)


def scan_recipes(rel: str, text: str, findings: list) -> None:
    """Parity half check 3: unknown module-recipe subcommands (AC-005)."""
    for lineno, line in enumerate(text.splitlines(), 1):
        for match in RECIPE_RE.finditer(line):
            sub = match.group(1)
            if sub not in SUBCOMMANDS:
                findings.append(
                    (
                        rel,
                        lineno,
                        f"unknown module subcommand {sub!r} in recipe "
                        "'python -m transon_authoring …' — not in the module "
                        "CLI's closed set (NFR-007 / AC-005)",
                    )
                )


def scan_self_sufficiency(rel: str, text: str, findings: list) -> None:
    """NFR-012 / AC-032 lint over rendered (comment-stripped) text."""
    rendered = strip_html_comments(text)
    for lineno, line in enumerate(rendered.splitlines(), 1):
        for match in UNSHIPPED_PATH_RE.finditer(line):
            token = match.group(0).rstrip(".")
            if token.startswith("./"):
                token = token[2:]  # normalize `./docs/…` -> `docs/…`
            findings.append(
                (
                    rel,
                    lineno,
                    f"reference to unshipped repo path {token!r} — shipped "
                    "files must be self-sufficient with no repo-path "
                    "references; cite Transon authority through the "
                    "'python -m transon_authoring language' recipe, not "
                    "docs/SPECIFICATION.md (NFR-012 / AC-032)",
                )
            )
        for match in CONTRACT_MD_RE.finditer(line):
            findings.append(
                (
                    rel,
                    lineno,
                    f"reference to {match.group(0)} — the contract docs are "
                    "not shipped with the skill (NFR-012 / AC-032)",
                )
            )
        if "§" in line:
            findings.append(
                (
                    rel,
                    lineno,
                    "'§' section reference in rendered text — spec-section "
                    "citations belong in markdown comments only "
                    "(NFR-012 / AC-032)",
                )
            )
        for match in ID_RE.finditer(line):
            findings.append(
                (
                    rel,
                    lineno,
                    f"requirement-ID citation {match.group(0)!r} in rendered "
                    "text — IDs are allowed only inside <!-- --> comments "
                    "(NFR-012 / AC-032)",
                )
            )


def load_adapter(path: Path, rel: str, findings: list):
    """Parse one adapter.json; append a finding and return None on failure."""
    if not path.is_file():
        findings.append((rel, 0, "missing adapter manifest (NFR-007 / AC-005)"))
        return None
    try:
        adapter = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(adapter, dict):
            raise ValueError("adapter manifest must be a JSON object")
    except (ValueError, UnicodeDecodeError) as exc:
        findings.append((rel, 0, f"adapter manifest does not parse: {exc}"))
        return None
    return adapter


def check_adapter_parity(root: Path, findings: list) -> None:
    """Parity half checks 2: equal files lists + documented exclusions."""
    manifests = {}
    for tool in ("claude", "cursor"):
        rel = f"adapters/{tool}/adapter.json"
        manifests[tool] = load_adapter(root / "adapters" / tool / "adapter.json", rel, findings)
    claude, cursor = manifests["claude"], manifests["cursor"]
    if claude is None or cursor is None:
        return

    files = {}
    for tool, adapter in (("claude", claude), ("cursor", cursor)):
        files[tool] = adapter.get("files")
        if not isinstance(files[tool], list) or not files[tool]:
            findings.append(
                (
                    f"adapters/{tool}/adapter.json",
                    0,
                    "adapter 'files' must be a non-empty list of shipped "
                    "files (NFR-007 / AC-005)",
                )
            )
    both_valid = all(isinstance(v, list) and v for v in files.values())
    if both_valid and files["claude"] != files["cursor"]:
        findings.append(
            (
                "adapters/claude/adapter.json",
                0,
                "adapter 'files' lists differ between claude "
                f"({files['claude']!r}) and cursor "
                f"({files['cursor']!r}) — adapters must ship the same "
                "single-source surface (NFR-007 / AC-005)",
            )
        )

    pairs = (
        ("claude", claude, "cursor", cursor),
        ("cursor", cursor, "claude", claude),
    )
    for narrow_name, narrow, wide_name, wide in pairs:
        narrow_scopes = set(narrow.get("scopes") or [])
        wide_scopes = set(wide.get("scopes") or [])
        exclusions = narrow.get("exclusions") or []
        for scope in sorted(wide_scopes - narrow_scopes):
            documented = any(
                isinstance(entry, dict)
                and scope in str(entry.get("capability", ""))
                and str(entry.get("reason", "")).strip()
                for entry in exclusions
            )
            if not documented:
                findings.append(
                    (
                        f"adapters/{narrow_name}/adapter.json",
                        0,
                        f"scope {scope!r} is present in the {wide_name} "
                        f"adapter but absent here without a documented "
                        "exclusion (capability + non-empty reason) "
                        "(NFR-007 / AC-005)",
                    )
                )


def is_pruned(rel_dir: str) -> bool:
    """True for a repo-relative directory path outside the AC-005 walk."""
    if rel_dir in PRUNED_DIR_PATHS:
        return True
    name = rel_dir.rsplit("/", 1)[-1]
    return name in PRUNED_DIR_NAMES or any(
        fnmatch.fnmatch(name, glob) for glob in PRUNED_DIR_GLOBS
    )


def find_skill_bodies(root: Path) -> list[str]:
    """Repo-relative paths of every ``SKILL.md`` in the walked tree (AC-005)."""
    found: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root):
        rel_dir = Path(dirpath).relative_to(root).as_posix()
        prefix = "" if rel_dir == "." else f"{rel_dir}/"
        dirnames[:] = [
            name for name in dirnames if not is_pruned(f"{prefix}{name}")
        ]
        if "SKILL.md" in filenames:
            found.append(f"{prefix}SKILL.md")
    return found


def check_single_source(root: Path, findings: list) -> None:
    """Parity half check 1: the canonical body exists and is the only one."""
    if not (root / SKILL_REL).is_file():
        findings.append(
            (
                CANONICAL_SKILL_REL,
                0,
                f"missing {CANONICAL_SKILL_REL} — the single shipped skill "
                "body lives at that canonical path (NFR-007 / AC-005)",
            )
        )
    for rel in find_skill_bodies(root):
        if rel == CANONICAL_SKILL_REL:
            continue
        if rel == "SKILL.md":
            where = "second SKILL.md at the repo root"
        elif rel.startswith("adapters/"):
            where = (
                "adapter-side SKILL.md copy — adapters share the ONE "
                "canonical body, never a fork"
            )
        else:
            where = f"second SKILL.md at {rel}"
        findings.append(
            (
                rel,
                0,
                f"{where} — the one body lives at {CANONICAL_SKILL_REL} and "
                "is never copied (NFR-007 / AC-005)",
            )
        )


def scan(root: Path) -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []

    skill_path = root / SKILL_REL
    check_single_source(root, findings)

    adapters_dir = root / "adapters"
    adapter_files: list[Path] = []
    if adapters_dir.is_dir():
        adapter_files = sorted(
            path for path in adapters_dir.rglob("*") if path.is_file()
        )
    else:
        findings.append(
            ("adapters", 0, "missing adapters/ directory (NFR-007 / AC-005)")
        )

    # Parity check 2: adapter manifests agree or document exclusions.
    if adapters_dir.is_dir():
        check_adapter_parity(root, findings)

    # Per-file text scans: recipe lint (parity 3) + NFR-012 lint.
    scanned = ([skill_path] if skill_path.is_file() else []) + adapter_files
    for path in scanned:
        rel = path.relative_to(root).as_posix()
        try:
            text = path.read_bytes().decode("utf-8")
        except UnicodeDecodeError as exc:
            findings.append((rel, 0, f"not valid UTF-8 text: {exc}"))
            continue
        scan_recipes(rel, text, findings)
        scan_self_sufficiency(rel, text, findings)

    return sorted(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_parity",
        description="Fail on adapter parity violations (NFR-007 / AC-005) or "
        "shipped-skill self-sufficiency violations (NFR-012 / AC-032).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help=f"repo root containing {CANONICAL_SKILL_REL} and adapters/ "
        "(default: this script's repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()

    messages = [
        f"{rel}:{lineno}: {message}" if lineno else f"{rel}: {message}"
        for rel, lineno, message in scan(root)
    ]
    return report_failures("check-parity", messages, "finding(s)")


if __name__ == "__main__":
    sys.exit(main())
