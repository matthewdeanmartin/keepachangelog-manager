# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog Manager CLI package.

The CLI was split out of a single ``cli.py`` module into a small package:

* :mod:`changelogmanager.cli.context` - the shared ``CliContext`` and output helpers.
* :mod:`changelogmanager.cli.config_resolve` - config/flag precedence resolution.
* :mod:`changelogmanager.cli.prompts` - interactive ``inquirer`` helpers.
* :mod:`changelogmanager.cli.loaders` - changelog loading and formatter discovery.
* :mod:`changelogmanager.cli.commands` - the thin ``command_*`` handlers.
* :mod:`changelogmanager.cli.parser` - argument parser construction.
* :mod:`changelogmanager.cli.entry` - the ``main()`` entrypoint and dispatch.

The orchestration the handlers used to own now lives in
:mod:`changelogmanager.services`, so the Tkinter GUI can call it directly.

This module re-exports the stable public surface (``main``, ``build_parser``,
``CliContext``, the ``command_*`` handlers, and a handful of helpers) so callers
and tests can keep importing them from ``changelogmanager.cli``.
"""

from __future__ import annotations

from changelogmanager.cli.commands import (
    GitHub,
    GitLab,
    command_add,
    command_backfill,
    command_config,
    command_config_init,
    command_create,
    command_edit,
    command_from_commits,
    command_github_pr,
    command_github_release,
    command_gitlab_release,
    command_gui,
    command_release,
    command_remove,
    command_skill_export,
    command_to_html,
    command_to_json,
    command_validate,
    command_version,
    run_validate_all,
)
from changelogmanager.cli.config_resolve import (
    apply_config_defaults,
    config_source_text,
    configure_logging,
    resolve_config,
    resolved_config_path,
)
from changelogmanager.cli.context import CliContext, emit, print_dry_run
from changelogmanager.cli.entry import main
from changelogmanager.cli.loaders import (
    discover_formatter,
    load_changelog,
    load_changelog_for_validate_fix,
    resolve_changelog_file,
    resolve_formatter,
    resolve_versioning_scheme,
)
from changelogmanager.cli.parser import (
    VERSION_REFERENCES,
    add_dry_run_argument,
    build_parser,
)

# Interactive front-end module, re-exported so ``cli.inquirer`` patch targets work.
from changelogmanager.cli.prompts import (
    component_defaults,
    inquirer,
    interactive_enabled,
    prompt_for_config_init,
    prompt_for_missing_add_arguments,
    prompt_for_skill_export_path,
    prompt_for_unreleased_entry,
    prompt_text,
    resolve_entry_selection,
    resolve_required_value,
)
from changelogmanager.services import build_updated_config, classify_commit

__all__ = [
    "CliContext",
    "GitHub",
    "GitLab",
    "VERSION_REFERENCES",
    "add_dry_run_argument",
    "apply_config_defaults",
    "build_parser",
    "build_updated_config",
    "classify_commit",
    "command_add",
    "command_backfill",
    "command_config",
    "command_config_init",
    "command_create",
    "command_edit",
    "command_from_commits",
    "command_github_pr",
    "command_github_release",
    "command_gitlab_release",
    "command_gui",
    "command_remove",
    "command_release",
    "command_skill_export",
    "command_to_html",
    "command_to_json",
    "command_validate",
    "command_version",
    "component_defaults",
    "config_source_text",
    "configure_logging",
    "discover_formatter",
    "emit",
    "inquirer",
    "interactive_enabled",
    "load_changelog",
    "load_changelog_for_validate_fix",
    "main",
    "print_dry_run",
    "prompt_for_config_init",
    "prompt_for_missing_add_arguments",
    "prompt_for_skill_export_path",
    "prompt_for_unreleased_entry",
    "prompt_text",
    "resolve_changelog_file",
    "resolve_config",
    "resolve_entry_selection",
    "resolve_formatter",
    "resolve_required_value",
    "resolve_versioning_scheme",
    "resolved_config_path",
    "run_validate_all",
]
