"""Contract assertions over the SKILL.md authoring-skill body (A3 slice).

FR-001 — the skill body documents the grounded draft flow (snapshot-grounded,
AD-018 authority order, AC-003 refusal, AD-004 verify-before-return).
FR-002 — authoring is SampleSet-driven: no draft until `coverage_complete`
AND `confirmed` (AD-014/AD-016; the library never confirms).
AC-013 — every CLI command/flag the body cites exists in the real
`python -m transon_authoring` surface (§11.6), so a small gate model
(AD-021) can execute the steps verbatim.
FR-023/FR-024/FR-025 — the conversational sample-loop protocol (propose /
present / confirm / exits) with the OQ-023 split: AC-011's conversational
half (fingerprint bound via the OQ-015 acquisition path) plus a scripted
AC-010 gap→waiver→confirm simulation over library calls only.

These are text-contract tests: they parse SKILL.md for the normative
statements and markers the A3 slice locked in, resilient to prose tweaks
(case-insensitive substring/regex on phrases the body owns). The AC-010
simulation is the deterministic exception — it drives `check_samples`
end to end exactly as the skill body instructs.
"""
from __future__ import annotations

import argparse
import inspect
import re
from pathlib import Path

import transon_authoring
from transon_authoring import check_samples
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


def _sample_loop_section() -> str:
    """The `## 3. Sample loop` section body (up to `## 4.`)."""
    body = _body()
    section = body.split("## 3. Sample loop", 1)[1].split("## 4.", 1)[0]
    assert "<!-- sample-loop protocol: FR-023/024/025 -->" in section, (
        "sample-loop traceability marker missing from section 3"
    )
    return section


def test_fr_025_skill_proposes_obligations_as_proposed_in_sample_set():
    """FR-025 / AD-016: the SKILL body drafts `coverage` obligations from the
    user's NL intent, inside the SampleSet, with `acceptance: "proposed"` —
    and states that the library never infers obligations from NL."""
    section = _sample_loop_section()

    # Obligations are proposed by the skill, from NL, inside the SampleSet.
    assert _has(
        r"coverage.{0,200}?obligation.{0,300}?acceptance.{0,10}?"
        r"\"proposed\"",
        section,
    ), "FR-025 propose step (coverage obligations, acceptance proposed) missing"
    assert _has(r"(NL|natural.language)\s+intent", section), (
        "propose step does not source obligations from the user's NL intent"
    )
    # Candidate cases are proposed alongside the obligations.
    assert _has(r"candidate\s+case", section) or _has(
        r"cases.{0,120}?satisfies", section
    ), "propose step does not draft candidate cases"

    # AD-016 division of labor: the library does no NL inference.
    assert _has(
        r"library\s+never\s+(infers|parses|derives).{0,60}?"
        r"(NL|natural\s+language)",
        section,
    ) or _has(
        r"never\s+(infers|parses).{0,40}NL", section
    ), "AD-016 library-does-no-NL-inference statement missing"


def test_fr_025_library_has_no_nl_inference_api():
    """FR-025 / AD-016 guard: the public library surface exposes NO entry
    point that infers/proposes obligations from natural language — proposing
    is the skill body's job; the library only checks the artifact."""
    banned = ("propose", "infer", "suggest", "obligation", "intent", "coverage")

    # Public Python API (AD-006 surface).
    for name in transon_authoring.__all__:
        lowered = name.lower()
        assert not any(word in lowered for word in banned), (
            f"public API name {name!r} looks like an NL/obligation-inference"
            " entry point (AD-016 forbids one in the library)"
        )

    # Module CLI surface (§11.6): no subcommand or flag either.
    for command, flags in _real_cli_surface().items():
        for token in command + tuple(flags):
            lowered = token.lower()
            assert not any(word in lowered for word in banned), (
                f"CLI surface token {token!r} under {command!r} looks like an"
                " NL/obligation-inference entry point (AD-016)"
            )

    # check_samples checks the artifact alone: one positional SampleSet
    # parameter, no NL/intent inputs (AD-016, NFR-002).
    parameters = inspect.signature(check_samples).parameters
    assert list(parameters) == ["sample_set"], (
        "check_samples must be a function of the SampleSet artifact alone"
    )


def test_ac_011_skill_body_binds_fingerprint_via_check_samples_only():
    """AC-011 (OQ-023 conversational half) / OQ-015: on explicit user
    confirmation the skill copies `SampleCheck.content_fingerprint` verbatim
    into `confirmation.content_fingerprint` and never hand-computes it."""
    section = _sample_loop_section()

    # Confirmation only on explicit user say-so, written by the skill.
    assert _has(r"explicit(ly)?\s+.{0,40}?confirm", section), (
        "confirm step is not gated on explicit user confirmation"
    )
    assert _has(
        r"confirmed:\s*true.{0,120}?confirmed_by:\s*\"user\"", section
    ) or _has(
        r"confirmed_by:\s*\"user\"", section
    ), "confirm step does not write confirmed_by: \"user\""

    # OQ-015 acquisition path: run check-samples on the not-yet-confirmed
    # set; copy the reported fingerprint VERBATIM.
    assert _has(
        r"check-samples.{0,600}?content_fingerprint.{0,200}?verbatim"
        r".{0,200}?confirmation\.content_fingerprint",
        section,
    ) or _has(
        r"copy.{0,120}?content_fingerprint.{0,200}?verbatim", section
    ), "verbatim copy of SampleCheck.content_fingerprint not mandated"
    assert _has(r"not.yet.confirmed", section), (
        "fingerprint must be acquired from check-samples on the"
        " not-yet-confirmed SampleSet"
    )

    # Hand-computation is forbidden.
    assert _has(
        r"never\s+(compute|calculate|hash|recompute|guess|reconstruct)",
        section,
    ), "confirm step does not forbid hand-computing the fingerprint"


