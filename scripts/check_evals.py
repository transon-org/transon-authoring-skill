#!/usr/bin/env python
"""check-evals — eval gate for the committed corpus under ``evals/``
(NFR-010 / NFR-011 / AC-025; SPEC §11.8, §13, §15 OQ-017e).

This file currently implements only the ``--lint`` mode: the NFR-011 fixture
privacy lint that per-PR CI runs (OQ-017e; the §13 check_evals row carries
this lint). It is credential-free, engine-free and deterministic. The full
eval-run mode (provider tool loop via scripts/eval_harness.py, FR-017) lands
separately; invoking without ``--lint`` exits 2 until then.

Lint checks (every failure names the offending file, all reported on stderr):

1. ``evals/runner.json`` / ``targets.json`` / ``baseline.json`` exist and pass
   full §11.0 ingress against their bundled schemas (AD-020).
2. Every ``evals/cases/*.json`` validates against the bundled
   ``eval_fixture.json`` schema; the fixture ``id`` equals the filename stem;
   ids are unique across the corpus.
3. Every ``baseline.json`` ``passing`` id references an existing fixture id
   (OQ-016f — no dangling baseline entries).
4. Fixtures carrying ``samples``: ``check_samples(samples)`` must report
   ``ok_for_verify: true`` (FR-027; the harness hands the SampleSet straight
   to the skill under test, OQ-017a).
5. Privacy invariants (NFR-011 / FR-018): ``consent`` present ⇒
   ``redacted: true``; ``redacted: false`` is allowed only for synthetic
   fixtures (no ``consent``).
6. Best-effort secret scan over each fixture's raw bytes against
   ``SECRET_PATTERNS`` (AWS access key ids, private-key PEM headers, GitHub
   tokens, ``sk-…`` API keys, JWT-looking payloads); any hit is red.

Exit codes: 0 lint green, 1 any lint failure, 2 usage (full-run mode not yet
implemented).
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from transon_authoring import check_samples
    from transon_authoring._ingress import IngressError, load_document
except ImportError:  # pragma: no cover - source-checkout fallback (SPEC §10)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from transon_authoring import check_samples
    from transon_authoring._ingress import IngressError, load_document

#: Committed eval-policy files and their bundled schemas (AD-020, §11.8).
POLICY_FILES = (
    ("runner.json", "eval_runner.json"),
    ("targets.json", "eval_targets.json"),
    ("baseline.json", "eval_baseline.json"),
)

#: Best-effort secret patterns scanned over raw fixture bytes (NFR-011 /
#: AC-025). Fixed list of obvious credential shapes — a red hit is always a
#: lint failure; absence of hits is necessary, not sufficient (human privacy
#: review still applies per FR-018).
SECRET_PATTERNS: tuple[tuple[str, re.Pattern[bytes]], ...] = (
    ("AWS access key id", re.compile(rb"AKIA[0-9A-Z]{16}")),
    ("private-key PEM header", re.compile(rb"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("GitHub personal access token", re.compile(rb"ghp_[A-Za-z0-9]{36}")),
    ("sk- API key", re.compile(rb"sk-[A-Za-z0-9\-_]{20,}")),
    ("JWT-looking token", re.compile(rb"eyJ[A-Za-z0-9_-]+\.eyJ")),
)


def lint_evals(repo_root: Path, verbose: bool = False) -> list[str]:
    """Run the NFR-011 fixture lint over ``<repo_root>/evals``; return the
    (possibly empty) list of failure messages, each naming the offending file.

    Engine-free and deterministic (no network, no provider credentials); safe
    for per-PR CI (OQ-017e).
    """
    failures: list[str] = []
    evals_dir = repo_root / "evals"

    def note(message: str) -> None:
        if verbose:
            print(f"check-evals: {message}", file=sys.stderr)

    # --- Check 1: policy files exist and validate (AD-020). ----------------
    baseline: dict | None = None
    for file_name, schema_name in POLICY_FILES:
        path = evals_dir / file_name
        if not path.is_file():
            failures.append(f"{path}: missing eval-policy file (SPEC §11.8, AD-020)")
            continue
        try:
            doc = load_document(path, schema_name)
        except IngressError as exc:
            failures.extend(f"{path}: {error['message']}" for error in exc.errors)
            continue
        note(f"policy file OK: {path}")
        if file_name == "baseline.json":
            baseline = doc

    # --- Check 2: every fixture validates; id == stem; ids unique. ---------
    cases_dir = evals_dir / "cases"
    fixture_ids: set[str] = set()
    if not cases_dir.is_dir():
        failures.append(f"{cases_dir}: missing eval cases directory (SPEC §11.8)")
        fixture_paths: list[Path] = []
    else:
        fixture_paths = sorted(cases_dir.glob("*.json"))

    for path in fixture_paths:
        fixture: dict | None = None
        try:
            fixture = load_document(path, "eval_fixture.json")
        except IngressError as exc:
            failures.extend(f"{path}: {error['message']}" for error in exc.errors)
        if fixture is not None:
            fixture_id = fixture["id"]
            if fixture_id != path.stem:
                failures.append(
                    f"{path}: fixture id {fixture_id!r} does not equal the "
                    f"filename stem {path.stem!r} (SPEC §11.8)"
                )
            if fixture_id in fixture_ids:
                failures.append(
                    f"{path}: duplicate fixture id {fixture_id!r} (SPEC §11.8)"
                )
            fixture_ids.add(fixture_id)

            # --- Check 4: supplied SampleSets are ok_for_verify (OQ-017a). -
            if "samples" in fixture:
                check = check_samples(fixture["samples"])
                if not check["ok_for_verify"]:
                    gaps = ", ".join(
                        sorted({gap["code"] for gap in check.get("gaps", [])})
                    )
                    failures.append(
                        f"{path}: samples are not ok_for_verify"
                        f" (gaps: {gaps or 'none reported'}; FR-027 / OQ-017a)"
                    )

            # --- Check 5: consent/redaction invariants (NFR-011). ----------
            if "consent" in fixture and fixture["redacted"] is not True:
                failures.append(
                    f"{path}: consent recorded but redacted is not true — "
                    "real-use fixtures require redaction before commit "
                    "(NFR-011 / FR-018 / AC-025)"
                )

        # --- Check 6: best-effort secret scan over raw bytes (AC-025). -----
        raw = path.read_bytes()
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(raw):
                failures.append(
                    f"{path}: secret scan hit — looks like a {label} "
                    "(NFR-011 / AC-025); redact before committing"
                )
        if fixture is not None:
            note(f"fixture OK: {path}")

    # --- Check 3: baseline ids reference existing fixtures (OQ-016f). ------
    if baseline is not None:
        baseline_path = evals_dir / "baseline.json"
        for dangling in sorted(set(baseline["passing"]) - fixture_ids):
            failures.append(
                f"{baseline_path}: passing id {dangling!r} has no fixture under "
                f"{cases_dir} (OQ-016f)"
            )

    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_evals",
        description="Eval gate (NFR-010/AD-020). --lint runs the credential-"
        "free NFR-011 fixture privacy lint (AC-025) used by per-PR CI "
        "(OQ-017e); the full eval-run mode lands with FR-017.",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="run only the fixture lint (schema, ids, baseline refs, sample "
        "readiness, consent/redaction, secret scan)",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repo root containing evals/ (default: this script's repo)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="report each file that passed the lint on stderr",
    )
    args = parser.parse_args(argv)

    if not args.lint:
        print(
            "check-evals: full eval run not yet implemented (lands with "
            "FR-017); use --lint for the NFR-011 fixture lint",
            file=sys.stderr,
        )
        return 2

    failures = lint_evals(args.root.resolve(), verbose=args.verbose)
    for message in failures:
        print(f"check-evals: FAIL: {message}", file=sys.stderr)
    if failures:
        print(f"check-evals: {len(failures)} lint failure(s)", file=sys.stderr)
        return 1
    print("check-evals: lint green", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
