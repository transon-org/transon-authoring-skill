"""FR-017 / NFR-010 / NFR-011 / AC-008 / AC-025 — the `check_evals` gate.

Two surfaces:

- `--lint` (NFR-011 / AC-025 plus the FR-029 / AC-030 seed checks): the
  credential-free, network-free, deterministic fixture lint per-PR CI runs
  (SPEC §15 OQ-017e; the §13 check_evals row carries it; the AC-030 regen
  check exercises the pinned local engine): bundled-schema validation of
  the eval-policy files and every `evals/cases/*.json` (AD-020), id/filename
  agreement and baseline references (OQ-016f), `ok_for_verify` SampleSets
  (FR-027 / OQ-017a), the consent⇒redaction invariant (FR-018), the
  best-effort secret scan (AC-025), and the FR-029 seed provenance +
  bit-identical regeneration gate (AC-030).
- the full red/green gate (FR-017 / NFR-010 / AC-008): OQ-016 mechanical
  scoring (`score_episode`, incl. the independent re-verify — AD-004),
  §11.8 aggregation (`aggregate`: majority-of-runs, buckets with
  infra-excluded denominators and the 10% infra cap, targets/ratchet,
  fixture-regression baseline, correction bucket reported-only) and the
  orchestrated default mode with its 0/1/2 exit-code discipline.

All tests are offline and provider-free (OQ-017e): scoring/aggregation is
driven with hand-built episodes; orchestration tests monkeypatch
`eval_harness.run_fixture` and the provider factory, and never need the
anthropic SDK or an API key. Only the pinned local engine is exercised
(the OQ-016a re-verify subprocess).
"""

import copy
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK = REPO_ROOT / "scripts" / "check_evals.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
import check_evals  # noqa: E402
import eval_harness  # noqa: E402
from check_evals import aggregate, lint_evals, score_episode  # noqa: E402

from transon_authoring._ingress import schema_violations  # noqa: E402


def run_check(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), *args],
        capture_output=True,
        text=True,
    )


@pytest.fixture
def tmp_repo(tmp_path: Path) -> Path:
    """A tmp repo root with the committed evals/ corpus copied in."""
    shutil.copytree(REPO_ROOT / "evals", tmp_path / "evals")
    return tmp_path


def mutate_fixture(root: Path, name: str, **changes) -> Path:
    path = root / "evals" / "cases" / f"{name}.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture.update(changes)
    path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return path


def test_nfr_011_ac_025_committed_fixtures_lint_green():
    # NFR-011 / AC-025 — the committed corpus passes the lint, both through
    # the importable function and via the CLI exactly as per-PR CI runs it
    # (OQ-017e).
    assert lint_evals(REPO_ROOT) == []
    result = run_check("--lint", "--root", str(REPO_ROOT))
    assert result.returncode == 0, result.stderr
    assert "FAIL" not in result.stderr


def test_nfr_011_ac_025_consent_requires_redaction(tmp_repo: Path):
    # NFR-011 / AC-025 / FR-018 — a real-use fixture (consent recorded) with
    # redacted:false is red, and the failure names the file.
    path = mutate_fixture(
        tmp_repo,
        "seed-refuse-nonexistent-mode",
        consent={"by": "alice", "at": "2026-07-11T00:00:00Z", "note": "shared in issue"},
        redacted=False,
    )
    failures = lint_evals(tmp_repo)
    consent_failures = [f for f in failures if "redacted" in f and "consent" in f]
    assert consent_failures, failures
    assert any(str(path) in f for f in consent_failures)
    # consent + redacted:true is the compliant real-use shape — lint green.
    mutate_fixture(tmp_repo, "seed-refuse-nonexistent-mode", redacted=True)
    assert lint_evals(tmp_repo) == []


def test_nfr_011_secret_pattern_is_red(tmp_repo: Path):
    # NFR-011 / AC-025 — an AWS access key id in any fixture string trips the
    # best-effort secret scan.
    path = mutate_fixture(
        tmp_repo,
        "seed-refuse-nonexistent-operator",
        notes="reported with credentials AKIAABCDEFGHIJKLMNOP left in",
    )
    failures = lint_evals(tmp_repo)
    secret_failures = [f for f in failures if "secret scan" in f]
    assert secret_failures, failures
    assert any(str(path) in f and "AWS access key id" in f for f in secret_failures)
    # CLI agrees: exit 1, failure on stderr (subprocess path, as CI sees it).
    result = run_check("--lint", "--root", str(tmp_repo))
    assert result.returncode == 1
    assert "secret scan" in result.stderr and path.name in result.stderr


