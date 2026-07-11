"""AC-015 — dry-run sandbox invariants (FR-028; SPEC §11.3 profile table
AD-015/AD-017; NFR-003 groundwork): no real FS or network, in-memory write
capture (last write wins), includes resolved from the request map only,
engine-verbatim include-miss errors.

Engine-behavior expectations are derived by *running* the pinned engine
(``transon==0.1.7``) in-process, never from memory (AD-018 / NFR-001).
"""

import socket

from transon_authoring import dry_run

TAG_KEY = "$transon_authoring"
NO_CONTENT_REF = {TAG_KEY: "NO_CONTENT"}


def _assert_dir_untouched(tmp_path):
    assert list(tmp_path.iterdir()) == [], "dry-run touched the real filesystem"


# ---------------------------------------------------------------------------
# `file` rule: in-memory capture, never the FS (AD-015)
# ---------------------------------------------------------------------------


def test_ac_015_file_writes_captured_no_fs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # any real write would land here
    template = [
        {"$": "file", "name": "out.json", "content": {"$": "this"}},
        {"$": "file", "name": "meta.json", "content": "static"},
    ]
    envelope = dry_run(template, {"x": 1})
    assert envelope["ok"] is True
    assert envelope["writes"] == {"out.json": {"x": 1}, "meta.json": "static"}
    # `file` produces no result; the top-level list carries two sentinels (§11.0 enc).
    assert envelope["result"] == [NO_CONTENT_REF, NO_CONTENT_REF]
    _assert_dir_untouched(tmp_path)


def test_ac_015_duplicate_write_name_last_write_wins(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    template = [
        {"$": "file", "name": "out.json", "content": "first"},
        {"$": "file", "name": "out.json", "content": "second"},
    ]
    envelope = dry_run(template, None)
    assert envelope["ok"] is True
    assert envelope["writes"] == {"out.json": "second"}
    _assert_dir_untouched(tmp_path)


# ---------------------------------------------------------------------------
# `include`: resolved from the request map ONLY (AD-017)
# ---------------------------------------------------------------------------


def test_ac_015_include_resolved_from_map_only():
    template = {"$": "include", "name": "sub"}
    includes = {"sub": {"wrapped": {"$": "this"}}}
    envelope = dry_run(template, 42, includes)
    assert envelope == {
        "ok": True,
        "result": {"wrapped": 42},
        "writes": {},
        "errors": [],
    }


def test_ac_015_include_miss_verbatim_engine_definition_error():
    # AD-018: derive the expected message from the pinned engine's own default
    # loader (`no_template_loader`) — the worker's miss path must be verbatim.
    from transon.transformers import DefinitionError, Transformer

    template = {"$": "include", "name": "nope"}
    try:
        Transformer(template).transform(None, no_content=Transformer.NO_CONTENT)
        raise AssertionError("engine did not raise for include miss")
    except DefinitionError as exc:
        engine_message = str(exc)
    assert "template with name `nope` was not found" in engine_message

    envelope = dry_run(template, None, {"other": {"$": "this"}})
    assert envelope["ok"] is False
    (error,) = envelope["errors"]
    assert error["type"] == "DefinitionError"
    assert error["engine_type"] == "DefinitionError"
    assert error["message"] == engine_message


def test_ac_015_include_loaded_subtemplate_writes_captured(tmp_path, monkeypatch):
    # The include-loaded sub-template shares the same in-memory write capture.
    monkeypatch.chdir(tmp_path)
    template = {"$": "include", "name": "sub"}
    includes = {
        "sub": {"$": "file", "name": "from-sub.json", "content": {"$": "this"}}
    }
    envelope = dry_run(template, {"payload": True}, includes)
    assert envelope["ok"] is True
    assert envelope["writes"] == {"from-sub.json": {"payload": True}}
    # `file` yields NO_CONTENT; `include` without `default` passes it through.
    assert envelope["result"] == NO_CONTENT_REF
    _assert_dir_untouched(tmp_path)


def test_ac_015_nested_include_shares_write_capture(tmp_path, monkeypatch):
    # Two include hops: the IncludeContext-built sub-transformer inherits the
    # sandbox loader (so `b` still resolves from the map) and every hop writes
    # into the same capture dict.
    monkeypatch.chdir(tmp_path)
    template = {"$": "include", "name": "a"}
    includes = {
        "a": [
            {"$": "file", "name": "a.json", "content": "from-a"},
            {"$": "include", "name": "b"},
        ],
        "b": {"$": "file", "name": "b.json", "content": "from-b"},
    }
    envelope = dry_run(template, None, includes)
    assert envelope["ok"] is True
    assert envelope["writes"] == {"a.json": "from-a", "b.json": "from-b"}
    _assert_dir_untouched(tmp_path)


# ---------------------------------------------------------------------------
# No network (NFR-003 groundwork)
# ---------------------------------------------------------------------------


def test_ac_015_no_network_host_socket_blocked(monkeypatch):
    # The host-side dry-run path opens no sockets: it keeps working with
    # socket.socket forced to raise. The worker is a separate fresh process
    # with no network code path at all (subprocess pipes only), so patching
    # the host is the observable seam.
    def _no_network(*args, **kwargs):
        raise AssertionError("dry-run attempted network access")

    monkeypatch.setattr(socket, "socket", _no_network)
    envelope = dry_run({"$": "this"}, {"ok": True})
    assert envelope == {
        "ok": True,
        "result": {"ok": True},
        "writes": {},
        "errors": [],
    }
