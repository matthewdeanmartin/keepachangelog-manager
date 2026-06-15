# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Interactive prompting helpers (the ``inquirer`` front-end).

Everything that asks the user a question lives here, isolated from the
orchestration logic in :mod:`changelogmanager.services` so non-interactive
front-ends (the GUI, CI) never pull prompting code into their decision paths.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Any

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import TYPES_OF_CHANGE
from changelogmanager.changelog import Changelog
from changelogmanager.config import VERSIONING_SCHEMES
from changelogmanager.runtime_logging import VERBOSE, get_logger
from changelogmanager.skill_bundle import (
    CLAUDE_PERSONAL_SKILLS_DIR,
    CLAUDE_PROJECT_SKILLS_DIR,
    COPILOT_SKILLS_DIR,
)

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)

# Module-level cache so we only pay the import cost once per process.
_inquirer_module: Any = None


def _get_inquirer() -> Any:
    global _inquirer_module  # noqa: PLW0603
    if _inquirer_module is None:
        import inquirer as _inq  # type: ignore[import-untyped] # noqa: PLC0415

        _inquirer_module = _inq
    return _inquirer_module


def interactive_enabled() -> bool:
    """Returns True when prompting the user for missing input is appropriate."""

    return sys.stdin.isatty()


def config_prompt_choices(
    options: Mapping[str, str],
) -> tuple[list[str], dict[str, str]]:
    reverse = {label: value for value, label in options.items()}
    return list(options.values()), reverse


def component_defaults(config: Mapping[str, Any]) -> tuple[str, str]:
    components = config.get("project", {}).get("components", []) or []
    first = components[0] if components else {}
    name = str(first.get("name", "default"))
    changelog = str(first.get("changelog", "CHANGELOG.md"))
    return name, changelog


def skill_location_choices() -> tuple[list[str], dict[str, Path]]:
    cwd = Path.cwd()
    mapping = {
        f"GitHub Copilot project ({cwd / COPILOT_SKILLS_DIR})": cwd
        / COPILOT_SKILLS_DIR,
        f"Claude project ({cwd / CLAUDE_PROJECT_SKILLS_DIR})": cwd
        / CLAUDE_PROJECT_SKILLS_DIR,
        f"Claude personal ({CLAUDE_PERSONAL_SKILLS_DIR})": CLAUDE_PERSONAL_SKILLS_DIR,
        f"Current directory ({cwd})": cwd,
        "Other path": Path(),
    }
    return list(mapping.keys()), mapping


def prompt_for_skill_export_path(path: str | None) -> Path:
    """Returns the destination root for a bundled skill export."""

    if path:
        logger.info("Using explicit skill export path %s", path)
        return Path(path).expanduser()
    if not sys.stdin.isatty():
        raise logging.Error(
            message="skill export requires --path in non-interactive mode",
        )

    inq = _get_inquirer()
    choices, choice_map = skill_location_choices()
    answers = inq.prompt(
        [
            inq.List(
                "location",
                message="Where should the bundled skill be exported?",
                choices=choices,
                default=choices[0],
            )
        ]
    )
    if not answers:
        raise logging.Info(message="Skill export cancelled by user")

    selected = str(answers["location"])
    destination = choice_map[selected]
    if selected != "Other path":
        logger.info("Selected interactive skill export destination %s", destination)
        return destination

    custom = inq.prompt(
        [
            inq.Text(
                "path",
                message="Skill export path",
                default=str(Path.cwd()),
            )
        ]
    )
    if not custom or not str(custom.get("path", "")).strip():
        raise logging.Info(message="Skill export cancelled by user")
    destination = Path(str(custom["path"]).strip()).expanduser()
    logger.info("Selected custom skill export destination %s", destination)
    return destination


