"""FR-036 / AC-039 — `python -m transon_authoring language` serves the bundled
Language Reference offline (SPEC §11.6 `language` row, AD-026; NFR-003 grounding).

The subcommand reads the committed `resources/language-reference.json` (the
canonical dump of the pinned engine's `get_language_reference()`) via the same
engine-free resource reader as `metadata`, emitting a library envelope. Engine
ground truth is derived from the pinned `transon==0.2.3` install (AD-018 /
NFR-001), never from memory.
"""

import json
import subprocess
import sys
from pathlib import Path


def _run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "transon_authoring", *args],
        capture_output=True,
        timeout=60,
        check=False,
    )


def _engine_reference() -> dict:
    from transon.reference import get_language_reference

    return get_language_reference()


def test_fr_036_full_content_envelope():
    # FR-036 / AC-039(a) — no args → the full library envelope whose `content`
    # is byte-exact get_language_reference().content for the pinned engine.
    reference = _engine_reference()
    result = _run_cli("language")
    assert result.returncode == 0, result.stderr
    assert result.stderr == b""
    doc = json.loads(result.stdout.decode("utf-8"))
    assert doc["schema_version"] == "1.0"
    assert doc["reference_version"] == reference["reference_version"]
    assert doc["engine_version"] == reference["engine_version"]
    assert doc["format"] == reference["format"]
    assert doc["content"] == reference["content"]


def test_fr_036_list_sections_ordered():
    # FR-036 / AC-039(a) — --list-sections → the ordered {id, title} index in
    # document order.
    reference = _engine_reference()
    result = _run_cli("language", "--list-sections")
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout.decode("utf-8"))
    assert doc["schema_version"] == "1.0"
    assert doc["reference_version"] == reference["reference_version"]
    assert doc["engine_version"] == reference["engine_version"]
    assert doc["sections"] == [
        {"id": s["id"], "title": s["title"]} for s in reference["sections"]
    ]


def test_fr_036_section_lookup():
    # FR-036 / AC-039(a) — --section ID → that section's full record.
    reference = _engine_reference()
    target = reference["sections"][1]  # templates-and-the-marker (non-empty title)
    result = _run_cli("language", "--section", target["id"])
    assert result.returncode == 0, result.stderr
    doc = json.loads(result.stdout.decode("utf-8"))
    assert doc["schema_version"] == "1.0"
    assert doc["reference_version"] == reference["reference_version"]
    assert doc["engine_version"] == reference["engine_version"]
    assert doc["section"] == {
        "id": target["id"],
        "title": target["title"],
        "heading_level": target["heading_level"],
        "content": target["content"],
    }


def test_ac_039_unknown_section_exit2():
    # AC-039 — an unknown --section id is a §11.6 schema-error CliError, exit 2.
    result = _run_cli("language", "--section", "no-such-section")
    assert result.returncode == 2
    doc = json.loads(result.stdout.decode("utf-8"))
    assert doc["ok"] is False
    assert doc["status"] == "schema-error"
    assert doc["errors"][0]["type"] == "PreflightError"


def test_ac_039_mutually_exclusive_exit2():
    # AC-039 — --section and --list-sections together → schema-error, exit 2.
    result = _run_cli("language", "--section", "preamble", "--list-sections")
    assert result.returncode == 2
    doc = json.loads(result.stdout.decode("utf-8"))
    assert doc["ok"] is False
    assert doc["status"] == "schema-error"


def test_ac_039_unsupported_major_exit2(monkeypatch, capsys):
    # AC-039 — a bundled reference_version whose major exceeds the supported
    # major (1) is a schema-error, exit 2 (consumers MUST fail loudly).
    from transon_authoring import __main__ as cli
    from transon_authoring import metadata

    future = json.dumps(
        {
            "reference_version": "2.0",
            "engine_version": "0.2.3",
            "format": "markdown",
            "content": "# future",
            "sections": [],
        }
    ).encode("utf-8")
    monkeypatch.setattr(
        metadata, "_resource_bytes", lambda name: future, raising=True
    )
    assert cli.main(["language"]) == 2
    doc = json.loads(capsys.readouterr().out)
    assert doc["ok"] is False
    assert doc["status"] == "schema-error"
    assert "major" in doc["explanation"]


def test_ac_039_language_offline_no_engine_import():
    # AC-039 / NFR-003 — every `language` path is engine-import-free: running
    # each mode in a fresh interpreter must never import the live `transon`
    # engine (grounded in the bundled resource only, like `metadata`).
    probe = (
        "import sys, io, contextlib\n"
        "from transon_authoring.__main__ import main\n"
        "for argv in (['language'], ['language', '--list-sections'],"
        " ['language', '--section', 'preamble']):\n"
        "    buf = io.StringIO()\n"
        "    with contextlib.redirect_stdout(buf):\n"
        "        rc = main(argv)\n"
        "    assert rc == 0, (argv, rc)\n"
        "sys.exit(1 if 'transon' in sys.modules else 0)\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
