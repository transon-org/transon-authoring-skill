"""FR-022 / AC-014 — ProjectConfig ``.transon-authoring.json`` + the
``init-config`` CLI verb (SPEC §11.9 write-location
block, §11.6 init-config row, §11.0 schema-version list).

CLI invocations go through a real subprocess with ``cwd`` set to a temp repo
root and stdin NOT a TTY (``DEVNULL``), so the no-prompt guarantees of
FR-022/AC-014 are exercised for real (a regression that prompts would hang
and trip the subprocess timeout, not silently pass).
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from transon_authoring._ingress import IngressError, schema_violations
from transon_authoring.config import (
    CONFIG_FILENAME,
    PatternError,
    build_config,
    load_config,
    resolve_samples_path,
)
from transon_authoring.samples import content_fingerprint


def run_cli(*args: str, cwd) -> subprocess.CompletedProcess:
    """Run ``python -m transon_authoring`` in *cwd* with stdin closed
    (non-TTY): per FR-022 the CLI must never prompt and never hang here."""
    return subprocess.run(
        [sys.executable, "-m", "transon_authoring", *args],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        cwd=str(cwd),
        timeout=60,
    )


def one_json_document(result) -> dict:
    """§11.0/§11.6 emission discipline: stdout is exactly ONE compact JSON
    document plus a trailing newline."""
    text = result.stdout.decode("utf-8")
    document = json.loads(text)
    assert text == (
        json.dumps(
            document, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    )
    return document


def assert_schema_error(result) -> dict:
    """§11.6: input/validation problems → exit 2 CliError schema-error."""
    assert result.returncode == 2
    document = one_json_document(result)
    assert document["ok"] is False
    assert document["status"] == "schema-error"
    assert schema_violations(document, "cli_error.json") == []
    assert all(e["type"] == "PreflightError" for e in document["errors"])
    return document


# ---------------------------------------------------------------------------
# init-config happy path (FR-022; §11.9 write location)
# ---------------------------------------------------------------------------


def test_fr_022_init_config_writes_cwd_file_and_emits_valid_project_config(tmp_path):
    result = run_cli("init-config", "--layout", "sibling", cwd=tmp_path)
    assert result.returncode == 0
    document = one_json_document(result)
    # stdout document validates against the bundled ProjectConfig schema.
    assert schema_violations(document, "project_config.json") == []
    assert document == {
        "schema_version": "1.0",
        "layout": "sibling",
        "repair_attempts": 3,
    }
    # §11.9: the file lands in the CURRENT WORKING DIRECTORY.
    written = tmp_path / CONFIG_FILENAME
    assert written.is_file()
    assert json.loads(written.read_text(encoding="utf-8")) == document
    # And it round-trips through the ingress loader (FR-026 semantics).
    assert load_config(written) == document


def test_fr_022_init_config_all_flags_recorded(tmp_path):
    result = run_cli(
        "init-config",
        "--layout",
        "central",
        "--samples-dir",
        "samples",
        "--repair-attempts",
        "5",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    document = one_json_document(result)
    assert schema_violations(document, "project_config.json") == []
    assert document["layout"] == "central"
    assert document["samples_dir"] == "samples"
    assert document["repair_attempts"] == 5


def test_fr_022_init_config_custom_with_pattern(tmp_path):
    result = run_cli(
        "init-config",
        "--layout",
        "custom",
        "--pattern",
        "samples/{dir}/{stem}.samples.json",
        cwd=tmp_path,
    )
    assert result.returncode == 0
    document = one_json_document(result)
    assert schema_violations(document, "project_config.json") == []
    assert document["pattern"] == "samples/{dir}/{stem}.samples.json"


# ---------------------------------------------------------------------------
# init-config collisions (§11.9: refuse overwrite unless --force)
# ---------------------------------------------------------------------------


def test_fr_022_init_config_refuses_overwrite_without_force(tmp_path):
    assert run_cli("init-config", "--layout", "sibling", cwd=tmp_path).returncode == 0
    before = (tmp_path / CONFIG_FILENAME).read_text(encoding="utf-8")
    result = run_cli("init-config", "--layout", "central", cwd=tmp_path)
    document = assert_schema_error(result)
    assert "--force" in document["explanation"]
    # File untouched.
    assert (tmp_path / CONFIG_FILENAME).read_text(encoding="utf-8") == before


def test_fr_022_init_config_force_overwrites(tmp_path):
    assert run_cli("init-config", "--layout", "sibling", cwd=tmp_path).returncode == 0
    result = run_cli("init-config", "--layout", "central", "--force", cwd=tmp_path)
    assert result.returncode == 0
    document = one_json_document(result)
    assert document["layout"] == "central"
    assert json.loads(
        (tmp_path / CONFIG_FILENAME).read_text(encoding="utf-8")
    ) == document


# ---------------------------------------------------------------------------
# init-config non-interactive / missing-field failures (§11.9, exit 2)
# ---------------------------------------------------------------------------


def test_fr_022_non_interactive_missing_layout_exit_2(tmp_path):
    result = run_cli("init-config", "--non-interactive", cwd=tmp_path)
    document = assert_schema_error(result)
    assert "--layout" in document["explanation"]
    assert not (tmp_path / CONFIG_FILENAME).exists()


def test_fr_022_custom_without_pattern_exit_2(tmp_path):
    result = run_cli(
        "init-config", "--layout", "custom", "--non-interactive", cwd=tmp_path
    )
    document = assert_schema_error(result)
    assert "pattern" in document["explanation"]
    assert not (tmp_path / CONFIG_FILENAME).exists()


def test_fr_022_force_write_replaces_symlink_not_its_target(tmp_path):
    # §11.9 collisions hardening: --force must replace the config path itself
    # atomically, never follow a symlinked .transon-authoring.json and write
    # through it into another file.
    victim = tmp_path / "victim.json"
    victim.write_text("original", encoding="utf-8")
    (tmp_path / CONFIG_FILENAME).symlink_to(victim)
    result = run_cli("init-config", "--layout", "sibling", "--force", cwd=tmp_path)
    assert result.returncode == 0
    assert victim.read_text(encoding="utf-8") == "original"
    config_path = tmp_path / CONFIG_FILENAME
    assert not config_path.is_symlink()
    assert json.loads(config_path.read_text(encoding="utf-8"))["layout"] == "sibling"


def test_fr_022_pattern_on_non_custom_layout_exit_2(tmp_path):
    # §11.9 "pattern required IFF layout=custom": a stray pattern on a
    # non-custom layout is a schema error, not silently persisted.
    result = run_cli(
        "init-config", "--layout", "sibling", "--pattern", "{dir}/{stem}.json",
        "--non-interactive", cwd=tmp_path,
    )
    assert_schema_error(result)
    assert not (tmp_path / CONFIG_FILENAME).exists()


def test_ac_014_collision_check_precedes_layout_prompt(tmp_path):
    # AC-014: with a config already present, init-config refuses at the
    # collision check before ever reaching the layout prompt — observable
    # non-TTY as the overwrite refusal (not the layout-required error) when
    # --layout is omitted.
    assert run_cli("init-config", "--layout", "sibling", cwd=tmp_path).returncode == 0
    result = run_cli("init-config", cwd=tmp_path)
    document = assert_schema_error(result)
    assert "--force" in document["explanation"]
    assert "layout is required" not in document["explanation"]


def test_fr_022_repair_attempts_out_of_range_exit_2(tmp_path):
    for bad in ("0", "11"):
        result = run_cli(
            "init-config", "--layout", "sibling", "--repair-attempts", bad,
            cwd=tmp_path,
        )
        assert_schema_error(result)
        assert not (tmp_path / CONFIG_FILENAME).exists()


@pytest.mark.parametrize(
    "pattern",
    [
        "/abs/{stem}.samples.json",       # absolute expansion
        "../{stem}.samples.json",         # escapes repo root
        "{..}/x.samples.json",            # forbidden {..}
        "{home}/{stem}.samples.json",     # unknown placeholder
        "$HOME/{stem}.samples.json",      # env interpolation $VAR
        "${HOME}/{stem}.samples.json",    # env interpolation ${VAR}
        "%HOME%/{stem}.samples.json",     # env interpolation %VAR%
    ],
)
def test_fr_022_init_config_rejects_11_9_pattern_violations(tmp_path, pattern):
    result = run_cli(
        "init-config", "--layout", "custom", "--pattern", pattern, cwd=tmp_path
    )
    assert_schema_error(result)
    assert not (tmp_path / CONFIG_FILENAME).exists()


# ---------------------------------------------------------------------------
# build_config / load_config unit behavior (FR-022)
# ---------------------------------------------------------------------------


def test_fr_022_build_config_validates_and_defaults():
    assert build_config("sibling") == {
        "schema_version": "1.0",
        "layout": "sibling",
        "repair_attempts": 3,
    }
    custom = build_config("custom", pattern="{dir}/{stem}.samples.json")
    assert schema_violations(custom, "project_config.json") == []
    with pytest.raises(IngressError):
        build_config("custom")  # pattern required iff layout=custom
    with pytest.raises(IngressError):
        build_config("diagonal")  # not in the layout enum
    with pytest.raises(IngressError):
        build_config("sibling", repair_attempts=11)  # range 1..10
    with pytest.raises(PatternError):
        build_config("custom", pattern="/etc/{stem}.json")


def test_fr_022_load_config_rejects_malformed_file(tmp_path):
    path = tmp_path / CONFIG_FILENAME
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(IngressError):
        load_config(path)
    path.write_text(
        json.dumps({"schema_version": "1.0", "layout": "custom",
                    "repair_attempts": 3}),
        encoding="utf-8",
    )
    with pytest.raises(IngressError):
        load_config(path)  # custom without pattern is schema-invalid


# ---------------------------------------------------------------------------
# resolve_samples_path (§11.9 layouts + placeholder safety)
# ---------------------------------------------------------------------------


def test_fr_022_resolve_sibling(tmp_path):
    (tmp_path / "templates").mkdir()
    template = tmp_path / "templates" / "orders.json"
    config = build_config("sibling")
    assert resolve_samples_path(config, template, tmp_path) == (
        tmp_path / "templates" / "orders.samples.json"
    ).resolve()


def test_fr_022_resolve_central_default_and_custom_dir(tmp_path):
    template = tmp_path / "orders.json"
    config = build_config("central")
    assert resolve_samples_path(config, template, tmp_path) == (
        tmp_path / "transon-samples" / "orders.samples.json"
    ).resolve()
    config = build_config("central", samples_dir="qa/samples")
    assert resolve_samples_path(config, template, tmp_path) == (
        tmp_path / "qa" / "samples" / "orders.samples.json"
    ).resolve()


def test_fr_022_resolve_custom_expands_stem_and_dir(tmp_path):
    (tmp_path / "etl" / "jobs").mkdir(parents=True)
    template = tmp_path / "etl" / "jobs" / "orders.json"
    config = build_config("custom", pattern="samples/{dir}/{stem}.samples.json")
    assert resolve_samples_path(config, template, tmp_path) == (
        tmp_path / "samples" / "etl" / "jobs" / "orders.samples.json"
    ).resolve()


@pytest.mark.parametrize(
    "pattern",
    [
        "{home}/x.json",                # unknown placeholder
        "{..}/x.json",                  # forbidden {..}
        "$HOME/{stem}.json",            # env interpolation $VAR
        "${HOME}/{stem}.json",          # env interpolation ${VAR}
        "%APPDATA%/{stem}.json",        # env interpolation %VAR%
        "/etc/{stem}.json",             # absolute expansion
        "../{stem}.samples.json",       # escapes repo root
        "a/../../{stem}.samples.json",  # escapes repo root after normalizing
    ],
)
def test_fr_022_resolve_custom_rejects_unsafe_patterns(tmp_path, pattern):
    template = tmp_path / "orders.json"
    config = {
        "schema_version": "1.0",
        "layout": "custom",
        "pattern": pattern,
        "repair_attempts": 3,
    }
    with pytest.raises(ValueError):  # PatternError is a ValueError
        resolve_samples_path(config, template, tmp_path)


def test_fr_022_resolve_central_rejects_escaping_samples_dir(tmp_path):
    template = tmp_path / "orders.json"
    for bad in ("..", "/abs", "$HOME"):
        config = {
            "schema_version": "1.0",
            "layout": "central",
            "samples_dir": bad,
            "repair_attempts": 3,
        }
        with pytest.raises(ValueError):
            resolve_samples_path(config, template, tmp_path)


# ---------------------------------------------------------------------------
# AC-014 — no prompt when non-interactive; check-samples never reads config
# ---------------------------------------------------------------------------


def _confirmed_sample_set() -> dict:
    ss = {
        "schema_version": "1.0",
        "coverage": [
            {
                "id": "happy",
                "kind": "happy_path",
                "description": "happy path",
                "acceptance": "accepted",
            }
        ],
        "cases": [
            {"id": "c1", "input": {"x": 1}, "output": 1, "satisfies": ["happy"]}
        ],
        "waivers": [],
    }
    ss["confirmation"] = {
        "confirmed": True,
        "confirmed_by": "user",
        "content_fingerprint": content_fingerprint(ss),
    }
    return ss


def test_ac_014_no_prompt_when_config_present_or_samples_given(tmp_path):
    # 1) init-config with a non-TTY stdin and NO --non-interactive flag:
    # must not prompt or hang (run_cli's DEVNULL stdin + timeout make a
    # prompt regression fail loudly); layout missing → exit 2, no file.
    result = run_cli("init-config", cwd=tmp_path)
    assert_schema_error(result)
    assert not (tmp_path / CONFIG_FILENAME).exists()

    # 2) check-samples with --samples given never reads .transon-authoring.json
    # (§11.9: check-samples/verify never read config and never prompt) —
    # a malformed config in cwd must not affect it.
    (tmp_path / CONFIG_FILENAME).write_text("{definitely not json", encoding="utf-8")
    samples = tmp_path / "orders.samples.json"
    samples.write_text(
        json.dumps(_confirmed_sample_set(), ensure_ascii=False), encoding="utf-8"
    )
    result = run_cli("check-samples", "--samples", str(samples), cwd=tmp_path)
    assert result.returncode == 0
    document = one_json_document(result)
    assert document["ok_for_verify"] is True
    assert schema_violations(document, "sample_check.json") == []
