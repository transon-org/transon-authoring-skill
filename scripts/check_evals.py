#!/usr/bin/env python
"""check-evals — eval gate for the committed corpus under ``evals/``
(FR-017 / FR-029 / NFR-010 / NFR-011 / AC-008 / AC-025 / AC-030; SPEC §11.8,
§13, §15 OQ-016/OQ-017/OQ-025).

Two modes:

- ``--lint`` — the fixture lint that per-PR CI runs (OQ-017e; the §13
  check_evals row carries this lint plus the FR-029 seed-regen check,
  AC-030). Credential-free, network-free and deterministic — no provider is
  ever touched; the AC-030 regen check does exercise the pinned local engine
  through the AD-017 sandbox.
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
7. Every ``evals/seeds/*.json`` parses, is shape-valid
   (``{source_example, template, generator: {version, notes?}}`` — validated
   structurally, not by the §11.0 ingress, per OQ-025), and has a matching
   fixture ``evals/cases/<stem>.json``; a seed without a fixture is red, a
   fixture without a seed is hand-authored and ignored (FR-029 / AC-030).
8. Snapshot provenance (FR-029a): the seed ``source_example`` names an entry
   in the pinned snapshot ``docs.examples``, the seed ``template``
   JSON-equals that entry's ``template``, and fixture case 1 ``input``
   JSON-equals that entry's ``data`` (AD-021: a seed cannot smuggle in a
   template that never originated from the corpus).
9. Regeneration (FR-029b / AC-030): the fixture regenerates bit-identically
   from its seed under the current pin — the §11.1 SampleSet content subset
   (compared via its OQ-015 canonical bytes / ``content_fingerprint``) and
   the recorded confirmation fingerprint both match a fresh
   ``scripts/gen_fixtures.py`` run — the same drift discipline as
   ``check_snapshot``.

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
    from transon_authoring import check_samples, get_metadata
    from transon_authoring._ingress import (
        IngressError,
        load_document,
        schema_violations,
    )
    from transon_authoring.samples import content_fingerprint
except ImportError:  # pragma: no cover - source-checkout fallback (SPEC §10)
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
    from transon_authoring import check_samples, get_metadata
    from transon_authoring._ingress import (
        IngressError,
        load_document,
        schema_violations,
    )
    from transon_authoring.samples import content_fingerprint

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
    """Run the NFR-011 fixture lint plus the FR-029 / AC-030 seed checks over
    ``<repo_root>/evals``; return the (possibly empty) list of failure
    messages, each naming the offending file.

    Credential-free, network-free and deterministic (no provider is ever
    touched); safe for per-PR CI (OQ-017e). The AC-030 regen check runs the
    pinned local engine through the AD-017 sandbox — same determinism, no
    external dependency.
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
    fixtures_by_stem: dict[str, dict] = {}
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
            fixtures_by_stem[path.stem] = fixture
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

    # --- Checks 7–9: seed provenance + AC-030 regeneration (FR-029). -------
    failures.extend(_lint_seeds(evals_dir, cases_dir, fixtures_by_stem, note))

    return failures


def _seed_shape_errors(seed: Any) -> list[str]:
    """Structural validation of a seed provenance doc (FR-029 shape;
    OQ-025 tail: no ``schema_version``, never the §11.0 ingress validator)."""
    if not isinstance(seed, dict):
        return ["seed document must be a JSON object"]
    errors: list[str] = []
    extras = sorted(set(seed) - {"source_example", "template", "generator"})
    if extras:
        errors.append(f"unknown seed keys: {', '.join(extras)}")
    if not isinstance(seed.get("source_example"), str):
        errors.append("`source_example` must be a string")
    if "template" not in seed:
        errors.append("`template` is required")
    generator = seed.get("generator")
    if not isinstance(generator, dict):
        errors.append("`generator` must be an object")
    else:
        if not isinstance(generator.get("version"), str):
            errors.append("`generator.version` must be a string")
        if "notes" in generator and not isinstance(generator["notes"], str):
            errors.append("`generator.notes` must be a string when present")
        gen_extras = sorted(set(generator) - {"version", "notes"})
        if gen_extras:
            errors.append(f"unknown generator keys: {', '.join(gen_extras)}")
    return errors


