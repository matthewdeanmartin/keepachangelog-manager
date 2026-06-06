# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""CLI entrypoint and command dispatch."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import orjson

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.changelog import Changelog
from changelogmanager.cli.commands import run_validate_all
from changelogmanager.cli.config_resolve import (
    apply_config_defaults,
    configure_logging,
    resolve_config,
)
from changelogmanager.cli.context import CliContext
from changelogmanager.cli.loaders import load_changelog, load_changelog_for_validate_fix
from changelogmanager.cli.parser import build_parser
from changelogmanager.config import get_versioning_scheme
from changelogmanager.runtime_logging import configure_runtime_logging, get_logger

logger = get_logger(__name__)


def main(  # pylint: disable=too-many-return-statements
    argv: Sequence[str] | None = None,
) -> int:
    """CLI entrypoint."""

    parser = build_parser()

    try:
        args = parser.parse_args(argv)
        configure_runtime_logging(
            info=bool(getattr(args, "info", False) or getattr(args, "verbose", False)),
            verbose=bool(getattr(args, "verbose", False)),
        )
        logger.info("Starting CLI command %s", getattr(args, "command", "<none>"))
        if args.command == "gui":
            from changelogmanager.gui import (
                run_gui,
            )  # pylint: disable=import-outside-toplevel

            return run_gui()

        config_arg = args.config if isinstance(args.config, str) else None
        resolved_config = resolve_config(config_arg)
        args.resolved_config_path = resolved_config

        # Apply config-backed flag defaults (flag > env > config > built-in default)
        # before consuming any defaulted flag such as --error-format. Skip when the
        # explicit config path does not exist yet (e.g. `config init --config new`).
        config_for_defaults = (
            resolved_config
            if resolved_config and Path(resolved_config).is_file()
            else None
        )
        apply_config_defaults(args, config_for_defaults)
        configure_logging(args.error_format)

        # --all branch for validate uses an aggregate flow, no single changelog load.
        if args.command == "validate" and getattr(args, "all_components", False):
            if not resolved_config:
                raise logging.Error(
                    message=(
                        "--all requires a configuration file (use --config or place changelogmanager.toml in cwd)"
                    ),
                )
            ctx = CliContext(
                changelog=Changelog(file_path="<all>"),
                quiet=args.quiet,
                json_output=args.json,
            )
            exit_code = run_validate_all(args, ctx, resolved_config)
            if args.json:
                print(
                    orjson.dumps(ctx.json_payload, option=orjson.OPT_INDENT_2).decode()
                )
            logger.info(
                "Finished CLI command %s with exit code %d", args.command, exit_code
            )
            return exit_code

        # from-commits --all routes commits across components; no single load.
        if args.command == "from-commits" and getattr(args, "all_components", False):
            ctx = CliContext(
                changelog=Changelog(file_path="<all>"),
                quiet=args.quiet,
                json_output=args.json,
            )
            args.handler(args, ctx)
            if args.json:
                print(
                    orjson.dumps(ctx.json_payload, option=orjson.OPT_INDENT_2).decode()
                )
            logger.info("Finished CLI command %s successfully", args.command)
            return 0

        # lint-commits and rewrite-messages operate on git history, not the
        # changelog: placeholder context, never reads the changelog from disk.
        if args.command in {"lint-commits", "rewrite-messages"}:
            ctx = CliContext(
                changelog=Changelog(file_path="<commits>"),
                quiet=args.quiet,
                json_output=args.json,
            )
            args.handler(args, ctx)
            if args.json:
                print(
                    orjson.dumps(ctx.json_payload, option=orjson.OPT_INDENT_2).decode()
                )
            logger.info("Finished CLI command %s successfully", args.command)
            return 0

        if args.command in {"config", "skill"}:
            # `config` / `config init` may legitimately point --config at a path
            # that does not exist yet (the init handler creates it). Only resolve
            # the versioning scheme from a config file that is actually present;
            # otherwise fall back to defaults so dispatch does not crash before the
            # handler can create the file.
            existing_config = (
                resolved_config
                if resolved_config and Path(resolved_config).is_file()
                else None
            )
            versioning_scheme = (
                get_versioning_scheme(existing_config)
                if args.command == "config"
                else "semver"
            )
            context = CliContext(
                changelog=Changelog(
                    file_path=args.input_file or "CHANGELOG.md",
                    versioning_scheme=versioning_scheme,
                ),
                quiet=args.quiet,
                json_output=args.json,
            )
            args.handler(args, context)
            if args.json:
                print(
                    orjson.dumps(
                        context.json_payload, option=orjson.OPT_INDENT_2
                    ).decode()
                )
            logger.info("Finished CLI command %s successfully", args.command)
            return 0

        changelog = (
            load_changelog_for_validate_fix(args, resolved_config)
            if args.command == "validate" and getattr(args, "fix", False)
            else load_changelog(
                config=resolved_config,
                component=args.component,
                input_file=args.input_file,
            )
        )
        context = CliContext(
            changelog=changelog,
            quiet=args.quiet,
            json_output=args.json,
        )
        args.handler(args, context)
        if args.json:
            print(
                orjson.dumps(context.json_payload, option=orjson.OPT_INDENT_2).decode()
            )
        logger.info("Finished CLI command %s successfully", args.command)
        return 0
    except (logging.Info, logging.Warning) as exc_info:
        logger.info(
            "CLI command completed with non-error diagnostic: %s", exc_info.message
        )
        exc_info.report()
        return 0
    except logging.Error as exc_info:
        logger.error("CLI command failed: %s", exc_info.message)
        exc_info.report()
        return 1
    except SystemExit as exc_info:
        logger.error("CLI exited via SystemExit: %s", exc_info)
        return exc_info.code if isinstance(exc_info.code, int) else 1
