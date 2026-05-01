# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog Manager."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess  # nosec
import sys
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import inquirer  # type: ignore
import yaml

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import TYPES_OF_CHANGE, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.config import (
    COMMIT_STYLE_LABELS,
    VERSIONING_SCHEMES,
    auto_detect_config,
    config_format_from_path,
    default_config_path_for_format,
    get_component_from_config,
    get_components_from_config,
    get_effective_configuration,
    get_preamble_keywords,
    get_validation_options,
    get_versioning_scheme,
    write_configuration,
)
from changelogmanager.github import GitHub
from changelogmanager.runtime_logging import (
    VERBOSE,
    configure_runtime_logging,
    get_logger,
)
from changelogmanager.skill_bundle import (
    CLAUDE_PERSONAL_SKILLS_DIR,
    CLAUDE_PROJECT_SKILLS_DIR,
    COPILOT_SKILLS_DIR,
    SKILL_NAME,
    export_skill,
)

VERSION_REFERENCES = ["previous", "current", "future"]
logger = get_logger(__name__)


@dataclass
class CliContext:
    """CLI context shared across commands."""

    changelog: Changelog
    quiet: bool = False
    json_output: bool = False
    json_payload: dict[str, Any] = field(default_factory=dict)


def emit(
    ctx: CliContext,
    *,
    text: str | None = None,
    json_key: str | None = None,
    json_value: Any = None,
) -> None:
    """Prints text unless --quiet, and accumulates JSON payload."""

    if json_key is not None:
        ctx.json_payload[json_key] = json_value
    if ctx.quiet or ctx.json_output:
        if text is not None:
            logger.log(VERBOSE, "Suppressing human-readable output: %s", text)
        return
    if text is not None:
        print(text)


def print_dry_run(ctx: CliContext, message: str) -> None:
    """Reports that a command ran in dry-run mode."""

    logger.info("Dry-run: %s", message)
    emit(ctx, text=f"Dry run: {message}", json_key="dry_run", json_value=message)


def add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    """Adds the shared dry-run option to a parser."""

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview the command without modifying files or calling GitHub",
    )


def configure_logging(error_format: str) -> None:
    """Configures diagnostic formatting."""

    logger.log(VERBOSE, "Configuring diagnostic formatter: %s", error_format)
    logging.config(
        logging.formatters.Llvm()
        if error_format == "llvm"
        else logging.formatters.GitHub()
    )


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


def _config_source_text(args: argparse.Namespace, config_path: str | None) -> str:
    if args.config:
        return f"explicit --config ({config_path})"
    if config_path:
        return f"auto-detected ({config_path})"
    return "built-in defaults"


def _config_prompt_choices(
    options: Mapping[str, str],
) -> tuple[list[str], dict[str, str]]:
    reverse = {label: value for value, label in options.items()}
    return list(options.values()), reverse


def _component_defaults(config: Mapping[str, Any]) -> tuple[str, str]:
    components = config.get("project", {}).get("components", []) or []
    first = components[0] if components else {}
    name = str(first.get("name", "default"))
    changelog = str(first.get("changelog", "CHANGELOG.md"))
    return name, changelog


