# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog Manager."""

# pylint: disable=too-many-lines,cyclic-import

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess  # nosec
import sys
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import inquirer  # type: ignore

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.backfill import (
    apply_backfill_plan,
    classify_commit_subject,
    plan_backfill,
    plan_unreleased_backfill,
)
from changelogmanager.change_types import TYPES_OF_CHANGE, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.commit_routing import (
    git_log_with_files,
    route_commit,
    validate_routing_components,
)
from changelogmanager.config import (
    VERSIONING_SCHEMES,
    auto_detect_config,
    config_format_from_path,
    default_config_path_for_format,
    get_component_from_config,
    get_components_from_config,
    get_defaults_options,
    get_effective_configuration,
    get_format_options,
    get_github_options,
    get_gitlab_options,
    get_preamble_keywords,
    get_validation_options,
    get_versioning_scheme,
    serialize_config_toml,
    write_configuration,
)
from changelogmanager.formatting import Formatter, discover_formatter
from changelogmanager.github import GitHub
from changelogmanager.gitlab import DEFAULT_GITLAB_URL, GitLab
from changelogmanager.runtime_logging import (
    VERBOSE,
    configure_runtime_logging,
    get_logger,
)
from changelogmanager.schema_validation import DEFAULT_SCHEMA_VERSION, SCHEMA_VERSIONS
from changelogmanager.skill_bundle import (
    CLAUDE_PERSONAL_SKILLS_DIR,
    CLAUDE_PROJECT_SKILLS_DIR,
    COPILOT_SKILLS_DIR,
    SKILL_NAME,
    export_skill,
)
from changelogmanager.version_bumper import bump_version_files, jiggle_available
from changelogmanager.versioning import (
    detect_versioning_scheme_from_file,
    version_scheme_label,
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
    logging.config(logging.formatters.Llvm() if error_format == "llvm" else logging.formatters.GitHub())


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
_CONFIG_DEFAULTS: tuple[tuple[str, Any, str, Any], ...] = (
    ("error_format", get_defaults_options, "error_format", "llvm"),
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

    for attr, getter, key, builtin_default in _CONFIG_DEFAULTS:
        if not hasattr(args, attr):
            continue
        if getattr(args, attr) != builtin_default:
            # Explicit flag (or already non-default) wins over config.
            continue
        options = getter(config)
        if key in options and options[key] is not None:
            logger.info("Applying config default %s=%s", attr, options[key])
            setattr(args, attr, options[key])


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
        f"GitHub Copilot project ({cwd / COPILOT_SKILLS_DIR})": cwd / COPILOT_SKILLS_DIR,
        f"Claude project ({cwd / CLAUDE_PROJECT_SKILLS_DIR})": cwd / CLAUDE_PROJECT_SKILLS_DIR,
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

    choices, choice_map = skill_location_choices()
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


def prompt_for_config_init(  # pylint: disable=too-many-locals
    config: Mapping[str, Any],
    *,
    default_format: str,
    prompt_for_format: bool,
) -> dict[str, Any]:
    """Prompts for config values using the existing inquirer library."""

    logger.info("Prompting for configuration initialization values")
    prompts: list[inquirer.questions.Question] = []
    version_choices, version_reverse = config_prompt_choices({scheme: data["label"] for scheme, data in VERSIONING_SCHEMES.items()})
    component_name, changelog_path = component_defaults(config)
    components = config.get("project", {}).get("components", []) or []
    versioning_scheme = str(config.get("project", {}).get("versioning", {}).get("scheme", "semver"))

    standalone_label = "changelogmanager.toml"
    if prompt_for_format:
        prompts.append(
            inquirer.List(
                "config_format",
                message="Where should the config live?",
                choices=["pyproject.toml", standalone_label],
                default=("pyproject.toml" if default_format == "pyproject" else standalone_label),
            )
        )
    prompts.extend(
        [
            inquirer.List(
                "versioning_scheme",
                message="Which versioning scheme should the changelog mention?",
                choices=version_choices,
                default=VERSIONING_SCHEMES.get(versioning_scheme, VERSIONING_SCHEMES["semver"])["label"],
            ),
            inquirer.List(
                "enforce_preamble",
                message="Require the canonical changelog preamble during validation?",
                choices=["No", "Yes"],
                default=("Yes" if bool(config.get("project", {}).get("validation", {}).get("enforce_preamble", False)) else "No"),
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

    selected_format = "pyproject" if answers.get("config_format", "pyproject.toml") == "pyproject.toml" else "toml"
    selected_version_label = str(answers["versioning_scheme"])

    return {
        "config_format": selected_format,
        "versioning_scheme": version_reverse[selected_version_label],
        "enforce_preamble": answers["enforce_preamble"] == "Yes",
        "component_name": answers.get("component_name", component_name),
        "changelog_path": answers.get("changelog_path", changelog_path),
        "prompted_components": len(components) <= 1,
    }


def build_updated_config(base_config: Mapping[str, Any], answers: Mapping[str, Any]) -> dict[str, Any]:
    logger.log(VERBOSE, "Building updated configuration from prompt answers")
    updated = deepcopy(dict(base_config))
    project = dict(updated.get("project", {}) or {})
    validation = dict(project.get("validation", {}) or {})
    versioning = dict(project.get("versioning", {}) or {})

    validation["enforce_preamble"] = bool(answers["enforce_preamble"])
    versioning["scheme"] = answers["versioning_scheme"]

    project["validation"] = validation
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
    resolved_config = resolved_config_path(args)
    config_arg = args.config if isinstance(args.config, str) else None
    if config_arg and not Path(config_arg).is_file():
        raise logging.Error(file_path=config_arg, message="Configuration file not found")

    active_path = resolved_config if resolved_config and Path(resolved_config).is_file() else None
    config = get_effective_configuration(active_path)
    source = config_source_text(args, active_path)
    emit(ctx, text=f"Config source: {source}")
    emit(
        ctx,
        text=serialize_config_toml(config, prefix="").rstrip(),
        json_key="config",
        json_value=config,
    )
    ctx.json_payload["config_source"] = source
    if active_path:
        ctx.json_payload["config_path"] = active_path


def command_config_init(args: argparse.Namespace, ctx: CliContext) -> None:
    """Creates or updates configuration interactively."""

    logger.info("Running config init command")
    resolved_config = resolved_config_path(args)
    config_arg = args.config if isinstance(args.config, str) else None
    existing_path = resolved_config if resolved_config and Path(resolved_config).is_file() else None
    existing_config = get_effective_configuration(existing_path)
    if config_arg:
        default_format = config_format_from_path(config_arg)
    elif existing_path:
        default_format = config_format_from_path(existing_path)
    else:
        default_format = "pyproject"
    answers = prompt_for_config_init(
        existing_config,
        default_format=default_format,
        prompt_for_format=config_arg is None,
    )
    target_path = (
        config_arg
        if config_arg
        else (
            existing_path
            if existing_path and config_format_from_path(existing_path) == answers["config_format"]
            else default_config_path_for_format(str(answers["config_format"]))
        )
    )
    updated = build_updated_config(existing_config, answers)
    write_configuration(str(target_path), updated)

    action = "Updated" if existing_path and str(target_path) == existing_path else "Wrote"
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
    file_path = resolve_changelog_file(config, component, input_file)

    enforce_preamble = bool(get_validation_options(config).get("enforce_preamble", False))
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
    return detect_versioning_scheme_from_file(file_path) or get_versioning_scheme(config)


def load_changelog_for_validate_fix(args: argparse.Namespace, config: str | None) -> Changelog:
    """Loads a changelog after applying raw-text validate --fix repairs."""

    file_path = resolve_changelog_file(config, args.component, args.input_file)
    enforce_preamble = bool(get_validation_options(config).get("enforce_preamble", False))
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


def command_create(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to create a new (empty) CHANGELOG.md."""

    logger.info("Running create command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog

    if changelog.exists():
        raise logging.Info(file_path=changelog.get_file_path(), message="File already exists")

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


def resolve_formatter(args: argparse.Namespace, config: Any) -> tuple[Any, dict[str, Any]]:
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

    if (force_format or config_format is True or config_format == "true") and formatter is None:
        raise logging.Error(
            message=(
                "Markdown format pass requested (--format or format: true) "
                "but no formatter is available. "
                "Install mdformat: pip install 'keepachangelog-manager-fork[format]'"
            )
        )

    return formatter, mdformat_options


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
    config = resolved_config_path(args)
    enforce_preamble = bool(get_validation_options(config).get("enforce_preamble", False))
    preamble_keywords = get_preamble_keywords(config)
    reader = ChangelogReader(
        file_path=ctx.changelog.get_file_path(),
        enforce_preamble=enforce_preamble,
        preamble_keywords=preamble_keywords,
        versioning_scheme=resolve_versioning_scheme(config, ctx.changelog.get_file_path()),
    )
    fixed_data, applied = reader.autofix(dict(ctx.changelog.get()))

    formatter, fmt_options = resolve_formatter(args, config)

    # Check whether the format pass would change anything (needed for dry-run and
    # the "no fixes required" early-exit check).
    format_entry: str = ""
    if formatter is not None:
        ctx.changelog.set_data(fixed_data)
        pre_format = ctx.changelog.render()
        post_format = ctx.changelog.render(formatter=formatter, format_options=fmt_options)
        if post_format != pre_format:
            format_entry = f"formatted {ctx.changelog.get_file_path()} with mdformat"
        else:
            logger.log(VERBOSE, "mdformat produced no changes; skipping format entry")
        ctx.json_payload["formatted"] = bool(format_entry)

    raw_applied: list[str] = list(getattr(args, "raw_autofixes", []) or [])
    all_applied = raw_applied + applied + ([format_entry] if format_entry else [])

    if not all_applied:
        logger.info("No autofixes were required for %s", ctx.changelog.get_file_path())
        emit(ctx, text="No fixes required", json_key="fixed", json_value=[])
        ctx.json_payload["formatted"] = False
        return

    if args.dry_run:
        for entry in all_applied:
            emit(ctx, text=f"would fix: {entry}")
        ctx.json_payload["fixed"] = all_applied
        print_dry_run(
            ctx,
            f"would write {len(all_applied)} fix(es) to {ctx.changelog.get_file_path()}",
        )
        return

    ctx.changelog.set_data(fixed_data)
    ctx.changelog.write_to_file(
        formatter=formatter if format_entry else None,
        format_options=fmt_options if format_entry else None,
    )
    for entry in all_applied:
        emit(ctx, text=f"fixed: {entry}")
    ctx.json_payload["fixed"] = all_applied


def command_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Release changes added to [Unreleased] block."""

    logger.info("Running release command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    bump_versions: bool = bool(getattr(args, "bump_versions", False))
    pyproject_only: bool = bool(getattr(args, "pyproject_only", False))

    if bump_versions and not jiggle_available():
        raise logging.Error(message=("--bump-versions requires jiggle-version. Install it with: pip install 'keepachangelog-manager-fork[jiggle]'"))

    changelog.release(args.override_version)
    new_version = str(next(iter(changelog.get())))

    if args.dry_run:
        print_dry_run(ctx, f"would release {changelog.get_file_path()}")
        ctx.json_payload["released"] = new_version
        if bump_versions:
            print_dry_run(
                ctx,
                f"would bump version to {new_version} in pyproject.toml" + ("" if pyproject_only else " and Python source files"),
            )
            ctx.json_payload["bumped_version"] = new_version
        return

    if not args.yes:
        if ctx.json_output or ctx.quiet or not sys.stdin.isatty():
            raise logging.Error(
                file_path=changelog.get_file_path(),
                message=("Refusing to release without --yes (non-interactive). Pass --yes to confirm or --dry-run to preview."),
            )
        answer = input(f"Release {new_version} to {changelog.get_file_path()}? [y/N] ").strip().lower()
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

    if bump_versions:
        bumped = bump_version_files(
            new_version,
            pyproject_only=pyproject_only,
        )
        bumped_strs = [str(p) for p in bumped]
        for path in bumped_strs:
            emit(ctx, text=f"Bumped version in {path}")
        ctx.json_payload["bumped_files"] = bumped_strs
        ctx.json_payload["bumped_version"] = new_version


def export_target(args: argparse.Namespace, default_name: str) -> str:
    file_name = getattr(args, "file_name", None)
    return file_name or default_name


def command_to_json(args: argparse.Namespace, ctx: CliContext) -> None:
    """Exports the contents of the CHANGELOG.md to a JSON file."""

    logger.info("Running to-json command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    output = export_target(args, "CHANGELOG.json")
    schema_version = getattr(args, "schema_version", DEFAULT_SCHEMA_VERSION)

    if args.dry_run:
        changelog.to_json(schema_version=schema_version)
        print_dry_run(ctx, f"would write JSON output to {output}")
        ctx.json_payload["output"] = output
        ctx.json_payload["schema_version"] = schema_version
        return

    changelog.write_to_json(file=output, schema_version=schema_version)
    ctx.json_payload["output"] = output
    ctx.json_payload["schema_version"] = schema_version


def command_to_html(args: argparse.Namespace, ctx: CliContext) -> None:
    """Exports the contents of the CHANGELOG.md to an HTML file."""

    logger.info("Running to-html command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    output = export_target(args, "CHANGELOG.html")

    if args.dry_run:
        changelog.to_html()
        print_dry_run(ctx, f"would write HTML output to {output}")
        ctx.json_payload["output"] = output
        return

    changelog.write_to_html(file=output)
    ctx.json_payload["output"] = output


def prompt_for_missing_add_arguments(change_type: str | None, message: str | None) -> dict[str, str]:
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
        prompts.append(inquirer.Text("message", message="Message of the changelog entry to add"))

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
    changelog_entry = prompt_for_missing_add_arguments(change_type=args.change_type, message=args.message)

    changelog = ctx.changelog
    changelog.add(change_type=changelog_entry["change_type"], message=changelog_entry["message"])

    if changelog_entry["confirm"] == "Yes":
        if args.dry_run:
            print_dry_run(ctx, f"would update {changelog.get_file_path()}")
            return

        changelog.write_to_file()


def interactive_enabled() -> bool:
    """Returns True when prompting the user for missing input is appropriate."""

    return sys.stdin.isatty()


def prompt_for_unreleased_entry(changelog: Changelog, *, action: str) -> tuple[str, int]:
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

    answers = inquirer.prompt(
        [
            inquirer.List(
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


def resolve_entry_selection(args: argparse.Namespace, changelog: Changelog, *, action: str) -> tuple[str, int]:
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

    answers = inquirer.prompt([inquirer.Text("value", message=message, default=default or "")])
    if not answers:
        raise logging.Info(message=f"{message} cancelled by user")
    return str(answers.get("value", "")).strip()


def resolve_required_value(provided: str | None, *, env_var: str | None, message: str) -> str | None:
    """Returns ``provided``/env value, prompting interactively when both are blank."""

    if provided:
        return provided
    env_value = os.environ.get(env_var, "").strip() if env_var else ""
    if env_value:
        return env_value
    if interactive_enabled():
        return prompt_text(message) or None
    return None


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
            payload.append({"change_type": change_type, "index": index, "message": message})
        ctx.json_payload["entries"] = payload
        return

    if (not args.change_type or args.index is None) and not interactive_enabled():
        raise logging.Error(
            file_path=changelog.get_file_path(),
            message="--change-type and --index are required (or use --list)",
        )

    change_type, index = resolve_entry_selection(args, changelog, action="removed")
    removed = changelog.remove(change_type=change_type, index=index)
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
    change_type, index = resolve_entry_selection(args, changelog, action="edited")

    new_message = args.message
    new_change_type = args.new_change_type
    if not new_message and not new_change_type:
        if interactive_enabled():
            new_message = prompt_text("Replacement message") or None
        if not new_message and not new_change_type:
            raise logging.Error(
                file_path=changelog.get_file_path(),
                message="Provide --message and/or --new-change-type",
            )

    changelog.edit(
        change_type=change_type,
        index=index,
        new_message=new_message,
        new_change_type=new_change_type,
    )

    if args.dry_run:
        print_dry_run(ctx, f"would edit {changelog.get_file_path()}")
        return

    changelog.write_to_file()
    emit(ctx, text="Entry updated", json_key="edited", json_value=True)


def command_github_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Creates or updates a GitHub release from the changelog."""

    changelog = ctx.changelog
    repository = resolve_required_value(args.repository, env_var=None, message="GitHub repository (owner/repo)")
    if not repository:
        raise logging.Error(
            message="GitHub repository required: pass --repository (owner/repo)",
        )
    args.repository = repository
    logger.info(
        "Running github-release command for %s against %s",
        ctx.changelog.get_file_path(),
        repository,
    )

    if not changelog.has_unreleased():
        # Nothing staged for release (e.g. the push right after a release landed).
        # Report a clear skip and exit 0 so the CI step reads as "skipped",
        # not a silent green success that quietly did nothing.
        emit(
            ctx,
            text=(f"Skipping GitHub release: no [Unreleased] entries in {changelog.get_file_path()}"),
            json_key="skipped",
            json_value="no_unreleased_entries",
        )
        return

    token = resolve_required_value(
        args.github_token,
        env_var="GITHUB_TOKEN",
        message="GitHub token",
    )
    if not token:
        raise logging.Error(
            message=("GitHub token required: pass --github-token or set GITHUB_TOKEN"),
        )

    if args.dry_run:
        future_version = changelog.suggest_future_version()
        release_state = "draft" if args.draft else "published"
        print_dry_run(
            ctx,
            f"would create or update {release_state} GitHub release v{future_version} in {args.repository}",
        )
        ctx.json_payload["release_state"] = release_state
        ctx.json_payload["version"] = str(future_version)
        return

    github = GitHub(repository=args.repository, token=token)
    github.delete_draft_releases()
    release = github.create_release(changelog=changelog, draft=args.draft)
    release_state = "draft" if bool(release.get("draft", args.draft)) else "published"
    tag_name = str(release.get("tag_name", ""))
    html_url = str(release.get("html_url", "")).strip()
    release_id = release.get("id")
    message = f"Created {release_state} GitHub release {tag_name} in {args.repository}"
    if html_url:
        message += f": {html_url}"
    emit(ctx, text=message)
    ctx.json_payload.update(
        {
            "release_state": release_state,
            "tag_name": tag_name,
            "repository": args.repository,
            "html_url": html_url or None,
            "release_id": release_id,
        }
    )


def command_github_pr(args: argparse.Namespace, ctx: CliContext) -> None:
    """Opens (or updates) a GitHub pull request for the changelog update."""

    args.repository = resolve_required_value(args.repository, env_var=None, message="GitHub repository (owner/repo)")
    args.head = resolve_required_value(args.head, env_var=None, message="Head branch (PR source)")
    args.base = resolve_required_value(args.base, env_var=None, message="Base branch (PR target)")
    missing = [
        name
        for name, value in (
            ("--repository", args.repository),
            ("--head", args.head),
            ("--base", args.base),
        )
        if not value
    ]
    if missing:
        raise logging.Error(
            message=f"GitHub PR requires: {', '.join(missing)}",
        )

    logger.info(
        "Running github-pr command repository=%s head=%s base=%s",
        args.repository,
        args.head,
        args.base,
    )

    token = resolve_required_value(args.github_token, env_var="GITHUB_TOKEN", message="GitHub token")
    if not token:
        raise logging.Error(
            message="GitHub token required: pass --github-token or set GITHUB_TOKEN",
        )

    title = args.title or f"docs: update CHANGELOG.md for release on {args.head}"
    body = args.body or f"Update `CHANGELOG.md` on branch `{args.head}`."

    if args.dry_run:
        print_dry_run(
            ctx,
            f"would open or update PR head={args.head} base={args.base} in {args.repository}",
        )
        ctx.json_payload.update({"repository": args.repository, "head": args.head, "base": args.base})
        return

    github = GitHub(repository=args.repository, token=token)
    pr = github.create_pull_request(
        head=args.head,
        base=args.base,
        title=title,
        body=body,
    )
    pr_number = pr.get("number")
    html_url = str(pr.get("html_url", "")).strip()
    message = f"Pull request #{pr_number} in {args.repository}"
    if html_url:
        message += f": {html_url}"
    emit(ctx, text=message)
    ctx.json_payload.update(
        {
            "pr_number": pr_number,
            "repository": args.repository,
            "head": args.head,
            "base": args.base,
            "html_url": html_url or None,
        }
    )


def command_gitlab_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Creates or updates a GitLab release from the changelog."""

    changelog = ctx.changelog
    project = resolve_required_value(args.project, env_var=None, message="GitLab project (id or group/project)")
    if not project:
        raise logging.Error(
            message="GitLab project required: pass --project (id or group/project)",
        )
    args.project = project
    logger.info(
        "Running gitlab-release command for %s against %s",
        ctx.changelog.get_file_path(),
        project,
    )

    if not changelog.has_unreleased():
        emit(
            ctx,
            text=(f"Skipping GitLab release: no [Unreleased] entries in {changelog.get_file_path()}"),
            json_key="skipped",
            json_value="no_unreleased_entries",
        )
        return

    token = args.gitlab_token or os.environ.get("GITLAB_TOKEN", "").strip() or os.environ.get("CI_JOB_TOKEN", "").strip()
    if not token and interactive_enabled():
        token = prompt_text("GitLab token") or None
    if not token:
        raise logging.Error(
            message=("GitLab token required: pass --gitlab-token or set GITLAB_TOKEN / CI_JOB_TOKEN"),
        )

    if args.dry_run:
        future_version = changelog.suggest_future_version()
        print_dry_run(
            ctx,
            f"would create or update GitLab release v{future_version} in {args.project}",
        )
        ctx.json_payload["version"] = str(future_version)
        ctx.json_payload["project"] = args.project
        return

    gitlab = GitLab(project=args.project, token=token, gitlab_url=args.gitlab_url)
    release = gitlab.create_release(changelog=changelog, ref=args.ref)
    tag_name = str(release.get("tag_name", ""))
    web_url = str(release.get("_links", {}).get("self", "") if isinstance(release.get("_links"), Mapping) else "").strip()
    message = f"Created GitLab release {tag_name} in {args.project}"
    if web_url:
        message += f": {web_url}"
    emit(ctx, text=message)
    ctx.json_payload.update(
        {
            "tag_name": tag_name,
            "project": args.project,
            "web_url": web_url or None,
        }
    )


# ----------------------------------------------------------------------
# from-commits
# ----------------------------------------------------------------------


def git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git executable not found on PATH")
    return git


def git_log_since(since: str | None) -> list[str]:
    """Returns commit subjects since a ref (or all if since is None)."""

    cmd = [git_executable(), "log", "--no-merges", "--pretty=%s"]
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


def last_release_tag() -> str | None:
    logger.log(VERBOSE, "Looking up last release tag with git describe")
    try:
        result = subprocess.run(  # nosec B603
            [git_executable(), "describe", "--tags", "--abbrev=0"],
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
    return classify_commit_subject(subject, schema="auto")


def command_from_commits(  # pylint: disable=too-many-locals,too-many-branches
    args: argparse.Namespace, ctx: CliContext
) -> None:
    """Seeds [Unreleased] from git commit messages."""

    since = args.since
    if since is None and not args.all_history:
        since = last_release_tag()

    if getattr(args, "all_components", False):
        from_commits_all(args, ctx, since)
        return

    logger.info("Running from-commits command for %s", ctx.changelog.get_file_path())
    subjects = git_log_since(since)
    if not subjects:
        emit(ctx, text="No commits found", json_key="added", json_value=0)
        return

    classified: list[tuple[str, str]] = []
    skipped = 0
    for subject in subjects:
        result = classify_commit_subject(subject, schema=getattr(args, "commit_schema", "auto"))
        if result is None:
            if args.strict:
                emit(ctx, text=f"skip (non-matching schema): {subject}")
                skipped += 1
                continue
            classified.append(("changed", subject))
        else:
            classified.append(result)

    added = apply_classified_to_changelog(ctx.changelog, classified)

    ctx.json_payload["added"] = added
    ctx.json_payload["skipped"] = skipped
    ctx.json_payload["since"] = since

    if args.dry_run:
        for entry in added:
            emit(ctx, text=f"would add: [{entry['change_type']}] {entry['message']}")
        print_dry_run(
            ctx,
            f"would update {ctx.changelog.get_file_path()} with {len(added)} entries",
        )
        return

    if added:
        ctx.changelog.write_to_file()
    for entry in added:
        emit(ctx, text=f"added: [{entry['change_type']}] {entry['message']}")


def existing_unreleased_keys(changelog: Changelog) -> set[tuple[str, str]]:
    """Returns (change_type, normalized_message) keys already in [Unreleased]."""

    existing: set[tuple[str, str]] = set()
    data = changelog.get()
    unreleased = data.get(UNRELEASED_ENTRY, {}) if UNRELEASED_ENTRY in data else {}
    for change_type, entries in unreleased.items():
        if change_type == "metadata" or not isinstance(entries, list):
            continue
        for entry in entries:
            existing.add((change_type, str(entry).strip().lower()))
    return existing


def apply_classified_to_changelog(changelog: Changelog, classified: Sequence[tuple[str, str]]) -> list[dict[str, str]]:
    """Adds classified (change_type, message) pairs, skipping existing dupes."""

    existing = existing_unreleased_keys(changelog)
    added: list[dict[str, str]] = []
    for change_type, message in classified:
        key = (change_type, message.strip().lower())
        if key in existing:
            continue
        existing.add(key)
        changelog.add(change_type=change_type, message=message)
        added.append({"change_type": change_type, "message": message})
    return added


def from_commits_all(args: argparse.Namespace, ctx: CliContext, since: str | None) -> None:
    """Routes commits to components by touched files and seeds each [Unreleased]."""

    config_path = resolved_config_path(args)
    if not config_path:
        raise logging.Error(
            message=("--all requires a configuration file (use --config or place changelogmanager.toml in cwd)"),
        )
    components = get_components_from_config(config_path)
    validate_routing_components(components, config_path=config_path)

    commits = git_log_with_files(since)
    if not commits:
        emit(ctx, text="No commits found", json_key="components", json_value=[])
        return

    schema = getattr(args, "commit_schema", "auto")
    versioning_scheme = get_versioning_scheme(config_path)
    enforce_preamble = bool(get_validation_options(config_path).get("enforce_preamble", False))
    preamble_keywords = get_preamble_keywords(config_path)

    # Bucket classified entries per component name.
    per_component: dict[str, list[tuple[str, str]]] = {str(component.get("name")): [] for component in components}
    skipped = 0
    for commit in commits:
        classified = classify_commit_subject(commit.subject, schema=schema)
        if classified is None:
            if args.strict:
                skipped += 1
                continue
            classified = ("changed", commit.subject)
        targets = route_commit(commit.files, components)
        for name in targets:
            per_component.setdefault(name, []).append(classified)

    summaries: list[dict[str, Any]] = []
    for component in components:
        name = str(component.get("name"))
        path = str(component.get("changelog"))
        changelog = Changelog(
            file_path=path,
            changelog=ChangelogReader(
                file_path=path,
                enforce_preamble=enforce_preamble,
                preamble_keywords=preamble_keywords,
                versioning_scheme=versioning_scheme,
            ).read(),
            versioning_scheme=versioning_scheme,
        )
        added = apply_classified_to_changelog(changelog, per_component.get(name, []))
        for entry in added:
            verb = "would add" if args.dry_run else "added"
            emit(
                ctx,
                text=f"[{name}] {verb}: [{entry['change_type']}] {entry['message']}",
            )
        if added and not args.dry_run:
            changelog.write_to_file()
        summaries.append({"component": name, "path": path, "added": added})

    ctx.json_payload["components"] = summaries
    ctx.json_payload["skipped"] = skipped
    ctx.json_payload["since"] = since
    if args.dry_run:
        total = sum(len(s["added"]) for s in summaries)
        print_dry_run(ctx, f"would add {total} entries across {len(summaries)} components")


def backfill_unreleased(args: argparse.Namespace, ctx: CliContext) -> None:
    """Seeds [Unreleased] from commits since the latest release tag."""

    changelog = ctx.changelog
    entries = plan_unreleased_backfill(
        changelog,
        since=args.since,
        commit_schema=getattr(args, "commit_schema", "auto"),
    )

    added = [{"change_type": entry.change_type, "message": entry.text} for entry in entries]
    ctx.json_payload["unreleased_added"] = added
    ctx.json_payload["since"] = args.since

    if not added:
        emit(
            ctx,
            text="No new [Unreleased] entries from commits",
            json_key="unreleased_added",
            json_value=[],
        )
        return

    if args.dry_run:
        for entry in added:
            emit(ctx, text=f"would add: [{entry['change_type']}] {entry['message']}")
        print_dry_run(
            ctx,
            f"would seed {len(added)} [Unreleased] entr{'y' if len(added) == 1 else 'ies'} in {changelog.get_file_path()}",
        )
        return

    for entry in added:
        changelog.add(change_type=entry["change_type"], message=entry["message"])
        emit(ctx, text=f"added: [{entry['change_type']}] {entry['message']}")
    changelog.write_to_file()


def command_backfill(args: argparse.Namespace, ctx: CliContext) -> None:
    """Backfills missing changelog versions from existing release history."""

    logger.info(
        "Running backfill command for %s from source %s",
        ctx.changelog.get_file_path(),
        args.source,
    )
    if args.source not in {"tags", "commits", "all"}:
        raise logging.Error(
            message=(f"Backfill source '{args.source}' is not implemented yet; local sources are tags, commits, and all"),
        )
    if args.strategy == "replace":
        raise logging.Error(
            message=(
                "Backfill strategy 'replace' is not supported: changelog entries "
                "have no stable identity, so replacing them is unsafe. Use "
                "'merge' to additively fill gaps in existing versions."
            ),
        )
    if not args.missing_only and args.strategy != "merge":
        raise logging.Error(
            message=("Backfill into existing versions requires --strategy merge; the conservative strategy only adds missing versions"),
        )

    if args.include_unreleased:
        backfill_unreleased(args, ctx)
        return

    plan = plan_backfill(
        ctx.changelog,
        source=args.source,
        since=args.since,
        until=args.until,
        missing_only=args.missing_only,
        dry_run=args.dry_run,
        commit_schema=getattr(args, "commit_schema", "auto"),
        strategy=args.strategy,
    )
    ctx.json_payload.update(plan.to_json())

    emit(ctx, text=f"Backfill plan for {plan.changelog_path}")
    for version in plan.added_versions:
        release = next(item for item in plan.releases if item.version == version)
        tag = release.tag or version
        source_text = release.sources[0].name if release.sources else "unknown"
        if source_text == "commits":
            commit_entries = [entry for entry in release.entries if entry.source == "commits"]
            if commit_entries:
                emit(
                    ctx,
                    text=(f"  add {version} from {len(commit_entries)} commit{'s' if len(commit_entries) != 1 else ''} through tag {tag}"),
                )
                continue
        emit(ctx, text=f"  add {version} from tag {tag}")
    for version in plan.merged_versions:
        release = next(item for item in plan.releases if item.version == version)
        count = len(release.entries)
        emit(
            ctx,
            text=(f"  merge {count} new entr{'y' if count == 1 else 'ies'} into {version}"),
        )
    for version in plan.skipped_versions:
        emit(ctx, text=f"  skip {version} already present")
    for tag in plan.skipped_tags:
        emit(
            ctx,
            text=(f"  skip {tag} not {version_scheme_label(ctx.changelog.get_versioning_scheme())} compatible"),
        )

    if args.dry_run:
        added = len(plan.added_versions)
        merged = len(plan.merged_versions)
        message = f"would update {ctx.changelog.get_file_path()} with {added} version section{'' if added == 1 else 's'}"
        if merged:
            message += f" and merge into {merged} existing version{'' if merged == 1 else 's'}"
        logger.info("Dry-run: %s", message)
        emit(
            ctx,
            text=f"Dry run: {message}",
            json_key="dry_run_message",
            json_value=message,
        )
        return

    apply_backfill_plan(ctx.changelog, plan)
    if plan.added_versions or plan.merged_versions:
        ctx.changelog.write_to_file()


# ----------------------------------------------------------------------
# --all components handling
# ----------------------------------------------------------------------


def changed_files() -> set[str]:
    """Returns paths changed vs HEAD (staged+unstaged+untracked)."""

    logger.log(VERBOSE, "Inspecting git status for changed files")
    try:
        result = subprocess.run(  # nosec B603
            [git_executable(), "status", "--porcelain"],
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


def run_validate_all(  # pylint: disable=too-many-locals
    args: argparse.Namespace, ctx: CliContext, config_path: str
) -> int:
    """Runs `validate` against every component in the config."""

    logger.info("Running validate --all using %s", config_path)
    components = get_components_from_config(config_path)
    changed = changed_files() if getattr(args, "changed_only", False) else None

    failures = 0
    summaries: list[dict[str, Any]] = []
    enforce_preamble = bool(get_validation_options(config_path).get("enforce_preamble", False))
    preamble_keywords = get_preamble_keywords(config_path)
    versioning_scheme = get_versioning_scheme(config_path)
    formatter, fmt_options = resolve_formatter(args, config_path)

    for component in components:
        path = component.get("changelog")
        name = component.get("name")
        if not isinstance(path, str) or not isinstance(name, str):
            raise logging.Error(
                file_path=config_path,
                message="Each component must define string 'name' and 'changelog' values",
            )
        if changed is not None and Path(path).as_posix() not in changed:
            logger.info("Skipping unchanged component %s at %s", name, path)
            summaries.append({"component": name, "path": path, "status": "skipped"})
            continue
        try:
            raw_applied: list[str] = []
            read_path = path
            temp_path: str | None = None
            if getattr(args, "fix", False):
                raw_reader = ChangelogReader(
                    file_path=path,
                    enforce_preamble=enforce_preamble,
                    preamble_keywords=preamble_keywords,
                    versioning_scheme=versioning_scheme,
                )
                fixed_text, raw_applied = raw_reader.autofix_text()
                if raw_applied:
                    if args.dry_run:
                        with tempfile.NamedTemporaryFile(
                            mode="w",
                            encoding="UTF-8",
                            suffix=".md",
                            dir=str(Path(path).resolve().parent),
                            delete=False,
                        ) as temp_handle:
                            temp_handle.write(fixed_text)
                            temp_path = temp_handle.name
                        read_path = temp_path
                    else:
                        Path(path).write_text(fixed_text, encoding="UTF-8")

            reader = ChangelogReader(
                file_path=read_path,
                enforce_preamble=enforce_preamble,
                preamble_keywords=preamble_keywords,
                versioning_scheme=versioning_scheme,
            )
            try:
                data = reader.read()
            finally:
                if temp_path:
                    Path(temp_path).unlink(missing_ok=True)
            if getattr(args, "fix", False):
                fixed, applied = reader.autofix(data)
                cl = Changelog(
                    file_path=path,
                    changelog=fixed,
                    versioning_scheme=versioning_scheme,
                )
                format_entry = ""
                if formatter is not None:
                    pre = cl.render()
                    post = cl.render(formatter=formatter, format_options=fmt_options)
                    if post != pre:
                        format_entry = f"formatted {path} with mdformat"
                all_applied = raw_applied + applied + ([format_entry] if format_entry else [])
                if all_applied and not args.dry_run:
                    cl.write_to_file(
                        formatter=formatter if format_entry else None,
                        format_options=fmt_options if format_entry else None,
                    )
                    for entry in all_applied:
                        emit(ctx, text=f"[{name}] fixed: {entry}")
                elif all_applied:
                    for entry in all_applied:
                        emit(ctx, text=f"[{name}] would fix: {entry}")
            summaries.append({"component": name, "path": path, "status": "ok"})
        except logging.Error as err:
            logger.error("Component validation failed for %s at %s: %s", name, path, err.message)
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


def build_parser() -> (  # pylint: disable=too-many-locals,too-many-statements
    argparse.ArgumentParser
):
    """Builds the CLI argument parser."""

    parser = argparse.ArgumentParser(
        prog="changelogmanager",
        description="(Keep a) Changelog Manager",
    )
    parser.add_argument("--config", default=None, help="Configuration file")
    parser.add_argument("--component", default="default", help="Name of the component to update")
    parser.add_argument(
        "-f",
        "--error-format",
        choices=["llvm", "github"],
        default="llvm",
        help="Type of formatting to apply to error messages",
    )
    parser.add_argument("--input-file", default="CHANGELOG.md", help="Changelog file to work with")
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

    create_parser = subparsers.add_parser("create", help="Command to create a new (empty) CHANGELOG.md")
    add_dry_run_argument(create_parser)
    create_parser.set_defaults(handler=command_create)

    config_parser = subparsers.add_parser("config", help="Show or initialize changelogmanager configuration")
    config_parser.set_defaults(handler=command_config)
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_init_parser = config_subparsers.add_parser("init", help="Create or update configuration interactively")
    config_init_parser.set_defaults(handler=command_config_init)

    skill_parser = subparsers.add_parser("skill", help="Export bundled AI skill files")
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)
    skill_export_parser = skill_subparsers.add_parser("export", help="Export the bundled changelogmanager skill")
    skill_export_parser.add_argument(
        "--path",
        default=None,
        help="Directory that should receive the exported skill folder",
    )
    add_dry_run_argument(skill_export_parser)
    skill_export_parser.set_defaults(handler=command_skill_export)

    version_parser = subparsers.add_parser("version", help="Command to retrieve versions from a CHANGELOG.md")
    version_parser.add_argument(
        "-r",
        "--reference",
        choices=VERSION_REFERENCES,
        default="current",
        help="Which version to retrieve",
    )
    add_dry_run_argument(version_parser)
    version_parser.set_defaults(handler=command_version)

    validate_parser = subparsers.add_parser("validate", help="Command to validate the CHANGELOG.md for inconsistencies")
    validate_parser.add_argument(
        "--fix",
        action="store_true",
        default=False,
        help="Apply autofixes for safe layout and structural changelog issues",
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
    fmt_group = validate_parser.add_mutually_exclusive_group()
    fmt_group.add_argument(
        "--format",
        dest="format",
        action="store_true",
        default=False,
        help="Run mdformat after structural fixes (error if mdformat not found)",
    )
    fmt_group.add_argument(
        "--no-format",
        dest="no_format",
        action="store_true",
        default=False,
        help="Skip the mdformat pass even when mdformat is installed",
    )
    add_dry_run_argument(validate_parser)
    validate_parser.set_defaults(handler=command_validate)

    release_parser = subparsers.add_parser("release", help="Release changes added to [Unreleased] block")
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
    release_parser.add_argument(
        "--bump-versions",
        dest="bump_versions",
        action="store_true",
        default=False,
        help=("Bump the version in pyproject.toml (and Python source __version__ vars) to match the released version. Requires jiggle-version."),
    )
    release_parser.add_argument(
        "--pyproject-only",
        dest="pyproject_only",
        action="store_true",
        default=False,
        help=("When --bump-versions is set, only update pyproject.toml; skip Python source files containing __version__."),
    )
    add_dry_run_argument(release_parser)
    release_parser.set_defaults(handler=command_release)

    to_json_parser = subparsers.add_parser("to-json", help="Exports the contents of the CHANGELOG.md to a JSON file")
    to_json_parser.add_argument("--file-name", default="CHANGELOG.json", help="Filename of the JSON output")
    to_json_parser.add_argument(
        "--schema-version",
        choices=SCHEMA_VERSIONS,
        default=DEFAULT_SCHEMA_VERSION,
        help="KAG-Manager JSON schema version to validate the export against",
    )
    add_dry_run_argument(to_json_parser)
    to_json_parser.set_defaults(handler=command_to_json)

    to_html_parser = subparsers.add_parser("to-html", help="Exports the contents of the CHANGELOG.md to an HTML file")
    to_html_parser.add_argument("--file-name", default="CHANGELOG.html", help="Filename of the HTML output")
    add_dry_run_argument(to_html_parser)
    to_html_parser.set_defaults(handler=command_to_html)

    add_parser = subparsers.add_parser("add", help="Command to add a new message to the CHANGELOG.md")
    add_parser.add_argument(
        "-t",
        "--change-type",
        choices=TYPES_OF_CHANGE,
        help="Type of the change",
    )
    add_parser.add_argument("-m", "--message", help="Changelog entry")
    add_dry_run_argument(add_parser)
    add_parser.set_defaults(handler=command_add)

    remove_parser = subparsers.add_parser("remove", help="Removes an entry from [Unreleased]")
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

    edit_parser = subparsers.add_parser("edit", help="Edits an existing entry in [Unreleased]")
    edit_parser.add_argument(
        "-t",
        "--change-type",
        choices=TYPES_OF_CHANGE,
        default=None,
        help="Type of the change to edit (prompted interactively if omitted)",
    )
    edit_parser.add_argument(
        "-i",
        "--index",
        type=int,
        default=None,
        help="0-based index within the change-type list (prompted if omitted)",
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
        "-r",
        "--repository",
        default=None,
        help="Repository (prompted interactively if omitted)",
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

    github_pr_parser = subparsers.add_parser(
        "github-pr",
        help="Opens or updates a GitHub pull request for a changelog branch",
    )
    github_pr_parser.add_argument(
        "-r",
        "--repository",
        default=None,
        help="Repository (owner/repo); prompted interactively if omitted",
    )
    github_pr_parser.add_argument(
        "--head",
        default=None,
        help="Head branch (the PR source branch); prompted if omitted",
    )
    github_pr_parser.add_argument(
        "--base",
        default=None,
        help="Base branch (the PR target branch); prompted if omitted",
    )
    github_pr_parser.add_argument("--title", default=None, help="PR title")
    github_pr_parser.add_argument("--body", default=None, help="PR body")
    github_pr_parser.add_argument(
        "-t",
        "--github-token",
        default=None,
        help="GitHub token (falls back to GITHUB_TOKEN env var)",
    )
    add_dry_run_argument(github_pr_parser)
    github_pr_parser.set_defaults(handler=command_github_pr)

    backfill_parser = subparsers.add_parser(
        "backfill",
        help="Backfill missing changelog versions from existing release history",
    )
    backfill_parser.add_argument(
        "--source",
        choices=["tags", "github-releases", "github-prs", "pypi", "commits", "all"],
        default="all",
        help="Source or source set to import from",
    )
    backfill_parser.add_argument(
        "--repository",
        default=None,
        help="GitHub repository in owner/repo format (reserved for future phases)",
    )
    backfill_parser.add_argument(
        "--package",
        default=None,
        help="PyPI package name (reserved for future phases)",
    )
    backfill_parser.add_argument(
        "--since",
        default=None,
        help="Earliest version/tag/ref to consider",
    )
    backfill_parser.add_argument(
        "--until",
        default=None,
        help="Latest version/tag/ref to consider",
    )
    backfill_parser.add_argument(
        "--missing-only",
        dest="missing_only",
        action=argparse.BooleanOptionalAction,
        default=True,
        help=("Only add versions missing from the changelog; pass --no-missing-only with --strategy merge to also backfill entries into existing versions"),
    )
    backfill_parser.add_argument(
        "--include-unreleased",
        action="store_true",
        default=False,
        help=("Seed [Unreleased] from commits since the latest release tag instead of adding past version sections"),
    )
    backfill_parser.add_argument(
        "--strategy",
        choices=["conservative", "merge", "replace"],
        default="conservative",
        help=(
            "How to handle versions already present: conservative skips them, "
            "merge additively fills in missing entries; replace is unsupported "
            "because changelog entries have no stable identity"
        ),
    )
    backfill_parser.add_argument(
        "--commit-schema",
        choices=["auto", "conventional", "gitmoji", "keepachangelog"],
        default="auto",
        help=("Commit message schema for commit-derived entries; auto tries Conventional Commits, gitmoji, and Keep a Changelog flavored subjects"),
    )
    add_dry_run_argument(backfill_parser)
    backfill_parser.set_defaults(handler=command_backfill)

    gitlab_release_parser = subparsers.add_parser(
        "gitlab-release",
        help="Creates or updates a GitLab release from the changelog",
    )
    gitlab_release_parser.add_argument(
        "-p",
        "--project",
        default=None,
        help=("GitLab project ID or path (e.g. group/project); prompted interactively if omitted"),
    )
    gitlab_release_parser.add_argument(
        "-t",
        "--gitlab-token",
        default=None,
        help="GitLab token (falls back to GITLAB_TOKEN or CI_JOB_TOKEN)",
    )
    gitlab_release_parser.add_argument(
        "--gitlab-url",
        default=DEFAULT_GITLAB_URL,
        help=f"Base URL of the GitLab instance (default: {DEFAULT_GITLAB_URL})",
    )
    gitlab_release_parser.add_argument(
        "--ref",
        default="HEAD",
        help="Commit or branch the tag should point at when created (default: HEAD)",
    )
    add_dry_run_argument(gitlab_release_parser)
    gitlab_release_parser.set_defaults(handler=command_gitlab_release)

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
        "--all",
        dest="all_components",
        action="store_true",
        default=False,
        help=("Route commits to every configured component by the files they touch (uses each component's 'match' globs; requires a config file)"),
    )
    from_commits_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Skip commits that don't match the selected commit schema",
    )
    from_commits_parser.add_argument(
        "--commit-schema",
        choices=["auto", "conventional", "gitmoji", "keepachangelog"],
        default="auto",
        help=("Commit message schema; auto tries Conventional Commits, gitmoji, and Keep a Changelog flavored subjects"),
    )
    add_dry_run_argument(from_commits_parser)
    from_commits_parser.set_defaults(handler=command_from_commits)

    gui_parser = subparsers.add_parser("gui", help="Launch the Tkinter GUI")
    gui_parser.set_defaults(handler=command_gui)

    return parser


def command_gui(_args: argparse.Namespace, _ctx: CliContext) -> None:
    """Launch the Tkinter GUI (handler used only as a fallback path)."""

    from changelogmanager.gui import run_gui  # pylint: disable=import-outside-toplevel

    raise SystemExit(run_gui())


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
        config_for_defaults = resolved_config if resolved_config and Path(resolved_config).is_file() else None
        apply_config_defaults(args, config_for_defaults)
        configure_logging(args.error_format)

        # --all branch for validate uses an aggregate flow, no single changelog load.
        if args.command == "validate" and getattr(args, "all_components", False):
            if not resolved_config:
                raise logging.Error(
                    message=("--all requires a configuration file (use --config or place changelogmanager.toml in cwd)"),
                )
            ctx = CliContext(
                changelog=Changelog(file_path="<all>"),
                quiet=args.quiet,
                json_output=args.json,
            )
            exit_code = run_validate_all(args, ctx, resolved_config)
            if args.json:
                print(json.dumps(ctx.json_payload, indent=2))
            logger.info("Finished CLI command %s with exit code %d", args.command, exit_code)
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
                print(json.dumps(ctx.json_payload, indent=2))
            logger.info("Finished CLI command %s successfully", args.command)
            return 0

        if args.command in {"config", "skill"}:
            # `config` / `config init` may legitimately point --config at a path
            # that does not exist yet (the init handler creates it). Only resolve
            # the versioning scheme from a config file that is actually present;
            # otherwise fall back to defaults so dispatch does not crash before the
            # handler can create the file.
            existing_config = resolved_config if resolved_config and Path(resolved_config).is_file() else None
            versioning_scheme = get_versioning_scheme(existing_config) if args.command == "config" else "semver"
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
            print(json.dumps(context.json_payload, indent=2))
        logger.info("Finished CLI command %s successfully", args.command)
        return 0
    except (logging.Info, logging.Warning) as exc_info:
        logger.info("CLI command completed with non-error diagnostic: %s", exc_info.message)
        exc_info.report()
        return 0
    except logging.Error as exc_info:
        logger.error("CLI command failed: %s", exc_info.message)
        exc_info.report()
        return 1
    except SystemExit as exc_info:
        logger.error("CLI exited via SystemExit: %s", exc_info)
        return exc_info.code if isinstance(exc_info.code, int) else 1
