"""NFR-004 / AC-006 / OQ-021 — `check_snapshot` drift gate.

`check_snapshot` must fail when the bundled snapshot differs from
`get_editor_metadata()` under the pinned `transon==0.1.7` (SPEC §8 NFR-004,
§9 AC-006, §11.7 pin/drift) and must enforce the OQ-021 sidecar consistency
rules (SPEC §15). It never tracks unpinned newer releases (AD-007) and never
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
dependencies = ["transon==0.1.7"]
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


def test_nfr_004_off_pin_root_is_red(synced_root: Path):
    # NFR-004 — installed engine != pyproject pin is red; the gate never
    # tracks unpinned newer releases (AD-007), only the pin itself.
    pyproject = synced_root / "pyproject.toml"
    pyproject.write_text(
        PYPROJECT_PINNED.replace("transon==0.1.7", "transon==9.9.9"), encoding="utf-8"
    )
    result = run_check(synced_root)
    assert result.returncode == 1
    assert "9.9.9" in result.stderr
    assert "0.1.7" in result.stderr


def test_nfr_004_repo_root_is_green():
    # NFR-004 / AC-006 — A0 DoD: check_snapshot green on the real repo root.
    result = run_check(REPO_ROOT)
    assert result.returncode == 0, result.stderr
