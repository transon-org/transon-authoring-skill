"""Module CLI entry — ``python -m transon_authoring`` (SPEC §11.6; FR-003 /
FR-014 / AC-021; §14 A1 DoD; AD-006).

A1 surface: ``metadata`` (A0 behavior kept verbatim — bundled pinned snapshot
bytes on stdout, exit 0), ``examples search``, ``check-samples``, ``verify``
(single-shot; **no** ``--repair-attempts``, FR-007), ``validate`` and
``dry-run``. ``init-config`` is A2 scope and stays an unknown command
(argparse usage error, exit 2).

Contract highlights implemented here:

* **Emission discipline (§11.0/§11.6):** exactly ONE JSON document on stdout
  per invocation, written in a single compact write (``ensure_ascii=False``,
  ``allow_nan=False``, ``separators=(",", ":")``) plus a trailing newline;
  stderr carries human diagnostics only, never machine output.
* **Ingress (FR-026 / AC-026 / OQ-014c):** unreadable files, strict-JSON
  failures (duplicate keys, non-finite numbers), bundled JSON-Schema failures
  and unsupported ``schema_version`` → exit 2 with a ``CliError``
  ``schema-error`` envelope of ``PreflightError`` entries. Templates, inputs
  and includes are schema-free plain JSON, except that ``--includes`` must be
  a bare JSON object of the ``SampleSet.includes`` map shape (OQ-014d).
* **Reserved profile knobs (FR-028 / AC-027):** ``--marker`` /
  ``--transformer`` parse for forward-compat but are rejected post-parse,
  BEFORE any input file read or engine work — exit 2, ``CliError``
  ``profile-rejected`` with exactly one stable-text ``ProfileError``.
* **Exit codes (§11.6):** 0 success; 1 semantic failure on schema-valid
  inputs; 2 usage/schema/profile error; 3 internal fault — best-effort
  ``CliError`` ``internal-error`` on stdout, traceback on stderr (OQ-014a).
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from typing import Any

from transon_authoring import metadata
from transon_authoring._ingress import (
    IngressError,
    load_document,
    load_json_file,
    preflight_error,
)
from transon_authoring.examples import search_examples
from transon_authoring.samples import check_samples
from transon_authoring.verify import dry_run, validate, verify

#: Reserved profile knobs (§11.6 / AC-027): parsed for forward compatibility,
#: rejected post-parse in a fixed order before any input file is read.
_RESERVED_KNOBS = (("marker", "--marker"), ("transformer", "--transformer"))


class _ProfileRejected(Exception):
    """A reserved profile knob was requested (AC-027). ``flag`` is the CLI
    flag name; the rejection happens before any file read or engine work."""

    def __init__(self, flag: str):
        self.flag = flag
        super().__init__(flag)


def _profile_error_message(flag: str) -> str:
    """Stable library text for the single ProfileError (§11.6; never
    parameterized by the requested value)."""
    return (
        f"{flag} is a reserved profile knob: v1 always executes under the"
        ' AD-017 default profile (base Transformer, marker "$") and rejects'
        " non-default profiles (SPEC §11.6 / AC-027)"
    )


def _cli_error(status: str, explanation: str, errors: list) -> dict[str, Any]:
    """§11.6 CliError envelope (always ``ok: false`` — AC-026)."""
    return {
        "schema_version": "1.0",
        "ok": False,
        "status": status,
        "explanation": explanation,
        "errors": errors,
    }


def _emit(document: Any) -> None:
    """Write the one machine result: a single compact write on stdout with a
    trailing newline (§11.0 serialization; §11.6 global contract)."""
    sys.stdout.write(
        json.dumps(
            document, ensure_ascii=False, allow_nan=False, separators=(",", ":")
        )
        + "\n"
    )
    sys.stdout.flush()


def _reject_reserved_knobs(args: argparse.Namespace) -> None:
    for attr, flag in _RESERVED_KNOBS:
        if getattr(args, attr, None) is not None:
            raise _ProfileRejected(flag)


# ---------------------------------------------------------------------------
# Subcommand handlers (dispatched via parser set_defaults; each returns the
# §11.6 exit code)
# ---------------------------------------------------------------------------


def _cmd_metadata(_args: argparse.Namespace) -> int:
    """A0 behavior, unchanged: the bundled pinned snapshot bytes VERBATIM —
    an engine document exempt from the ``schema_version`` envelope rule."""
    sys.stdout.buffer.write(metadata._resource_bytes("metadata-snapshot.json"))
    sys.stdout.buffer.flush()
    return 0


def _cmd_examples_search(args: argparse.Namespace) -> int:
    _emit({"schema_version": "1.0", "hits": search_examples(args.query, limit=args.limit)})
    return 0


def _cmd_check_samples(args: argparse.Namespace) -> int:
    # Full ingress (read, strict parse, schema_version, sample_set.json):
    # schema invalidity is a CLI-level exit 2 CliError, NOT an all-flags-false
    # SampleCheck body — that library behavior is for embedded use (§11.6).
    sample_set = load_document(args.samples, "sample_set.json")
    result = check_samples(sample_set)
    _emit(result)
    return 0 if result["ok_for_verify"] else 1


def _cmd_verify(args: argparse.Namespace) -> int:
    _reject_reserved_knobs(args)
    # Template is schema-free plain Transon JSON (§11.0): strict parse only.
    template = load_json_file(args.template)
    sample_set = load_document(args.samples, "sample_set.json")
    verdict = verify(template, sample_set)
    _emit(verdict)
    return 0 if verdict["ok"] else 1


def _cmd_validate(args: argparse.Namespace) -> int:
    _reject_reserved_knobs(args)
    template = load_json_file(args.template)
    result = validate(template)
    _emit({"schema_version": "1.0", "ok": result["ok"], "errors": result["errors"]})
    return 0 if result["ok"] else 1


def _load_includes(path: str) -> dict:
    """OQ-014d: the ``--includes`` file is exactly the ``SampleSet.includes``
    map shape — a bare JSON object; any other JSON value → schema-error."""
    includes = load_json_file(path)
    if not isinstance(includes, dict):
        raise IngressError(
            [
                preflight_error(
                    f"{path}: --includes must be a bare JSON object"
                    " (include name -> template JSON), no schema_version"
                    " wrapper; got a non-object JSON value"
                )
            ]
        )
    return includes


def _cmd_dry_run(args: argparse.Namespace) -> int:
    _reject_reserved_knobs(args)
    template = load_json_file(args.template)
    input_value = load_json_file(args.input)
    includes = _load_includes(args.includes) if args.includes is not None else None
    envelope = dry_run(template, input_value, includes)
    # OQ-014b: on success `result` AND `writes` both present (`writes` may be
    # {}); on failure both omitted and `errors` non-empty.
    document: dict[str, Any] = {"schema_version": "1.0", "ok": envelope["ok"]}
    if envelope["ok"]:
        document["result"] = envelope["result"]
        document["writes"] = envelope["writes"]
    document["errors"] = envelope["errors"]
    _emit(document)
    return 0 if envelope["ok"] else 1


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def _positive_int(text: str) -> int:
    value = int(text)  # ValueError → argparse invalid-value usage error
    if value < 1:
        raise argparse.ArgumentTypeError("must be >= 1")
    return value


def _add_reserved_knobs(subparser: argparse.ArgumentParser) -> None:
    for _attr, flag in _RESERVED_KNOBS:
        subparser.add_argument(
            flag,
            metavar="RESERVED",
            help=(
                "reserved profile knob; always rejected with a ProfileError"
                " (exit 2, SPEC §11.6 / AC-027)"
            ),
        )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m transon_authoring",
        description=(
            "transon-authoring module CLI (SPEC §11.6). stdout carries exactly"
            " one JSON result document; stderr is human diagnostics only."
        ),
    )
    subcommands = parser.add_subparsers(dest="subcommand", required=True)

    metadata_parser = subcommands.add_parser(
        "metadata",
        help=(
            "print the bundled pinned get_editor_metadata() snapshot"
            " (resources/metadata-snapshot.json) verbatim on stdout"
        ),
    )
    metadata_parser.set_defaults(handler=_cmd_metadata)

    examples_parser = subcommands.add_parser(
        "examples", help="example-corpus operations over the pinned snapshot"
    )
    examples_subcommands = examples_parser.add_subparsers(
        dest="examples_subcommand", required=True
    )
    search_parser = examples_subcommands.add_parser(
        "search", help="search the snapshot docs.examples corpus (FR-010/OQ-022)"
    )
    search_parser.add_argument("query", help="natural-language / name / tag query")
    search_parser.add_argument(
        "--limit",
        type=_positive_int,
        default=10,
        metavar="N",
        help="maximum number of hits (>= 1, default 10)",
    )
    search_parser.set_defaults(handler=_cmd_examples_search)

    check_parser = subcommands.add_parser(
        "check-samples",
        help="run check_samples on a SampleSet file (exit 0 iff ok_for_verify)",
    )
    check_parser.add_argument(
        "--samples", required=True, metavar="PATH", help="SampleSet JSON file"
    )
    check_parser.set_defaults(handler=_cmd_check_samples)

    verify_parser = subcommands.add_parser(
        "verify",
        help=(
            "single-shot verify of a template against a SampleSet"
            " (exit 0 iff the Verdict is ok / matched); no repair loop"
        ),
    )
    verify_parser.add_argument(
        "--template", required=True, metavar="PATH", help="template JSON file"
    )
    verify_parser.add_argument(
        "--samples", required=True, metavar="PATH", help="SampleSet JSON file"
    )
    _add_reserved_knobs(verify_parser)
    verify_parser.set_defaults(handler=_cmd_verify)

    validate_parser = subcommands.add_parser(
        "validate", help="engine validate() debug check of a template (exit 0/1)"
    )
    validate_parser.add_argument(
        "--template", required=True, metavar="PATH", help="template JSON file"
    )
    _add_reserved_knobs(validate_parser)
    validate_parser.set_defaults(handler=_cmd_validate)

    dry_run_parser = subcommands.add_parser(
        "dry-run",
        help="sandboxed dry-run debug of one template + input (exit 0/1)",
    )
    dry_run_parser.add_argument(
        "--template", required=True, metavar="PATH", help="template JSON file"
    )
    dry_run_parser.add_argument(
        "--input", required=True, metavar="PATH", help="input JSON file"
    )
    dry_run_parser.add_argument(
        "--includes",
        metavar="PATH",
        help="bare JSON object mapping include name -> template JSON (OQ-014d)",
    )
    _add_reserved_knobs(dry_run_parser)
    dry_run_parser.set_defaults(handler=_cmd_dry_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the module CLI; returns the §11.6 exit code.

    ``argparse`` handles usage errors itself (unknown/missing subcommand or
    flag → ``SystemExit(2)``, usage text on stderr, nothing on stdout).
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except _ProfileRejected as exc:
        message = _profile_error_message(exc.flag)
        _emit(
            _cli_error(
                "profile-rejected",
                message,
                [{"type": "ProfileError", "message": message}],
            )
        )
        return 2
    except IngressError as exc:
        _emit(_cli_error("schema-error", str(exc), exc.errors))
        return 2
    except Exception as exc:  # noqa: BLE001 — OQ-014a internal-fault contract
        traceback.print_exc(file=sys.stderr)
        _emit(_cli_error("internal-error", f"{type(exc).__name__}: {exc}", []))
        return 3


if __name__ == "__main__":
    sys.exit(main())
