"""NFR-004 / AC-006 / OQ-021 — `check_snapshot` drift gate.

`check_snapshot` must fail when the bundled snapshot differs from
`get_editor_metadata()` under the pinned `transon==0.2.3` (SPEC §8 NFR-004,
§9 AC-006, §11.7 pin/drift) and must enforce the OQ-021 sidecar consistency
rules (ROADMAP §15). It never tracks unpinned newer releases (AD-007) and never
compares `synced_at` (determinism, FR-011).

The gate is run via subprocess with the interpreter pytest runs under (the
repo .venv, which has the pinned engine), so exit codes are observed exactly
as CI would see them.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
CHECK = REPO_ROOT / "scripts" / "check_snapshot.py"
SYNC = REPO_ROOT / "scripts" / "sync_metadata.py"

CANONICAL_KWARGS = dict(ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)

PYPROJECT_PINNED = """\
[project]
name = "tmp-check-target"
version = "0.0.0"
dependencies = ["transon==0.2.3"]
"""


def run_check(root: Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CHECK), "--root", str(root), *extra],
        capture_output=True,
        text=True,
    )


def provenance_block(md_text: str) -> dict:
    """Extract the single fenced ```json block from the provenance markdown."""
    blocks = re.findall(r"```json\n(.*?)```", md_text, flags=re.DOTALL)
    assert len(blocks) == 1, f"expected exactly one fenced json block, got {len(blocks)}"
    return json.loads(blocks[0])


@pytest.fixture
def synced_root(tmp_path: Path) -> Path:
    """A tmp repo root freshly synced by the real sync_metadata.py (FR-011)."""
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_PINNED, encoding="utf-8")
    result = subprocess.run(
        [sys.executable, str(SYNC), "--root", str(tmp_path)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return tmp_path


def test_nfr_004_ac_006_fresh_sync_is_green(synced_root: Path):
    # NFR-004 / AC-006 / OQ-021 — freshly synced root passes the gate.
    result = run_check(synced_root)
    assert result.returncode == 0, result.stderr
    assert "FAIL" not in result.stderr


def test_nfr_004_ac_006_drift_gate(synced_root: Path):
    # NFR-004 / AC-006 / OQ-021 — one changed byte in the bundle → gate red.
    snapshot_path = synced_root / "resources" / "metadata-snapshot.json"
    original = snapshot_path.read_bytes()
    # Flip one byte inside a value, keeping the JSON parseable so the byte
    # comparison itself (not a parse error) is what trips the gate.
    drifted = original.replace(b'"metadata_version": "3.0"', b'"metadata_version": "3.1"', 1)
    assert drifted != original
    snapshot_path.write_bytes(drifted)

    result = run_check(synced_root)
    assert result.returncode == 1
    # AC-006 wording: the bundle drifted from the pinned engine; remediation
    # is sync-metadata.
    assert "drift" in result.stderr
    assert "sync" in result.stderr


def test_nfr_004_stale_provenance_snapshot_hash_is_red(synced_root: Path):
    # NFR-004 / AC-006 / OQ-021 — provenance snapshot_sha256 must match the
    # actual snapshot bytes.
    provenance_path = synced_root / "resources" / "metadata-snapshot.md"
    md_text = provenance_path.read_text(encoding="utf-8")
    prov = provenance_block(md_text)
    stale = md_text.replace(prov["snapshot_sha256"], "0" * 64)
    assert stale != md_text
    provenance_path.write_text(stale, encoding="utf-8")

    result = run_check(synced_root)
    assert result.returncode == 1
    assert "snapshot_sha256" in result.stderr


def test_nfr_004_oq_021_dangling_sidecar_key_is_red(synced_root: Path):
    # NFR-004 / AC-006 / OQ-021(b) — an intents key that is not a snapshot
    # docs.examples name is a failure, listed on stderr.
    sidecar_path = synced_root / "resources" / "nl-intents.json"
    provenance_path = synced_root / "resources" / "metadata-snapshot.md"

    old_bytes = sidecar_path.read_bytes()
    sidecar = json.loads(old_bytes.decode("utf-8"))
    sidecar["intents"]["NotARealExample"] = {"nl": "does not exist in the snapshot"}
    new_bytes = (json.dumps(sidecar, **CANONICAL_KWARGS) + "\n").encode("utf-8")
    sidecar_path.write_bytes(new_bytes)

    # Re-record the sidecar hash in the provenance so ONLY the dangling-key
    # check (OQ-021 b) fires, not the sidecar_sha256 check (OQ-021 d).
    md_text = provenance_path.read_text(encoding="utf-8")
    md_text = md_text.replace(
        hashlib.sha256(old_bytes).hexdigest(), hashlib.sha256(new_bytes).hexdigest()
    )
    provenance_path.write_text(md_text, encoding="utf-8")

    result = run_check(synced_root)
    assert result.returncode == 1
    assert "NotARealExample" in result.stderr
    assert "sidecar_sha256" not in result.stderr


def test_nfr_004_oq_021_uncovered_examples_stay_green_with_count(synced_root: Path):
    # NFR-004 / AC-006 / OQ-021(c) — the fresh-sync sidecar skeleton is empty,
    # so every snapshot example is uncovered: gate stays green but reports the
    # count on stderr; the full sorted name list appears only under --verbose.
    snapshot = json.loads(
        (synced_root / "resources" / "metadata-snapshot.json").read_text(encoding="utf-8")
    )
    names = sorted(example["name"] for example in snapshot["docs"]["examples"])
    assert names, "pinned snapshot must have docs.examples"

    quiet = run_check(synced_root)
    assert quiet.returncode == 0, quiet.stderr
    assert str(len(names)) in quiet.stderr
    assert "uncovered" in quiet.stderr
    assert names[0] not in quiet.stderr  # names only under --verbose

    verbose = run_check(synced_root, "--verbose")
    assert verbose.returncode == 0, verbose.stderr
    for name in names:
        assert name in verbose.stderr


def test_fr_036_reference_drift_red(synced_root: Path):
    # FR-036 / AC-039(b) — one changed byte in the bundled Language Reference
    # → gate red with the drift diagnostic (same discipline as the metadata
    # snapshot).
    reference_path = synced_root / "resources" / "language-reference.json"
    original = reference_path.read_bytes()
    drifted = original.replace(
        b'"engine_version": "0.2.3"', b'"engine_version": "0.2.4"', 1
    )
    assert drifted != original
    reference_path.write_bytes(drifted)

    result = run_check(synced_root)
    assert result.returncode == 1
    assert "language-reference.json" in result.stderr
    assert "drift" in result.stderr


def test_ac_039_reference_provenance_stale_red(synced_root: Path):
    # FR-036 / AC-039(b) — provenance reference_sha256 must match the actual
    # language-reference.json bytes.
    provenance_path = synced_root / "resources" / "metadata-snapshot.md"
    md_text = provenance_path.read_text(encoding="utf-8")
    prov = provenance_block(md_text)
    stale = md_text.replace(prov["reference_sha256"], "0" * 64)
    assert stale != md_text
    provenance_path.write_text(stale, encoding="utf-8")

    result = run_check(synced_root)
    assert result.returncode == 1
    assert "reference_sha256" in result.stderr


def test_ac_039_unsupported_reference_major_red(synced_root: Path):
    # FR-036 / AC-039(b) — a bundled reference_version whose major exceeds the
    # supported major (1) is red; consumers MUST fail loudly on an unsupported
    # major.
    reference_path = synced_root / "resources" / "language-reference.json"
    provenance_path = synced_root / "resources" / "metadata-snapshot.md"

    reference = json.loads(reference_path.read_bytes().decode("utf-8"))
    reference["reference_version"] = "2.0"
    new_bytes = (json.dumps(reference, **CANONICAL_KWARGS) + "\n").encode("utf-8")
    reference_path.write_bytes(new_bytes)

    md_text = provenance_path.read_text(encoding="utf-8")
    prov = provenance_block(md_text)
    md_text = md_text.replace(
        prov["reference_sha256"], hashlib.sha256(new_bytes).hexdigest()
    )
    md_text = md_text.replace(
        '"reference_version": "1.0"', '"reference_version": "2.0"'
    )
    provenance_path.write_text(md_text, encoding="utf-8")

    result = run_check(synced_root)
    assert result.returncode == 1
    assert "major" in result.stderr


def test_nfr_004_off_pin_root_is_red(synced_root: Path):
    # NFR-004 — installed engine != pyproject pin is red; the gate never
    # tracks unpinned newer releases (AD-007), only the pin itself.
    pyproject = synced_root / "pyproject.toml"
    pyproject.write_text(
        PYPROJECT_PINNED.replace("transon==0.2.3", "transon==9.9.9"), encoding="utf-8"
    )
    result = run_check(synced_root)
    assert result.returncode == 1
    assert "9.9.9" in result.stderr
    assert "0.2.3" in result.stderr


def test_nfr_004_repo_root_is_green():
    # NFR-004 / AC-006 — A0 DoD: check_snapshot green on the real repo root.
    result = run_check(REPO_ROOT)
    assert result.returncode == 0, result.stderr


def test_nfr_004_unreadable_pyproject_is_gate_failure_not_crash(tmp_path: Path):
    # NFR-004 / §11.7 — read_pin must return a descriptive failure when
    # pyproject.toml exists but cannot be decoded, so check_snapshot reports
    # a gate failure (exit 1) instead of crashing with a traceback.
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe not utf-8")
    result = run_check(tmp_path)
    assert result.returncode == 1
    assert "cannot read" in result.stderr
    assert "Traceback" not in result.stderr


def test_read_pin_returns_error_on_undecodable_or_missing(tmp_path: Path):
    # Unit: read_pin (NFR-004) — missing file, bad UTF-8, and no-pin cases.
    from transon_authoring._snapshot import read_pin

    pin, err = read_pin(tmp_path)
    assert pin is None
    assert err is not None and "no pyproject.toml" in err

    bad = tmp_path / "pyproject.toml"
    bad.write_bytes(b"\xff\xfe")
    pin, err = read_pin(tmp_path)
    assert pin is None
    assert err is not None and "cannot read" in err

    bad.write_text("[project]\ndependencies = []\n", encoding="utf-8")
    pin, err = read_pin(tmp_path)
    assert pin is None
    assert err is not None and "transon==" in err