def _lint_seeds(
    evals_dir: Path,
    cases_dir: Path,
    fixtures_by_stem: dict[str, dict],
    note,
) -> list[str]:
    """FR-029 / AC-030 seed checks (lint checks 7–9). A fixture without a
    seed file is hand-authored and ignored; every seed file must agree with
    its fixture and the pinned snapshot, and regenerate bit-identically."""
    failures: list[str] = []
    seeds_dir = evals_dir / "seeds"
    seed_paths = sorted(seeds_dir.glob("*.json")) if seeds_dir.is_dir() else []
    snapshot_examples: dict[str, dict] | None = None
    generator = None

    for path in seed_paths:
        # Check 7 — parse + shape + matching fixture.
        try:
            seed = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            failures.append(f"{path}: seed does not parse: {exc} (FR-029)")
            continue
        shape_errors = _seed_shape_errors(seed)
        if shape_errors:
            failures.extend(
                f"{path}: {error} (FR-029 seed shape)" for error in shape_errors
            )
            continue
        fixture = fixtures_by_stem.get(path.stem)
        if fixture is None:
            failures.append(
                f"{path}: seed has no matching fixture "
                f"{cases_dir / (path.stem + '.json')} (FR-029 / AC-030)"
            )
            continue

        # Check 8 — snapshot provenance (FR-029a / AD-021).
        if snapshot_examples is None:
            snapshot_examples = {
                entry["name"]: entry
                for entry in get_metadata()["docs"]["examples"]
            }
        entry = snapshot_examples.get(seed["source_example"])
        if entry is None:
            failures.append(
                f"{path}: source_example {seed['source_example']!r} is not in "
                "the pinned snapshot docs.examples (FR-029 / AC-030)"
            )
            continue
        if seed["template"] != entry["template"]:
            failures.append(
                f"{path}: seed template does not JSON-equal the snapshot "
                f"entry's template (FR-029 / AC-030 / AD-021)"
            )
            continue
        fixture_path = cases_dir / f"{path.stem}.json"
        samples = fixture.get("samples")
        if not isinstance(samples, dict) or not samples.get("cases"):
            failures.append(
                f"{fixture_path}: seeded fixture carries no SampleSet cases — "
                "case 1 provenance cannot be established (FR-029 / AC-030)"
            )
            continue
        if samples["cases"][0].get("input") != entry["data"]:
            failures.append(
                f"{fixture_path}: case 1 input does not JSON-equal the "
                f"snapshot entry's data (FR-029 / AC-030 / AD-021)"
            )
            continue

        # Check 9 — bit-identical regeneration under the current pin
        # (AC-030): §11.1 content subset compared via its OQ-015 canonical
        # bytes (content_fingerprint is sha256 over exactly those bytes)
        # plus the recorded confirmation fingerprint.
        if generator is None:
            generator = _import_fixture_generator()
        try:
            regen_fixture, _regen_seed = generator.generate(
                entry, path.stem, fixture["intent_nl"]
            )
        except Exception as exc:
            failures.append(
                f"{path}: fixture does not regenerate from its seed under the "
                f"current pin: {exc} (FR-029 / AC-030)"
            )
            continue
        regen_samples = regen_fixture["samples"]
        subset_agrees = content_fingerprint(samples) == content_fingerprint(
            regen_samples
        )
        # A generator regression that drops the confirmation fingerprint must
        # be a clean red, never a KeyError crash — and never a silent
        # None == None pass against a fixture missing it too.
        regen_fp = regen_samples.get("confirmation", {}).get("content_fingerprint")
        if not regen_fp:
            failures.append(
                f"{fixture_path}: regenerated fixture carries no confirmation "
                "content_fingerprint — generator regression (FR-029 / AC-030)"
            )
            continue
        recorded_agrees = (
            samples.get("confirmation", {}).get("content_fingerprint") == regen_fp
        )
        if not (subset_agrees and recorded_agrees):
            failures.append(
                f"{fixture_path}: fixture does not regenerate bit-identically "
                "from its seed under the current pin (SampleSet content "
                "subset / content_fingerprint drift) — same discipline as "
                "check_snapshot (FR-029 / AC-030)"
            )
            continue
        note(f"seed OK: {path}")

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