def test_fr_023_skill_body_defines_three_exits_no_auto_confirm():
    """FR-023 / AC-012: the loop is unbounded until exactly one of
    confirm / defer / abort; no auto-confirm; defer/abort emit `deferred` /
    `aborted` with no template."""
    section = _sample_loop_section()

    assert _has(r"unbounded", section), "FR-023 unbounded-loop rule missing"
    assert _has(
        r"exactly\s+one", section
    ), "FR-023 exactly-one-exit rule missing"
    for exit_name in ("confirm", "defer", "abort"):
        assert _has(rf"\*\*{exit_name}\*\*", section), (
            f"FR-023 exit {exit_name!r} not defined in section 3"
        )
    assert _has(r"never\s+auto.confirm", section), (
        "FR-023 no-auto-confirm rule missing"
    )
    # AC-012: defer -> deferred, abort -> aborted, and no template on either.
    assert _has(r"defer.{0,200}?status:\s*\"deferred\"", section)
    assert _has(r"abort.{0,200}?status:\s*\"aborted\"", section)
    assert _has(r"no\s+template", section), (
        "AC-012 no-template-on-defer/abort rule missing"
    )


def test_ac_010_scripted_gap_waiver_flow_end_to_end():
    """AC-010 / AC-011 / AC-017 — scripted simulation of the section-3
    protocol using ONLY library calls: proposed obligation gaps →
    user accepts obligation → coverage gap → user accepts a clearing waiver →
    coverage_complete → confirmation with the SampleCheck fingerprint →
    confirmed + ok_for_verify. Every expectation below is what
    `check_samples` actually returns, per §11.1."""
    sample_set = {
        "schema_version": "1.0",
        "intent_nl": "flatten each order's line items with the customer name",
        "coverage": [
            {
                "id": "ob-happy",
                "kind": "happy_path",
                "description": "one order with items flattens",
                "acceptance": "accepted",
            },
            {
                # FR-025: skill-proposed obligation enters as "proposed".
                "id": "ob-empty",
                "kind": "list_empty",
                "target": "/orders",
                "description": "no orders at all",
                "acceptance": "proposed",
            },
        ],
        "cases": [
            {
                "id": "case-happy",
                "input": {"orders": [{"customer": "a", "items": [1]}]},
                "output": [{"customer": "a", "item": 1}],
                "satisfies": ["ob-happy"],
            }
        ],
        "waivers": [],
        "confirmation": {"confirmed": False, "content_fingerprint": ""},
    }

    # Step 1 — proposed obligation is reported as a gap (AC-010 gap codes).
    check = check_samples(sample_set)
    assert check["coverage_complete"] is False
    assert check["confirmed"] is False
    assert check["ok_for_verify"] is False
    codes = [gap["code"] for gap in check["gaps"]]
    assert "obligation_not_accepted" in codes
    gap = next(g for g in check["gaps"] if g["code"] == "obligation_not_accepted")
    assert gap["obligation_id"] == "ob-empty"

    # Step 2 — user accepts the obligation (FR-024 accept/reject) → the
    # obligation is now accepted but unmet: structural gap code reported.
    sample_set["coverage"][1]["acceptance"] = "accepted"
    check = check_samples(sample_set)
    assert check["coverage_complete"] is False
    codes = [gap["code"] for gap in check["gaps"]]
    assert "list_empty_unmet" in codes

    # Step 3 — user accepts a proposed waiver clearing the obligation
    # (FR-024: structured waivers that clear obligation ids) → coverage
    # complete, still unconfirmed (AC-017 independence).
    sample_set["waivers"].append(
        {
            "id": "waive-empty",
            "clears_obligation_ids": ["ob-empty"],
            "reason": "upstream guarantees at least one order",
            "acceptance": "accepted",
        }
    )
    check = check_samples(sample_set)
    assert check["coverage_complete"] is True
    assert check["confirmed"] is False
    assert check["ok_for_verify"] is False
    # OQ-018(a/b): the pre-confirmation placeholder "" differs from the
    # recomputed fingerprint, so fingerprint_mismatch rides along with
    # unconfirmed until 3.3 binds the real value.
    assert [gap["code"] for gap in check["gaps"]] == [
        "unconfirmed",
        "fingerprint_mismatch",
    ]

    # Step 4 — confirm (AC-011): fingerprint comes VERBATIM from the
    # SampleCheck on the not-yet-confirmed set (OQ-015 acquisition path).
    fingerprint = check["content_fingerprint"]
    assert re.fullmatch(r"[0-9a-f]{64}", fingerprint)
    sample_set["confirmation"] = {
        "confirmed": True,
        "confirmed_by": "user",
        "content_fingerprint": fingerprint,
    }

    # Step 5 — re-run: confirmed + ok_for_verify, no gaps (AC-029 schema half
    # already proves the mismatch flip; here the happy path closes AC-010).
    check = check_samples(sample_set)
    assert check["coverage_complete"] is True
    assert check["confirmed"] is True
    assert check["ok_for_verify"] is True
    assert check["gaps"] == []
    assert check["content_fingerprint"] == fingerprint
