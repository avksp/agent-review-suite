"""Command-line entry point for bounded validation."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from typing import Never

from agent_review_suite.contracts import ValidationError
from agent_review_suite.validation import validate_inputs


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        raise ValidationError()


def main(argv: Sequence[str] | None = None) -> int:
    """Return a fixed status and never echo untrusted values."""
    parser = _Parser(prog="agent_review_suite")
    subcommands = parser.add_subparsers(dest="command", required=True, parser_class=_Parser)
    validate = subcommands.add_parser(
        "validate", add_help=False, help="check a request or report against trusted expectations"
    )
    validate.add_argument("--kind", choices=("request", "report"), required=True)
    validate.add_argument("--input", required=True)
    validate.add_argument("--root", required=True)
    validate.add_argument("--expectations", required=True)
    try:
        args = parser.parse_args(argv)
        descriptor = -1
        if args.input == "-":
            if sys.stdin is None:
                raise ValidationError()
            descriptor = sys.stdin.fileno()
        validate_inputs(args.kind, args.input, args.root, args.expectations, stdin_descriptor=descriptor)
    except ValidationError as exc:
        if exc.kind == "binding-mismatch":
            print("ARS validation failed: expected bindings differ.", file=sys.stderr)
            return 3
        print("ARS validation failed: malformed, refused, or unsupported input.", file=sys.stderr)
        return 2
    except (OSError, ValueError):
        print("ARS validation failed: malformed, refused, or unsupported input.", file=sys.stderr)
        return 2
    print('{"status":"VALID"}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
