"""NFR-011 / AC-025 — `check_evals --lint` fixture privacy lint (FR-018 A2 slice).

Per-PR CI runs `check_evals --lint` (SPEC §15 OQ-017e; the §13 check_evals
row carries the NFR-011 lint). The lint is credential-free, engine-free and
deterministic: it validates the committed eval-policy files and every
`evals/cases/*.json` fixture against the bundled schemas (AD-020), enforces
id/filename agreement and baseline references (OQ-016f), requires supplied
SampleSets to be `ok_for_verify` (FR-027 / OQ-017a), enforces the NFR-011
consent⇒redaction invariant (FR-018), and red-flags obvious secrets in raw
fixture bytes (AC-025).

Tests drive both the importable `lint_evals()` and the CLI via subprocess on
tmp eval trees copied from the committed `evals/` corpus. The full eval-run
mode is FR-017 (parallel work): invoking without `--lint` must exit 2.
"""

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK = REPO_ROOT / "scripts" / "check_evals.py"

sys.path.insert(0, str(REPO_ROOT / "scripts"))
from check_evals import lint_evals  # noqa: E402


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


def test_nfr_011_full_run_mode_not_yet_implemented_exit_2():
    # FR-017 boundary — the full-run mode is not in this slice; invoking
    # without --lint exits 2 with a pointer to FR-017 on stderr.
    result = run_check("--root", str(REPO_ROOT))
    assert result.returncode == 2
    assert "not yet implemented" in result.stderr
    assert "FR-017" in result.stderr
