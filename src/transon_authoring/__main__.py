"""Module CLI entry — ``python -m transon_authoring`` (SPEC §11.6; FR-014;
§14 A0 DoD; AD-006).

A0 scope: only the ``metadata`` subcommand — it writes the bundled pinned
``resources/metadata-snapshot.json`` bytes VERBATIM to stdout (byte-stable;
§11.6 global contract: stdout = one JSON value, stderr = human diagnostics
only) and exits 0. It never touches the live engine (NFR-003 offline;
AD-018 grounding: the pinned snapshot is the answer-time source).

Any other or missing subcommand is an argparse usage error on stderr with
exit ``2`` (§11.6 exit codes). The remaining subcommands and the JSON
schema-error envelope machinery (FR-026) land at A1.
"""

from __future__ import annotations

import sys

from transon_authoring import metadata


def main(argv: list[str] | None = None) -> int:
    """Run the module CLI; returns the §11.6 exit code.

    ``argparse`` handles usage errors itself: unknown/missing subcommands
    raise ``SystemExit(2)`` with the usage message on stderr.
    """
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m transon_authoring",
        description=(
            "transon-authoring module CLI (SPEC §11.6). A0: `metadata` only; "
            "further subcommands land at A1."
        ),
    )
    subcommands = parser.add_subparsers(dest="subcommand", required=True)
    subcommands.add_parser(
        "metadata",
        help=(
            "print the bundled pinned get_editor_metadata() snapshot "
            "(resources/metadata-snapshot.json) verbatim on stdout"
        ),
    )
    parser.parse_args(argv)

    # `required=True` guarantees the only reachable subcommand is `metadata`.
    sys.stdout.buffer.write(metadata._resource_bytes("metadata-snapshot.json"))
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
