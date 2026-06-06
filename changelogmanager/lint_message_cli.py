# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Fast-starting ``commit-msg`` linter entry point.

Wired as the ``changelogmanager-lint-message`` console script and referenced by
``.pre-commit-hooks.yaml`` at the ``commit-msg`` stage. It is deliberately *not*
routed through the full :mod:`changelogmanager.cli` argparse tree so the hook
does not pay for the GUI / github / gitlab / pypi import graph on every commit.

Usage::

    changelogmanager-lint-message [--config FILE] [--error-format llvm|github]
                                  [--schema auto|...] COMMIT_MSG_FILE

Exit codes:
  0  subject passes (changelog, skip, or exempt)
  1  lint failure (unclassified subject)
  2  usage / configuration error
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.llvm_diagnostics import Range
from changelogmanager.message_lint import (
    LintOutcome,
    classify_subject,
    subject_of,
)


def _configure_formatter(error_format: str) -> None:
    logging.config(
        logging.formatters.Llvm()
        if error_format == "llvm"
        else logging.formatters.GitHub()
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="changelogmanager-lint-message",
        description=(
            "Lint a commit message subject against the Keep a Changelog commit "
            "schema (intended for the pre-commit commit-msg stage)."
        ),
    )
    parser.add_argument(
        "message_file",
        help="Path to the commit message file passed by git/pre-commit",
    )
    parser.add_argument(
        "--config",
        default=None,
        help="Configuration file (defaults to auto-detection in cwd)",
    )
    parser.add_argument(
        "-f",
        "--error-format",
        choices=["llvm", "github"],
        default="llvm",
        help="Diagnostic formatting for failures",
    )
    parser.add_argument(
        "--schema",
        choices=["auto", "conventional", "gitmoji", "keepachangelog"],
        default=None,
        help="Override the commit-message schema (defaults to config or auto)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Lints the subject line of a commit message file."""

    from changelogmanager.cli.config_resolve import resolve_config  # noqa: PLC0415
    from changelogmanager.config import get_message_lint_options  # noqa: PLC0415

    parser = _build_parser()
    args = parser.parse_args(argv)
    _configure_formatter(args.error_format)

    try:
        config_path = resolve_config(args.config)
        options = get_message_lint_options(config_path)
    except logging.Error as exc:
        exc.report()
        return 2

    if args.schema is not None:
        from dataclasses import replace  # noqa: PLC0415

        options = replace(options, schema=args.schema)

    try:
        message = Path(args.message_file).read_text(encoding="utf-8")
    except OSError as exc:
        logging.Error(
            file_path=args.message_file,
            message=f"could not read commit message file: {exc}",
        ).report()
        return 2

    subject = subject_of(message)
    result = classify_subject(subject, options=options)

    if result.outcome is not LintOutcome.UNCLASSIFIED:
        return 0

    logging.Error(
        file_path=args.message_file,
        line_number=Range(start=1),
        column_number=Range(start=1),
        message=(
            f"commit subject is not classifiable by the '{options.schema}' "
            f"schema: {result.reason}"
        ),
        line=subject,
    ).report()
    return 1


if __name__ == "__main__":  # pragma: no cover
    import sys

    sys.exit(main())
