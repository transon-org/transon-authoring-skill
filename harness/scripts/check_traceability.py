#!/usr/bin/env python3
"""Traceability consistency checker for the Transon Authoring Skill.

Keeps requirement IDs consistent across the contract docs, the traceability matrix,
and the code/tests (SPEC §12, §17):

1. No dead IDs — every FR/NFR/AC/UC/AD/OQ referenced in ``docs/traceability.md`` or in
   code/tests must be defined in a contract doc (see CONTRACT_DOCS).
2. No deprecated IDs cited by code/tests.
3. Coverage — any FR/NFR/AC marked done (``[x]``) in ``docs/traceability.md`` must have
   at least one test citing its ID.

Pure stdlib, Python 3.9+, no project imports. Run:

  python3 harness/scripts/check_traceability.py

Exit 0 when consistent, 1 otherwise. Check (3) becomes meaningful once tests exist.
Also importable: ``check()`` returns the list of problems.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Set

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = PROJECT_ROOT / "docs"

# Accept the compact slash-separated citation form too (e.g. "AC-005/007/009"),
# same semantics as check_append_only_ids.py.
ID_RE = re.compile(r"\b(FR|NFR|AC|UC|AD|OQ)-(\d+(?:/\d+)*)\b")
CONTRACT_DOCS = ("SPEC.md", "ARCHITECTURE.md", "ROADMAP.md")
CONTRACT_DESC = "the contract docs (SPEC.md / ARCHITECTURE.md / ROADMAP.md)"
# Product-code directories per ARCHITECTURE §10 (evals/ holds fixtures that may cite ACs).
CODE_DIRS = ("src", "tests", "scripts", "evals", "install", "adapters")
CODE_EXTS = (".py",)
COVERAGE_FAMILIES = {"FR", "NFR", "AC"}
DONE_ROW = re.compile(r"^\|.*\|\s*\[x\]\s*\|", re.IGNORECASE)


def _ids(text: str) -> Set[str]:
    return {
        f"{m.group(1)}-{number}"
        for m in ID_RE.finditer(text)
        for number in m.group(2).split("/")
    }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore") if path.exists() else ""


def defined_ids() -> Set[str]:
    return _ids("\n".join(_read(DOCS / name) for name in CONTRACT_DOCS))


def deprecated_ids() -> Set[str]:
    found: Set[str] = set()
    for name in CONTRACT_DOCS:
        for line in _read(DOCS / name).splitlines():
            if "deprecated" in line.lower():
                found |= _ids(line)
    return found


TEST_DIR_NAMES = {"test", "tests"}


def _is_test_path(rel: str) -> bool:
    """A file counts as a test when it lives under a test/tests directory or is test_*.py / *_test.py."""
    path = Path(rel)
    return (
        any(part in TEST_DIR_NAMES for part in path.parts)
        or path.name.startswith("test_")
        or path.name.endswith("_test.py")
    )


# Generated/vendored trees — never scanned (speed + no spurious ID matches).
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "node_modules",
}


def code_id_refs() -> Dict[str, List[str]]:
    refs: Dict[str, List[str]] = {}
    for directory in CODE_DIRS:
        base = PROJECT_ROOT / directory
        if not base.exists():
            continue
        # os.walk so excluded trees are pruned before descent (rglob would still traverse them).
        for root, dirnames, filenames in os.walk(base):
            dirnames[:] = [d for d in dirnames if d not in EXCLUDED_DIR_NAMES]
            for filename in filenames:
                path = Path(root, filename)
                if path.suffix in CODE_EXTS:
                    for ident in _ids(_read(path)):
                        refs.setdefault(ident, []).append(str(path.relative_to(PROJECT_ROOT)))
    return refs


def test_id_refs(code_refs: Dict[str, List[str]]) -> Dict[str, List[str]]:
    """Test-scoped subset of ``code_refs`` — the coverage gate (3) must only accept test citations."""
    refs: Dict[str, List[str]] = {}
    for ident, paths in code_refs.items():
        tests = [p for p in paths if _is_test_path(p)]
        if tests:
            refs[ident] = tests
    return refs


def traceability_done_ids() -> Set[str]:
    done: Set[str] = set()
    for line in _read(DOCS / "traceability.md").splitlines():
        if DONE_ROW.match(line):
            done |= _ids(line)
    return done


def check() -> List[str]:
    problems: List[str] = []
    defined = defined_ids()
    if not defined:
        return ["no requirement IDs found in docs/ — are the contract docs present?"]

    deprecated = deprecated_ids()
    trace_ids = _ids(_read(DOCS / "traceability.md"))
    code_refs = code_id_refs()

    for ident in sorted(trace_ids - defined):
        problems.append(
            f"{ident}: referenced in docs/traceability.md but not defined in "
            f"{CONTRACT_DESC}"
        )

    for ident in sorted(set(code_refs) - defined):
        where = ", ".join(sorted(set(code_refs[ident]))[:3])
        problems.append(
            f"{ident}: cited in code/tests ({where}) but not defined in "
            f"{CONTRACT_DESC}"
        )

    for ident in sorted(set(code_refs) & deprecated):
        where = ", ".join(sorted(set(code_refs[ident]))[:3])
        problems.append(f"{ident}: cited in code/tests ({where}) but marked deprecated")

    test_refs = test_id_refs(code_refs)
    for ident in sorted(traceability_done_ids()):
        if ident.split("-")[0] in COVERAGE_FAMILIES and ident not in test_refs:
            problems.append(
                f"{ident}: marked done ([x]) in docs/traceability.md but no test cites it"
            )

    return problems


def main() -> int:
    problems = check()
    if problems:
        print(f"traceability: {len(problems)} issue(s):")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print("traceability: consistent.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
