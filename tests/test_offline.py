"""NFR-003 / AC-020 — offline after install, across the whole A1 surface.

SPEC §8 NFR-003: no network required for verify/check/metadata once the pinned
engine and package are installed (local package import and optional local
worker subprocesses only). §9 AC-020: with network disabled post-install,
`metadata` / `check-samples` / `verify` still work.

Three layers of guarantee, weakest to strongest:

1. **In-process** (here): the library surface runs to completion with the
   host's socket layer patched to raise — any in-process network attempt in
   `get_metadata` / `search_examples` / `check_samples` / `verify` fails loudly.
2. **Subprocess sanity** (here): the §11.6 CLI verbs succeed with every proxy
   variable pointed at an unroutable address — pure-stdlib code that never
   talks to the network is unaffected; anything that consulted the proxies
   would fail fast. Honest scope: a sanity check, not a hard cutoff.
3. **Hard guarantee** (CI): the dedicated `offline` job in
   `.github/workflows/ci.yml` runs the same verbs — and this whole file —
   inside `unshare -rn`, a user+network namespace with no usable interfaces.

Related, NOT duplicated here: tests/test_authority.py
`test_nfr_001_no_network_imports_in_product_code` (static no-network-imports
guard over all product modules, which covers the worker's code too) and
tests/test_sandbox.py `test_ac_015_no_network_host_socket_blocked` (dry-run
host path under a socket block).

Fixtures are the committed files under tests/fixtures/offline/ — the same
files the CI job uses (see the README there for OQ-015 regeneration rules).
"""

import json
import os
import socket
import subprocess
import sys
from pathlib import Path

import pytest

from transon_authoring import check_samples, verify
from transon_authoring.examples import search_examples
from transon_authoring.metadata import get_metadata

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "offline"

#: Every proxy variable an http client would consult (both cases), pointed at
#: an unroutable address: TCP port 1 on localhost is never listening, so any
#: proxied connection attempt fails immediately instead of hanging.
UNROUTABLE_PROXY_ENV = {
    name: "http://127.0.0.1:1"
    for name in (
        "http_proxy",
        "https_proxy",
        "all_proxy",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "ALL_PROXY",
    )
}


def fixture_path(name: str) -> str:
    return str(FIXTURES / name)


def load_fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Layer 1 — in-process: socket layer patched to raise (NFR-003)
# ---------------------------------------------------------------------------


@pytest.fixture
def no_network(monkeypatch):
    """Block network at the socket layer for THIS process (NFR-003).

    Scope caveat, deliberate: `verify` runs each dry-run case in a sandboxed
    WORKER SUBPROCESS (src/transon_authoring/_worker.py, host in verify.py) —
    an in-process patch cannot reach it, and per NFR-003 local worker
    subprocesses are explicitly allowed. The subprocess-level guarantee is the
    CI `offline` job's role (network namespace covers children too), backed by
    the static no-network-imports guard in tests/test_authority.py.
    """

    def _blocked(*args, **kwargs):
        raise AssertionError(
            "NFR-003 violated: in-process network access attempted"
        )

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


def test_nfr_003_get_metadata_offline(no_network):
    # NFR-003: the pinned snapshot is served from the bundled resource — no
    # network. Sanity-check the document is the engine metadata shape.
    snapshot = get_metadata()
    assert isinstance(snapshot, dict) and snapshot


def test_nfr_003_search_examples_offline(no_network):
    # NFR-003 / AC-022: hits come from the bundled snapshot corpus offline.
    hits = search_examples("join")
    assert isinstance(hits, list) and hits


def test_nfr_003_check_samples_offline(no_network):
    # NFR-003 / AC-020: the committed confirmed fixture passes check_samples
    # end-to-end with the socket layer blocked.
    result = check_samples(load_fixture("sample_set.json"))
    assert result["ok_for_verify"] is True
    assert result["gaps"] == []


def test_ac_020_verify_matched_offline(no_network):
    # AC-020 / NFR-003 — end-to-end: samples → validate → dry_run → match to
    # `assurance: "matched"` with the host socket layer blocked. The dry-run
    # stage spawns local worker subprocesses (pipes only, allowed by NFR-003);
    # see the `no_network` fixture docstring for why the patch stops here.
    verdict = verify(load_fixture("template.json"), load_fixture("sample_set.json"))
    assert verdict["ok"] is True
    assert verdict["assurance"] == "matched"


# ---------------------------------------------------------------------------
# Layer 2 — subprocess sanity: CLI verbs under unroutable proxies (AC-020)
# ---------------------------------------------------------------------------


def _offline_env() -> dict:
    """Child env for the CLI: no PYTHONSTARTUP (nothing injected at
    interpreter startup), every proxy variable unroutable."""
    env = dict(os.environ)
    env.pop("PYTHONSTARTUP", None)
    env.pop("no_proxy", None)  # nothing may bypass the unroutable proxies
    env.pop("NO_PROXY", None)
    env.update(UNROUTABLE_PROXY_ENV)
    return env


def run_cli_offline(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "transon_authoring", *args],
        capture_output=True,
        timeout=120,
        env=_offline_env(),
    )


@pytest.mark.subprocess
def test_ac_020_cli_verbs_offline_with_unroutable_proxies():
    # AC-020 sanity check (the hard guarantee is the CI `offline` job): every
    # §11.6 verb succeeds while http_proxy/https_proxy/all_proxy point at an
    # unroutable address — pure-stdlib code that never talks to the network is
    # unaffected; anything that consulted the proxies would fail fast.
    result = run_cli_offline("metadata")
    assert result.returncode == 0
    assert json.loads(result.stdout.decode("utf-8"))  # snapshot document

    result = run_cli_offline("examples", "search", "join")
    assert result.returncode == 0
    assert json.loads(result.stdout.decode("utf-8"))["hits"]

    result = run_cli_offline(
        "check-samples", "--samples", fixture_path("sample_set.json")
    )
    assert result.returncode == 0
    assert json.loads(result.stdout.decode("utf-8"))["ok_for_verify"] is True

    # verify spawns the sandboxed worker subprocess, which inherits the same
    # unroutable-proxy env — the whole process tree runs "offline".
    result = run_cli_offline(
        "verify",
        "--template",
        fixture_path("template.json"),
        "--samples",
        fixture_path("sample_set.json"),
    )
    assert result.returncode == 0
    verdict = json.loads(result.stdout.decode("utf-8"))
    assert verdict["ok"] is True
    assert verdict["assurance"] == "matched"

    result = run_cli_offline(
        "dry-run",
        "--template",
        fixture_path("template.json"),
        "--input",
        fixture_path("input.json"),
    )
    assert result.returncode == 0
    envelope = json.loads(result.stdout.decode("utf-8"))
    assert envelope["ok"] is True
    assert envelope["result"] == "hello"