def prompt_for_config_init(  # pylint: disable=too-many-locals
    config: Mapping[str, Any],
    *,
    default_format: str,
    prompt_for_format: bool,
) -> dict[str, Any]:
    """Prompts for config values using the existing inquirer library."""

    inq = _get_inquirer()
    logger.info("Prompting for configuration initialization values")
    prompts: list[Any] = []
    version_choices, version_reverse = config_prompt_choices(
        {scheme: data["label"] for scheme, data in VERSIONING_SCHEMES.items()}
    )
    component_name, changelog_path = component_defaults(config)
    components = config.get("project", {}).get("components", []) or []
    versioning_scheme = str(
        config.get("project", {}).get("versioning", {}).get("scheme", "semver")
    )

    standalone_label = "changelogmanager.toml"
    if prompt_for_format:
        prompts.append(
            inq.List(
                "config_format",
                message="Where should the config live?",
                choices=["pyproject.toml", standalone_label],
                default=(
                    "pyproject.toml"
                    if default_format == "pyproject"
                    else standalone_label
                ),
            )
        )
    prompts.extend(
        [
            inq.List(
                "versioning_scheme",
                message="Which versioning scheme should the changelog mention?",
                choices=version_choices,
                default=VERSIONING_SCHEMES.get(
                    versioning_scheme, VERSIONING_SCHEMES["semver"]
                )["label"],
            ),
            inq.List(
                "enforce_preamble",
                message="Require the canonical changelog preamble during validation?",
                choices=["No", "Yes"],
                default=(
                    "Yes"
                    if bool(
                        config.get("project", {})
                        .get("validation", {})
                        .get("enforce_preamble", False)
                    )
                    else "No"
                ),
            ),
        ]
    )
    if len(components) <= 1:
        prompts.extend(
            [
                inq.Text(
                    "component_name",
                    message="Default component name",
                    default=component_name,
                ),
                inq.Text(
                    "changelog_path",
                    message="Default changelog path",
                    default=changelog_path,
                ),
            ]
        )

    answers = inq.prompt(prompts)
    if not answers:
        raise logging.Info(message="Config init cancelled by user")

    selected_format = (
        "pyproject"
        if answers.get("config_format", "pyproject.toml") == "pyproject.toml"
        else "toml"
    )
    selected_version_label = str(answers["versioning_scheme"])

    return {
        "config_format": selected_format,
        "versioning_scheme": version_reverse[selected_version_label],
        "enforce_preamble": answers["enforce_preamble"] == "Yes",
        "component_name": answers.get("component_name", component_name),
        "changelog_path": answers.get("changelog_path", changelog_path),
        "prompted_components": len(components) <= 1,
    }


def prompt_for_missing_add_arguments(
    change_type: str | None, message: str | None
) -> dict[str, str]:
    """Prompts for any missing add arguments."""

    logger.log(
        VERBOSE,
        "Resolving add arguments change_type=%s message_provided=%s",
        change_type,
        message is not None,
    )
    changelog_entry: dict[str, str] = {}
    prompts: list[Any] = []

    if not change_type:
        inq = _get_inquirer()
        prompts.append(
            inq.List(
                "change_type",
                message="Specify the type of your change",
                choices=TYPES_OF_CHANGE,
            )
        )

    if not message:
        inq = _get_inquirer()
        prompts.append(
            inq.Text("message", message="Message of the changelog entry to add")
        )

    if prompts:
        inq = _get_inquirer()
        prompts.append(
            inq.List(
                "confirm",
                message="Apply changes to your CHANGELOG.md",
                choices=["Yes", "No"],
                default="Yes",
            )
        )
        changelog_entry = inq.prompt(prompts) or {}

    if change_type:
        changelog_entry.setdefault("change_type", change_type)
    if message:
        changelog_entry.setdefault("message", message)
    changelog_entry.setdefault("confirm", "Yes")
    return changelog_entry


def prompt_for_unreleased_entry(
    changelog: Changelog, *, action: str
) -> tuple[str, int]:
    """Lets the user pick an [Unreleased] entry, returning (change_type, index)."""

    entries = changelog.list_unreleased()
    if not entries:
        raise logging.Error(
            file_path=changelog.get_file_path(),
            message="No [Unreleased] entries to choose from",
        )

    choices: list[str] = []
    choice_map: dict[str, tuple[str, int]] = {}
    for change_type, index, message in entries:
        label = f"[{change_type}] {index}: {message}"
        choices.append(label)
        choice_map[label] = (change_type, index)

    inq = _get_inquirer()
    answers = inq.prompt(
        [
            inq.List(
                "entry",
                message=f"Which entry should be {action}?",
                choices=choices,
            )
        ]
    )
    if not answers:
        raise logging.Info(
            file_path=changelog.get_file_path(),
            message=f"{action.capitalize()} cancelled by user",
        )
    return choice_map[str(answers["entry"])]


def resolve_entry_selection(
    args: Any, changelog: Changelog, *, action: str
) -> tuple[str, int]:
    """Returns (change_type, index), prompting interactively when both are absent."""

    if args.change_type and args.index is not None:
        return args.change_type, args.index
    if interactive_enabled():
        return prompt_for_unreleased_entry(changelog, action=action)
    raise logging.Error(
        file_path=changelog.get_file_path(),
        message="--change-type and --index are required",
    )


def prompt_text(message: str, *, default: str | None = None) -> str:
    """Prompts for a single line of text, returning the stripped answer."""

    inq = _get_inquirer()
    answers = inq.prompt([inq.Text("value", message=message, default=default or "")])
    if not answers:
        raise logging.Info(message=f"{message} cancelled by user")
    return str(answers.get("value", "")).strip()


def resolve_required_value(
    provided: str | None, *, env_var: str | None, message: str
) -> str | None:
    """Returns ``provided``/env value, prompting interactively when both are blank."""

    if provided:
        return provided
    env_value = os.environ.get(env_var, "").strip() if env_var else ""
    if env_value:
        return env_value
    if interactive_enabled():
        return prompt_text(message) or None
    return None
