"""A0 DoD glue — ``python -m transon_authoring metadata`` works offline
against the pin (ROADMAP §14 A0 DoD; FR-009 / AC-006; §11.6 ``metadata`` row;
NFR-003 / AD-018 grounding).

The module entry serves the committed ``resources/metadata-snapshot.json``
bytes VERBATIM on stdout (§11.6: stdout = one JSON value), exit 0, nothing on
stderr. Any other or missing subcommand is an argparse usage error on stderr,
exit 2 (§11.6 exit codes; the JSON schema-error envelope and the remaining
subcommands are FR-014 / A1 scope).
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = REPO_ROOT / "resources" / "metadata-snapshot.json"


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "transon_authoring", *args],
        capture_output=True,
        timeout=60,
    )


def test_a0_dod_metadata_subcommand():
    # A0 DoD / FR-009 / AC-006 — `python -m transon_authoring metadata`
    # emits the bundled pinned snapshot on stdout, exit 0.
    snapshot_bytes = SNAPSHOT_PATH.read_bytes()

    result = _run_cli("metadata")
    assert result.returncode == 0
    # §11.6 global contract: stdout = one JSON value; here byte-identical to
    # the committed snapshot file (verbatim, byte-stable).
    assert result.stdout == snapshot_bytes
    # stderr = human diagnostics only; nothing on success.
    assert result.stderr == b""

    # stdout parses as JSON deep-equal to the bundled snapshot (§11.7 pin).
    emitted = json.loads(result.stdout.decode("utf-8"))
    committed = json.loads(snapshot_bytes.decode("utf-8"))
    assert emitted == committed
    assert emitted["metadata_version"] == "3.0"
    assert emitted["engine_version"] == "0.2.3"

    # §11.6 exit 2 = usage error: bogus subcommand → exit 2, empty stdout
    # (never a partial machine result on stdout).
    bogus = _run_cli("no-such-subcommand")
    assert bogus.returncode == 2
    assert bogus.stdout == b""
    assert bogus.stderr != b""

    # Missing subcommand is a usage error too.
    missing = _run_cli()
    assert missing.returncode == 2
    assert missing.stdout == b""
    assert missing.stderr != b""


def test_a0_dod_metadata_path_never_imports_engine():
    # A0 DoD / NFR-003 / AD-018 — the `metadata` answer path is grounded in
    # the bundled snapshot only: importing the CLI module in a fresh
    # interpreter must not import the live `transon` engine, so the
    # subcommand works offline with the engine unreachable at answer time.
    probe = (
        "import sys; import transon_authoring.__main__; "
        "sys.exit(1 if 'transon' in sys.modules else 0)"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