def _failure_key(
    fixture: dict[str, Any], episode: dict[str, Any], score: str
) -> str:
    """FR-032 / AC-034 — the ``failure_modes`` histogram key for one FAILED or
    infra episode, first match in the §11.8 precedence wins. Derived purely
    from the already-scored result: the submitted status only ever *labels* a
    failure, it is never the score (AD-004).
    """
    if score == "infra":
        return "infra_error"
    outcome = episode["outcome"]
    if outcome == "no_submit":
        return "no_submit"
    if outcome == "budget_exceeded":
        return "budget_exceeded"

    # outcome == "submitted" with score "fail": inspect the submitted envelope.
    submitted = episode.get("submitted")
    if not isinstance(submitted, dict) or schema_violations(
        submitted, "authoring_result.json"
    ):
        return "invalid_submission"

    verdict = submitted.get("verdict")
    claims_matched = (
        submitted.get("ok") is True
        and submitted.get("status") == "matched"
        and "template" in submitted
        and isinstance(verdict, dict)
        and verdict.get("ok") is True
        and verdict.get("assurance") == "matched"
    )
    # A matched claim that scored fail can only mean the OQ-016a independent
    # re-verify rejected it (the claim is never trusted, AD-004). (A matched
    # fixture always carries a SampleSet — the lint enforces it — so the
    # "re-verify impossible" score-fail branch is unreachable in practice; and
    # failure_modes is diagnostic-only and gates nothing regardless.)
    if fixture["expect"] in ("matched", "matched_correction") and claims_matched:
        return "reverify_failed"

    # Otherwise label with the submitted §11.5 status, suffixed with the
    # verdict.failed_stage when present (e.g. "verify-failed/match"; a refuse
    # bucket key of "matched" is an invented success where refusal was owed).
    status = submitted.get("status")
    stage = verdict.get("failed_stage") if isinstance(verdict, dict) else None
    return f"{status}/{stage}" if stage else str(status)


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
    # FR-032 — per-bucket failure-mode histogram over the runs that failed
    # their bucket's OQ-016 rule plus reported-only infra_error runs, keyed by
    # the scored outcome (§11.8). Always all three bucket keys, each possibly
    # empty. Non-gating: derived mechanically from the same scores below.
    bucket_by_expect = {expect: bucket for expect, bucket in BUCKETS}
    failure_modes: dict[str, dict[str, int]] = {
        "authoring": {},
        "adversarial": {},
        "correction": {},
    }

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
        bucket = bucket_by_expect[fixture["expect"]]
        for episode, score in zip(episodes, scores):
            if score == "pass":
                continue  # passing runs are excluded from failure_modes
            key = _failure_key(fixture, episode, score)
            histogram = failure_modes[bucket]
            histogram[key] = histogram.get(key, 0) + 1

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
        "failure_modes": failure_modes,
        "red": red,
    }


def _import_fixture_generator():
    """Import scripts/gen_fixtures.py lazily (same pattern as
    :func:`_import_eval_harness`): the FR-029 generator is only needed when
    seed files exist, and module-level lookups keep it monkeypatchable."""
    try:
        import gen_fixtures
    except ImportError:  # pragma: no cover - invoked outside scripts/
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import gen_fixtures
    return gen_fixtures


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


def write_transcripts(
    transcripts_dir: Path,
    fixtures: list[dict[str, Any]],
    per_fixture_episodes: dict[str, list[dict[str, Any]]],
    runner_cfg: dict[str, Any],
) -> None:
    """FR-032 / AC-034 — persist one EpisodeTranscript JSON per episode to
    ``transcripts_dir`` (§11.8 shape). A build artifact only: **never
    committed** to the repo. Derived mechanically from the recorded episodes —
    changes no scoring, target, baseline, or lint semantics.
    """
    transcripts_dir.mkdir(parents=True, exist_ok=True)
    model_id = runner_cfg["model_id"]
    for fixture in fixtures:
        fixture_id = fixture["id"]
        for run_index, episode in enumerate(per_fixture_episodes[fixture_id]):
            transcript = {
                "schema_version": "1.0",
                "fixture_id": fixture_id,
                "run_index": run_index,
                "model_id": model_id,
                "outcome": episode["outcome"],
                "tool_calls": episode.get("tool_call_log", []),
                # The submit_result payload VERBATIM — possibly schema-invalid,
                # retained so OQ-016(b) failures stay diagnosable (§11.8).
                "submitted": episode.get("submitted"),
                "error": episode.get("error"),
            }
            path = transcripts_dir / f"{fixture_id}.{run_index}.json"
            path.write_text(
                json.dumps(transcript, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )


def run_evals(
    repo_root: Path,
    *,
    update_baseline: bool = False,
    verbose: bool = False,
    transcripts_dir: Path | None = None,
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

    # FR-032 — persist episode transcripts when a directory is given, before
    # scoring and regardless of red/green (a build artifact, never committed).
    if transcripts_dir is not None:
        write_transcripts(transcripts_dir, fixtures, per_fixture_episodes, runner_cfg)

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
        "(AC-025) plus the FR-029 seed provenance/regen checks (AC-030) "
        "used by per-PR CI (OQ-017e).",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="run only the fixture lint (schema, ids, baseline refs, sample "
        "readiness, consent/redaction, secret scan, seed provenance + "
        "AC-030 regeneration)",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="after a green full run, record the passing fixture ids in "
        "evals/baseline.json (OQ-016f)",
    )
    parser.add_argument(
        "--transcripts-dir",
        type=Path,
        default=None,
        help="write one FR-032 EpisodeTranscript JSON per episode to this "
        "directory (SPEC §11.8); a build artifact only — transcripts are "
        "never committed to the repo (repo hygiene + NFR-011)",
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
            transcripts_dir=args.transcripts_dir,
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
