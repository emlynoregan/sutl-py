"""Command-line interface for evaluating sUTL programs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional, Sequence, TextIO

from . import __version__, evaluate


def _json_value(argument: str, stdin: TextIO) -> Any:
    """Load JSON from a literal, ``@file``, or standard input (``-``)."""
    if argument == "-":
        text = stdin.read()
    elif argument.startswith("@"):
        text = Path(argument[1:]).read_text(encoding="utf-8")
    else:
        text = argument
    return json.loads(text)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sutl",
        description=(
            "Evaluate a sUTL 1.0 transform. Arguments are JSON literals; "
            "prefix a path with @ to read JSON from a file, or use - for stdin."
        ),
    )
    parser.add_argument("source", help="source JSON, @file, or -")
    parser.add_argument("transform", help="transform JSON or @file")
    parser.add_argument(
        "--library",
        default="{}",
        help="library map as JSON or @file (default: {})",
    )
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="pretty-print the result",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the command-line interface and return its process exit code."""
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        source = _json_value(args.source, sys.stdin)
        transform = _json_value(args.transform, sys.stdin)
        library = _json_value(args.library, sys.stdin)
        if not isinstance(library, dict):
            parser.error("--library must decode to a JSON object")
        result = evaluate(source, transform, library)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        parser.error(str(error))

    json.dump(
        result,
        sys.stdout,
        ensure_ascii=False,
        indent=2 if args.pretty else None,
        separators=None if args.pretty else (",", ":"),
    )
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