def test_nfr_011_bad_sample_set_is_red(tmp_repo: Path):
    # NFR-011 (lint scope) / OQ-017a — a fixture whose supplied SampleSet is
    # not ok_for_verify (confirmation withdrawn) is red, naming the file.
    name = "seed-matched-flatten-orders"
    path = tmp_repo / "evals" / "cases" / f"{name}.json"
    fixture = json.loads(path.read_text(encoding="utf-8"))
    fixture["samples"]["confirmation"]["confirmed"] = False
    path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    failures = lint_evals(tmp_repo)
    sample_failures = [f for f in failures if "ok_for_verify" in f]
    assert sample_failures, failures
    assert any(str(path) in f for f in sample_failures)


def test_nfr_011_id_mismatch_and_dangling_baseline_red(tmp_repo: Path):
    # NFR-011 (lint scope) / SPEC §11.8, OQ-016f — a fixture id that differs
    # from its filename stem and a baseline `passing` id with no fixture are
    # both individual failures naming their files.
    fixture_path = mutate_fixture(
        tmp_repo, "seed-refuse-nonexistent-mode", id="some-other-id"
    )
    baseline_path = tmp_repo / "evals" / "baseline.json"
    baseline_path.write_text(
        json.dumps({"schema_version": "1.0", "passing": ["seed-no-such-fixture"]})
        + "\n",
        encoding="utf-8",
    )
    failures = lint_evals(tmp_repo)
    mismatch = [f for f in failures if "filename stem" in f]
    dangling = [f for f in failures if "seed-no-such-fixture" in f]
    assert mismatch and str(fixture_path) in mismatch[0], failures
    assert dangling and str(baseline_path) in dangling[0], failures


def test_nfr_011_missing_policy_file_and_invalid_fixture_red(tmp_repo: Path):
    # NFR-011 (lint scope) / AD-020 — a missing eval-policy file and a
    # schema-invalid fixture are failures naming the files.
    (tmp_repo / "evals" / "targets.json").unlink()
    bad = tmp_repo / "evals" / "cases" / "seed-bad.json"
    bad.write_text(
        json.dumps({"schema_version": "1.0", "id": "seed-bad"}) + "\n",
        encoding="utf-8",
    )
    failures = lint_evals(tmp_repo)
    assert any("targets.json" in f and "missing" in f for f in failures), failures
    assert any(str(bad) in f for f in failures), failures


# ---------------------------------------------------------------------------
# FR-029 / AC-030 — seed provenance + bit-identical regeneration lint.
# ---------------------------------------------------------------------------

import gen_fixtures  # noqa: E402

from transon_authoring import check_samples as _check_samples  # noqa: E402
from transon_authoring import get_metadata as _get_metadata  # noqa: E402

SNAPSHOT_EXAMPLES = {e["name"]: e for e in _get_metadata()["docs"]["examples"]}
#: Small writes-capable seed used by the AC-030 lint tests (fast to regen).
SEED_EXAMPLE = "FileWriteViaMap"
SEED_ID = "seed-file-write-via-map"
SEED_INTENT = "Write each input item to its own numbered output file."


