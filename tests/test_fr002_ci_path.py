"""FR-002 / AC-014 / AC-017 / UC-003 — SampleSet-driven authoring works
non-interactively in CI (A2 slice; the AC-001 skill-loop half lands at A3).

FR-002 says authoring is driven by a SampleSet and nothing else; UC-003 is
the CI batch shape: a pre-confirmed, coverage-complete fixture SampleSet
drives ``check-samples`` -> ``verify`` end to end with **no prompt and no
config read** (§11.9 write-location note: "check-samples/verify never read
config and never prompt"). These tests run the real CLI in a subprocess with
stdin closed (non-TTY) and a poisoned environment, so a prompt regression
hangs against DEVNULL and trips the timeout instead of silently passing.

Fixtures are the committed AC-001 artifacts under tests/fixtures/ac001/
(see tests/test_ac001_path.py); all engine expectations in them were derived
by running the pinned ``transon==0.1.7`` (AD-018 / NFR-001).
"""

import copy
import json
import os
import subprocess
import sys
from pathlib import Path

from transon_authoring import check_samples

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "ac001"
SAMPLES_PATH = FIXTURES / "sample_set.json"
TEMPLATE_PATH = FIXTURES / "template.json"


def ci_env() -> dict:
    """A poisoned, CI-shaped environment: no TTY hints, CI=true, and a
    hostile TERM — none of which may make the CLI prompt or misbehave."""
    env = dict(os.environ)
    env.pop("COLUMNS", None)
    env.pop("LINES", None)
    env["CI"] = "true"
    env["TERM"] = "dumb"
    return env


def run_cli(*args: str, cwd=None) -> subprocess.CompletedProcess:
    """Run ``python -m transon_authoring`` exactly the way a CI job would:
    stdin is DEVNULL (not a TTY), so any prompt blocks forever and fails
    the 120s timeout loudly (AC-014 exercised for real)."""
    return subprocess.run(
        [sys.executable, "-m", "transon_authoring", *args],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        env=ci_env(),
        cwd=None if cwd is None else str(cwd),
        timeout=120,
    )


def one_json_document(result) -> dict:
    """§11.0/§11.6 emission discipline: stdout is exactly ONE compact JSON
    document plus a trailing newline — i.e. no prompt text ever reached
    stdout."""
    text = result.stdout.decode("utf-8")
    document = json.loads(text)
    assert text == (
        json.dumps(
            document, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    )
    return document


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_fr_002_ac_014_preconfirmed_fixture_ci_path():
    # AC-014 / UC-003: CI fixture with confirmed + coverage_complete drives
    # the whole non-interactive path — check-samples then verify, both exit 0,
    # no layout prompt (--samples given), stdout exactly one JSON document.
    check_result = run_cli("check-samples", "--samples", str(SAMPLES_PATH))
    assert check_result.returncode == 0
    check_doc = one_json_document(check_result)
    assert check_doc["coverage_complete"] is True
    assert check_doc["confirmed"] is True
    assert check_doc["ok_for_verify"] is True

    verify_result = run_cli(
        "verify", "--template", str(TEMPLATE_PATH), "--samples", str(SAMPLES_PATH)
    )
    assert verify_result.returncode == 0
    verdict = one_json_document(verify_result)
    # AD-004/AC-013: the only success shape.
    assert verdict["ok"] is True
    assert verdict["assurance"] == "matched"


def test_fr_002_ac_014_config_never_read_by_check_or_verify(tmp_path):
    # §11.9 (rev 2026-07-11): "check-samples/verify never read config and
    # never prompt". A malformed .transon-authoring.json in cwd would crash
    # any code path that parses it — both verbs must still succeed.
    (tmp_path / ".transon-authoring.json").write_text(
        "{this is not json at all", encoding="utf-8"
    )

    check_result = run_cli(
        "check-samples", "--samples", str(SAMPLES_PATH), cwd=tmp_path
    )
    assert check_result.returncode == 0
    assert one_json_document(check_result)["ok_for_verify"] is True

    verify_result = run_cli(
        "verify",
        "--template", str(TEMPLATE_PATH),
        "--samples", str(SAMPLES_PATH),
        cwd=tmp_path,
    )
    assert verify_result.returncode == 0
    verdict = one_json_document(verify_result)
    assert verdict["ok"] is True
    assert verdict["assurance"] == "matched"


def test_fr_002_ac_017_flag_independence_on_ci_fixture():
    # FR-002 + AC-017: coverage_complete and confirmed are INDEPENDENT flags
    # and both are required for ok_for_verify. Flipping only the user
    # confirmation on the otherwise coverage-complete CI fixture must leave
    # coverage_complete true while confirmed and ok_for_verify go false.
    ss = copy.deepcopy(load(SAMPLES_PATH))
    ss["confirmation"]["confirmed"] = False
    check = check_samples(ss)
    assert check["coverage_complete"] is True
    assert check["confirmed"] is False
    assert check["ok_for_verify"] is False
