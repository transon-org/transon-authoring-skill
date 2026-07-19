#!/usr/bin/env python
"""check-install — install-integrity gate
(FR-019 / NFR-009; AC-007 / AC-009; SPEC §11.9, §13, OQ-010).

An end-to-end install rehearsal, offline and deterministic: the real
``install/claude.py`` / ``install/cursor.py`` scripts run as subprocesses
against a **temp staged copy** of the source root and a temp ``--home`` —
the real ``~`` and the real repo's ``.claude``/``.cursor`` are never touched,
and no ``claude``/``cursor`` binary is invoked.

Per (tool, scope) in {claude/project, claude/personal, cursor/project}:

1. Install: destination matches the §11.9 table; every adapter-listed file
   (including ``SKILL.md``) is byte-identical to the canonical source;
   ``.install-manifest.json`` carries exactly {schema_version, tool, scope,
   skill_version, engine_pin, snapshot_sha256, files} with correct values
   (NFR-008 triplet from ``pyproject.toml`` + snapshot hash).
2. OQ-010 discoverability-precondition lint on the installed ``SKILL.md``:
   frontmatter parses, ``name`` equals the skill directory name, non-empty
   ``description``. This asserts **preconditions only** — no headless
   listing exists, so the gate never claims host discoverability.
3. Re-install → destination tree byte-identical (idempotent upgrade).
4. Uninstall behaviors (AC-007): clean destination fully removed; a stray
   user file survives uninstall (only manifest paths removed, directory
   retained); uninstall without a manifest is a no-op, exit 0.

Plus, once: cursor runtime smoke — ``python -m transon_authoring metadata``
exits 0 and its JSON carries ``metadata_version == "3.0"`` (no
"discovered/ingested" claim, OQ-008).

Exit codes: 0 all green, 1 any finding.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Optional

from _shared import report_failures

PROG = "check-install"
SKILL_DIR_NAME = "transon-authoring"
MANIFEST_NAME = ".install-manifest.json"
COMBOS = (("claude", "project"), ("claude", "personal"), ("cursor", "project"))
MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "tool",
        "scope",
        "skill_version",
        "engine_pin",
        "snapshot_sha256",
        "files",
    }
)

# Textual pyproject parses, same anchors as install/_shared.py (not imported:
# both helper modules are named _shared and install/ ships standalone).
_PIN_RE = re.compile(
    r"^dependencies\s*=\s*\[[^\]]*[\"']transon==([0-9A-Za-z.!+*-]+)[\"']",
    re.MULTILINE,
)
_VERSION_RE = re.compile(r"^version\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)

_FRONTMATTER_LINE_RE = re.compile(r"^([A-Za-z0-9_-]+):\s*(.*)$")


def parse_frontmatter(text: str) -> Optional[dict[str, str]]:
    """Minimal YAML-frontmatter parse (no PyYAML dependency): the block
    between the leading ``---`` lines, ``key: value`` pairs only."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        match = _FRONTMATTER_LINE_RE.match(line)
        if match:
            fields[match.group(1)] = match.group(2).strip()
    return None


def tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def stage_source(root: Path, staged: Path, findings: list[str]) -> Optional[list[str]]:
    """Copy only what the installers read from *root* into the temp *staged*
    root; return the union of adapter ``files`` lists, or None when the
    source tree cannot be rehearsed at all."""
    required = ("SKILL.md", "pyproject.toml", "resources/metadata-snapshot.json")
    missing = [rel for rel in required if not (root / rel).is_file()]
    adapters = root / "adapters"
    if not adapters.is_dir():
        missing.append("adapters/")
    if missing:
        findings.append(
            f"source root {root} is missing {', '.join(sorted(missing))} — "
            "cannot rehearse the install (FR-019)"
        )
        return None

    staged.mkdir(parents=True)
    for rel in required:
        target = staged / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / rel, target)
    shutil.copytree(adapters, staged / "adapters")

    listed: list[str] = []
    for tool, _scope in COMBOS:
        adapter_path = staged / "adapters" / tool / "adapter.json"
        try:
            adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
            files = adapter["files"]
        except (OSError, ValueError, KeyError) as exc:
            findings.append(
                f"adapters/{tool}/adapter.json unusable ({exc}) — cannot "
                "rehearse the install (FR-019)"
            )
            return None
        listed.extend(name for name in files if name not in listed)
    # Copy adapter-listed extras that exist; a listed-but-missing file is
    # left for the installer to fail on (surfaced as a finding).
    for name in listed:
        source = root / name
        target = staged / name
        if source.is_file() and not target.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    return listed


