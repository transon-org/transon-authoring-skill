"""OQ-027f(iv) / NFR-011 — secret scan over eval episode transcripts.

Before episode transcripts leave the sandbox as a build artifact, scan them for
anything that looks like a leaked credential (SPEC §11.8 transcript privacy).
Reuses the exact ``SECRET_PATTERNS`` the ``check_evals --lint`` fixture scan
uses, so the transcript bar matches the committed-fixture bar. Exit 1 (and name
the file) on any hit; exit 0 when the directory is clean or absent.

Dispatch-only CI tooling (not shipped in the package).
"""

from __future__ import annotations

import sys
from pathlib import Path


def _import_check_evals():
    try:
        import check_evals
    except ImportError:  # pragma: no cover - invoked outside scripts/
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import check_evals
    return check_evals


def scan(directory: Path) -> list[str]:
    """Return a list of ``"<file>: <label>"`` hits over every file under
    *directory* (recursively). Empty when clean or the directory is missing."""
    patterns = _import_check_evals().SECRET_PATTERNS
    hits: list[str] = []
    if not directory.is_dir():
        return hits
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        raw = path.read_bytes()
        for label, pattern in patterns:
            if pattern.search(raw):
                hits.append(f"{path}: looks like a {label}")
    return hits


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        print("usage: scan_transcripts.py <transcripts-dir>", file=sys.stderr)
        return 2
    directory = Path(args[0])
    hits = scan(directory)
    for hit in hits:
        print(f"scan-transcripts: SECRET SCAN HIT: {hit}", file=sys.stderr)
    if hits:
        print(
            f"scan-transcripts: {len(hits)} hit(s) — transcripts withheld "
            "(OQ-027f(iv) / NFR-011)",
            file=sys.stderr,
        )
        return 1
    print(f"scan-transcripts: clean ({directory})", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
