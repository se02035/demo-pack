#!/usr/bin/env python3
"""Acme Widgets CLI. Copy-adapt: replace acme_widgets, ACME ids, and the SDK.

argparse facade over the official Python client proven in probes.
``help`` and ``--version`` must not construct the client.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from typing import Any, Sequence

from acme_widgets import __version__

# Replace with live values from probes.
API_VERSION = "v1"
DEFAULT_WAIT_TIMEOUT_S = 300


@dataclass(frozen=True)
class IssueBlurb:
    """One known issue surfaced in ``help`` JSON.

    Attributes:
        id: Stable prefix id (for example ``ACME-1``).
        workaround: One-line action the caller should take.
    """

    id: str
    workaround: str


@dataclass(frozen=True)
class CommandHelp:
    """Machine-readable help for one CLI command.

    Attributes:
        name: Dotted command name such as ``widgets.list``.
        summary: One-line description.
        when: When an agent should pick this command.
        required_flags: Flags that must be present.
        optional_flags: Flags that may be omitted.
        placeholders: Tokens used in the example (never real ids).
        example: Copy-paste invocation with placeholders.
        issues: Known mismatches that apply before running the command.
    """

    name: str
    summary: str
    when: str
    required_flags: tuple[str, ...]
    optional_flags: tuple[str, ...]
    placeholders: tuple[str, ...]
    example: str
    issues: tuple[IssueBlurb, ...]


ACME_1 = IssueBlurb(
    id="ACME-1",
    workaround="There is no vendor CLI for this API; use acme-widgets.",
)


def usage_catalog() -> dict[str, Any]:
    """Return the agent-facing help catalog.

    Returns:
        JSON-serializable dict with a ``commands`` list.
    """

    commands = (
        CommandHelp(
            name="widgets.list",
            summary="List widgets in the user-stated environment.",
            when="The user asks to list or discover widgets.",
            required_flags=("--env",),
            optional_flags=(),
            placeholders=("ENV",),
            example="acme-widgets --env ENV widgets list",
            issues=(ACME_1,),
        ),
        CommandHelp(
            name="widgets.delete",
            summary="Delete a widget. Requires --yes.",
            when="The user asks to delete a named widget.",
            required_flags=("--env", "NAME", "--yes"),
            optional_flags=(),
            placeholders=("ENV", "NAME"),
            example="acme-widgets --env ENV widgets delete NAME --yes",
            issues=(ACME_1,),
        ),
    )
    return {"commands": [asdict(item) for item in commands]}


def emit(payload: Any) -> None:
    """Write JSON to stdout."""

    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


def emit_error(message: str, issue: str | None = None, code: int = 2) -> int:
    """Write an error object and return a non-zero code.

    Args:
        message: Plain-language error.
        issue: Known-issue id, or None.
        code: Process exit code.

    Returns:
        The exit code.
    """

    emit({"error": message, "issue": issue})
    return code


def make_client(env: str) -> Any:
    """Construct the official SDK client. Do not call from help/version.

    Args:
        env: User-stated environment flag.

    Returns:
        SDK client. Replace this body with the live constructor.
    """

    raise NotImplementedError("replace make_client with the probed SDK constructor")


def require_env(args: argparse.Namespace) -> str | None:
    """Return env or None if missing.

    Args:
        args: Parsed CLI args.

    Returns:
        The env string, or None.
    """

    env = getattr(args, "env", None)
    if not env:
        return None
    return str(env)


def build_parser() -> argparse.ArgumentParser:
    """Build the argparse tree.

    Returns:
        Parser with ``prog="acme-widgets"``.
    """

    parser = argparse.ArgumentParser(prog="acme-widgets")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument(
        "--env",
        default=None,
        help="Target environment (required on API commands; no default).",
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("help", help="JSON usage catalog (no API client).")

    widgets = sub.add_parser("widgets")
    wsub = widgets.add_subparsers(dest="widgets_command")
    wsub.add_parser("list")
    delete = wsub.add_parser("delete")
    delete.add_argument("name")
    delete.add_argument(
        "--yes",
        action="store_true",
        help="Confirm destructive delete.",
    )
    return parser


def main_with_args(argv: Sequence[str] | None = None) -> int:
    """Run the CLI.

    Args:
        argv: Argument vector without the program name.

    Returns:
        Process exit code.
    """

    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.command == "help" or args.command is None:
        emit(usage_catalog())
        return 0

    env = require_env(args)
    if env is None:
        return emit_error("Missing required --env. Do not guess. Ask the user.", None)

    if args.command == "widgets" and args.widgets_command == "delete":
        if not args.yes:
            return emit_error("Refusing delete without --yes.", None)
        # Example refuse: replace with real kind/precondition checks from probes.
        if args.name == "known-broken":
            return emit_error("Refusing a known-broken call.", "ACME-1")

    # API commands construct the client only after help/version and required flags.
    _client = make_client(env)
    emit({"ok": True, "env": env, "command": args.command})
    return 0


def main() -> None:
    """Entrypoint for ``acme-widgets`` and ``python3 -m acme_widgets``."""

    raise SystemExit(main_with_args())


if __name__ == "__main__":
    main()
