"""Repo project config ``.transon-authoring.json`` (FR-022 / AC-014).

SPEC §11.9 ProjectConfig: ``layout`` selects where a template's SampleSet
file lives — ``sibling`` ("<stem>.samples.json" beside the template),
``central`` ("<samples_dir or 'transon-samples'>/<stem>.samples.json" under
the repo root) or ``custom`` (a pattern with the ``{stem}`` / ``{dir}``
placeholders only).

Pattern safety (§11.9): ``{..}``, unknown placeholders, environment-variable
interpolation (``$VAR`` / ``${VAR}`` / ``%VAR%``) and absolute results are
forbidden, and every expansion MUST resolve inside the repo root (no ``..``
escape) — violations raise :class:`PatternError` (a ``ValueError``) with
stable library text.

Engine-free by design: this module uses only the stdlib plus the shared
ingress layer (like ``metadata`` / ``examples``, the config path never
imports the pinned engine).
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from transon_authoring._ingress import load_document, validate_schema

#: Repo config file name (§11.9); ``init-config`` writes it to the cwd.
CONFIG_FILENAME = ".transon-authoring.json"

#: Bundled JSON Schema for the ProjectConfig document (FR-026 / OQ-014e).
CONFIG_SCHEMA = "project_config.json"

#: §11.9 defaults.
DEFAULT_REPAIR_ATTEMPTS = 3
DEFAULT_SAMPLES_DIR = "transon-samples"

#: The only placeholders a custom pattern may use (§11.9).
ALLOWED_PLACEHOLDERS = ("stem", "dir")

_PLACEHOLDER_RE = re.compile(r"\{([^{}]*)\}")
# $VAR / ${VAR} / %VAR% — any env-interpolation syntax is forbidden (§11.9).
_ENV_INTERPOLATION_RE = re.compile(
    r"\$\{[^}]*\}|\$[A-Za-z_][A-Za-z0-9_]*|%[A-Za-z_][A-Za-z0-9_]*%"
)


class PatternError(ValueError):
    """A §11.9 pattern/path-safety violation (stable library message)."""


def _check_pattern_text(pattern: str) -> None:
    """Static §11.9 checks on the pattern text itself (before expansion)."""
    if "{..}" in pattern:
        raise PatternError(
            'pattern contains the forbidden placeholder "{..}" (SPEC 11.9)'
        )
    for name in _PLACEHOLDER_RE.findall(pattern):
        if name not in ALLOWED_PLACEHOLDERS:
            raise PatternError(
                f'pattern contains unknown placeholder "{{{name}}}":'
                ' only {stem} and {dir} are allowed (SPEC 11.9)'
            )
    if _ENV_INTERPOLATION_RE.search(pattern):
        raise PatternError(
            "pattern must not contain environment-variable interpolation"
            " ($VAR, ${VAR} or %VAR%) (SPEC 11.9)"
        )


def _expand(pattern: str, stem: str, dir_: str) -> str:
    return pattern.replace("{stem}", stem).replace("{dir}", dir_)


def validate_pattern(pattern: str) -> None:
    """Validate a custom-layout pattern without a concrete template (§11.9).

    Runs the static text checks plus a probe expansion to catch patterns
    that are absolute or escape the repo root regardless of the template
    (e.g. ``../{stem}.samples.json``). Raises :class:`PatternError`.
    """
    _check_pattern_text(pattern)
    probe = _expand(pattern, "probe", ".")
    if os.path.isabs(probe) or Path(probe).drive:
        raise PatternError(
            "pattern must not expand to an absolute path (SPEC 11.9)"
        )
    normalized = os.path.normpath(probe)
    if normalized == ".." or normalized.startswith(".." + os.sep):
        raise PatternError(
            "pattern expansion escapes the repo root (SPEC 11.9)"
        )


def build_config(
    layout: str,
    pattern: str | None = None,
    samples_dir: str | None = None,
    repair_attempts: int = DEFAULT_REPAIR_ATTEMPTS,
) -> dict[str, Any]:
    """Build a validated §11.9 ProjectConfig document.

    Schema problems (bad layout, out-of-range ``repair_attempts``, ``custom``
    without ``pattern``) raise ``IngressError`` (PreflightError semantics);
    a pattern violating §11.9 raises :class:`PatternError`.
    """
    config: dict[str, Any] = {
        "schema_version": "1.0",
        "layout": layout,
        "repair_attempts": repair_attempts,
    }
    if pattern is not None:
        config["pattern"] = pattern
    if samples_dir is not None:
        config["samples_dir"] = samples_dir
    validate_schema(config, CONFIG_SCHEMA, source=CONFIG_FILENAME)
    if pattern is not None:
        validate_pattern(pattern)
    return config


def load_config(path: str | os.PathLike[str]) -> dict[str, Any]:
    """Load and validate a ``.transon-authoring.json`` file.

    Full ingress like every other document load (FR-026): strict JSON,
    ``schema_version`` check, bundled-schema validation; failures raise
    ``IngressError`` with PreflightError-shaped entries (§11.6 exit-2
    semantics when surfaced through the CLI).
    """
    return load_document(path, CONFIG_SCHEMA)


def resolve_samples_path(
    config: dict[str, Any],
    template_path: str | os.PathLike[str],
    repo_root: str | os.PathLike[str],
) -> Path:
    """Resolve the SampleSet file path for *template_path* per §11.9.

    - ``sibling``: ``<stem>.samples.json`` beside the template.
    - ``central``: ``<samples_dir or "transon-samples">/<stem>.samples.json``
      under *repo_root*.
    - ``custom``: expand ``{stem}`` (template file stem) and ``{dir}``
      (template directory, relative to *repo_root*) in ``pattern``, relative
      to *repo_root*.

    Returns an absolute, resolved path. Every result MUST resolve inside
    *repo_root* (no ``..`` escape, no absolute expansion) — violations raise
    :class:`PatternError` with stable messages.
    """
    root = Path(repo_root).resolve()
    template = Path(template_path)
    if not template.is_absolute():
        template = root / template
    template = template.resolve()
    stem = template.stem

    layout = config.get("layout")
    if layout == "sibling":
        candidate = template.parent / f"{stem}.samples.json"
    elif layout == "central":
        samples_dir = config.get("samples_dir", DEFAULT_SAMPLES_DIR)
        _check_pattern_text(samples_dir)
        if os.path.isabs(samples_dir) or Path(samples_dir).drive:
            raise PatternError(
                "samples_dir must not be an absolute path (SPEC 11.9)"
            )
        candidate = root / samples_dir / f"{stem}.samples.json"
    elif layout == "custom":
        pattern = config.get("pattern")
        if not isinstance(pattern, str):
            raise PatternError(
                'layout "custom" requires a pattern string (SPEC 11.9)'
            )
        _check_pattern_text(pattern)
        try:
            template_dir = template.parent.relative_to(root)
        except ValueError as exc:
            raise PatternError(
                "template path is outside the repo root (SPEC 11.9)"
            ) from exc
        expanded = _expand(pattern, stem, template_dir.as_posix())
        if os.path.isabs(expanded) or Path(expanded).drive:
            raise PatternError(
                "pattern must not expand to an absolute path (SPEC 11.9)"
            )
        candidate = root / expanded
    else:
        raise PatternError(
            f"unknown layout {layout!r}: expected sibling, central or custom"
            " (SPEC 11.9)"
        )

    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise PatternError(
            "samples path escapes the repo root after expansion (SPEC 11.9)"
        )
    return resolved
