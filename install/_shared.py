"""Shared install/uninstall mechanics for ``install/claude.py`` and
``install/cursor.py`` (FR-015, FR-016, NFR-008, NFR-009, SPEC §11.9).

Runs standalone from a repo checkout or release archive: stdlib-only, never
imports from ``scripts/`` or ``src/``, and never runs ``pip`` (OQ-020) — the
runtime package is installed separately (``pip install transon-authoring``).

Strategy per §11.9: **copy** the adapter-listed files (never symlink) into the
tool's skill directory under the target project root (``--target-root``;
default: the source checkout) and record ``.install-manifest.json`` listing
owned paths + versions. Upgrade = re-run install (idempotent replace of owned
files). Uninstall deletes only manifest paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Optional

MANIFEST_NAME = ".install-manifest.json"
SKILL_DIR_NAME = "transon-authoring"

# Textual pyproject parses on purpose: no ``tomllib`` — the Python floor is
# 3.10 (OQ-019). Pin anchored to the ``dependencies`` line, same as
# ``src/transon_authoring/_snapshot.py`` (not imported: install/ ships alone).
_PIN_RE = re.compile(
    r"^dependencies\s*=\s*\[[^\]]*[\"']transon==([0-9A-Za-z.!+*-]+)[\"']",
    re.MULTILINE,
)
_VERSION_RE = re.compile(r"^version\s*=\s*[\"']([^\"']+)[\"']", re.MULTILINE)


def _canonical_bytes(obj: Any) -> bytes:
    """Deterministic JSON byte form (repo canonical style): sorted keys,
    2-space indent, newline-terminated — idempotency is tree equality."""
    return (
        json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")


def _fail(prog: str, message: str) -> int:
    print(f"{prog}: {message}", file=sys.stderr)
    return 2


def destination(tool: str, scope: str, target_root: Path, home: Path) -> Path:
    """§11.9 install-destination table. ``<repo>`` there is the **target
    project root** (``--target-root``; default: the source checkout root)."""
    base = target_root if scope == "project" else home
    return base / f".{tool}" / "skills" / SKILL_DIR_NAME


def read_versions(repo_root: Path) -> tuple[Optional[dict], Optional[str]]:
    """NFR-008 triplet inputs from ``pyproject.toml`` — ``(fields, error)``."""
    pyproject = repo_root / "pyproject.toml"
    if not pyproject.is_file():
        return None, f"no pyproject.toml under {repo_root}"
    text = pyproject.read_text(encoding="utf-8")
    version = _VERSION_RE.search(text)
    if version is None:
        return None, f"no [project] version found in {pyproject}"
    pin = _PIN_RE.search(text)
    if pin is None:
        return None, f"no 'transon==<version>' pin found in {pyproject}"
    return {
        "skill_version": version.group(1),
        "engine_pin": f"transon=={pin.group(1)}",
    }, None


def _report(
    prog: str, tool: str, scope: str, action: str, dest: Path, files: list[str]
) -> int:
    print(
        json.dumps(
            {
                "schema_version": "1.0",
                "tool": tool,
                "scope": scope,
                "action": action,
                "dest": str(dest),
                "files": files,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


def _install(
    prog: str, tool: str, scope: str, adapter: dict, repo_root: Path, dest: Path
) -> int:
    versions, error = read_versions(repo_root)
    if error is not None:
        return _fail(prog, error)
    snapshot = repo_root / "resources" / "metadata-snapshot.json"
    if not snapshot.is_file():
        return _fail(prog, f"missing {snapshot}")

    sources: list[tuple[str, bytes]] = []
    for name in adapter["files"]:
        source = repo_root / name
        if not source.is_file():
            return _fail(prog, f"adapter file missing from repo root: {source}")
        sources.append((name, source.read_bytes()))

    dest.mkdir(parents=True, exist_ok=True)
    for name, payload in sources:
        target = dest / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)

    owned = list(adapter["files"]) + [MANIFEST_NAME]
    manifest = {
        "schema_version": "1.0",
        "tool": tool,
        "scope": scope,
        "skill_version": versions["skill_version"],
        "engine_pin": versions["engine_pin"],
        "snapshot_sha256": hashlib.sha256(snapshot.read_bytes()).hexdigest(),
        "files": owned,
    }
    (dest / MANIFEST_NAME).write_bytes(_canonical_bytes(manifest))

    try:
        import transon_authoring  # noqa: F401
    except ImportError:
        # OQ-020: structural install is valid without the runtime — hint only.
        print(
            f"{prog}: hint: the runtime is not importable here; install it "
            "with `pip install transon-authoring`",
            file=sys.stderr,
        )
    return _report(prog, tool, scope, "install", dest, owned)


def _uninstall(prog: str, tool: str, scope: str, dest: Path) -> int:
    manifest_path = dest / MANIFEST_NAME
    if not manifest_path.is_file():
        return _report(prog, tool, scope, "uninstall", dest, [])
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    removed: list[str] = []
    deferred_manifest = False
    for name in manifest["files"]:
        if name == MANIFEST_NAME:
            deferred_manifest = True
            continue
        target = dest / name
        if target.is_file():
            target.unlink()
        removed.append(name)
    if deferred_manifest:
        manifest_path.unlink()
        removed.append(MANIFEST_NAME)

    try:
        dest.rmdir()  # only succeeds when empty — stray user files survive
    except OSError:
        pass
    return _report(prog, tool, scope, "uninstall", dest, removed)


def run(tool: str, argv: Optional[list[str]] = None) -> int:
    prog = f"install/{tool}.py"
    parser = argparse.ArgumentParser(
        prog=prog,
        description=f"Install/uninstall the {SKILL_DIR_NAME} skill files for "
        f"{tool} (SPEC §11.9; FR-015/FR-016). Copies files only; never runs pip.",
    )
    parser.add_argument("--scope", choices=("project", "personal"), default="project")
    parser.add_argument(
        "--repo-root", default=".", help="skill repo checkout root (source files)"
    )
    parser.add_argument(
        "--target-root",
        default=None,
        help="target project root receiving the project-scope install "
        "(default: --repo-root)",
    )
    parser.add_argument("--home", default=None, help="override ~ (personal scope)")
    parser.add_argument("--uninstall", action="store_true")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve()
    target_root = Path(args.target_root).resolve() if args.target_root else repo_root
    home = Path(args.home).resolve() if args.home else Path.home()

    adapter_path = repo_root / "adapters" / tool / "adapter.json"
    if not adapter_path.is_file():
        return _fail(prog, f"missing adapter descriptor: {adapter_path}")
    adapter = json.loads(adapter_path.read_text(encoding="utf-8"))
    if args.scope not in adapter["scopes"]:
        return _fail(
            prog,
            f"scope '{args.scope}' is not supported for {tool} "
            f"(documented exclusion, SPEC §11.9 install table; "
            f"supported: {', '.join(adapter['scopes'])})",
        )

    dest = destination(tool, args.scope, target_root, home)
    if args.uninstall:
        return _uninstall(prog, tool, args.scope, dest)
    return _install(prog, tool, args.scope, adapter, repo_root, dest)
