"""FR-021 / AC-029 / AC-017 — persisting a SampleSet (§11.1) and confirming
it via the OQ-015 acquisition path (schema-testable half of the OQ-023 split).

A SampleSet written per §11.1 with `confirmation` set from the fingerprint
obtained via `SampleCheck.content_fingerprint` (never hand-computed — OQ-015
acquisition path) round-trips through disk and yields `check_samples` →
`confirmed: true`; any subsequent edit to the hashed content subset flips it
back via `fingerprint_mismatch`, while `intent_nl` edits do not (§11.1
Confirmation comment). `coverage_complete` stays independent (AC-017).

Everything here is deterministic library/CLI behavior (NFR-002); no engine
execution is involved. The CLI acquisition route runs as a real subprocess
(`sys.executable -m transon_authoring check-samples`), like tests/test_cli_a1.py.
"""

import copy
import json
import subprocess
import sys

from transon_authoring import check_samples
from transon_authoring.samples import content_fingerprint


def unconfirmed_sample_set():
    """§11.1 SampleSet, complete coverage, pre-confirmation state: placeholder
    fingerprint "" (OQ-018a) and `confirmed: false`."""
    return {
        "schema_version": "1.0",
        "intent_nl": "extract the greeting attribute",
        "coverage": [
            {
                "id": "happy",
                "kind": "happy_path",
                "description": "happy path",
                "acceptance": "accepted",
            }
        ],
        "cases": [
            {
                "id": "c1",
                "input": {"x": "héllo"},
                "output": "héllo",
                "satisfies": ["happy"],
            }
        ],
        "waivers": [],
        "confirmation": {"confirmed": False, "content_fingerprint": ""},
    }


def confirm_via_acquisition_path(ss):
    """OQ-015 acquisition path: run check_samples on the not-yet-confirmed
    SampleSet and copy SampleCheck.content_fingerprint into the confirmation —
    the fingerprint is never hand-computed here."""
    check = check_samples(ss)
    assert check["confirmed"] is False  # unconfirmed input
    confirmed = copy.deepcopy(ss)
    confirmed["confirmation"] = {
        "confirmed": True,
        "confirmed_by": "user",
        "content_fingerprint": check["content_fingerprint"],
    }
    return confirmed


def round_trip(tmp_path, document, name="samples.json"):
    """Persist with plain json.dump and re-load (FR-021 disk round trip)."""
    path = tmp_path / name
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(document, fh, ensure_ascii=False)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def gap_codes(check):
    return [gap["code"] for gap in check["gaps"]]


def test_fr_021_ac_029_persisted_confirmation_round_trips(tmp_path):
    ss = unconfirmed_sample_set()

    # Pre-confirmation state: placeholder fingerprint "" is not a mismatch
    # against nothing special — check reports unconfirmed + fingerprint_mismatch
    # per OQ-018a/b — but the SampleCheck still carries the recomputed value.
    before = check_samples(ss)
    assert before["confirmed"] is False
    assert "unconfirmed" in gap_codes(before)
    assert before["content_fingerprint"] != ""

    confirmed = confirm_via_acquisition_path(ss)
    reloaded = round_trip(tmp_path, confirmed)
    assert reloaded == confirmed  # §11.1 persistence is faithful

    after = check_samples(reloaded)
    assert after["confirmed"] is True  # AC-029
    assert after["coverage_complete"] is True
    assert after["ok_for_verify"] is True  # complete coverage + confirmed
    assert after["gaps"] == []


def test_ac_029_content_edit_flips_fingerprint_mismatch(tmp_path):
    confirmed = confirm_via_acquisition_path(unconfirmed_sample_set())
    reloaded = round_trip(tmp_path, confirmed)

    # Edit a hashed-subset field (a case output): confirmation is invalidated.
    edited = copy.deepcopy(reloaded)
    edited["cases"][0]["output"] = "tampered"
    check = check_samples(edited)
    assert check["confirmed"] is False  # AC-029: flips back
    assert "fingerprint_mismatch" in gap_codes(check)
    assert check["ok_for_verify"] is False

    # Editing intent_nl only does NOT invalidate (§11.1 Confirmation comment:
    # intent_nl is deliberately excluded from the hashed subset).
    prose_only = copy.deepcopy(reloaded)
    prose_only["intent_nl"] = "completely rewritten human prose"
    check = check_samples(prose_only)
    assert check["confirmed"] is True
    assert "fingerprint_mismatch" not in gap_codes(check)
    assert check["ok_for_verify"] is True


def test_fr_021_oq_015_fingerprint_only_from_sample_check():
    ss = unconfirmed_sample_set()

    # Acquisition path (OQ-015, normative): the exit-1/unconfirmed SampleCheck
    # still carries the recomputed fingerprint — that field is THE source.
    check = check_samples(ss)
    assert check["confirmed"] is False
    assert check["ok_for_verify"] is False
    acquired = check["content_fingerprint"]
    assert isinstance(acquired, str) and acquired != ""

    # The single implementation agrees with what the SampleCheck carries; the
    # test (like agents/skill) treats the SampleCheck field as the source and
    # never recomputes it for confirmation.
    assert acquired == content_fingerprint(ss)

    confirmed = copy.deepcopy(ss)
    confirmed["confirmation"] = {
        "confirmed": True,
        "confirmed_by": "user",
        "content_fingerprint": acquired,
    }
    assert check_samples(confirmed)["confirmed"] is True


def test_fr_021_oq_015_cli_acquisition_route(tmp_path):
    # The CLI acquisition route (§11.6): `check-samples` on the unconfirmed
    # SampleSet exits 1 (semantic failure) but the SampleCheck envelope still
    # carries the recomputed content_fingerprint to copy at confirmation time.
    ss = unconfirmed_sample_set()
    path = tmp_path / "unconfirmed.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(ss, fh, ensure_ascii=False)
    result = subprocess.run(
        [sys.executable, "-m", "transon_authoring", "check-samples",
         "--samples", str(path)],
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 1
    envelope = json.loads(result.stdout.decode("utf-8"))
    assert envelope["confirmed"] is False
    acquired = envelope["content_fingerprint"]
    assert isinstance(acquired, str) and acquired != ""

    confirmed = copy.deepcopy(ss)
    confirmed["confirmation"] = {
        "confirmed": True,
        "confirmed_by": "user",
        "content_fingerprint": acquired,  # copied verbatim from the envelope
    }
    assert check_samples(confirmed)["confirmed"] is True


def test_fr_021_ac_017_confirmation_alone_insufficient(tmp_path):
    # AC-017 independence: confirmed:true with INCOMPLETE coverage never
    # yields ok_for_verify. Add an accepted obligation no case satisfies.
    ss = unconfirmed_sample_set()
    ss["coverage"].append(
        {
            "id": "opt",
            "kind": "optional_present",
            "target": "/y",
            "description": "optional y present",
            "acceptance": "accepted",
        }
    )
    confirmed = confirm_via_acquisition_path(ss)
    check = check_samples(round_trip(tmp_path, confirmed))
    assert check["confirmed"] is True  # confirmation half holds
    assert check["coverage_complete"] is False  # coverage half fails
    assert check["ok_for_verify"] is False  # AC-017: both are required
    assert "optional_present_unmet" in gap_codes(check)
