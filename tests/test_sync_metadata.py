"""FR-011 / AC-006 — `sync-metadata` regenerates the snapshot from the pinned
engine and records provenance (SPEC §7 Grounding & corpus, §11.7 pin/drift,
OQ-021 sidecar/provenance interplay).

The script under test is run via subprocess with the same interpreter pytest
runs under (the repo .venv, which has the pinned ``transon==0.1.7``), so exit
codes are observed exactly as CI would see them.
"""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "sync_metadata.py"

CANONICAL_KWARGS = dict(ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False)

PYPROJECT_PINNED = """\
[project]
name = "tmp-sync-target"
version = "0.0.0"
dependencies = ["transon==0.1.7"]
"""

PYPROJECT_MISMATCHED = PYPROJECT_PINNED.replace("transon==0.1.7", "transon==9.9.9")


def run_sync(root: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root)],
        capture_output=True,
        text=True,
    )


def provenance_block(md_text: str) -> dict:
    """Extract the single fenced ```json block from the provenance markdown."""
    blocks = re.findall(r"```json\n(.*?)```", md_text, flags=re.DOTALL)
    assert len(blocks) == 1, f"expected exactly one fenced json block, got {len(blocks)}"
    return json.loads(blocks[0])


@pytest.fixture
def tmp_root(tmp_path: Path) -> Path:
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_PINNED, encoding="utf-8")
    return tmp_path


def test_fr_011_sync_is_canonical_and_records_provenance(tmp_root: Path):
    # FR-011 / AC-006
    first = run_sync(tmp_root)
    assert first.returncode == 0, first.stderr
    snapshot_path = tmp_root / "resources" / "metadata-snapshot.json"
    sidecar_path = tmp_root / "resources" / "nl-intents.json"
    provenance_path = tmp_root / "resources" / "metadata-snapshot.md"
    first_bytes = snapshot_path.read_bytes()

    second = run_sync(tmp_root)
    assert second.returncode == 0, second.stderr
    second_bytes = snapshot_path.read_bytes()

    # Atomic publication leaves no temp-file litter next to the outputs.
    litter = [p.name for p in (tmp_root / "resources").iterdir() if ".tmp-" in p.name]
    assert litter == []

    # Deterministic, canonical serialization: identical bytes across runs,
    # trailing LF, and a byte-exact round trip through the canonical dump.
    assert first_bytes == second_bytes
    assert first_bytes.endswith(b"\n")
    assert b"\r" not in first_bytes
    snapshot = json.loads(first_bytes.decode("utf-8"))
    recanonical = (json.dumps(snapshot, **CANONICAL_KWARGS) + "\n").encode("utf-8")
    assert first_bytes == recanonical

    # Snapshot comes from the pinned engine (SPEC §11.7 A0 pin).
    assert snapshot["engine_version"] == "0.1.7"
    assert snapshot["metadata_version"] == "3.0"

    # Provenance records content hashes over the exact file bytes.
    prov = provenance_block(provenance_path.read_text(encoding="utf-8"))
    assert prov["schema_version"] == "1.0"
    assert prov["engine_version"] == "0.1.7"
    assert prov["metadata_version"] == "3.0"
    assert prov["algorithm"] == "sha256"
    assert prov["snapshot_sha256"] == hashlib.sha256(first_bytes).hexdigest()
    assert prov["sidecar_sha256"] == hashlib.sha256(sidecar_path.read_bytes()).hexdigest()
    # synced_at is informational only (never gate-compared) but must be UTC ISO-8601 Z.
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", prov["synced_at"])


def test_fr_011_sidecar_skeleton_created_when_absent(tmp_root: Path):
    # FR-011 / AC-006 — fresh sync creates the FR-010 sidecar skeleton.
    result = run_sync(tmp_root)
    assert result.returncode == 0, result.stderr
    sidecar_bytes = (tmp_root / "resources" / "nl-intents.json").read_bytes()
    assert sidecar_bytes.endswith(b"\n")
    assert json.loads(sidecar_bytes.decode("utf-8")) == {
        "schema_version": "1.0",
        "intents": {},
    }


def test_fr_011_existing_sidecar_never_overwritten(tmp_root: Path):
    # FR-011 / AC-006 — re-sync must not clobber authored NL intents (OQ-021).
    resources = tmp_root / "resources"
    resources.mkdir()
    existing = (
        json.dumps(
            {
                "schema_version": "1.0",
                "intents": {"flatten-orders": {"nl": "flatten each order's line items"}},
            },
            **CANONICAL_KWARGS,
        )
        + "\n"
    ).encode("utf-8")
    sidecar_path = resources / "nl-intents.json"
    sidecar_path.write_bytes(existing)

    result = run_sync(tmp_root)
    assert result.returncode == 0, result.stderr
    assert sidecar_path.read_bytes() == existing

    prov = provenance_block(
        (resources / "metadata-snapshot.md").read_text(encoding="utf-8")
    )
    assert prov["sidecar_sha256"] == hashlib.sha256(existing).hexdigest()


def test_fr_011_pin_mismatch_exits_2(tmp_path: Path):
    # FR-011 / AC-006 — installed engine must equal the pyproject pin.
    (tmp_path / "pyproject.toml").write_text(PYPROJECT_MISMATCHED, encoding="utf-8")
    result = run_sync(tmp_path)
    assert result.returncode == 2
    assert "9.9.9" in result.stderr
    assert "0.1.7" in result.stderr
    # Nothing gets written on pin mismatch.
    assert not (tmp_path / "resources").exists()


def test_fr_011_undecodable_pyproject_exits_2(tmp_path: Path):
    # FR-011 / §11.7 — an unreadable pyproject is a config error (exit 2),
    # never a traceback (read_pin catches OSError/UnicodeDecodeError).
    (tmp_path / "pyproject.toml").write_bytes(b"\xff\xfe not utf-8")
    result = run_sync(tmp_path)
    assert result.returncode == 2
    assert "cannot read" in result.stderr
    assert "Traceback" not in result.stderr
    assert not (tmp_path / "resources").exists()


def test_fr_011_missing_engine_exits_2(tmp_root: Path, monkeypatch, capsys):
    # FR-011 / AC-006 — a missing pinned engine is a pin/config error (exit 2
    # with a diagnostic on stderr), never a traceback.
    import importlib.metadata
    import importlib.util

    # The script does `from _shared import ...`, which resolves via sys.path
    # when run as a subprocess (script dir is prepended automatically) but not
    # under spec_from_file_location — prepend it so this file passes in isolation.
    monkeypatch.syspath_prepend(str(SCRIPT.parent))
    spec = importlib.util.spec_from_file_location("sync_metadata_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def missing(_name: str) -> str:
        raise importlib.metadata.PackageNotFoundError("transon")

    monkeypatch.setattr(module, "installed_version", missing)
    assert module.main(["--root", str(tmp_root)]) == 2
    stderr = capsys.readouterr().err
    assert "not installed" in stderr
    assert "0.1.7" in stderr
    assert not (tmp_root / "resources").exists()
