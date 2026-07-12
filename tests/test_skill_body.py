"""Contract assertions over the SKILL.md authoring-skill body (A3 slice).

FR-001 — the skill body documents the grounded draft flow (snapshot-grounded,
AD-018 authority order, AC-003 refusal, AD-004 verify-before-return).
FR-002 — authoring is SampleSet-driven: no draft until `coverage_complete`
AND `confirmed` (AD-014/AD-016; the library never confirms).
AC-013 — every CLI command/flag the body cites exists in the real
`python -m transon_authoring` surface (§11.6), so a small gate model
(AD-021) can execute the steps verbatim.

These are text-contract tests: they parse SKILL.md for the normative
statements and markers the A3 slice locked in, resilient to prose tweaks
(case-insensitive substring/regex on phrases the body owns).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from transon_authoring.__main__ import _build_parser

SKILL_PATH = Path(__file__).resolve().parent.parent / "SKILL.md"


def _body() -> str:
    return SKILL_PATH.read_text(encoding="utf-8")


def _has(pattern: str, text: str) -> bool:
    return re.search(pattern, text, re.IGNORECASE | re.DOTALL) is not None


def test_fr_001_skill_body_documents_grounded_flow():
    """FR-001 / AC-003 / AD-018 / AD-004: grounding commands cited, authority
    order stated, ungroundable capability => aborted refusal, success only on
    ok:true + assurance:"matched"."""
    body = _body()

    # Grounding commands are cited verbatim (FR-001 / AD-018 source 3).
    assert "python -m transon_authoring metadata" in body
    assert "python -m transon_authoring examples search" in body

    # AD-018 authority order: engine pin -> engine spec -> snapshot -> sidecar
    # hints, in that order, in one statement.
    assert _has(
        r"pinned\s+running\s+engine.{0,200}?SPECIFICATION\.md"
        r".{0,200}?snapshot.{0,200}?sidecar.{0,60}?hints\s+only",
        body,
    ), "AD-018 authority precedence order not stated in SKILL.md"
    assert _has(r"never\s+use\s+model\s+memory", body)  # NFR-001

    # Refusal rule (AC-003): capability not groundable in the snapshot =>
    # status "aborted" envelope; never invent names.
    assert _has(
        r"cannot\s+be\s+grounded\s+in\s+the\s+pinned\s+snapshot"
        r".{0,300}?ok.{0,10}?false.{0,120}?status:\s*\"aborted\"",
        body,
    ), "AC-003 refusal-to-aborted rule not stated in SKILL.md"
    assert _has(r"never\s+invent\s+names", body)

    # Verify-before-return (AD-004 / AC-013): success ONLY on ok:true AND
    # assurance:"matched"; never report an unverified template as success.
    assert _has(
        r"success\s+only\s+when.{0,120}?ok:\s*true.{0,60}?"
        r"assurance:\s*\"matched\"",
        body,
    ), "AD-004 verify-before-return statement not found in SKILL.md"
    assert _has(
        r"never\s+report\s+or\s+return\s+the\s+template\s+as\s+success", body
    )

    # Locked D5 structure: six numbered sections plus both expansion markers.
    for heading in (
        "## 1. Config & samples location",
        "## 2. Ground & refuse",
        "## 3. Sample loop",
        "## 4. Draft",
        "## 5. Verify & repair",
        "## 6. Result",
    ):
        assert heading in body, f"missing section heading: {heading}"
    assert "<!-- sample-loop protocol: FR-023/024/025 -->" in body
    assert "<!-- repair protocol: FR-007/NFR-006 -->" in body

    # Section 6 carries the full section-11.5 status table: all nine statuses.
    result_section = body.split("## 6. Result", 1)[1]
    for status in (
        "matched",
        "need-samples",
        "deferred",
        "aborted",
        "repair-exhausted",
        "samples-rejected",
        "verify-failed",
        "schema-error",
        "profile-rejected",
    ):
        assert f"`{status}`" in result_section, (
            f"section-11.5 status {status!r} missing from the Result table"
        )
    # Failures are honest envelopes, never a template (FR-008 / AC-026).
    assert _has(r"failures\s+always\s+set\s+.?ok:\s*false", result_section)
    assert _has(
        r"never\s+present\s+a\s+template\s+as\s+success", result_section
    )
    # profile-rejected covers the skill half of AC-027: stop without verify.
    assert _has(
        r"profile-rejected.{0,300}?without\s+calling\s+verify", result_section
    )


def test_fr_002_skill_body_requires_sample_set_for_success():
    """FR-002 / AD-014 / AD-016 / AC-014: no draft until coverage_complete AND
    confirmed, both read from check-samples; the library never confirms."""
    body = _body()

    # The gate command is cited with its real flag.
    assert "python -m transon_authoring check-samples --samples" in body

    # Both flags gate the draft, and both come from check-samples output.
    assert _has(
        r"coverage_complete:\s*true.{0,60}?AND.{0,60}?confirmed:\s*true",
        body,
    ), "coverage_complete AND confirmed gate not stated"
    assert _has(
        r"both\s+must\s+come\s+from\s+the\s*.?check-samples.?\s+output", body
    )
    assert _has(
        r"do\s+not\s+draft\s+any\s+template\s+until\s+both\s+are\s+true", body
    ), "AD-014 no-draft-until-gate statement not found"

    # AD-016: the library never sets confirmed.
    assert _has(
        r"the\s+library\s+never\s+sets\s*.?confirmed:\s*true", body
    ), "AD-016 library-never-confirms statement not found"

    # AC-014 / FR-022: config init on first interactive use; CI never prompts;
    # explicit samples path wins.
    assert "python -m transon_authoring init-config" in body
    assert ".transon-authoring.json" in body
    assert _has(r"never\s+prompt", body)
    assert _has(
        r"(`--samples`\s+value|samples\s+path).{0,120}?always\s+wins", body
    )


def _real_cli_surface() -> dict[tuple[str, ...], set[str]]:
    """Command path -> option strings, introspected from the real parser
    (single source of truth for section 11.6, per FR-014)."""
    surface: dict[tuple[str, ...], set[str]] = {}

    def walk(parser: argparse.ArgumentParser, prefix: tuple[str, ...]) -> None:
        if prefix:
            surface[prefix] = {
                option
                for action in parser._actions
                for option in action.option_strings
            }
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for name, child in action.choices.items():
                    walk(child, prefix + (name,))

    walk(_build_parser(), ())
    return surface


def test_fr_001_ac_013_cited_cli_commands_exist_in_real_surface():
    """FR-001 / AC-013: every `python -m transon_authoring ...` invocation and
    every bare `--flag` named in SKILL.md exists in the real CLI surface, so
    the small gate model (AD-021) can run the body verbatim."""
    body = _body()
    surface = _real_cli_surface()
    assert surface, "could not introspect the CLI parser surface"

    invocations = re.findall(r"`(python -m transon_authoring[^`]*)`", body)
    assert invocations, "SKILL.md cites no CLI invocations at all"

    for invocation in invocations:
        tokens = invocation.split()[3:]  # strip "python -m transon_authoring"
        assert tokens, f"bare module invocation without a subcommand: {invocation!r}"
        # Longest command-path match first (handles "examples search").
        command: tuple[str, ...] | None = None
        for length in (2, 1):
            candidate = tuple(tokens[:length])
            if candidate in surface:
                command = candidate
                break
        assert command is not None, (
            f"SKILL.md cites unknown subcommand in {invocation!r}"
        )
        flags = {
            token.split("=", 1)[0]
            for token in tokens[len(command):]
            if token.startswith("--")
        }
        unknown = flags - surface[command] - {"--help"}
        assert not unknown, (
            f"SKILL.md cites flags {sorted(unknown)} that "
            f"'{' '.join(command)}' does not accept"
        )

    # Bare backticked flags mentioned outside a full invocation must exist
    # somewhere in the surface too.
    all_flags = set().union(*surface.values())
    for flag in re.findall(r"`(--[a-z][a-z-]*)`", body):
        assert flag in all_flags, f"SKILL.md names unknown flag {flag}"
