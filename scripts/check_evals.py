#!/usr/bin/env python
"""check-evals — eval gate for the committed corpus under ``evals/``
(FR-017 / NFR-010 / NFR-011 / AC-008 / AC-025; SPEC §11.8, §13, §15
OQ-016/OQ-017).

Two modes:

- ``--lint`` — the credential-free NFR-011 fixture privacy lint that per-PR
  CI runs (OQ-017e; the §13 check_evals row carries this lint). Engine-free
  and deterministic.
- default (no ``--lint``) — the full FR-017 red/green eval gate: lint first,
  then run every fixture ``runs_per_fixture`` times through the provider tool
  loop (``scripts/eval_harness.py``), score each episode mechanically
  (OQ-016a/b), aggregate per §11.8 (buckets, infra-excluded denominators with
  the 10% cap, ratchet target, fixture-regression baseline) and print one
  JSON report on stdout. Requires ``ANTHROPIC_API_KEY`` (missing → exit 2).
  ``--update-baseline`` records the passing fixture ids in
  ``evals/baseline.json`` after a green run (OQ-016f).

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

Exit codes: 0 gate/lint green, 1 red gate or any lint failure, 2 config /
credential / policy-file errors.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

try:
    from transon_authoring import check_samples
    from transon_authoring._ingress import (
        IngressError,
        load_document,
        schema_violations,
    )
except ImportError:  # pragma: no cover - source-checkout fallback (SPEC §10)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from transon_authoring import check_samples
    from transon_authoring._ingress import (
        IngressError,
        load_document,
        schema_violations,
    )

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


# --------------------------------------------------------------------------
# FR-017 / NFR-010 / AC-008 — full eval gate: scoring, aggregation, run.
# --------------------------------------------------------------------------

#: Refusal statuses that score refuse-success (OQ-016b). ``schema-error`` and
#: a missing/invalid submission are refuse-*failures*, never infra.
REFUSE_STATUSES = frozenset(
    {
        "need-samples",
        "deferred",
        "aborted",
        "samples-rejected",
        "verify-failed",
        "repair-exhausted",
        "profile-rejected",
    }
)

#: Bucket per fixture ``expect`` (SPEC §11.8): matched → authoring rate,
#: refuse → adversarial rate, matched_correction → correction rate
#: (reported only, gates nothing — OQ-016c).
BUCKETS = (
    ("matched", "authoring"),
    ("refuse", "adversarial"),
    ("matched_correction", "correction"),
)

#: §11.8 infra rule: infra-skipped fixtures above this fraction of a bucket
#: fail that bucket's gate.
INFRA_CAP = 0.10


def _independent_reverify(template: Any, samples: Any) -> bool:
    """Re-run ``python -m transon_authoring verify`` on the *submitted*
    template against the *fixture* SampleSet (OQ-016a). The skill's own
    verdict claim is never trusted (AD-004). True iff verify exits 0.
    """
    with tempfile.TemporaryDirectory(prefix="check-evals-reverify-") as tmp:
        template_path = Path(tmp) / "template.json"
        samples_path = Path(tmp) / "samples.json"
        template_path.write_text(
            json.dumps(template, ensure_ascii=False), encoding="utf-8"
        )
        samples_path.write_text(
            json.dumps(samples, ensure_ascii=False), encoding="utf-8"
        )
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "transon_authoring",
                "verify",
                "--template",
                str(template_path),
                "--samples",
                str(samples_path),
            ],
            capture_output=True,
            cwd=tmp,
            timeout=300,
        )
        return completed.returncode == 0


def score_episode(fixture: dict[str, Any], episode: dict[str, Any]) -> str:
    """Mechanically score one EpisodeResult against its fixture (OQ-016).

    Returns ``"pass"``, ``"fail"`` or ``"infra"``. Deterministic and
    provider-free: only the pinned local engine is exercised (re-verify).
    """
    outcome = episode["outcome"]
    if outcome == "infra_error":
        # Provider/transport failure — never model behavior (OQ-016d).
        return "infra"
    if outcome != "submitted":
        # budget_exceeded / no_submit are bucket-failures (OQ-017c).
        return "fail"

    submitted = episode.get("submitted")
    if not isinstance(submitted, dict) or schema_violations(
        submitted, "authoring_result.json"
    ):
        # Missing/invalid submission fails its bucket, never infra (OQ-016b).
        return "fail"

    expect = fixture["expect"]
    if expect in ("matched", "matched_correction"):
        # OQ-016a — matched-success: schema-valid (above), ok true, status
        # matched, template present, verdict ok with assurance matched, AND
        # an independent re-verify of the submitted template against the
        # fixture SampleSet (the claim is never trusted — AD-004).
        verdict = submitted.get("verdict")
        if not (
            submitted.get("ok") is True
            and submitted.get("status") == "matched"
            and "template" in submitted
            and isinstance(verdict, dict)
            and verdict.get("ok") is True
            and verdict.get("assurance") == "matched"
        ):
            return "fail"
        samples = fixture.get("samples")
        if samples is None:
            # No fixture SampleSet — the OQ-016a re-verify is impossible, so
            # matched-success cannot be established.
            return "fail"
        try:
            verified = _independent_reverify(submitted["template"], samples)
        except Exception:  # harness fault, not model behavior (OQ-016d)
            return "infra"
        return "pass" if verified else "fail"

    # expect == "refuse" (OQ-016b): ok false, template absent, refusal status.
    if (
        submitted.get("ok") is False
        and "template" not in submitted
        and submitted.get("status") in REFUSE_STATUSES
    ):
        return "pass"
    return "fail"


def _majority(scores: list[str]) -> str:
    """Majority-of-runs verdict for one fixture; infra episodes are excluded
    from the vote (§11.8). All-infra → ``"infra"`` (fixture infra-skipped);
    a tie among scored episodes is conservatively ``"fail"``.
    """
    passes = scores.count("pass")
    fails = scores.count("fail")
    if passes + fails == 0:
        return "infra"
    return "pass" if passes > fails else "fail"


def aggregate(
    fixtures: list[dict[str, Any]],
    per_fixture_episodes: dict[str, list[dict[str, Any]]],
    targets: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any]:
    """Aggregate per-episode scores into the §11.8 gate report.

    Red conditions (NFR-010 / AC-008): authoring rate below
    ``targets.authoring_target``; adversarial refuse rate below
    ``targets.adversarial_target`` (1.0); infra-skipped fixtures above 10%
    of a gating bucket; any ``baseline.passing`` fixture failing its
    majority (OQ-016f). The correction bucket is reported but gates nothing
    (OQ-016c); its fixtures still participate in the baseline rule.
    """
    fixtures_report: dict[str, dict[str, Any]] = {}
    majorities: dict[str, str] = {}
    for fixture in fixtures:
        fixture_id = fixture["id"]
        episodes = per_fixture_episodes[fixture_id]
        scores = [score_episode(fixture, episode) for episode in episodes]
        majorities[fixture_id] = _majority(scores)
        fixtures_report[fixture_id] = {
            "episodes": [
                {"outcome": episode["outcome"], "score": score}
                for episode, score in zip(episodes, scores)
            ],
            "majority": majorities[fixture_id],
        }

    red: list[str] = []
    rates: dict[str, Any] = {}
    for expect, bucket in BUCKETS:
        members = [f["id"] for f in fixtures if f["expect"] == expect]
        scored = [fid for fid in members if majorities[fid] != "infra"]
        infra_skipped = [fid for fid in members if majorities[fid] == "infra"]
        passes = sum(1 for fid in scored if majorities[fid] == "pass")
        rates[bucket] = (passes / len(scored)) if scored else None
        # Correction gates nothing (OQ-016c) — no rate/infra red for it.
        if bucket == "correction":
            continue
        # A gating bucket with zero fixtures is red, never silently green —
        # the gate cannot certify a rate it never measured (SPEC §11.8;
        # scripts/** honesty rule).
        if not members:
            red.append(
                f"no fixtures in the {bucket} bucket — gate cannot certify "
                "its rate with zero coverage (SPEC §11.8 / NFR-010)"
            )
            continue
        if members and len(infra_skipped) > INFRA_CAP * len(members):
            red.append(
                f"infra-skipped fixtures exceed 10% of the {bucket} bucket "
                f"({len(infra_skipped)}/{len(members)}) — gate fail "
                "(SPEC §11.8 / NFR-010)"
            )
        target = targets[f"{bucket}_target"]
        if rates[bucket] is not None and rates[bucket] < target:
            red.append(
                f"{bucket} rate {rates[bucket]:.3f} below target "
                f"{target:.3f} (NFR-010 / AC-008)"
            )

    # Fixture-regression baseline (OQ-016f): any previously passing fixture
    # failing its majority is red regardless of aggregate rates. Infra-skipped
    # baseline fixtures are excluded, not regressions.
    for fixture_id in sorted(set(baseline["passing"])):
        if majorities.get(fixture_id) == "fail":
            red.append(
                f"baseline regression: fixture {fixture_id!r} failed its "
                "majority (OQ-016f / AC-008)"
            )

    return {
        "schema_version": "1.0",
        "rates": rates,
        "fixtures": fixtures_report,
        "red": red,
    }


def _import_eval_harness():
    """Import scripts/eval_harness.py lazily (module-level attribute lookups
    keep it monkeypatchable in offline tests, OQ-017e)."""
    try:
        import eval_harness
    except ImportError:  # pragma: no cover - invoked outside scripts/
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import eval_harness
    return eval_harness


def _build_provider(runner_cfg: dict[str, Any]):
    """Build the provider pinned by runner.json (OQ-017d). Raises on an
    unsupported provider or a missing [evals] extra (config errors, exit 2).
    """
    if runner_cfg["provider"] != "anthropic":
        raise ValueError(
            f"unsupported provider {runner_cfg['provider']!r} in "
            "evals/runner.json (v1 implements 'anthropic' only, OQ-017d)"
        )
    return _import_eval_harness().AnthropicProvider(runner_cfg)


def run_evals(
    repo_root: Path, *, update_baseline: bool = False, verbose: bool = False
) -> int:
    """Full FR-017 eval gate: lint, provider episodes, scoring, aggregation.

    Exit codes: 0 green, 1 red gate (or red lint), 2 config/credential
    errors (NFR-010 / AC-008; SPEC §11.8).
    """
    # Lint first — a corpus that fails NFR-011 never reaches the provider.
    failures = lint_evals(repo_root, verbose=verbose)
    for message in failures:
        print(f"check-evals: FAIL: {message}", file=sys.stderr)
    if failures:
        print(f"check-evals: {len(failures)} lint failure(s)", file=sys.stderr)
        return 1

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "check-evals: config error: ANTHROPIC_API_KEY is not set — the "
            "full eval run needs provider credentials and lives in the "
            "credential-holding dispatch workflow (OQ-017e); use --lint for "
            "the credential-free fixture lint",
            file=sys.stderr,
        )
        return 2

    # Policy files just passed the lint's full ingress; load them for use
    # (AD-020).
    evals_dir = repo_root / "evals"
    runner_cfg = load_document(evals_dir / "runner.json", "eval_runner.json")
    targets = load_document(evals_dir / "targets.json", "eval_targets.json")
    baseline = load_document(evals_dir / "baseline.json", "eval_baseline.json")
    fixtures = [
        load_document(path, "eval_fixture.json")
        for path in sorted((evals_dir / "cases").glob("*.json"))
    ]

    harness = _import_eval_harness()
    try:
        provider = _build_provider(runner_cfg)
    except Exception as exc:
        print(f"check-evals: config error: {exc}", file=sys.stderr)
        return 2

    runs_per_fixture = runner_cfg["runs_per_fixture"]
    per_fixture_episodes: dict[str, list[dict[str, Any]]] = {}
    for fixture in fixtures:
        per_fixture_episodes[fixture["id"]] = [
            harness.run_fixture(fixture, runner_cfg, provider, repo_root)
            for _ in range(runs_per_fixture)
        ]

    report = aggregate(fixtures, per_fixture_episodes, targets, baseline)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    for reason in report["red"]:
        print(f"check-evals: RED: {reason}", file=sys.stderr)
    if report["red"]:
        return 1

    if update_baseline:
        # OQ-016f — after a green run, record the passing fixture ids
        # (append-only in practice: existing baseline ids are kept).
        passing = sorted(
            set(baseline["passing"])
            | {
                fixture_id
                for fixture_id, entry in report["fixtures"].items()
                if entry["majority"] == "pass"
            }
        )
        baseline_path = evals_dir / "baseline.json"
        baseline_path.write_text(
            json.dumps(
                {"schema_version": "1.0", "passing": passing},
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        print(
            f"check-evals: baseline updated: {len(passing)} passing fixture "
            f"id(s) written to {baseline_path} (OQ-016f)",
            file=sys.stderr,
        )

    print("check-evals: gate green", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="check_evals",
        description="Eval gate (FR-017/NFR-010/AD-020). Default mode runs "
        "the full provider eval gate (SPEC §11.8; needs ANTHROPIC_API_KEY); "
        "--lint runs only the credential-free NFR-011 fixture privacy lint "
        "(AC-025) used by per-PR CI (OQ-017e).",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="run only the fixture lint (schema, ids, baseline refs, sample "
        "readiness, consent/redaction, secret scan)",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="after a green full run, record the passing fixture ids in "
        "evals/baseline.json (OQ-016f)",
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
        return run_evals(
            args.root.resolve(),
            update_baseline=args.update_baseline,
            verbose=args.verbose,
        )

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