def expected_manifest_values(staged: Path, findings: list[str]) -> Optional[dict]:
    text = (staged / "pyproject.toml").read_text(encoding="utf-8")
    version = _VERSION_RE.search(text)
    pin = _PIN_RE.search(text)
    if version is None or pin is None:
        findings.append(
            "pyproject.toml has no [project] version and/or 'transon==…' pin "
            "— manifest values cannot be checked (NFR-008 / FR-019)"
        )
        return None
    snapshot = (staged / "resources" / "metadata-snapshot.json").read_bytes()
    return {
        "skill_version": version.group(1),
        "engine_pin": f"transon=={pin.group(1)}",
        "snapshot_sha256": hashlib.sha256(snapshot).hexdigest(),
    }


def run_installer(
    installer: Path, staged: Path, home: Path, scope: str, *extra: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [
            sys.executable,
            str(installer),
            "--scope",
            scope,
            "--repo-root",
            str(staged),
            "--home",
            str(home),
            *extra,
        ],
        capture_output=True,
        text=True,
    )


def lint_frontmatter(
    combo: str, dest: Path, findings: list[str], oks: list[str]
) -> None:
    """OQ-010 discoverability-precondition lint (preconditions only — never a
    host-discoverability claim)."""
    text = (dest / "SKILL.md").read_text(encoding="utf-8")
    fields = parse_frontmatter(text)
    before = len(findings)
    if fields is None:
        findings.append(
            f"{combo}: installed SKILL.md has no parseable YAML frontmatter "
            "block (OQ-010 discoverability precondition, AC-009)"
        )
    else:
        name = fields.get("name", "")
        if name != SKILL_DIR_NAME:
            findings.append(
                f"{combo}: frontmatter name {name!r} != skill directory name "
                f"{SKILL_DIR_NAME!r} (OQ-010 discoverability precondition, "
                "AC-009)"
            )
        if not fields.get("description", ""):
            findings.append(
                f"{combo}: frontmatter description missing or empty (OQ-010 "
                "discoverability precondition, AC-009)"
            )
    if len(findings) == before:
        oks.append(
            f"{combo}: SKILL.md frontmatter discoverability preconditions "
            "hold (OQ-010 lint)"
        )


def check_manifest(
    combo: str,
    dest: Path,
    tool: str,
    scope: str,
    listed: list[str],
    expected: Optional[dict],
    findings: list[str],
    oks: list[str],
) -> None:
    manifest_path = dest / MANIFEST_NAME
    if not manifest_path.is_file():
        findings.append(f"{combo}: {MANIFEST_NAME} not written (FR-019)")
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    before = len(findings)
    if set(manifest) != MANIFEST_FIELDS:
        findings.append(
            f"{combo}: manifest field set {sorted(manifest)} != expected "
            f"{sorted(MANIFEST_FIELDS)} (FR-019)"
        )
    checks = {
        "schema_version": "1.0",
        "tool": tool,
        "scope": scope,
        "files": listed + [MANIFEST_NAME],
    }
    if expected is not None:
        checks.update(expected)
    for field, want in checks.items():
        got = manifest.get(field)
        if got != want:
            findings.append(
                f"{combo}: manifest {field} == {got!r}, expected {want!r} "
                "(NFR-008 / FR-019)"
            )
    if len(findings) == before:
        oks.append(f"{combo}: manifest complete and correct (NFR-008 triplet)")