def _skill_location_choices() -> tuple[list[str], dict[str, Path]]:
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

    choices, choice_map = _skill_location_choices()
    answers = inquirer.prompt(
        [
            inquirer.List(
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

    custom = inquirer.prompt(
        [
            inquirer.Text(
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


def prompt_for_config_init(
    config: Mapping[str, Any],
    *,
    default_format: str,
    prompt_for_format: bool,
) -> dict[str, Any]:
    """Prompts for config values using the existing inquirer library."""

    logger.info("Prompting for configuration initialization values")
    prompts: list[inquirer.questions.Question] = []
    version_choices, version_reverse = _config_prompt_choices(
        {scheme: data["label"] for scheme, data in VERSIONING_SCHEMES.items()}
    )
    commit_choices, commit_reverse = _config_prompt_choices(COMMIT_STYLE_LABELS)
    component_name, changelog_path = _component_defaults(config)
    components = config.get("project", {}).get("components", []) or []
    commit_style = str(
        config.get("project", {}).get("commits", {}).get("style", "conventional")
    )
    versioning_scheme = str(
        config.get("project", {}).get("versioning", {}).get("scheme", "semver")
    )

    if prompt_for_format:
        prompts.append(
            inquirer.List(
                "config_format",
                message="Where should the config live?",
                choices=["pyproject.toml", "YAML"],
                default="pyproject.toml" if default_format == "pyproject" else "YAML",
            )
        )
    prompts.extend(
        [
            inquirer.List(
                "commit_style",
                message="Which commit style should be configured?",
                choices=commit_choices,
                default=COMMIT_STYLE_LABELS.get(
                    commit_style, COMMIT_STYLE_LABELS["conventional"]
                ),
            ),
            inquirer.List(
                "versioning_scheme",
                message="Which versioning scheme should the changelog mention?",
                choices=version_choices,
                default=VERSIONING_SCHEMES.get(
                    versioning_scheme, VERSIONING_SCHEMES["semver"]
                )["label"],
            ),
            inquirer.List(
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
                inquirer.Text(
                    "component_name",
                    message="Default component name",
                    default=component_name,
                ),
                inquirer.Text(
                    "changelog_path",
                    message="Default changelog path",
                    default=changelog_path,
                ),
            ]
        )

    answers = inquirer.prompt(prompts)
    if not answers:
        raise logging.Info(message="Config init cancelled by user")

    selected_format = (
        "pyproject"
        if answers.get("config_format", "pyproject.toml") == "pyproject.toml"
        else "yaml"
    )
    selected_commit_label = str(answers["commit_style"])
    selected_version_label = str(answers["versioning_scheme"])

    return {
        "config_format": selected_format,
        "commit_style": commit_reverse[selected_commit_label],
        "versioning_scheme": version_reverse[selected_version_label],
        "enforce_preamble": answers["enforce_preamble"] == "Yes",
        "component_name": answers.get("component_name", component_name),
        "changelog_path": answers.get("changelog_path", changelog_path),
        "prompted_components": len(components) <= 1,
    }


def _build_updated_config(
    base_config: Mapping[str, Any], answers: Mapping[str, Any]
) -> dict[str, Any]:
    logger.log(VERBOSE, "Building updated configuration from prompt answers")
    updated = deepcopy(dict(base_config))
    project = dict(updated.get("project", {}) or {})
    validation = dict(project.get("validation", {}) or {})
    commits = dict(project.get("commits", {}) or {})
    versioning = dict(project.get("versioning", {}) or {})

    validation["enforce_preamble"] = bool(answers["enforce_preamble"])
    commits["style"] = answers["commit_style"]
    versioning["scheme"] = answers["versioning_scheme"]

    project["validation"] = validation
    project["commits"] = commits
    project["versioning"] = versioning

    if answers["prompted_components"]:
        project["components"] = [
            {
                "name": str(answers["component_name"]).strip() or "default",
                "changelog": str(answers["changelog_path"]).strip() or "CHANGELOG.md",
            }
        ]

    updated["project"] = project
    return updated


def command_config(args: argparse.Namespace, ctx: CliContext) -> None:
    """Shows the effective configuration and its origin."""

    logger.info("Running config command")
    resolved_config = getattr(args, "_resolved_config", None)
    if args.config and not Path(args.config).is_file():
        raise logging.Error(
            file_path=args.config, message="Configuration file not found"
        )

    active_path = (
        resolved_config if resolved_config and Path(resolved_config).is_file() else None
    )
    config = get_effective_configuration(active_path)
    source = _config_source_text(args, active_path)
    emit(ctx, text=f"Config source: {source}")
    emit(
        ctx,
        text=yaml.safe_dump(config, sort_keys=False, allow_unicode=True).rstrip(),
        json_key="config",
        json_value=config,
    )
    ctx.json_payload["config_source"] = source
    if active_path:
        ctx.json_payload["config_path"] = active_path


def command_config_init(args: argparse.Namespace, ctx: CliContext) -> None:
    """Creates or updates configuration interactively."""

    logger.info("Running config init command")
    resolved_config = getattr(args, "_resolved_config", None)
    existing_path = (
        resolved_config if resolved_config and Path(resolved_config).is_file() else None
    )
    existing_config = get_effective_configuration(existing_path)
    default_format = (
        config_format_from_path(args.config or existing_path)
        if (args.config or existing_path)
        else "pyproject"
    )
    answers = prompt_for_config_init(
        existing_config,
        default_format=default_format,
        prompt_for_format=args.config is None,
    )
    target_path = (
        args.config
        if args.config
        else (
            existing_path
            if existing_path
            and config_format_from_path(existing_path) == answers["config_format"]
            else default_config_path_for_format(str(answers["config_format"]))
        )
    )
    updated = _build_updated_config(existing_config, answers)
    write_configuration(str(target_path), updated)

    action = (
        "Updated" if existing_path and str(target_path) == existing_path else "Wrote"
    )
    emit(
        ctx,
        text=f"{action} config: {target_path}",
        json_key="config_path",
        json_value=str(target_path),
    )
    ctx.json_payload["config"] = updated


def command_skill_export(args: argparse.Namespace, ctx: CliContext) -> None:
    """Exports the bundled changelogmanager skill."""

    logger.info("Running skill export command")
    destination_root = prompt_for_skill_export_path(args.path)
    final_path = destination_root / SKILL_NAME

    if args.dry_run:
        print_dry_run(ctx, f"would export bundled skill to {final_path}")
        ctx.json_payload["skill_name"] = SKILL_NAME
        ctx.json_payload["output"] = str(final_path)
        return

    try:
        exported = export_skill(destination_root)
    except FileExistsError as exc:
        raise logging.Error(
            file_path=str(final_path),
            message="Skill destination already exists",
        ) from exc

    emit(
        ctx,
        text=f"Exported skill: {exported}",
        json_key="output",
        json_value=str(exported),
    )
    ctx.json_payload["skill_name"] = SKILL_NAME


def load_changelog(config: str | None, component: str, input_file: str) -> Changelog:
    """Loads the changelog configured for this invocation."""

    logger.info(
        "Loading changelog with config=%s component=%s input_file=%s",
        config or "<none>",
        component,
        input_file,
    )
    if config:
        component_config = get_component_from_config(config=config, component=component)
        file_path = component_config.get("changelog", input_file)
    else:
        file_path = input_file

    enforce_preamble = bool(
        get_validation_options(config).get("enforce_preamble", False)
    )
    preamble_keywords = get_preamble_keywords(config)
    versioning_scheme = get_versioning_scheme(config)

    changelog_dict = ChangelogReader(
        file_path=file_path,
        enforce_preamble=enforce_preamble,
        preamble_keywords=preamble_keywords,
    ).read()
    logger.info("Loaded changelog file %s", file_path)
    return Changelog(
        file_path=file_path,
        changelog=changelog_dict,
        versioning_scheme=versioning_scheme,
    )


def command_create(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to create a new (empty) CHANGELOG.md."""

    logger.info("Running create command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog

    if changelog.exists():
        raise logging.Info(
            file_path=changelog.get_file_path(), message="File already exists"
        )

    if args.dry_run:
        print_dry_run(ctx, f"would create {changelog.get_file_path()}")
        return

    changelog.write_to_file()


def command_version(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to retrieve versions from a CHANGELOG.md."""

    logger.info(
        "Running version command for %s with reference %s",
        ctx.changelog.get_file_path(),
        args.reference,
    )
    changelog = ctx.changelog

    if args.reference == "current":
        result = str(changelog.version())
    elif args.reference == "previous":
        result = str(changelog.previous_version())
    else:  # future
        result = str(changelog.suggest_future_version())

    emit(ctx, text=result, json_key="version", json_value=result)
    ctx.json_payload["reference"] = args.reference


def command_validate(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to validate the CHANGELOG.md for inconsistencies."""

    logger.info(
        "Running validate command for %s (fix=%s)",
        ctx.changelog.get_file_path(),
        getattr(args, "fix", False),
    )
    if not getattr(args, "fix", False):
        # Reading already validated; nothing further to do.
        return

    # --fix mode: re-read with autofix, normalise, and write back.
    config = getattr(args, "_resolved_config", None)
    enforce_preamble = bool(
        get_validation_options(config).get("enforce_preamble", False)
    )
    preamble_keywords = get_preamble_keywords(config)
    reader = ChangelogReader(
        file_path=ctx.changelog.get_file_path(),
        enforce_preamble=enforce_preamble,
        preamble_keywords=preamble_keywords,
    )
    fixed_data, applied = reader.autofix(dict(ctx.changelog.get()))

    if not applied:
        logger.info("No autofixes were required for %s", ctx.changelog.get_file_path())
        emit(ctx, text="No fixes required", json_key="fixed", json_value=[])
        return

    if args.dry_run:
        for entry in applied:
            emit(ctx, text=f"would fix: {entry}")
        ctx.json_payload["fixed"] = applied
        print_dry_run(
            ctx,
            f"would write {len(applied)} fix(es) to {ctx.changelog.get_file_path()}",
        )
        return

    ctx.changelog.set_data(fixed_data)
    ctx.changelog.write_to_file()
    for entry in applied:
        emit(ctx, text=f"fixed: {entry}")
    ctx.json_payload["fixed"] = applied


def command_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Release changes added to [Unreleased] block."""

    logger.info("Running release command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    changelog.release(args.override_version)
    new_version = str(next(iter(changelog.get())))

    if args.dry_run:
        print_dry_run(ctx, f"would release {changelog.get_file_path()}")
        ctx.json_payload["released"] = new_version
        return

    if not args.yes:
        if ctx.json_output or ctx.quiet or not sys.stdin.isatty():
            raise logging.Error(
                file_path=changelog.get_file_path(),
                message=(
                    "Refusing to release without --yes (non-interactive). "
                    "Pass --yes to confirm or --dry-run to preview."
                ),
            )
        answer = (
            input(f"Release {new_version} to {changelog.get_file_path()}? [y/N] ")
            .strip()
            .lower()
        )
        if answer not in {"y", "yes"}:
            raise logging.Info(
                file_path=changelog.get_file_path(),
                message="Release cancelled by user",
            )

    changelog.write_to_file()
    emit(
        ctx,
        text=f"Released {new_version}",
        json_key="released",
        json_value=new_version,
    )


def _export_target(args: argparse.Namespace, default_name: str) -> str:
    file_name = getattr(args, "file_name", None)
    return file_name or default_name


def command_to_json(args: argparse.Namespace, ctx: CliContext) -> None:
    """Exports the contents of the CHANGELOG.md to a JSON file."""

    logger.info("Running to-json command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    output = _export_target(args, "CHANGELOG.json")

    if args.dry_run:
        changelog.to_json()
        print_dry_run(ctx, f"would write JSON output to {output}")
        ctx.json_payload["output"] = output
        return

    changelog.write_to_json(file=output)
    ctx.json_payload["output"] = output


def command_to_yaml(args: argparse.Namespace, ctx: CliContext) -> None:
    """Exports the contents of the CHANGELOG.md to a YAML file."""

    logger.info("Running to-yaml command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    output = _export_target(args, "CHANGELOG.yaml")

    if args.dry_run:
        changelog.to_yaml()
        print_dry_run(ctx, f"would write YAML output to {output}")
        ctx.json_payload["output"] = output
        return

    changelog.write_to_yaml(file=output)
    ctx.json_payload["output"] = output


def command_to_html(args: argparse.Namespace, ctx: CliContext) -> None:
    """Exports the contents of the CHANGELOG.md to an HTML file."""

    logger.info("Running to-html command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    output = _export_target(args, "CHANGELOG.html")

    if args.dry_run:
        changelog.to_html()
        print_dry_run(ctx, f"would write HTML output to {output}")
        ctx.json_payload["output"] = output
        return

    changelog.write_to_html(file=output)
    ctx.json_payload["output"] = output


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
    prompts: list[inquirer.questions.Question] = []

    if not change_type:
        prompts.append(
            inquirer.List(
                "change_type",
                message="Specify the type of your change",
                choices=TYPES_OF_CHANGE,
            )
        )

    if not message:
        prompts.append(
            inquirer.Text("message", message="Message of the changelog entry to add")
        )

    if prompts:
        prompts.append(
            inquirer.List(
                "confirm",
                message="Apply changes to your CHANGELOG.md",
                choices=["Yes", "No"],
                default="Yes",
            )
        )
        changelog_entry = inquirer.prompt(prompts) or {}

    if change_type:
        changelog_entry.setdefault("change_type", change_type)
    if message:
        changelog_entry.setdefault("message", message)
    changelog_entry.setdefault("confirm", "Yes")
    return changelog_entry


def command_add(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to add a new message to the CHANGELOG.md."""

    logger.info("Running add command for %s", ctx.changelog.get_file_path())
    changelog_entry = prompt_for_missing_add_arguments(
        change_type=args.change_type, message=args.message
    )

    changelog = ctx.changelog
    changelog.add(
        change_type=changelog_entry["change_type"], message=changelog_entry["message"]
    )

    if changelog_entry["confirm"] == "Yes":
        if args.dry_run:
            print_dry_run(ctx, f"would update {changelog.get_file_path()}")
            return

        changelog.write_to_file()


def command_remove(args: argparse.Namespace, ctx: CliContext) -> None:
    """Removes an entry from [Unreleased]."""

    logger.info("Running remove command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    if args.list:
        entries = changelog.list_unreleased()
        if not entries:
            emit(ctx, text="No [Unreleased] entries", json_key="entries", json_value=[])
            return
        payload = []
        for change_type, index, message in entries:
            emit(ctx, text=f"  [{change_type}] {index}: {message}")
            payload.append(
                {"change_type": change_type, "index": index, "message": message}
            )
        ctx.json_payload["entries"] = payload
        return

    if not args.change_type or args.index is None:
        raise logging.Error(
            file_path=changelog.get_file_path(),
            message="--change-type and --index are required (or use --list)",
        )

    removed = changelog.remove(change_type=args.change_type, index=args.index)
    if args.dry_run:
        print_dry_run(ctx, f"would remove '{removed}' from {changelog.get_file_path()}")
        ctx.json_payload["removed"] = removed
        return

    changelog.write_to_file()
    emit(ctx, text=f"Removed: {removed}", json_key="removed", json_value=removed)


def command_edit(args: argparse.Namespace, ctx: CliContext) -> None:
    """Edits an existing [Unreleased] entry."""

    logger.info("Running edit command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    if args.index is None or not args.change_type:
        raise logging.Error(
            file_path=changelog.get_file_path(),
            message="--change-type and --index are required",
        )

    if not args.message and not args.new_change_type:
        raise logging.Error(
            file_path=changelog.get_file_path(),
            message="Provide --message and/or --new-change-type",
        )

    changelog.edit(
        change_type=args.change_type,
        index=args.index,
        new_message=args.message,
        new_change_type=args.new_change_type,
    )

    if args.dry_run:
        print_dry_run(ctx, f"would edit {changelog.get_file_path()}")
        return

    changelog.write_to_file()
    emit(ctx, text="Entry updated", json_key="edited", json_value=True)


def command_github_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Creates or updates a GitHub release from the changelog."""

    logger.info(
        "Running github-release command for %s against %s",
        ctx.changelog.get_file_path(),
        args.repository,
    )
    changelog = ctx.changelog
    token = args.github_token or os.environ.get("GITHUB_TOKEN", "").strip()
    if not token:
        raise logging.Error(
            message=("GitHub token required: pass --github-token or set GITHUB_TOKEN"),
        )

    if args.dry_run:
        changelog.get(UNRELEASED_ENTRY)
        future_version = changelog.suggest_future_version()
        release_state = "draft" if args.draft else "published"
        print_dry_run(
            ctx,
            "would create or update "
            f"{release_state} GitHub release v{future_version} in {args.repository}",
        )
        ctx.json_payload["release_state"] = release_state
        ctx.json_payload["version"] = str(future_version)
        return

    github = GitHub(repository=args.repository, token=token)
    github.delete_draft_releases()
    github.create_release(changelog=changelog, draft=args.draft)


# ----------------------------------------------------------------------
# from-commits
# ----------------------------------------------------------------------

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\([^)]+\))?(?P<breaking>!)?:\s*(?P<subject>.+)$"
)
CONVENTIONAL_TO_KAC = {
    "feat": "added",
    "feature": "added",
    "fix": "fixed",
    "bug": "fixed",
    "perf": "changed",
    "refactor": "changed",
    "docs": "changed",
    "style": "changed",
    "test": "changed",
    "tests": "changed",
    "build": "changed",
    "ci": "changed",
    "chore": "changed",
    "revert": "changed",
    "deprecate": "deprecated",
    "remove": "removed",
    "security": "security",
    "sec": "security",
}


def _git_log_since(since: str | None) -> list[str]:
    """Returns commit subjects since a ref (or all if since is None)."""

    cmd = ["git", "log", "--no-merges", "--pretty=%s"]
    if since:
        cmd.append(f"{since}..HEAD")
    logger.info("Running git log command with since=%s", since or "<all>")
    try:
        result = subprocess.run(  # nosec B603
            cmd, check=True, capture_output=True, text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.error("git log failed: %s", exc)
        raise logging.Error(
            message=f"git log failed: {exc}",
        ) from exc
    logger.info("Collected %d git commit subject(s)", len(result.stdout.splitlines()))
    return [line for line in result.stdout.splitlines() if line.strip()]


def _last_release_tag() -> str | None:
    logger.log(VERBOSE, "Looking up last release tag with git describe")
    try:
        result = subprocess.run(  # nosec B603
            ["git", "describe", "--tags", "--abbrev=0"],
            check=True,
            capture_output=True,
            text=True,
        )
        tag = result.stdout.strip() or None
        logger.info("Resolved last release tag: %s", tag or "<none>")
        return tag
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Unable to determine the last release tag")
        return None


def classify_commit(subject: str) -> tuple[str, str] | None:
    """Maps a commit subject onto (change_type, message). Returns None to skip."""

    logger.log(VERBOSE, "Classifying commit subject: %s", subject)
    match = CONVENTIONAL_RE.match(subject)
    if not match:
        return None
    cc_type = match.group("type").lower()
    breaking = bool(match.group("breaking"))
    body = match.group("subject").strip()

    if breaking:
        return ("removed", body)
    return (
        (CONVENTIONAL_TO_KAC.get(cc_type, "changed"), body)
        if cc_type in CONVENTIONAL_TO_KAC
        else ("changed", body)
    )


def command_from_commits(args: argparse.Namespace, ctx: CliContext) -> None:
    """Seeds [Unreleased] from git commit messages."""

    logger.info("Running from-commits command for %s", ctx.changelog.get_file_path())
    since = args.since
    if since is None and not args.all_history:
        since = _last_release_tag()

    subjects = _git_log_since(since)
    if not subjects:
        emit(ctx, text="No commits found", json_key="added", json_value=0)
        return

    classified: list[tuple[str, str]] = []
    skipped = 0
    for subject in subjects:
        result = classify_commit(subject)
        if result is None:
            if args.strict:
                emit(ctx, text=f"skip (non-conventional): {subject}")
                skipped += 1
                continue
            classified.append(("changed", subject))
        else:
            classified.append(result)

    changelog = ctx.changelog
    existing = set()
    unreleased = (
        changelog.get().get(UNRELEASED_ENTRY, {})
        if UNRELEASED_ENTRY in changelog.get()
        else {}
    )
    for change_type, entries in unreleased.items():
        if change_type == "metadata" or not isinstance(entries, list):
            continue
        for entry in entries:
            existing.add((change_type, str(entry).strip().lower()))

    added: list[dict[str, str]] = []
    for change_type, message in classified:
        key = (change_type, message.strip().lower())
        if key in existing:
            continue
        existing.add(key)
        changelog.add(change_type=change_type, message=message)
        added.append({"change_type": change_type, "message": message})

    ctx.json_payload["added"] = added
    ctx.json_payload["skipped"] = skipped
    ctx.json_payload["since"] = since

    if args.dry_run:
        for entry in added:
            emit(ctx, text=f"would add: [{entry['change_type']}] {entry['message']}")
        print_dry_run(
            ctx, f"would update {changelog.get_file_path()} with {len(added)} entries"
        )
        return

    if added:
        changelog.write_to_file()
    for entry in added:
        emit(ctx, text=f"added: [{entry['change_type']}] {entry['message']}")


# ----------------------------------------------------------------------
# --all components handling
# ----------------------------------------------------------------------


def _changed_files() -> set[str]:
    """Returns paths changed vs HEAD (staged+unstaged+untracked)."""

    logger.log(VERBOSE, "Inspecting git status for changed files")
    try:
        result = subprocess.run(  # nosec B603
            ["git", "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Unable to determine changed files from git status")
        return set()
    files: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        # Handle rename "old -> new"
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.add(str(Path(path).as_posix()))
    logger.info("Detected %d changed file(s) from git status", len(files))
    return files


def run_validate_all(
    args: argparse.Namespace, ctx: CliContext, config_path: str
) -> int:
    """Runs `validate` against every component in the config."""

    logger.info("Running validate --all using %s", config_path)
    components = get_components_from_config(config_path)
    changed = _changed_files() if getattr(args, "changed_only", False) else None

    failures = 0
    summaries: list[dict[str, Any]] = []
    enforce_preamble = bool(
        get_validation_options(config_path).get("enforce_preamble", False)
    )
    preamble_keywords = get_preamble_keywords(config_path)
    versioning_scheme = get_versioning_scheme(config_path)

    for component in components:
        path = component.get("changelog")
        name = component.get("name")
        if changed is not None and Path(path).as_posix() not in changed:
            logger.info("Skipping unchanged component %s at %s", name, path)
            summaries.append({"component": name, "path": path, "status": "skipped"})
            continue
        try:
            reader = ChangelogReader(
                file_path=path,
                enforce_preamble=enforce_preamble,
                preamble_keywords=preamble_keywords,
            )
            data = reader.read()
            if getattr(args, "fix", False):
                fixed, applied = reader.autofix(data)
                if applied and not args.dry_run:
                    cl = Changelog(
                        file_path=path,
                        changelog=fixed,
                        versioning_scheme=versioning_scheme,
                    )
                    cl.write_to_file()
                    for entry in applied:
                        emit(ctx, text=f"[{name}] fixed: {entry}")
                elif applied:
                    for entry in applied:
                        emit(ctx, text=f"[{name}] would fix: {entry}")
            summaries.append({"component": name, "path": path, "status": "ok"})
        except logging.Error as err:
            logger.error(
                "Component validation failed for %s at %s: %s", name, path, err.message
            )
            err.report()
            failures += 1
            summaries.append(
                {
                    "component": name,
                    "path": path,
                    "status": "error",
                    "message": err.message,
                }
            )

    ctx.json_payload["components"] = summaries
    return 1 if failures else 0


# ----------------------------------------------------------------------
# Parser
# ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Builds the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="changelogmanager",
        description="(Keep a) Changelog Manager",
    )
    parser.add_argument("--config", default=None, help="Configuration file")
    parser.add_argument(
        "--component", default="default", help="Name of the component to update"
    )
    parser.add_argument(
        "-f",
        "--error-format",
        choices=["llvm", "github"],
        default="llvm",
        help="Type of formatting to apply to error messages",
    )
    parser.add_argument(
        "--input-file", default="CHANGELOG.md", help="Changelog file to work with"
    )
    parser.add_argument(
        "--info",
        action="store_true",
        default=False,
        help="Enable runtime info/warning/error logging on stderr",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        default=False,
        help="Enable verbose runtime logging on stderr (implies --info)",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        default=False,
        help="Suppress non-error output (overrides default human-friendly text)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Emit a single machine-readable JSON object on stdout",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create", help="Command to create a new (empty) CHANGELOG.md"
    )
    add_dry_run_argument(create_parser)
    create_parser.set_defaults(handler=command_create)

    config_parser = subparsers.add_parser(
        "config", help="Show or initialize changelogmanager configuration"
    )
    config_parser.set_defaults(handler=command_config)
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_init_parser = config_subparsers.add_parser(
        "init", help="Create or update configuration interactively"
    )
    config_init_parser.set_defaults(handler=command_config_init)

    skill_parser = subparsers.add_parser("skill", help="Export bundled AI skill files")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)
    skill_export_parser = skill_subparsers.add_parser(
        "export", help="Export the bundled changelogmanager skill"
    )
    skill_export_parser.add_argument(
        "--path",
        default=None,
        help="Directory that should receive the exported skill folder",
    )
    add_dry_run_argument(skill_export_parser)
    skill_export_parser.set_defaults(handler=command_skill_export)

    version_parser = subparsers.add_parser(
        "version", help="Command to retrieve versions from a CHANGELOG.md"
    )
    version_parser.add_argument(
        "-r",
        "--reference",
        choices=VERSION_REFERENCES,
        default="current",
        help="Which version to retrieve",
    )
    add_dry_run_argument(version_parser)
    version_parser.set_defaults(handler=command_version)

    validate_parser = subparsers.add_parser(
        "validate", help="Command to validate the CHANGELOG.md for inconsistencies"
    )
    validate_parser.add_argument(
        "--fix",
        action="store_true",
        default=False,
        help="Apply autofixes (re-order versions, lowercase change types, dedupe)",
    )
    validate_parser.add_argument(
        "--all",
        dest="all_components",
        action="store_true",
        default=False,
        help="Validate every component declared in the config file",
    )
    validate_parser.add_argument(
        "--changed-only",
        dest="changed_only",
        action="store_true",
        default=False,
        help="When combined with --all, only validate components changed in git",
    )
    add_dry_run_argument(validate_parser)
    validate_parser.set_defaults(handler=command_validate)

    release_parser = subparsers.add_parser(
        "release", help="Release changes added to [Unreleased] block"
    )
    release_parser.add_argument(
        "--override-version",
        default=None,
        help="Version to release, defaults to auto-resolve",
    )
    release_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="Skip the interactive confirmation prompt",
    )
    add_dry_run_argument(release_parser)
    release_parser.set_defaults(handler=command_release)

    to_json_parser = subparsers.add_parser(
        "to-json", help="Exports the contents of the CHANGELOG.md to a JSON file"
    )
    to_json_parser.add_argument(
        "--file-name", default="CHANGELOG.json", help="Filename of the JSON output"
    )
    add_dry_run_argument(to_json_parser)
    to_json_parser.set_defaults(handler=command_to_json)

    to_yaml_parser = subparsers.add_parser(
        "to-yaml", help="Exports the contents of the CHANGELOG.md to a YAML file"
    )
    to_yaml_parser.add_argument(
        "--file-name", default="CHANGELOG.yaml", help="Filename of the YAML output"
    )
    add_dry_run_argument(to_yaml_parser)
    to_yaml_parser.set_defaults(handler=command_to_yaml)

    to_html_parser = subparsers.add_parser(
        "to-html", help="Exports the contents of the CHANGELOG.md to an HTML file"
    )
    to_html_parser.add_argument(
        "--file-name", default="CHANGELOG.html", help="Filename of the HTML output"
    )
    add_dry_run_argument(to_html_parser)
    to_html_parser.set_defaults(handler=command_to_html)

    add_parser = subparsers.add_parser(
        "add", help="Command to add a new message to the CHANGELOG.md"
    )
    add_parser.add_argument(
        "-t",
        "--change-type",
        choices=TYPES_OF_CHANGE,
        help="Type of the change",
    )
    add_parser.add_argument("-m", "--message", help="Changelog entry")
    add_dry_run_argument(add_parser)
    add_parser.set_defaults(handler=command_add)

    remove_parser = subparsers.add_parser(
        "remove", help="Removes an entry from [Unreleased]"
    )
    remove_parser.add_argument(
        "-t",
        "--change-type",
        choices=TYPES_OF_CHANGE,
        help="Type of the change",
    )
    remove_parser.add_argument(
        "-i",
        "--index",
        type=int,
        default=None,
        help="0-based index within the change-type list",
    )
    remove_parser.add_argument(
        "--list",
        action="store_true",
        default=False,
        help="List all entries in [Unreleased] with their indices",
    )
    add_dry_run_argument(remove_parser)
    remove_parser.set_defaults(handler=command_remove)

    edit_parser = subparsers.add_parser(
        "edit", help="Edits an existing entry in [Unreleased]"
    )
    edit_parser.add_argument(
        "-t",
        "--change-type",
        choices=TYPES_OF_CHANGE,
        required=True,
        help="Type of the change to edit",
    )
    edit_parser.add_argument(
        "-i",
        "--index",
        type=int,
        required=True,
        help="0-based index within the change-type list",
    )
    edit_parser.add_argument("-m", "--message", help="Replacement message")
    edit_parser.add_argument(
        "--new-change-type",
        choices=TYPES_OF_CHANGE,
        default=None,
        help="Move this entry into a different change-type bucket",
    )
    add_dry_run_argument(edit_parser)
    edit_parser.set_defaults(handler=command_edit)

    github_release_parser = subparsers.add_parser(
        "github-release",
        help="Deletes draft GitHub releases and creates a new one",
    )
    github_release_parser.add_argument(
        "-r", "--repository", required=True, help="Repository"
    )
    github_release_parser.add_argument(
        "-t",
        "--github-token",
        default=None,
        help="GitHub token (falls back to GITHUB_TOKEN env var)",
    )
    github_release_parser.add_argument(
        "--draft",
        dest="draft",
        action="store_true",
        default=True,
        help="Update/Create the GitHub Release in Draft state",
    )
    github_release_parser.add_argument(
        "--release",
        dest="draft",
        action="store_false",
        help="Update/Create the GitHub Release in Release state",
    )
    add_dry_run_argument(github_release_parser)
    github_release_parser.set_defaults(handler=command_github_release)

    from_commits_parser = subparsers.add_parser(
        "from-commits",
        help="Seed [Unreleased] from git commits (parses Conventional Commits)",
    )
    from_commits_parser.add_argument(
        "--since",
        default=None,
        help="Git ref to start from; defaults to the last tag if any",
    )
    from_commits_parser.add_argument(
        "--all-history",
        action="store_true",
        default=False,
        help="Walk full history rather than starting at the last tag",
    )
    from_commits_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Skip commits that don't match the Conventional Commit format",
    )
    add_dry_run_argument(from_commits_parser)
    from_commits_parser.set_defaults(handler=command_from_commits)

    gui_parser = subparsers.add_parser("gui", help="Launch the Tkinter GUI")
    gui_parser.set_defaults(handler=_command_gui)

    return parser


def _command_gui(_args: argparse.Namespace, _ctx: CliContext) -> None:
    """Launch the Tkinter GUI (handler used only as a fallback path)."""

    from changelogmanager.gui import run_gui

    raise SystemExit(run_gui())


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entrypoint."""

    parser = build_parser()

    try:
        args = parser.parse_args(argv)
        configure_runtime_logging(
            info=bool(getattr(args, "info", False) or getattr(args, "verbose", False)),
            verbose=bool(getattr(args, "verbose", False)),
        )
        configure_logging(args.error_format)
        logger.info("Starting CLI command %s", getattr(args, "command", "<none>"))
        if args.command == "gui":
            from changelogmanager.gui import run_gui

            return run_gui()

        resolved_config = resolve_config(args.config)
        args._resolved_config = resolved_config  # type: ignore[attr-defined]

        # --all branch for validate uses an aggregate flow, no single changelog load.
        if args.command == "validate" and getattr(args, "all_components", False):
            if not resolved_config:
                raise logging.Error(
                    message="--all requires a configuration file (use --config or place .changelogmanager.yml in cwd)",
                )
            ctx = CliContext(
                changelog=Changelog(file_path="<all>"),
                quiet=args.quiet,
                json_output=args.json,
            )
            exit_code = run_validate_all(args, ctx, resolved_config)
            if args.json:
                print(json.dumps(ctx.json_payload, indent=2))
            logger.info(
                "Finished CLI command %s with exit code %d", args.command, exit_code
            )
            return exit_code

        if args.command in {"config", "skill"}:
            versioning_scheme = (
                get_versioning_scheme(resolved_config)
                if args.command == "config"
                else "semver"
            )
            context = CliContext(
                changelog=Changelog(
                    file_path=args.input_file,
                    versioning_scheme=versioning_scheme,
                ),
                quiet=args.quiet,
                json_output=args.json,
            )
            args.handler(args, context)
            if args.json:
                print(json.dumps(context.json_payload, indent=2))
            logger.info("Finished CLI command %s successfully", args.command)
            return 0

        context = CliContext(
            changelog=load_changelog(
                config=resolved_config,
                component=args.component,
                input_file=args.input_file,
            ),
            quiet=args.quiet,
            json_output=args.json,
        )
        args.handler(args, context)
        if args.json:
            print(json.dumps(context.json_payload, indent=2))
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