def mint_into(root: Path) -> tuple[Path, Path]:
    """Mint the test seed fixture + provenance doc into *root* via the SAME
    generator core the lint regen uses (FR-029)."""
    fixture, seed = gen_fixtures.generate(
        SNAPSHOT_EXAMPLES[SEED_EXAMPLE], SEED_ID, SEED_INTENT
    )
    seeds_dir = root / "evals" / "seeds"
    seeds_dir.mkdir(parents=True, exist_ok=True)
    fixture_path = root / "evals" / "cases" / f"{SEED_ID}.json"
    seed_path = seeds_dir / f"{SEED_ID}.json"
    fixture_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    seed_path.write_text(
        json.dumps(seed, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return fixture_path, seed_path


def rewrite_samples(fixture_path: Path, mutate) -> None:
    """Apply *mutate(samples)* and refresh the confirmation fingerprint via
    the library (OQ-015 acquisition path) so ok_for_verify stays true and
    only the AC-030 checks can catch the drift."""
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    samples = fixture["samples"]
    mutate(samples)
    samples["confirmation"]["content_fingerprint"] = ""
    samples["confirmation"]["confirmed"] = False
    check = _check_samples(samples)
    samples["confirmation"]["content_fingerprint"] = check["content_fingerprint"]
    samples["confirmation"]["confirmed"] = True
    fixture_path.write_text(
        json.dumps(fixture, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def test_ac_030_agreeing_seed_fixture_snapshot_lint_green(tmp_repo: Path):
    # AC-030 — a repo whose seeds, fixtures, and snapshot agree lints green,
    # importable-function and CLI alike.
    mint_into(tmp_repo)
    assert lint_evals(tmp_repo) == []
    result = run_check("--lint", "--root", str(tmp_repo))
    assert result.returncode == 0, result.stderr


def test_ac_030_regen_mismatch_red(tmp_repo: Path):
    # AC-030 / FR-029 — a committed fixture that no longer regenerates
    # bit-identically (content subset drifted; fingerprint refreshed so only
    # the regen check can catch it) is red, naming the file.
    fixture_path, _seed_path = mint_into(tmp_repo)

    def tamper(samples):
        samples["cases"][1]["output"] = {"tampered": True}

    rewrite_samples(fixture_path, tamper)
    failures = lint_evals(tmp_repo)
    regen = [f for f in failures if "regenerate" in f and "AC-030" in f]
    assert regen, failures
    assert any(str(fixture_path) in f for f in regen)


def test_ac_030_seed_without_fixture_red(tmp_repo: Path):
    # AC-030 — a seed file with no matching fixture is red; the reverse
    # (hand-authored fixture without a seed) is ignored.
    fixture_path, seed_path = mint_into(tmp_repo)
    fixture_path.unlink()
    failures = lint_evals(tmp_repo)
    assert any(
        str(seed_path) in f and "no matching fixture" in f for f in failures
    ), failures


def test_ac_030_unknown_source_example_red(tmp_repo: Path):
    # AC-030 / FR-029 snapshot provenance — source_example must name an
    # entry in the pinned snapshot docs.examples.
    _fixture_path, seed_path = mint_into(tmp_repo)
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    seed["source_example"] = "NoSuchExample"
    seed_path.write_text(json.dumps(seed) + "\n", encoding="utf-8")
    failures = lint_evals(tmp_repo)
    assert any(
        str(seed_path) in f and "NoSuchExample" in f for f in failures
    ), failures


def test_ac_030_seed_template_not_snapshot_verbatim_red(tmp_repo: Path):
    # AC-030 / FR-029 — the seed template must JSON-equal the snapshot
    # entry's template (a seed cannot smuggle in a foreign template, AD-021).
    _fixture_path, seed_path = mint_into(tmp_repo)
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    seed["template"] = {"$": "this"}
    seed_path.write_text(json.dumps(seed) + "\n", encoding="utf-8")
    failures = lint_evals(tmp_repo)
    assert any(
        str(seed_path) in f and "template" in f for f in failures
    ), failures


def test_ac_030_case_1_input_differs_red(tmp_repo: Path):
    # AC-030 / FR-029 — fixture case 1 input must JSON-equal the snapshot
    # entry's data (the AD-021 corpus pair).
    fixture_path, _seed_path = mint_into(tmp_repo)

    def tamper(samples):
        samples["cases"][0]["input"] = [{"id": 999}]

    rewrite_samples(fixture_path, tamper)
    failures = lint_evals(tmp_repo)
    case1 = [f for f in failures if "case 1" in f]
    assert case1, failures
    assert any(str(fixture_path) in f or "seed" in f for f in case1)


def test_ac_030_seed_shape_invalid_red(tmp_repo: Path):
    # FR-029 / OQ-025 tail — seed docs are validated structurally by the
    # lint (no schema_version, no §11.0 ingress): a wrong-shaped seed is red.
    mint_into(tmp_repo)
    bad = tmp_repo / "evals" / "seeds" / "seed-bad-shape.json"
    bad.write_text(
        json.dumps({"source_example": 42, "generator": {}}) + "\n",
        encoding="utf-8",
    )
    failures = lint_evals(tmp_repo)
    assert any(str(bad) in f for f in failures), failures


def test_ac_030_hand_authored_fixture_without_seed_ignored():
    # AC-030 — fixtures without seed files are hand-authored and outside the
    # seed checks: the committed corpus mixes seeded syn-* fixtures (the
    # FR-029 / AD-021 v1 wave) with hand-authored seed-* ones and lints green.
    seed_stems = {p.stem for p in (REPO_ROOT / "evals" / "seeds").glob("*.json")}
    case_stems = {p.stem for p in (REPO_ROOT / "evals" / "cases").glob("*.json")}
    assert seed_stems, "expected the committed FR-029 seeds"
    assert case_stems - seed_stems, "expected hand-authored fixtures too"
    assert lint_evals(REPO_ROOT) == []


# ---------------------------------------------------------------------------
# FR-017 / NFR-010 / AC-008 — full gate: scoring, aggregation, orchestration.
# ---------------------------------------------------------------------------

FLATTEN_FIXTURE = json.loads(
    (REPO_ROOT / "evals" / "cases" / "seed-matched-flatten-orders.json").read_text(
        encoding="utf-8"
    )
)
#: The committed AC-001 template — verifies matched against the fixture's
#: SampleSet under the pinned engine (the fixture is adapted from that set).
CORRECT_TEMPLATE = json.loads(
    (REPO_ROOT / "tests" / "fixtures" / "ac001" / "template.json").read_text(
        encoding="utf-8"
    )
)

#: Committed corpus ids by bucket (SPEC §11.8).
MATCHED_IDS = (
    "seed-matched-attr-dynamic-name",
    "seed-matched-flatten-orders",
    "seed-matched-map-chain-attrs",
)
REFUSE_IDS = ("seed-refuse-nonexistent-mode", "seed-refuse-nonexistent-operator")
CORRECTION_ID = "seed-correction-attr-misspelled"

#: The full committed corpus, id → expect bucket (dynamic: alongside the
#: hand-authored seed-* fixtures the corpus carries the FR-029 / AD-021 v1
#: synthetic wave, one seeded syn-* fixture per snapshot tag family).
ALL_FIXTURES = {
    path.stem: json.loads(path.read_text(encoding="utf-8"))["expect"]
    for path in sorted((REPO_ROOT / "evals" / "cases").glob("*.json"))
}
ALL_MATCHED_IDS = tuple(
    fid for fid, expect in ALL_FIXTURES.items() if expect == "matched"
)

DEFAULT_TARGETS = {
    "schema_version": "1.0",
    "authoring_target": 0.80,
    "adversarial_target": 1.0,
}
EMPTY_BASELINE = {"schema_version": "1.0", "passing": []}


def episode(submitted=None, outcome="submitted", tool_calls=1, error=None):
    """Hand-built EpisodeResult in the eval_harness shape (OQ-017e)."""
    return {
        "submitted": submitted,
        "outcome": outcome,
        "tool_calls": tool_calls,
        "error": error,
    }


def matched_result(template):
    """A schema-valid AuthoringResult claiming matched (OQ-016a shape)."""
    return {
        "schema_version": "1.0",
        "ok": True,
        "status": "matched",
        "explanation": "verified matched",
        "template": template,
        "verdict": {
            "schema_version": "1.0",
            "ok": True,
            "assurance": "matched",
            "errors": [],
        },
    }


def refuse_result(status="aborted"):
    """A schema-valid refusal AuthoringResult (OQ-016b shape)."""
    return {
        "schema_version": "1.0",
        "ok": False,
        "status": status,
        "explanation": "cannot be grounded in the pinned metadata",
    }


def verify_failed_result(stage="match"):
    """A schema-valid verify-failed AuthoringResult carrying
    verdict.failed_stage (§11.5) — the FR-032 status/stage failure label."""
    return {
        "schema_version": "1.0",
        "ok": False,
        "status": "verify-failed",
        "explanation": "candidate failed verify at the match stage",
        "verdict": {
            "schema_version": "1.0",
            "ok": False,
            "failed_stage": stage,
            "errors": [],
        },
    }


def corpus_scores(**overrides):
    """Per-fixture score plan for orchestration tests: default all-pass."""
    plan = {fid: "pass" for fid in ALL_FIXTURES}
    plan.update(overrides)
    return plan


def orchestrate(
    monkeypatch,
    root,
    scores_by_id,
    update_baseline=False,
    transcripts_dir=None,
    episode_for=None,
):
    """Run `check_evals.main` in full-run mode, fully offline (OQ-017e):
    env key faked, provider factory stubbed, `eval_harness.run_fixture`
    scripted, and `score_episode` replaced by the episode's planned score.

    ``episode_for(fixture)`` optionally supplies a richer EpisodeResult
    (e.g. carrying ``tool_call_log`` + a schema-invalid ``submitted``) for the
    FR-032 transcript path; ``transcripts_dir`` passes ``--transcripts-dir``.
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")
    monkeypatch.setattr(check_evals, "_build_provider", lambda cfg: object())

    def scripted_run_fixture(fixture, runner_cfg, provider, repo_root):
        base = episode_for(fixture) if episode_for is not None else episode(
            outcome="submitted"
        )
        return dict(base, score=scores_by_id[fixture["id"]])

    monkeypatch.setattr(eval_harness, "run_fixture", scripted_run_fixture)
    monkeypatch.setattr(
        check_evals, "score_episode", lambda fixture, ep: ep["score"]
    )
    argv = ["--root", str(root)]
    if update_baseline:
        argv.append("--update-baseline")
    if transcripts_dir is not None:
        argv += ["--transcripts-dir", str(transcripts_dir)]
    return check_evals.main(argv)


def report_from(capsys):
    captured = capsys.readouterr()
    return json.loads(captured.out), captured.err


def test_fr_017_ac_008_matched_scoring_requires_independent_reverify():
    # FR-017 / AC-008 / OQ-016a — a matched claim is only a pass when the
    # harness's own re-verify of the submitted template against the fixture
    # SampleSet exits 0; the claimed verdict is never trusted (AD-004).
    good = episode(submitted=matched_result(CORRECT_TEMPLATE))
    assert score_episode(FLATTEN_FIXTURE, good) == "pass"

    corrupted = copy.deepcopy(CORRECT_TEMPLATE)
    corrupted["funcs"][0]["name"] = "orderz"  # attr no longer exists
    lying = episode(submitted=matched_result(corrupted))
    # The submission still claims ok/verdict.ok/assurance matched — only the
    # independent re-verify catches it.
    assert score_episode(FLATTEN_FIXTURE, lying) == "fail"


def test_fr_017_oq_016_scoring_rules_without_reverify():
    # FR-017 / OQ-016b/c/d and OQ-017c — the provider-free scoring rules.
    refuse_fixture = {"id": "r", "expect": "refuse"}
    assert score_episode(refuse_fixture, episode(refuse_result())) == "pass"
    # schema-error status is refuse-FAILURE, not a refusal (OQ-016b).
    assert (
        score_episode(refuse_fixture, episode(refuse_result("schema-error")))
        == "fail"
    )
    # Missing / schema-invalid submissions fail the bucket, never infra.
    assert score_episode(refuse_fixture, episode(submitted=None)) == "fail"
    assert score_episode(refuse_fixture, episode(submitted={"ok": False})) == "fail"
    # Budget/no-submit are bucket failures (OQ-017c); infra is infra (OQ-016d).
    assert (
        score_episode(refuse_fixture, episode(outcome="budget_exceeded")) == "fail"
    )
    assert score_episode(refuse_fixture, episode(outcome="no_submit")) == "fail"
    assert (
        score_episode(
            refuse_fixture, episode(outcome="infra_error", error="boom")
        )
        == "infra"
    )
    # A refusal submitted against a matched fixture fails the authoring bucket.
    assert score_episode(FLATTEN_FIXTURE, episode(refuse_result())) == "fail"


def test_nfr_010_ac_008_rate_below_target_exit_1(monkeypatch, tmp_repo, capsys):
    # NFR-010 / AC-008 — an authoring majority-pass rate below the 0.80
    # target reds the gate: exit 1 and an explicit red reason in the report.
    # Fail just enough matched fixtures to drop below the target.
    total = len(ALL_MATCHED_IDS)
    fails = int(total * (1 - DEFAULT_TARGETS["authoring_target"])) + 1
    scores = corpus_scores(**{fid: "fail" for fid in ALL_MATCHED_IDS[:fails]})
    assert orchestrate(monkeypatch, tmp_repo, scores) == 1
    report, err = report_from(capsys)
    assert report["rates"]["authoring"] == pytest.approx((total - fails) / total)
    assert report["rates"]["authoring"] < DEFAULT_TARGETS["authoring_target"]
    assert any("authoring rate" in reason for reason in report["red"]), report
    assert "RED" in err


def test_nfr_010_refuse_below_100_exit_1(monkeypatch, tmp_repo, capsys):
    # NFR-010 — the adversarial refuse rate must be 100% (SPEC §11.8): one
    # refuse fixture failing its majority reds the gate even though the
    # authoring rate is perfect.
    scores = corpus_scores(**{REFUSE_IDS[0]: "fail"})
    assert orchestrate(monkeypatch, tmp_repo, scores) == 1
    report, _ = report_from(capsys)
    assert report["rates"]["authoring"] == 1.0
    assert report["rates"]["adversarial"] == 0.5
    assert any("adversarial rate" in reason for reason in report["red"]), report
    assert not any("authoring" in reason for reason in report["red"])


def test_nfr_010_ac_008_baseline_regression_exit_1(monkeypatch, tmp_repo, capsys):
    # NFR-010 / AC-008 / OQ-016f — a baselined fixture failing its majority is
    # red regardless of aggregate rates. Uses the correction fixture, whose
    # bucket otherwise gates nothing (OQ-016c) — only the baseline rule fires.
    baseline_path = tmp_repo / "evals" / "baseline.json"
    baseline_path.write_text(
        json.dumps({"schema_version": "1.0", "passing": [CORRECTION_ID]}) + "\n",
        encoding="utf-8",
    )
    scores = corpus_scores(**{CORRECTION_ID: "fail"})
    assert orchestrate(monkeypatch, tmp_repo, scores) == 1
    report, _ = report_from(capsys)
    assert report["red"] == [
        f"baseline regression: fixture {CORRECTION_ID!r} failed its "
        "majority (OQ-016f / AC-008)"
    ]


def test_nfr_010_infra_cap_trips_bucket():
    # NFR-010 / SPEC §11.8 — infra runs are excluded from denominators, but
    # infra-skipped fixtures above 10% of a bucket fail that bucket's gate.
    # Real score_episode throughout (refusals need no re-verify subprocess).
    fixtures = [{"id": f"refuse-{n}", "expect": "refuse"} for n in range(3)]
    per_fixture = {
        "refuse-0": [episode(refuse_result()) for _ in range(3)],
        "refuse-1": [episode(refuse_result()) for _ in range(3)],
        # All-infra fixture: excluded from the rate, 1/3 > 10% trips the cap.
        "refuse-2": [
            episode(outcome="infra_error", error="api down") for _ in range(3)
        ],
    }
    report = aggregate(fixtures, per_fixture, DEFAULT_TARGETS, EMPTY_BASELINE)
    assert report["fixtures"]["refuse-2"]["majority"] == "infra"
    # Infra-excluded denominator: 2/2 scored fixtures pass.
    assert report["rates"]["adversarial"] == 1.0
    infra_reasons = [r for r in report["red"] if "infra-skipped" in r]
    assert infra_reasons and "adversarial" in infra_reasons[0], report
    # No rate reason — the cap is the only red condition here.
    assert all("below target" not in r for r in report["red"])


def test_nfr_010_empty_gating_bucket_is_red():
    # NFR-010 / SPEC §11.8 — a gating bucket with zero fixtures (corpus drift,
    # accidental deletion) is red, never silently green: the gate cannot
    # certify a rate it never measured. The reported rate is None.
    fixtures = [{"id": "refuse-0", "expect": "refuse"}]
    per_fixture = {"refuse-0": [episode(refuse_result()) for _ in range(3)]}
    report = aggregate(fixtures, per_fixture, DEFAULT_TARGETS, EMPTY_BASELINE)
    assert report["rates"]["authoring"] is None
    assert any(
        "no fixtures in the authoring bucket" in reason for reason in report["red"]
    ), report
    # The empty correction bucket stays non-gating (OQ-016c).
    assert not any("correction" in reason for reason in report["red"])


def test_fr_017_oq_016_correction_bucket_reported_not_gating(
    monkeypatch, tmp_repo, capsys
):
    # FR-017 / OQ-016c — matched_correction failures are reported as the
    # correction rate but never red the gate (empty baseline).
    scores = corpus_scores(**{CORRECTION_ID: "fail"})
    assert orchestrate(monkeypatch, tmp_repo, scores) == 0
    report, _ = report_from(capsys)
    assert report["rates"]["correction"] == 0.0
    assert report["fixtures"][CORRECTION_ID]["majority"] == "fail"
    assert report["red"] == []


def test_fr_017_missing_credentials_exit_2():
    # FR-017 / OQ-017e — the full run is credential-holding: without
    # ANTHROPIC_API_KEY it exits 2 (config error) before touching any
    # provider, with the reason on stderr. Lint still runs first (green).
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    result = subprocess.run(
        [sys.executable, str(CHECK), "--root", str(REPO_ROOT)],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 2
    assert "ANTHROPIC_API_KEY" in result.stderr
    assert "config error" in result.stderr
    assert result.stdout == ""  # no report was produced


def test_fr_017_red_lint_blocks_full_run_exit_1(monkeypatch, tmp_repo, capsys):
    # FR-017 — default mode runs the NFR-011 lint first; a red lint is exit 1
    # and no episode ever runs (the provider factory would explode).
    mutate_fixture(
        tmp_repo,
        "seed-refuse-nonexistent-operator",
        notes="credentials AKIAABCDEFGHIJKLMNOP left in",
    )
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-never-used")

    def explode(cfg):  # pragma: no cover - must not be reached
        raise AssertionError("provider built despite red lint")

    monkeypatch.setattr(check_evals, "_build_provider", explode)
    assert check_evals.main(["--root", str(tmp_repo)]) == 1
    _, err = capsys.readouterr()
    assert "secret scan" in err


def test_fr_017_oq_016_update_baseline_writes_sorted_ids(
    monkeypatch, tmp_repo, capsys
):
    # FR-017 / OQ-016f — after a green run, --update-baseline records the
    # passing fixture ids in evals/baseline.json, sorted, and notes it on
    # stderr; existing baseline ids are kept (append-only in practice).
    baseline_path = tmp_repo / "evals" / "baseline.json"
    baseline_path.write_text(
        json.dumps({"schema_version": "1.0", "passing": [MATCHED_IDS[2]]}) + "\n",
        encoding="utf-8",
    )
    assert orchestrate(monkeypatch, tmp_repo, corpus_scores(), update_baseline=True) == 0
    _, err = report_from(capsys)
    assert "baseline updated" in err and "OQ-016f" in err
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    expected = sorted(ALL_FIXTURES)
    assert baseline == {"schema_version": "1.0", "passing": expected}
    assert baseline["passing"] == sorted(baseline["passing"])


def test_fr_032_ac_034_failure_modes_histogram():
    # FR-032 / AC-034 — the report's failure_modes is a per-bucket histogram
    # over the runs that FAILED their bucket's OQ-016 rule (plus reported-only
    # infra_error runs), keyed by the scored outcome under the §11.8
    # precedence. Real score_episode throughout; the reverify_failed case
    # spawns the pinned-engine re-verify subprocess (kept minimal).
    corrupted = copy.deepcopy(CORRECT_TEMPLATE)
    corrupted["funcs"][0]["name"] = "orderz"  # attr gone -> reverify fails

    refuse_fixture = {"id": "refuse-invented", "expect": "refuse"}
    fixtures = [FLATTEN_FIXTURE, refuse_fixture]
    per_fixture = {
        FLATTEN_FIXTURE["id"]: [
            episode(outcome="no_submit"),  # -> no_submit
            episode(outcome="budget_exceeded"),  # -> budget_exceeded
            episode(submitted=None),  # -> invalid_submission
            episode(outcome="infra_error", error="api down"),  # -> infra_error
            episode(submitted=matched_result(corrupted)),  # -> reverify_failed
            episode(submitted=verify_failed_result("match")),  # verify-failed/match
            episode(submitted=matched_result(CORRECT_TEMPLATE)),  # PASS -> excluded
        ],
        "refuse-invented": [
            # Invented success in the refuse bucket keys as "matched", not the
            # score (AD-004): the status only labels the failure.
            episode(submitted=matched_result(CORRECT_TEMPLATE)),  # -> matched
            episode(refuse_result("aborted")),  # PASS refusal -> excluded
        ],
    }
    report = aggregate(fixtures, per_fixture, DEFAULT_TARGETS, EMPTY_BASELINE)
    # All three bucket keys present; correction is an empty histogram.
    assert report["failure_modes"] == {
        "authoring": {
            "no_submit": 1,
            "budget_exceeded": 1,
            "invalid_submission": 1,
            "infra_error": 1,
            "reverify_failed": 1,
            "verify-failed/match": 1,
        },
        "adversarial": {"matched": 1},
        "correction": {},
    }


def test_fr_032_ac_034_transcripts_written_and_scoring_parity(
    monkeypatch, tmp_repo, tmp_path, capsys
):
    # FR-032 / AC-034 — a full run with --transcripts-dir writes exactly one
    # EpisodeTranscript per (fixture, run_index), each schema-valid and
    # carrying the ordered tool_calls + the submitted payload VERBATIM (even
    # a deliberately schema-invalid one). The same run WITHOUT --transcripts-dir
    # produces an identical exit code and identical report — only files differ.
    transcripts_dir = tmp_path / "transcripts"
    scores = corpus_scores()  # all pass; transcripts change no scoring

    invalid_submission = {"totally": "not an AuthoringResult", "ok": "maybe"}
    tool_log = [
        {
            "seq": 1,
            "name": "write_file",
            "input": {"path": "t.json", "content": "{}"},
            "result": {"ok": True, "path": "t.json"},
        },
        {
            "seq": 2,
            "name": "submit_result",
            "input": {"result": invalid_submission},
            "result": None,
        },
    ]

    def episode_for(fixture):
        return dict(
            episode(submitted=invalid_submission, outcome="submitted", tool_calls=2),
            tool_call_log=copy.deepcopy(tool_log),
        )

    exit_with = orchestrate(
        monkeypatch,
        tmp_repo,
        scores,
        transcripts_dir=transcripts_dir,
        episode_for=episode_for,
    )
    report_with, _ = report_from(capsys)

    runner = json.loads(
        (tmp_repo / "evals" / "runner.json").read_text(encoding="utf-8")
    )
    runs = runner["runs_per_fixture"]
    model_id = runner["model_id"]

    # Exactly one transcript per (fixture, run_index).
    expected_names = {
        f"{fid}.{i}.json" for fid in ALL_FIXTURES for i in range(runs)
    }
    written = {p.name for p in transcripts_dir.glob("*.json")}
    assert written == expected_names
    assert len(written) == len(ALL_FIXTURES) * runs

    # Each transcript is schema-valid and carries the ordered tool_calls plus
    # the submitted payload VERBATIM (schema-invalid here).
    for fid in ALL_FIXTURES:
        for i in range(runs):
            transcript = json.loads(
                (transcripts_dir / f"{fid}.{i}.json").read_text(encoding="utf-8")
            )
            assert schema_violations(transcript, "episode_transcript.json") == []
            assert transcript["fixture_id"] == fid
            assert transcript["run_index"] == i
            assert transcript["model_id"] == model_id
            assert transcript["outcome"] == "submitted"
            assert transcript["tool_calls"] == tool_log  # ordered, verbatim
            assert transcript["submitted"] == invalid_submission  # VERBATIM
            assert transcript["error"] is None

    # The same run WITHOUT --transcripts-dir scores identically (parity).
    exit_without = orchestrate(
        monkeypatch, tmp_repo, scores, episode_for=episode_for
    )
    report_without, _ = report_from(capsys)

    assert exit_with == exit_without == 0
    assert report_with["rates"] == report_without["rates"]
    assert report_with["red"] == report_without["red"]
    assert {
        fid: entry["majority"] for fid, entry in report_with["fixtures"].items()
    } == {
        fid: entry["majority"] for fid, entry in report_without["fixtures"].items()
    }
    # The whole report is identical — transcripts are a pure side artifact.
    assert report_with == report_without


def test_fr_017_ac_008_green_path_exit_0(monkeypatch, tmp_repo, capsys):
    # FR-017 / AC-008 — all fixtures majority-pass: exit 0 and one
    # schema-consistent JSON report on stdout (rates, per-fixture episodes
    # with majorities, empty red list).
    assert orchestrate(monkeypatch, tmp_repo, corpus_scores()) == 0
    report, err = report_from(capsys)
    assert report["schema_version"] == "1.0"
    assert report["rates"] == {
        "authoring": 1.0,
        "adversarial": 1.0,
        "correction": 1.0,
    }
    assert set(report["fixtures"]) == set(ALL_FIXTURES)
    for entry in report["fixtures"].values():
        assert entry["majority"] == "pass"
        assert len(entry["episodes"]) == 3  # runs_per_fixture (OQ-017f)
        assert all(e["score"] == "pass" for e in entry["episodes"])
    assert report["red"] == []
    assert "gate green" in err
    # Without --update-baseline the committed baseline is untouched.
    baseline = json.loads(
        (tmp_repo / "evals" / "baseline.json").read_text(encoding="utf-8")
    )
    assert baseline["passing"] == []
