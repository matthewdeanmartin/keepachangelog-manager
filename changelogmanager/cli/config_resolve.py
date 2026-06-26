# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Configuration resolution and the flag > env > config > default precedence."""

from __future__ import annotations

import argparse
import os
from typing import Any

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.config import (
    auto_detect_config,
    get_defaults_options,
    get_github_options,
    get_gitlab_options,
)
from changelogmanager.gitlab import DEFAULT_GITLAB_URL
from changelogmanager.runtime_logging import VERBOSE, get_logger
from changelogmanager.schema_validation import DEFAULT_SCHEMA_VERSION

logger = get_logger(__name__)


def configure_logging(error_format: str) -> None:
    """Configures diagnostic formatting."""

    logger.log(VERBOSE, "Configuring diagnostic formatter: %s", error_format)
    logging.config(
        logging.formatters.Llvm()
        if error_format == "llvm"
        else logging.formatters.GitHub()
    )


def running_in_github_actions() -> bool:
    """Returns True when the process appears to be running inside GitHub Actions.

    GitHub Actions always sets ``GITHUB_ACTIONS=true`` (and exposes the
    ``GITHUB_*`` family). We key off ``GITHUB_ACTIONS`` specifically so that
    GitLab CI (which also sets a generic ``CI``) does not trip this branch.
    """

    return os.environ.get("GITHUB_ACTIONS", "").strip().lower() == "true"


def detect_default_error_format() -> str:
    """Picks the default diagnostic format when neither flag nor config sets it.

    Inside GitHub Actions, ``github`` annotations render inline on the PR/run,
    so default to that; everywhere else keep the human-friendly ``llvm`` format.
    """

    return "github" if running_in_github_actions() else "llvm"


def resolve_config(config: str | None) -> str | None:
    """Returns ``config`` if provided, otherwise auto-detects in cwd."""

    if config:
        logger.info("Using explicit configuration path %s", config)
        return config
    detected = auto_detect_config()
    if detected:
        logger.info("Using auto-detected configuration path %s", detected)
    else:
        logger.info("No configuration file found; using built-in defaults")
    return detected


# Maps an args attribute to (config getter, config key, built-in default). When the
# arg is still at its built-in default, the config value (if any) is applied. Tokens
# are intentionally excluded: they stay flag-or-env only.
#
# Precedence: explicit CLI flag > env var (handled in command handlers) > config > default.
CONFIG_DEFAULTS: tuple[tuple[str, Any, str, Any], ...] = (
    ("error_format", get_defaults_options, "error_format", None),
    ("commit_schema", get_defaults_options, "commit_schema", "auto"),
    ("schema_version", get_defaults_options, "schema_version", DEFAULT_SCHEMA_VERSION),
    ("bump_versions", get_defaults_options, "bump_versions", False),
    ("pyproject_only", get_defaults_options, "pyproject_only", False),
    ("repository", get_github_options, "repository", None),
    ("project", get_gitlab_options, "project", None),
    ("gitlab_url", get_gitlab_options, "url", DEFAULT_GITLAB_URL),
)


def apply_config_defaults(args: argparse.Namespace, config: str | None) -> None:
    """Fills args still at their built-in default with values from config.

    Implements the "config" tier of the precedence chain
    (flag > env > config > built-in default). An explicit flag is detected by the
    arg differing from its known built-in default, in which case config is ignored.
    """

    for attr, getter, key, builtin_default in CONFIG_DEFAULTS:
        if not hasattr(args, attr):
            continue
        if getattr(args, attr) != builtin_default:
            # Explicit flag (or already non-default) wins over config.
            continue
        options = getter(config)
        if key in options and options[key] is not None:
            logger.info("Applying config default %s=%s", attr, options[key])
            setattr(args, attr, options[key])

    # Final tier for error_format: when neither an explicit -f flag nor config
    # supplied a value (it is still None), autodetect from the running CI so
    # GitHub Actions gets inline annotations without extra flags. An explicit
    # -f (e.g. "-f llvm") is a real string and is left untouched.
    if getattr(args, "error_format", None) is None:
        detected = detect_default_error_format()
        logger.info("Resolved default error_format=%s from environment", detected)
        args.error_format = detected


def config_source_text(args: argparse.Namespace, config_path: str | None) -> str:
    config_arg = args.config if isinstance(args.config, str) else None
    if config_arg:
        return f"explicit --config ({config_path})"
    if config_path:
        return f"auto-detected ({config_path})"
    return "built-in defaults"


def resolved_config_path(args: argparse.Namespace) -> str | None:
    resolved = getattr(args, "resolved_config_path", None)
    return resolved if isinstance(resolved, str) else None
