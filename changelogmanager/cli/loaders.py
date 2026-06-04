# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog loading and formatter resolution for CLI commands."""

from __future__ import annotations

import argparse
import tempfile
from pathlib import Path
from typing import Any

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.config import (
    get_component_from_config,
    get_format_options,
    get_preamble_keywords,
    get_validation_options,
    get_versioning_scheme,
)
from changelogmanager.formatting import Formatter
from changelogmanager.formatting import (
    discover_formatter as discover_formatter,
)  # noqa: PLC0414 (re-exported; patched in tests)
from changelogmanager.runtime_logging import VERBOSE, get_logger
from changelogmanager.versioning import detect_versioning_scheme_from_file

logger = get_logger(__name__)


def load_changelog(config: str | None, component: str, input_file: str) -> Changelog:
    """Loads the changelog configured for this invocation."""

    logger.info(
        "Loading changelog with config=%s component=%s input_file=%s",
        config or "<none>",
        component,
        input_file,
    )
    file_path = resolve_changelog_file(config, component, input_file)

    enforce_preamble = bool(
        get_validation_options(config).get("enforce_preamble", False)
    )
    preamble_keywords = get_preamble_keywords(config)
    versioning_scheme = resolve_versioning_scheme(config, file_path)

    changelog_dict = ChangelogReader(
        file_path=file_path,
        enforce_preamble=enforce_preamble,
        preamble_keywords=preamble_keywords,
        versioning_scheme=versioning_scheme,
    ).read()
    logger.info("Loaded changelog file %s", file_path)
    return Changelog(
        file_path=file_path,
        changelog=changelog_dict,
        versioning_scheme=versioning_scheme,
    )


def resolve_changelog_file(config: str | None, component: str, input_file: str) -> str:
    """Returns the changelog path for the current config/component selection."""

    if config:
        component_config = get_component_from_config(config=config, component=component)
        return str(component_config.get("changelog", input_file))
    return input_file


def resolve_versioning_scheme(config: str | None, file_path: str) -> str:
    """Returns configured scheme, or detects it from the changelog preamble."""

    if config:
        return get_versioning_scheme(config)
    return detect_versioning_scheme_from_file(file_path) or get_versioning_scheme(
        config
    )


def load_changelog_for_validate_fix(
    args: argparse.Namespace, config: str | None
) -> Changelog:
    """Loads a changelog after applying raw-text validate --fix repairs."""

    file_path = resolve_changelog_file(config, args.component, args.input_file)
    enforce_preamble = bool(
        get_validation_options(config).get("enforce_preamble", False)
    )
    preamble_keywords = get_preamble_keywords(config)
    versioning_scheme = resolve_versioning_scheme(config, file_path)

    reader = ChangelogReader(
        file_path=file_path,
        enforce_preamble=enforce_preamble,
        preamble_keywords=preamble_keywords,
        versioning_scheme=versioning_scheme,
    )
    fixed_text, raw_applied = reader.autofix_text()
    args.raw_autofixes = raw_applied

    read_path = file_path
    temp_path: str | None = None
    if raw_applied:
        if getattr(args, "dry_run", False):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="UTF-8",
                suffix=".md",
                dir=str(Path(file_path).resolve().parent),
                delete=False,
            ) as temp_handle:
                temp_handle.write(fixed_text)
                temp_path = temp_handle.name
            read_path = temp_path
        else:
            Path(file_path).write_text(fixed_text, encoding="UTF-8")

    try:
        changelog_dict = ChangelogReader(
            file_path=read_path,
            enforce_preamble=enforce_preamble,
            preamble_keywords=preamble_keywords,
            versioning_scheme=versioning_scheme,
        ).read()
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    return Changelog(
        file_path=file_path,
        changelog=changelog_dict,
        versioning_scheme=versioning_scheme,
    )


def resolve_formatter(
    args: argparse.Namespace, config: Any
) -> tuple[Any, dict[str, Any]]:
    """Returns (formatter_or_None, mdformat_options) honouring CLI flags and config."""

    format_opts = get_format_options(config)
    mdformat_options: dict[str, Any] = format_opts.get("mdformat_options") or {}

    no_format: bool = getattr(args, "no_format", False)
    force_format: bool = getattr(args, "format", False)
    config_format = format_opts.get("format", "auto")

    if no_format or config_format is False or config_format == "false":
        logger.log(VERBOSE, "Format pass disabled by --no-format or config")
        return None, mdformat_options

    formatter: Formatter | None = discover_formatter()

    if (
        force_format or config_format is True or config_format == "true"
    ) and formatter is None:
        raise logging.Error(
            message=(
                "Markdown format pass requested (--format or format: true) "
                "but no formatter is available. "
                "Install mdformat: pip install 'keepachangelog-manager-fork[format]'"
            )
        )

    return formatter, mdformat_options
