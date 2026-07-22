#!/usr/bin/env python
"""check-install — install-integrity gate
(FR-019 / NFR-009; AC-007 / AC-009; FR-037a / AC-040; FR-038 / AC-041;
NFR-008 / AC-042; SPEC §11.9, §13, OQ-010).

An end-to-end install rehearsal, offline and deterministic: the real
``install/claude.py`` / ``install/cursor.py`` scripts run as subprocesses
against a **temp staged copy** of the source root and a temp ``--home`` —
the real ``~`` and the real repo's ``.claude``/``.cursor`` are never touched,
and no ``claude``/``cursor`` binary is invoked.

Per (tool, scope) in {claude/project, claude/personal, cursor/project,
cursor/personal}:

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

Plus, once, on the real ``--root``: the FR-037a plugin tree — a repo artifact
outside the install-manifest regime, so it is checked in place, not staged.
``.claude-plugin/plugin.json`` and ``.claude-plugin/marketplace.json`` are
well-formed and agree with each other, with the skill directory name, and with
the ``pyproject.toml`` project version; the marketplace ``source`` resolves to
the plugin root itself; ``skills/transon-authoring/SKILL.md`` is byte-identical
to the canonical root body and satisfies the OQ-010 preconditions (AC-040).
This claims **packaging integrity only** — never catalog listing or host
discoverability.

Plus, once, on the real ``--root``: the NFR-008 release record — repo-root
``CHANGELOG.md`` exists and its topmost release record entry (headings naming
no release version, and "Unreleased"/"In progress" headings whatever version
they name, are skipped; a tag-style ``v`` prefix is stripped) names the
``pyproject.toml`` project version and states that version's engine pin
(``transon==…``, read textually from ``pyproject.toml``) and the
``snapshot_sha256`` recorded in ``resources/metadata-snapshot.md`` — the
stale-release-record failure (AC-042). This is agreement between the record and
the repo's own sources only: the entry exists before the tag is pushed, so a
green result is never evidence that the version was published, and the ladder
outcomes NFR-008 requires are maintainer prose, not mechanically verified.

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
COMBOS = (
    ("claude", "project"),
    ("claude", "personal"),
    ("cursor", "project"),
    ("cursor", "personal"),
)
PLUGIN_MANIFEST_REL = ".claude-plugin/plugin.json"
MARKETPLACE_REL = ".claude-plugin/marketplace.json"
PLUGIN_SKILL_REL = f"skills/{SKILL_DIR_NAME}/SKILL.md"
CHANGELOG_REL = "CHANGELOG.md"
SNAPSHOT_PROVENANCE_REL = "resources/metadata-snapshot.md"
RUNTIME_PREREQ = "pip install transon-authoring"
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

# Release-record parses (AC-042). Markdown ATX headings only; a heading names a
# release when it carries a dotted version token, optionally tag-style
# ``v``-prefixed as the ``refs/tags/v*`` release trigger writes it (dates are
# dash-separated and never match). Headings that open with "Unreleased" or
# "In progress" are never release entries, whatever version they name.
_HEADING_RE = re.compile(r"^(#{1,6})\s+(\S.*)$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_RELEASE_VERSION_RE = re.compile(r"(?<![\w.])[vV]?(\d+\.\d+(?:\.[0-9A-Za-z.+-]+)?)")
_UNRELEASED_HEADING_RE = re.compile(r"^\W*(unreleased|in[\s-]?progress)", re.IGNORECASE)
_SNAPSHOT_SHA_RE = re.compile(
    r"[\"']snapshot_sha256[\"']\s*:\s*[\"']([0-9a-fA-F]{64})[\"']"
)


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
    combo: str,
    dest: Path,
    findings: list[str],
    oks: list[str],
    ac: str = "AC-009",
) -> None:
    """OQ-010 discoverability-precondition lint (preconditions only — never a
    host-discoverability claim)."""
    text = (dest / "SKILL.md").read_text(encoding="utf-8")
    fields = parse_frontmatter(text)
    before = len(findings)
    if fields is None:
        findings.append(
            f"{combo}: SKILL.md has no parseable YAML frontmatter "
            f"block (OQ-010 discoverability precondition, {ac})"
        )
    else:
        name = fields.get("name", "")
        if name != SKILL_DIR_NAME:
            findings.append(
                f"{combo}: frontmatter name {name!r} != skill directory name "
                f"{SKILL_DIR_NAME!r} (OQ-010 discoverability precondition, "
                f"{ac})"
            )
        if not fields.get("description", ""):
            findings.append(
                f"{combo}: frontmatter description missing or empty (OQ-010 "
                f"discoverability precondition, {ac})"
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


def _nonempty(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _load_manifest(root: Path, rel: str, findings: list[str]) -> Optional[dict]:
    path = root / rel
    if not path.is_file():
        findings.append(f"plugin: {rel} is missing under {root} (AC-040)")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        findings.append(f"plugin: {rel} does not parse ({exc}) (AC-040)")
        return None
    if not isinstance(data, dict):
        findings.append(f"plugin: {rel} is not a JSON object (AC-040)")
        return None
    return data


def check_plugin_manifest(
    root: Path, findings: list[str], oks: list[str]
) -> Optional[str]:
    """AC-040(a). Returns the declared plugin name (for the marketplace
    cross-check), or None when the manifest is unusable."""
    data = _load_manifest(root, PLUGIN_MANIFEST_REL, findings)
    if data is None:
        return None
    before = len(findings)
    for field in ("name", "description", "version"):
        if not _nonempty(data.get(field)):
            findings.append(
                f"plugin: {PLUGIN_MANIFEST_REL} {field} is missing or empty "
                "(AC-040)"
            )
    name = data.get("name")
    if _nonempty(name) and name != SKILL_DIR_NAME:
        findings.append(
            f"plugin: {PLUGIN_MANIFEST_REL} name {name!r} != skill directory "
            f"name {SKILL_DIR_NAME!r} (AC-040)"
        )
    description = data.get("description")
    if _nonempty(description) and RUNTIME_PREREQ not in description:
        findings.append(
            f"plugin: {PLUGIN_MANIFEST_REL} description does not contain the "
            f"literal runtime prerequisite {RUNTIME_PREREQ!r} (OQ-029 / AC-040)"
        )
    version = data.get("version")
    pyproject = root / "pyproject.toml"
    project_version = None
    if pyproject.is_file():
        match = _VERSION_RE.search(pyproject.read_text(encoding="utf-8"))
        project_version = match.group(1) if match else None
    if project_version is None:
        findings.append(
            f"plugin: no [project] version in {pyproject} — the "
            f"{PLUGIN_MANIFEST_REL} version cannot be checked (AC-040)"
        )
    elif _nonempty(version) and version != project_version:
        findings.append(
            f"plugin: {PLUGIN_MANIFEST_REL} version {version!r} != "
            f"pyproject.toml project version {project_version!r} (AC-040)"
        )
    if len(findings) == before:
        oks.append(
            f"plugin: {PLUGIN_MANIFEST_REL} names {SKILL_DIR_NAME} at the "
            "project version, with the pip-install prerequisite in its "
            "description"
        )
    return name if isinstance(name, str) else None


def check_marketplace(
    root: Path, plugin_name: Optional[str], findings: list[str], oks: list[str]
) -> None:
    """AC-040(b)."""
    data = _load_manifest(root, MARKETPLACE_REL, findings)
    if data is None:
        return
    before = len(findings)
    if not _nonempty(data.get("name")):
        findings.append(
            f"plugin: {MARKETPLACE_REL} name is missing or empty (AC-040)"
        )
    owner = data.get("owner")
    if not (_nonempty(owner) or (isinstance(owner, dict) and _nonempty(owner.get("name")))):
        findings.append(
            f"plugin: {MARKETPLACE_REL} owner is missing or empty — expected a "
            "non-empty string or an object with a non-empty name (AC-040)"
        )
    wanted = plugin_name or SKILL_DIR_NAME
    plugins = data.get("plugins")
    entries = (
        [e for e in plugins if isinstance(e, dict) and e.get("name") == wanted]
        if isinstance(plugins, list)
        else []
    )
    if not entries:
        findings.append(
            f"plugin: {MARKETPLACE_REL} has no plugins[] entry named "
            f"{wanted!r} (AC-040)"
        )
    else:
        source = entries[0].get("source")
        if not _nonempty(source):
            findings.append(
                f"plugin: {MARKETPLACE_REL} entry {wanted!r} has source "
                f"{source!r}; this gate resolves local path sources only "
                "(AC-040)"
            )
        else:
            target = (root / source).resolve()
            complete = (target / PLUGIN_MANIFEST_REL).is_file() and (
                target / PLUGIN_SKILL_REL
            ).is_file()
            if target != root.resolve() or not complete:
                findings.append(
                    f"plugin: {MARKETPLACE_REL} entry source {source!r} "
                    f"resolves to {target}, not to the plugin root {root} "
                    f"carrying {PLUGIN_MANIFEST_REL} and {PLUGIN_SKILL_REL} "
                    "(AC-040)"
                )
    if len(findings) == before:
        oks.append(
            f"plugin: {MARKETPLACE_REL} entry {wanted} points at the plugin "
            "root itself"
        )


def check_plugin_skill(root: Path, findings: list[str], oks: list[str]) -> None:
    """AC-040(c) + (d)."""
    canonical = root / "SKILL.md"
    copy = root / PLUGIN_SKILL_REL
    if not canonical.is_file():
        findings.append(
            f"plugin: no canonical SKILL.md under {root} to compare the "
            "generated plugin body against (AC-040)"
        )
        return
    if not copy.is_file():
        findings.append(
            f"plugin: {PLUGIN_SKILL_REL} is missing — regenerate it with "
            "`python3 scripts/sync_plugin.py` (AC-040)"
        )
        return
    if copy.read_bytes() != canonical.read_bytes():
        findings.append(
            f"plugin: {PLUGIN_SKILL_REL} is not byte-identical to the "
            "canonical root SKILL.md — regenerate it with "
            "`python3 scripts/sync_plugin.py` (NFR-007 / AC-040)"
        )
        return
    oks.append(
        f"plugin: {PLUGIN_SKILL_REL} byte-identical to the canonical root "
        "SKILL.md"
    )
    lint_frontmatter("plugin", copy.parent, findings, oks, ac="AC-040")


def check_plugin(root: Path, findings: list[str], oks: list[str]) -> None:
    """AC-040 — packaging integrity of the FR-037a plugin tree at the real
    repo root (a repo artifact, never staged and never installed). Packaging
    integrity only: no claim about host discovery."""
    plugin_name = check_plugin_manifest(root, findings, oks)
    check_marketplace(root, plugin_name, findings, oks)
    check_plugin_skill(root, findings, oks)


def find_release_entry(text: str) -> Optional[tuple[str, str]]:
    """Return ``(version, entry_text)`` for the topmost heading naming a
    release version, or None when no heading names one. Headings above it that
    name no version, and headings that open with "Unreleased" / "In progress"
    (whatever version token they carry — a heading saying the release has not
    happened is never a release entry, AC-042), are skipped. The entry runs
    until the next heading at the same or a higher level. Fenced blocks are not
    scanned for headings. A tag-style leading ``v``/``V`` is stripped from the
    version token, since the release trigger is ``refs/tags/v*``."""
    lines = text.splitlines()
    fenced = False
    for index, line in enumerate(lines):
        if _FENCE_RE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = _HEADING_RE.match(line)
        if heading is None:
            continue
        title = heading.group(2)
        if _UNRELEASED_HEADING_RE.match(title):
            continue
        version = _RELEASE_VERSION_RE.search(title)
        if version is None:
            continue
        level = len(heading.group(1))
        end = len(lines)
        inner_fence = False
        for offset in range(index + 1, len(lines)):
            if _FENCE_RE.match(lines[offset]):
                inner_fence = not inner_fence
                continue
            if inner_fence:
                continue
            following = _HEADING_RE.match(lines[offset])
            if following is not None and len(following.group(1)) <= level:
                end = offset
                break
        return version.group(1), "\n".join(lines[index:end])
    return None


def check_release_record(root: Path, findings: list[str], oks: list[str]) -> None:
    """AC-042 — the repo-root release record carries the NFR-008 version
    triplet. Asserts agreement with the repo's own sources of truth only —
    never that the version was published; the ladder outcomes NFR-008 requires
    are maintainer prose, unverified here."""
    path = root / CHANGELOG_REL
    if not path.is_file():
        findings.append(
            f"release: {CHANGELOG_REL} is missing under {root} — every release "
            "is recorded there (NFR-008 / AC-042)"
        )
        return
    entry = find_release_entry(path.read_text(encoding="utf-8"))
    if entry is None:
        findings.append(
            f"release: no heading in {CHANGELOG_REL} names a release version — "
            "unreleased/in-progress headings alone are not a release record "
            "(NFR-008 / AC-042)"
        )
        return
    version, body = entry

    before = len(findings)
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8") if pyproject.is_file() else ""
    project_version = _VERSION_RE.search(text)
    pin = _PIN_RE.search(text)
    if project_version is None or pin is None:
        findings.append(
            f"release: no [project] version and/or 'transon==…' pin in "
            f"{pyproject} — the {CHANGELOG_REL} entry cannot be checked "
            "(NFR-008 / AC-042)"
        )
    else:
        if version != project_version.group(1):
            findings.append(
                f"release: topmost {CHANGELOG_REL} entry names {version!r}, "
                f"but the pyproject.toml project version is "
                f"{project_version.group(1)!r} — stale release record "
                "(NFR-008 / AC-042)"
            )
        expected_pin = f"transon=={pin.group(1)}"
        if expected_pin not in body:
            findings.append(
                f"release: the {CHANGELOG_REL} {version} entry does not state "
                f"the engine pin {expected_pin!r} from pyproject.toml — stale "
                "release record (NFR-008 / AC-042)"
            )

    provenance = root / SNAPSHOT_PROVENANCE_REL
    snapshot = (
        _SNAPSHOT_SHA_RE.search(provenance.read_text(encoding="utf-8"))
        if provenance.is_file()
        else None
    )
    if snapshot is None:
        findings.append(
            f"release: no snapshot_sha256 recorded in {provenance} — the "
            f"{CHANGELOG_REL} entry cannot be checked (NFR-008 / AC-042)"
        )
    elif snapshot.group(1) not in body:
        findings.append(
            f"release: the {CHANGELOG_REL} {version} entry does not state the "
            f"snapshot hash {snapshot.group(1)} from {SNAPSHOT_PROVENANCE_REL} "
            "— stale release record (NFR-008 / AC-042)"
        )

    if len(findings) == before:
        oks.append(
            f"release: {CHANGELOG_REL} topmost release record entry {version} "
            "agrees with the repo's sources — project version, engine pin and "
            "snapshot hash (NFR-008 triplet); source agreement only, not "
            "evidence that this version was published"
        )


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
        "discoverability-precondition, runtime-smoke, plugin-packaging or "
        "release-record violation (FR-019 / NFR-009 / AC-007 / AC-009 / "
        "AC-040 / AC-042).",
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
    check_plugin(root, findings, oks)
    check_release_record(root, findings, oks)

    for line in oks:
        print(f"{PROG}: OK {line}")
    return report_failures(PROG, findings, "finding(s)")


if __name__ == "__main__":
    sys.exit(main())