def rehearse(
    tool: str,
    scope: str,
    installer: Path,
    staged: Path,
    home: Path,
    listed: list[str],
    expected: Optional[dict],
    findings: list[str],
    oks: list[str],
) -> None:
    combo = f"{tool}/{scope}"
    base = staged if scope == "project" else home
    dest = base / f".{tool}" / "skills" / SKILL_DIR_NAME

    first = run_installer(installer, staged, home, scope)
    if first.returncode != 0:
        findings.append(
            f"{combo}: install exited {first.returncode} "
            f"({first.stderr.strip() or 'no stderr'}) (FR-019 / AC-009)"
        )
        return
    if not dest.is_dir():
        findings.append(
            f"{combo}: nothing installed at the install-table destination "
            f"{dest} (FR-019)"
        )
        return
    oks.append(f"{combo}: installed at the install-table destination")

    for name in listed:
        if (dest / name).read_bytes() != (staged / name).read_bytes():
            findings.append(
                f"{combo}: installed {name} is not byte-identical to the "
                "canonical source file (FR-019 / AC-009)"
            )
            break
    else:
        oks.append(f"{combo}: installed files byte-identical to canonical")

    check_manifest(combo, dest, tool, scope, listed, expected, findings, oks)
    lint_frontmatter(combo, dest, findings, oks)

    before = tree_bytes(dest)
    second = run_installer(installer, staged, home, scope)
    if second.returncode != 0 or tree_bytes(dest) != before:
        findings.append(
            f"{combo}: re-install is not idempotent (exit {second.returncode}"
            "; destination tree changed) (FR-016 / AC-007)"
        )
        return
    oks.append(f"{combo}: re-install idempotent (byte-identical tree)")

    clean = run_installer(installer, staged, home, scope, "--uninstall")
    if clean.returncode != 0 or dest.exists():
        findings.append(
            f"{combo}: uninstall of a clean install left {dest} behind "
            f"(exit {clean.returncode}) (FR-016 / AC-007)"
        )
        return
    oks.append(f"{combo}: uninstall removes the clean destination")

    if run_installer(installer, staged, home, scope).returncode != 0:
        findings.append(f"{combo}: re-install after uninstall failed (AC-007)")
        return
    stray = dest / "user-note.txt"
    stray.write_text("keep me\n", encoding="utf-8")
    kept = run_installer(installer, staged, home, scope, "--uninstall")
    owned_left = [name for name in listed + [MANIFEST_NAME] if (dest / name).exists()]
    if kept.returncode != 0 or not stray.is_file() or owned_left or not dest.is_dir():
        findings.append(
            f"{combo}: uninstall must remove only manifest paths and keep "
            f"stray user files (exit {kept.returncode}; owned left: "
            f"{owned_left}; stray kept: {stray.is_file()}) (FR-016 / AC-007)"
        )
        return
    oks.append(f"{combo}: stray file survives; only manifest paths removed")

    noop = run_installer(installer, staged, home, scope, "--uninstall")
    removed = json.loads(noop.stdout)["files"] if noop.returncode == 0 else None
    if noop.returncode != 0 or removed != []:
        findings.append(
            f"{combo}: uninstall without a manifest must be a no-op, exit 0 "
            f"(exit {noop.returncode}, removed {removed!r}) (FR-016 / AC-007)"
        )
        return
    oks.append(f"{combo}: uninstall without manifest is a no-op")
    stray.unlink()
    dest.rmdir()


def cursor_smoke(findings: list[str], oks: list[str]) -> None:
    """Runtime smoke only — never a "discovered/ingested" claim (OQ-008)."""
    proc = subprocess.run(
        [sys.executable, "-m", SKILL_DIR_NAME.replace("-", "_"), "metadata"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        findings.append(
            "cursor runtime smoke: `python -m transon_authoring metadata` "
            f"exited {proc.returncode} ({proc.stderr.strip() or 'no stderr'})"
            " — install the runtime with `pip install transon-authoring` "
            "(FR-019 / AC-009)"
        )
        return
    try:
        metadata = json.loads(proc.stdout)
    except ValueError as exc:
        findings.append(
            f"cursor runtime smoke: metadata output is not JSON ({exc}) "
            "(FR-019 / AC-009)"
        )
        return
    version = metadata.get("metadata_version")
    if version != "3.0":
        findings.append(
            f"cursor runtime smoke: metadata_version == {version!r}, "
            "expected '3.0' (FR-019 / AC-009)"
        )
        return
    oks.append(
        "cursor runtime smoke: python -m transon_authoring metadata → "
        "metadata_version 3.0"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_install",
        description="Rehearse skill install/uninstall in temp dirs and fail "
        "on any integrity, idempotency, uninstall, OQ-010 "
        "discoverability-precondition, or runtime-smoke violation "
        "(FR-019 / NFR-009 / AC-007 / AC-009).",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="source root containing SKILL.md, adapters/, pyproject.toml and "
        "resources/metadata-snapshot.json (default: this script's repo)",
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()
    install_dir = Path(__file__).resolve().parents[1] / "install"

    findings: list[str] = []
    oks: list[str] = []
    with tempfile.TemporaryDirectory(prefix="check-install-") as tmp:
        staged = Path(tmp) / "repo"
        home = Path(tmp) / "home"
        home.mkdir()
        listed = stage_source(root, staged, findings)
        if listed is not None:
            expected = expected_manifest_values(staged, findings)
            for tool, scope in COMBOS:
                rehearse(
                    tool,
                    scope,
                    install_dir / f"{tool}.py",
                    staged,
                    home,
                    listed,
                    expected,
                    findings,
                    oks,
                )
        cursor_smoke(findings, oks)

    for line in oks:
        print(f"{PROG}: OK {line}")
    return report_failures(PROG, findings, "finding(s)")


if __name__ == "__main__":
    sys.exit(main())
