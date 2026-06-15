# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""CLI command handlers.

Each ``command_*`` handler is a thin adapter: it resolves arguments (prompting
the user where needed), calls into :mod:`changelogmanager.services` for the
actual orchestration, and renders the result via :func:`emit`. Keeping the
business logic in ``services`` lets the Tkinter GUI drive the same operations
without replaying CLI argv.

``GitHub`` and ``discover_formatter`` are re-imported here so the tests that
patch ``changelogmanager.cli.commands.GitHub`` / ``.discover_formatter`` hit the
name the handlers actually resolve.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import TYPE_CHECKING

import changelogmanager.cli.prompts as prompts
import changelogmanager.llvm_diagnostics as logging
from changelogmanager import services

# Imported lazily where needed to avoid a circular import with parser/config_resolve.
from changelogmanager.cli.config_resolve import resolved_config_path  # noqa: E402
from changelogmanager.cli.context import CliContext, emit, print_dry_run
from changelogmanager.cli.loaders import resolve_formatter
from changelogmanager.config import (
    config_format_from_path,
    default_config_path_for_format,
    get_effective_configuration,
    get_fragments_options,
    get_tasks_options,
    serialize_config_toml,
    write_configuration,
)
from changelogmanager.github import GitHub as GitHub  # noqa: F401, PLC0414 # pylint: disable=unused-import # fmt: skip

# (re-exported; patched in tests)
from changelogmanager.runtime_logging import VERBOSE, get_logger
from changelogmanager.schema_validation import DEFAULT_SCHEMA_VERSION
from changelogmanager.services import build_updated_config  # re-exported for the GUI
from changelogmanager.skill_bundle import SKILL_NAME, export_skill
from changelogmanager.versioning import version_scheme_label

if TYPE_CHECKING:  # pragma: no cover - typing only
    from changelogmanager.message_lint import AuditReport, CommitLint, RewritePlan

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# config / skill
# ----------------------------------------------------------------------


def config_source_text(args: argparse.Namespace, config_path: str | None) -> str:
    config_arg = args.config if isinstance(args.config, str) else None
    if config_arg:
        return f"explicit --config ({config_path})"
    if config_path:
        return f"auto-detected ({config_path})"
    return "built-in defaults"


def command_config(args: argparse.Namespace, ctx: CliContext) -> None:
    """Shows the effective configuration and its origin."""

    logger.info("Running config command")
    resolved_config = resolved_config_path(args)
    config_arg = args.config if isinstance(args.config, str) else None
    if config_arg and not Path(config_arg).is_file():
        raise logging.Error(
            file_path=config_arg, message="Configuration file not found"
        )

    active_path = (
        resolved_config if resolved_config and Path(resolved_config).is_file() else None
    )
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
    existing_path = (
        resolved_config if resolved_config and Path(resolved_config).is_file() else None
    )
    existing_config = get_effective_configuration(existing_path)
    if config_arg:
        default_format = config_format_from_path(config_arg)
    elif existing_path:
        default_format = config_format_from_path(existing_path)
    else:
        default_format = "pyproject"
    answers = prompts.prompt_for_config_init(
        existing_config,
        default_format=default_format,
        prompt_for_format=config_arg is None,
    )
    target_path = (
        config_arg
        if config_arg
        else (
            existing_path
            if existing_path
            and config_format_from_path(existing_path) == answers["config_format"]
            else default_config_path_for_format(str(answers["config_format"]))
        )
    )
    updated = build_updated_config(existing_config, answers)
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
    destination_root = prompts.prompt_for_skill_export_path(args.path)
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


# ----------------------------------------------------------------------
# core changelog commands
# ----------------------------------------------------------------------


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
    from changelogmanager.changelog_reader import ChangelogReader  # noqa: PLC0415
    from changelogmanager.cli.loaders import resolve_versioning_scheme  # noqa: PLC0415
    from changelogmanager.config import (  # noqa: PLC0415
        get_preamble_keywords,
        get_validation_options,
    )

    config = resolved_config_path(args)
    enforce_preamble = bool(
        get_validation_options(config).get("enforce_preamble", False)
    )
    preamble_keywords = get_preamble_keywords(config)
    reader = ChangelogReader(
        file_path=ctx.changelog.get_file_path(),
        enforce_preamble=enforce_preamble,
        preamble_keywords=preamble_keywords,
        versioning_scheme=resolve_versioning_scheme(
            config, ctx.changelog.get_file_path()
        ),
    )
    fixed_data, applied = reader.autofix(dict(ctx.changelog.get()))

    formatter, fmt_options = resolve_formatter(args, config)

    # Check whether the format pass would change anything (needed for dry-run and
    # the "no fixes required" early-exit check).
    format_entry: str = ""
    if formatter is not None:
        ctx.changelog.set_data(fixed_data)
        pre_format = ctx.changelog.render()
        post_format = ctx.changelog.render(
            formatter=formatter, format_options=fmt_options
        )
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

    pre_errors: int = getattr(args, "pre_fix_error_count", 0) or 0
    ctx.changelog.set_data(fixed_data)
    ctx.changelog.write_to_file(
        formatter=formatter if format_entry else None,
        format_options=fmt_options if format_entry else None,
    )
    for entry in all_applied:
        emit(ctx, text=f"fixed: {entry}")
    ctx.json_payload["fixed"] = all_applied

    # Report before/after validation counts when there were pre-existing issues.
    if pre_errors:
        post_errors = reader.count_layout_errors()
        ctx.json_payload["validation_errors_before"] = pre_errors
        ctx.json_payload["validation_errors_after"] = post_errors
        if post_errors:
            emit(
                ctx,
                text=(
                    f"Validation: {pre_errors} problem(s) before fix, "
                    f"{post_errors} remaining. "
                    f"Run 'changelogmanager validate' for details."
                ),
            )
        else:
            emit(
                ctx,
                text=f"Validation: resolved all {pre_errors} problem(s).",
            )


def command_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Release changes added to [Unreleased] block."""

    logger.info(
        "Running release command for %s (override=%s, bump_versions=%s, pyproject_only=%s, dry_run=%s, yes=%s)",
        ctx.changelog.get_file_path(),
        args.override_version or "<auto>",
        bool(getattr(args, "bump_versions", False)),
        bool(getattr(args, "pyproject_only", False)),
        bool(getattr(args, "dry_run", False)),
        bool(getattr(args, "yes", False)),
    )
    changelog = ctx.changelog
    bump_versions = bool(getattr(args, "bump_versions", False))
    pyproject_only = bool(getattr(args, "pyproject_only", False))

    if changelog.has_unreleased_section() and not changelog.has_unreleased():
        logger.warning(
            "Skipping release for %s because the [Unreleased] section has no change entries",
            changelog.get_file_path(),
        )
        emit(
            ctx,
            text=(
                f"Skipping release: [Unreleased] section is empty in {changelog.get_file_path()}"
            ),
            json_key="skipped",
            json_value="no_unreleased_entries",
        )
        return

    if args.dry_run:
        result = services.release_changelog(
            changelog,
            args.override_version,
            bump_versions=bump_versions,
            pyproject_only=pyproject_only,
            dry_run=True,
        )
        print_dry_run(ctx, f"would release {changelog.get_file_path()}")
        ctx.json_payload["released"] = result.version
        if bump_versions:
            print_dry_run(
                ctx,
                f"would bump version to {result.version} in pyproject.toml"
                + ("" if pyproject_only else " and Python source files"),
            )
            ctx.json_payload["bumped_version"] = result.version
        return

    if not args.yes:
        if ctx.json_output or ctx.quiet or not prompts.interactive_enabled():
            raise logging.Error(
                file_path=changelog.get_file_path(),
                message=(
                    "Refusing to release without --yes (non-interactive). Pass --yes to confirm or --dry-run to preview."
                ),
            )
        # Compute predicted version without mutating the changelog object.
        override = args.override_version
        predicted_version = (
            override.lstrip("v")
            if override
            else str(changelog.suggest_future_version())
        )
        logger.info(
            "Prompting for release confirmation of %s for %s",
            predicted_version,
            changelog.get_file_path(),
        )
        answer = (
            input(f"Release {predicted_version} to {changelog.get_file_path()}? [y/N] ")
            .strip()
            .lower()
        )
        if answer not in {"y", "yes"}:
            raise logging.Info(
                file_path=changelog.get_file_path(),
                message="Release cancelled by user",
            )

    result = services.release_changelog(
        changelog,
        args.override_version,
        bump_versions=bump_versions,
        pyproject_only=pyproject_only,
    )
    emit(
        ctx,
        text=f"Released {result.version}",
        json_key="released",
        json_value=result.version,
    )
    for path in result.bumped_files:
        emit(ctx, text=f"Bumped version in {path}")
    if result.bumped_files:
        ctx.json_payload["bumped_files"] = result.bumped_files
        ctx.json_payload["bumped_version"] = result.version


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


def command_add(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to add a new message to the CHANGELOG.md."""

    logger.info("Running add command for %s", ctx.changelog.get_file_path())
    changelog_entry = prompts.prompt_for_missing_add_arguments(
        change_type=args.change_type, message=args.message
    )

    if getattr(args, "fragment", None) is not None:
        from changelogmanager.fragments import (  # noqa: PLC0415
            discover_fragment_dir,
            write_fragment,
        )

        fragment_value = getattr(args, "fragment", None)
        slug = None if fragment_value is True else str(fragment_value)
        fragment_dir = discover_fragment_dir(getattr(args, "fragment_dir", None))
        if changelog_entry["confirm"] == "Yes":
            if args.dry_run:
                path = write_fragment_preview(
                    fragment_dir,
                    changelog_entry["change_type"],
                    changelog_entry["message"],
                    slug,
                )
                print_dry_run(ctx, f"would write fragment {path}")
                ctx.json_payload["fragment"] = str(path)
                return
            path = write_fragment(
                fragment_dir,
                changelog_entry["change_type"],
                changelog_entry["message"],
                slug,
            )
            emit(
                ctx,
                text=f"Wrote fragment: {path}",
                json_key="fragment",
                json_value=str(path),
            )
        return

    changelog = ctx.changelog
    changelog.add(
        change_type=changelog_entry["change_type"], message=changelog_entry["message"]
    )

    if changelog_entry["confirm"] == "Yes":
        if args.dry_run:
            print_dry_run(ctx, f"would update {changelog.get_file_path()}")
            return

        changelog.write_to_file()


def write_fragment_preview(
    fragment_dir: Path, change_type: str, message: str, slug: str | None
) -> Path:
    from changelogmanager.fragments import fragment_path  # noqa: PLC0415

    return fragment_path(fragment_dir, change_type, message, slug)


def command_tasks(args: argparse.Namespace, ctx: CliContext) -> None:
    """Manages TASKS.md files."""

    from changelogmanager import tasks as task_files  # noqa: PLC0415

    config = getattr(args, "resolved_config_path", None)
    options = get_tasks_options(config)
    task_file_arg = getattr(args, "tasks_file", None) or options.get("file")
    task_path = task_files.discover_task_file(task_file_arg)
    subcommand = args.tasks_command

    if subcommand == "list":
        parsed = task_files.parse_task_file(task_path)
        if not parsed:
            emit(
                ctx,
                text=f"No tasks found in {task_path}",
                json_key="tasks",
                json_value=[],
            )
            return
        payload = []
        for task in parsed:
            status = "x" if task.checked else " "
            change_type = task.change_type or "unknown"
            emit(ctx, text=f"{task.line}: [{status}] {change_type}: {task.text}")
            payload.append(
                {
                    "line": task.line,
                    "checked": task.checked,
                    "change_type": task.change_type,
                    "text": task.text,
                    "done_date": task.done_date,
                }
            )
        ctx.json_payload["tasks"] = payload
        return

    if subcommand == "add":
        task_files.add_task(task_path, args.change_type, args.message)
        emit(
            ctx,
            text=f"Added task to {task_path}",
            json_key="tasks_file",
            json_value=str(task_path),
        )
        return

    if subcommand in {"check", "uncheck"}:
        checked = subcommand == "check"
        source = str(options.get("done_date_source", "today"))
        task = task_files.set_task_checked(
            task_path, args.selector, checked=checked, done_date_source=source
        )
        verb = "Checked" if checked else "Unchecked"
        emit(
            ctx,
            text=f"{verb} task on line {task.line}",
            json_key="line",
            json_value=task.line,
        )
        return

    if subcommand == "validate":
        parsed = task_files.parse_task_file(task_path)
        errors = task_files.validate_tasks(parsed, task_path)
        ctx.json_payload["errors"] = errors
        if errors:
            raise logging.Error(file_path=str(task_path), message="\n".join(errors))
        emit(ctx, text=f"Tasks valid: {task_path}", json_key="valid", json_value=True)
        return

    if subcommand == "promote":
        parsed = task_files.parse_task_file(task_path)
        entries = task_files.completed_entries(parsed)
        existing = {
            (change_type, message)
            for change_type, _index, message in ctx.changelog.list_unreleased()
        }
        new_entries = [
            (change_type, text)
            for change_type, text, _line in entries
            if (change_type, text) not in existing
        ]
        ctx.json_payload["promoted"] = [
            {"change_type": change_type, "message": text}
            for change_type, text in new_entries
        ]
        if args.dry_run:
            for change_type, text in new_entries:
                emit(ctx, text=f"would promote: [{change_type}] {text}")
            print_dry_run(ctx, f"would promote {len(new_entries)} task(s)")
            return
        ctx.changelog.add_many(new_entries)
        if new_entries:
            ctx.changelog.write_to_file()
        if not getattr(args, "keep", False):
            promoted_lines = {
                line
                for change_type, text, line in entries
                if (change_type, text) in set(new_entries)
                or (change_type, text) in existing
            }
            task_files.remove_completed_tasks(task_path, promoted_lines)
        emit(
            ctx,
            text=f"Promoted {len(new_entries)} task(s)",
            json_key="count",
            json_value=len(new_entries),
        )


def command_fragments(args: argparse.Namespace, ctx: CliContext) -> None:
    """Manages changelog fragments."""

    from changelogmanager import fragments as fragment_files  # noqa: PLC0415

    config = getattr(args, "resolved_config_path", None)
    options = get_fragments_options(config)
    directory_arg = getattr(args, "fragment_dir", None) or options.get("directory")
    fragment_dir = fragment_files.discover_fragment_dir(directory_arg)
    subcommand = args.fragments_command

    if subcommand == "list":
        fragments = fragment_files.read_fragments(fragment_dir)
        payload = []
        for fragment in fragments:
            emit(ctx, text=f"[{fragment.change_type}] {fragment.path}: {fragment.text}")
            payload.append(
                {
                    "path": str(fragment.path),
                    "change_type": fragment.change_type,
                    "text": fragment.text,
                }
            )
        if not fragments:
            emit(ctx, text=f"No fragments found in {fragment_dir}")
        ctx.json_payload["fragments"] = payload
        return

    if subcommand == "add":
        path = fragment_files.write_fragment(
            fragment_dir, args.change_type, args.message, getattr(args, "slug", None)
        )
        emit(
            ctx,
            text=f"Wrote fragment: {path}",
            json_key="fragment",
            json_value=str(path),
        )
        return

    if subcommand == "validate":
        errors = fragment_files.validate_fragments(fragment_dir)
        ctx.json_payload["errors"] = errors
        if errors:
            raise logging.Error(file_path=str(fragment_dir), message="\n".join(errors))
        emit(
            ctx,
            text=f"Fragments valid: {fragment_dir}",
            json_key="valid",
            json_value=True,
        )
        return

    if subcommand == "collect":
        fragments = fragment_files.read_fragments(fragment_dir)
        existing = {
            (change_type, message)
            for change_type, _index, message in ctx.changelog.list_unreleased()
        }
        new_entries = [
            (fragment.change_type, fragment.text)
            for fragment in fragments
            if (fragment.change_type, fragment.text) not in existing
        ]
        ctx.json_payload["collected"] = [
            {"change_type": change_type, "message": text}
            for change_type, text in new_entries
        ]
        if args.dry_run:
            for change_type, text in new_entries:
                emit(ctx, text=f"would collect: [{change_type}] {text}")
            print_dry_run(ctx, f"would collect {len(new_entries)} fragment(s)")
            return
        ctx.changelog.add_many(new_entries)
        if new_entries:
            ctx.changelog.write_to_file()
        consume = getattr(args, "consume", None) or options.get("consume") or "archive"
        consumed = fragment_files.consume_fragments(fragments, str(consume))
        emit(
            ctx,
            text=f"Collected {len(new_entries)} fragment(s)",
            json_key="count",
            json_value=len(new_entries),
        )
        ctx.json_payload["consumed"] = [str(path) for path in consumed]


def command_remove(args: argparse.Namespace, ctx: CliContext) -> None:
    """Removes an entry from [Unreleased]."""

    logger.info("Running remove command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    if getattr(args, "count", False):
        entries = changelog.list_unreleased()
        count = len(entries)
        if not ctx.quiet:
            print(count)
        ctx.json_payload["count"] = count
        return

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

    if (
        not args.change_type or args.index is None
    ) and not prompts.interactive_enabled():
        raise logging.Error(
            file_path=changelog.get_file_path(),
            message="--change-type and --index are required (or use --list)",
        )

    change_type, index = prompts.resolve_entry_selection(
        args, changelog, action="removed"
    )
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
    change_type, index = prompts.resolve_entry_selection(
        args, changelog, action="edited"
    )

    new_message = args.message
    new_change_type = args.new_change_type
    if not new_message and not new_change_type:
        if prompts.interactive_enabled():
            new_message = prompts.prompt_text("Replacement message") or None
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


# ----------------------------------------------------------------------
# github / gitlab
# ----------------------------------------------------------------------


def command_github_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Creates or updates a GitHub release from the changelog."""

    changelog = ctx.changelog
    repository = prompts.resolve_required_value(
        args.repository, env_var=None, message="GitHub repository (owner/repo)"
    )
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
        emit(
            ctx,
            text=(
                f"Skipping GitHub release: no [Unreleased] entries in {changelog.get_file_path()}"
            ),
            json_key="skipped",
            json_value="no_unreleased_entries",
        )
        return

    token = prompts.resolve_required_value(
        args.github_token,
        env_var="GITHUB_TOKEN",
        message="GitHub token",
    )
    if not token:
        raise logging.Error(
            message=("GitHub token required: pass --github-token or set GITHUB_TOKEN"),
        )

    result = services.github_release(
        changelog,
        repository=args.repository,
        token=token,
        draft=args.draft,
        dry_run=args.dry_run,
    )

    if result.dry_run:
        print_dry_run(
            ctx,
            f"would create or update {result.release_state} GitHub release v{result.version} in {args.repository}",
        )
        ctx.json_payload["release_state"] = result.release_state
        ctx.json_payload["version"] = result.version
        return

    message = f"Created {result.release_state} GitHub release {result.tag_name} in {args.repository}"
    if result.html_url:
        message += f": {result.html_url}"
    emit(ctx, text=message)
    ctx.json_payload.update(
        {
            "release_state": result.release_state,
            "tag_name": result.tag_name,
            "repository": args.repository,
            "html_url": result.html_url,
            "release_id": result.release_id,
        }
    )


def command_github_pr(args: argparse.Namespace, ctx: CliContext) -> None:
    """Opens (or updates) a GitHub pull request for the changelog update."""

    args.repository = prompts.resolve_required_value(
        args.repository, env_var=None, message="GitHub repository (owner/repo)"
    )
    args.head = prompts.resolve_required_value(
        args.head, env_var=None, message="Head branch (PR source)"
    )
    args.base = prompts.resolve_required_value(
        args.base, env_var=None, message="Base branch (PR target)"
    )
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

    token = prompts.resolve_required_value(
        args.github_token, env_var="GITHUB_TOKEN", message="GitHub token"
    )
    if not token:
        raise logging.Error(
            message="GitHub token required: pass --github-token or set GITHUB_TOKEN",
        )

    title = args.title or f"docs: update CHANGELOG.md for release on {args.head}"
    body = args.body or f"Update `CHANGELOG.md` on branch `{args.head}`."

    if not args.repository or not args.head or not args.base:
        raise logging.Error(
            message="Repository, head branch, and base branch are required for GitHub PR",
        )

    if args.dry_run:
        print_dry_run(
            ctx,
            f"would open or update PR head={args.head} base={args.base} in {args.repository}",
        )
        ctx.json_payload.update(
            {"repository": args.repository, "head": args.head, "base": args.base}
        )
        return

    result = services.github_pull_request(
        repository=args.repository,
        token=token,
        head=args.head,
        base=args.base,
        title=title,
        body=body,
    )
    message = f"Pull request #{result.pr_number} in {args.repository}"
    if result.html_url:
        message += f": {result.html_url}"
    emit(ctx, text=message)
    ctx.json_payload.update(
        {
            "pr_number": result.pr_number,
            "repository": args.repository,
            "head": args.head,
            "base": args.base,
            "html_url": result.html_url,
        }
    )


def command_gitlab_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Creates or updates a GitLab release from the changelog."""

    changelog = ctx.changelog
    project = prompts.resolve_required_value(
        args.project, env_var=None, message="GitLab project (id or group/project)"
    )
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
            text=(
                f"Skipping GitLab release: no [Unreleased] entries in {changelog.get_file_path()}"
            ),
            json_key="skipped",
            json_value="no_unreleased_entries",
        )
        return

    token = (
        args.gitlab_token
        or os.environ.get("GITLAB_TOKEN", "").strip()
        or os.environ.get("CI_JOB_TOKEN", "").strip()
    )
    if not token and prompts.interactive_enabled():
        token = prompts.prompt_text("GitLab token") or None
    if not token:
        raise logging.Error(
            message=(
                "GitLab token required: pass --gitlab-token or set GITLAB_TOKEN / CI_JOB_TOKEN"
            ),
        )

    result = services.gitlab_release(
        changelog,
        project=args.project,
        token=token,
        gitlab_url=args.gitlab_url,
        ref=args.ref,
        dry_run=args.dry_run,
    )

    if result.dry_run:
        print_dry_run(
            ctx,
            f"would create or update GitLab release v{result.version} in {args.project}",
        )
        ctx.json_payload["version"] = result.version
        ctx.json_payload["project"] = args.project
        return

    message = f"Created GitLab release {result.tag_name} in {args.project}"
    if result.web_url:
        message += f": {result.web_url}"
    emit(ctx, text=message)
    ctx.json_payload.update(
        {
            "tag_name": result.tag_name,
            "project": args.project,
            "web_url": result.web_url,
        }
    )


# ----------------------------------------------------------------------
# from-commits / backfill
# ----------------------------------------------------------------------


def command_from_commits(args: argparse.Namespace, ctx: CliContext) -> None:
    """Seeds [Unreleased] from git commit messages."""

    since = args.since
    if since is None and not args.all_history:
        since = services.last_release_tag()

    if getattr(args, "all_components", False):
        from_commits_all(args, ctx, since)
        return

    logger.info("Running from-commits command for %s", ctx.changelog.get_file_path())
    result = services.seed_unreleased_from_commits(
        ctx.changelog,
        since=since,
        commit_schema=getattr(args, "commit_schema", "auto"),
        strict=args.strict,
        dry_run=args.dry_run,
    )

    if result.no_commits:
        emit(ctx, text="No commits found", json_key="added", json_value=0)
        return

    for subject in result.skipped_subjects:
        emit(ctx, text=f"skip (non-matching schema): {subject}")

    ctx.json_payload["added"] = result.added
    ctx.json_payload["skipped"] = result.skipped
    ctx.json_payload["since"] = since

    if args.dry_run:
        for entry in result.added:
            emit(ctx, text=f"would add: [{entry['change_type']}] {entry['message']}")
        print_dry_run(
            ctx,
            f"would update {ctx.changelog.get_file_path()} with {len(result.added)} entries",
        )
        return

    for entry in result.added:
        emit(ctx, text=f"added: [{entry['change_type']}] {entry['message']}")


def from_commits_all(
    args: argparse.Namespace, ctx: CliContext, since: str | None
) -> None:
    """Routes commits to components and seeds each [Unreleased]."""

    config_path = resolved_config_path(args)
    result = services.seed_components_from_commits(
        config_path,
        since=since,
        commit_schema=getattr(args, "commit_schema", "auto"),
        strict=args.strict,
        dry_run=args.dry_run,
    )

    if result.no_commits:
        emit(ctx, text="No commits found", json_key="components", json_value=[])
        return

    summaries = []
    for component in result.components:
        for entry in component.added:
            verb = "would add" if args.dry_run else "added"
            emit(
                ctx,
                text=f"[{component.component}] {verb}: [{entry['change_type']}] {entry['message']}",
            )
        summaries.append(
            {
                "component": component.component,
                "path": component.path,
                "added": component.added,
            }
        )

    ctx.json_payload["components"] = summaries
    ctx.json_payload["skipped"] = result.skipped
    ctx.json_payload["since"] = since
    if args.dry_run:
        total = sum(len(s["added"]) for s in summaries)
        print_dry_run(
            ctx, f"would add {total} entries across {len(summaries)} components"
        )


def command_lint_commits(args: argparse.Namespace, ctx: CliContext) -> None:
    """Audits past commit subjects against the Keep a Changelog commit schema.

    Read-only: walks the selected commit range, classifies each subject, and
    reports how many would become changelog entries, be skipped, or land as junk
    ``changed`` entries on backfill. With ``--strict`` (or in CI gating mode) a
    non-empty unclassified set exits 1.
    """

    from dataclasses import replace  # noqa: PLC0415

    from changelogmanager import backfill, message_lint  # noqa: PLC0415
    from changelogmanager.config import get_message_lint_options  # noqa: PLC0415

    since = args.since
    if since is None and not args.all_history:
        since = services.last_release_tag()

    config = resolved_config_path(args)
    options = get_message_lint_options(config)
    schema = getattr(args, "commit_schema", None)
    if schema is not None:
        options = replace(options, schema=schema)

    max_commits = getattr(args, "max_commits", None)
    report = message_lint.audit_commits(
        since=since,
        until=args.until,
        options=options,
        max_commits=(
            max_commits if max_commits is not None else backfill.MAX_COMMITS_DEFAULT
        ),
    )

    ctx.json_payload.update(report.to_json())

    counts = report.counts
    emit(
        ctx,
        text=(
            f"Scanned {len(report.commits)} commit(s) in {report.revision}\n"
            f"  changelog : {counts['changelog']}   "
            f"skip : {counts['skip']}   "
            f"unclassified : {counts['unclassified']}"
        ),
    )

    show = getattr(args, "show", "fail")
    shown = _commits_to_show(report, show)
    if shown:
        emit(ctx, text="")
        for commit in shown:
            label = commit.result.outcome.value
            emit(ctx, text=f"  {commit.sha[:8]}  [{label}] {commit.subject}")

    if report.unclassified and not args.json:
        emit(
            ctx,
            text=(
                "\nFix unclassified commits with `changelogmanager rewrite-messages` "
                "or amend them; they would become low-confidence 'changed' entries."
            ),
        )

    if getattr(args, "strict", False) and report.unclassified:
        if args.json:
            # The error path skips the entry-point JSON print, so emit here.
            import orjson  # noqa: PLC0415

            print(orjson.dumps(ctx.json_payload, option=orjson.OPT_INDENT_2).decode())
        raise logging.Error(
            message=(
                f"{len(report.unclassified)} commit(s) are not classifiable by the "
                f"'{options.schema}' schema"
            )
        )


def _commits_to_show(report: AuditReport, show: str) -> list[CommitLint]:
    """Selects which audited commits to print based on the --show filter."""

    from changelogmanager.message_lint import LintOutcome  # noqa: PLC0415

    if show == "all":
        return list(report.commits)
    wanted = {
        "fail": LintOutcome.UNCLASSIFIED,
        "skip": LintOutcome.SKIP,
        "pass": LintOutcome.CHANGELOG,
    }.get(show)
    if wanted is None:
        return report.unclassified
    return [commit for commit in report.commits if commit.result.outcome is wanted]


def command_rewrite_messages(args: argparse.Namespace, ctx: CliContext) -> None:
    """Plans subject rewrites over the **unpushed** commit range.

    Scoped, by design, to commits not yet pushed to any remote
    (``@{upstream}..HEAD``) so a rewrite can never corrupt shared history. The
    plan path is implemented and touches no history; the ``--apply`` path is an
    explicit fail-fast stub (history rewriting is not yet implemented) that still
    exercises the consent gate so it is wired when apply lands.
    """

    from dataclasses import replace  # noqa: PLC0415

    from changelogmanager import backfill, message_lint  # noqa: PLC0415
    from changelogmanager.config import get_message_lint_options  # noqa: PLC0415

    config = resolved_config_path(args)
    options = get_message_lint_options(config)
    schema = getattr(args, "commit_schema", None)
    if schema is not None:
        options = replace(options, schema=schema)

    max_commits = getattr(args, "max_commits", None)
    plan = message_lint.plan_rewrite(
        options=options,
        auto_prefix=getattr(args, "auto_prefix", None),
        max_commits=(
            max_commits if max_commits is not None else backfill.MAX_COMMITS_DEFAULT
        ),
    )

    if getattr(args, "apply", False):
        _rewrite_apply_stub(args, plan)
        return

    _rewrite_emit_plan(args, ctx, plan)


def _rewrite_emit_plan(
    args: argparse.Namespace, ctx: CliContext, plan: RewritePlan
) -> None:
    """Renders / writes a rewrite plan. Never touches history."""

    ctx.json_payload.update(plan.to_json())

    scope = (
        plan.unpushed_range
        if plan.has_upstream
        else f"{plan.unpushed_range} (no upstream; all commits are local-only)"
    )
    emit(
        ctx,
        text=(
            f"Rewrite plan over unpushed range {scope}\n"
            f"  {len(plan.entries)} commit(s) would be rewritten"
        ),
    )

    plan_out = getattr(args, "plan_out", None)
    if plan_out:
        Path(plan_out).write_text(plan.to_tsv() + "\n", encoding="utf-8")
        emit(
            ctx,
            text=f"Wrote plan to {plan_out}",
            json_key="plan_out",
            json_value=plan_out,
        )
    else:
        for entry in plan.entries:
            emit(
                ctx,
                text=(
                    f"  {entry.sha[:8]}  {entry.old_subject!r} "
                    f"-> {entry.suggested_subject!r} [{entry.outcome_after}]"
                ),
            )

    if not plan.entries:
        emit(ctx, text="Nothing to rewrite: no unpushed unclassifiable commits.")


def _rewrite_apply_stub(args: argparse.Namespace, plan: RewritePlan) -> None:
    """The (unimplemented) apply path: enforce consent, then fail-fast.

    Consent is required *now* so the gate is in place for when apply is real:
    ``--yes`` (non-interactive) or a ``y``/``yes`` answer to an interactive
    ``input()`` prompt. Missing consent in a non-TTY is a usage error (exit 2);
    with consent, the command still refuses because history rewriting is not yet
    implemented (exit 1).
    """

    import sys  # noqa: PLC0415

    consented = bool(getattr(args, "yes", False))
    if not consented:
        if sys.stdin.isatty():
            try:
                answer = (
                    input(
                        f"Rewrite {len(plan.entries)} unpushed commit message(s) "
                        f"in {plan.unpushed_range}? [y/N] "
                    )
                    .strip()
                    .lower()
                )
            except EOFError:
                answer = ""
            consented = answer in {"y", "yes"}
            if not consented:
                raise logging.Info(message="Rewrite cancelled by user")
        else:
            # Missing consent in a non-interactive context is a usage error:
            # exit 2 (argparse convention) naming the flag, so an agent gets a
            # deterministic, recoverable failure instead of a hang.
            logging.Error(
                message=(
                    "Refusing to --apply without consent (non-interactive). "
                    "Pass --yes to confirm. (Note: history rewriting is not yet "
                    "implemented.)"
                ),
            ).report()
            raise SystemExit(2)

    # Consent given — but the rewrite engine is deliberately not built yet.
    raise logging.Error(
        message=(
            "rewrite-messages --apply is not yet implemented: history rewriting "
            "is intentionally disabled until full safety checks are in place. "
            "For now, fix unpushed commits with `git commit --amend` (last "
            "commit) or `git rebase -i` (a few commits). The plan above shows "
            "the suggested subjects."
        ),
    )


def command_backfill(args: argparse.Namespace, ctx: CliContext) -> None:
    """Backfills missing changelog versions from existing release history."""
    from changelogmanager.credentials import get_token  # noqa: PLC0415

    logger.info(
        "Running backfill command for %s from source %s",
        ctx.changelog.get_file_path(),
        args.source,
    )
    repository: str | None = getattr(args, "repository", None)
    package: str | None = getattr(args, "package", None)
    services.validate_backfill_options(
        source=args.source,
        strategy=args.strategy,
        missing_only=args.missing_only,
        repository=repository,
        package=package,
    )
    token = get_token(
        service_key="github_token",
        cli_value=getattr(args, "github_token", None),
        env_var="GITHUB_TOKEN",
    )

    if args.include_unreleased:
        backfill_unreleased(args, ctx)
        return

    plan = services.plan_changelog_backfill(
        ctx.changelog,
        source=args.source,
        since=args.since,
        until=args.until,
        missing_only=args.missing_only,
        dry_run=args.dry_run,
        commit_schema=getattr(args, "commit_schema", "auto"),
        strategy=args.strategy,
        max_commits=getattr(args, "max_commits", None),
        repository=repository,
        token=token,
        package=package,
    )
    ctx.json_payload.update(plan.to_json())

    emit(ctx, text=f"Backfill plan for {plan.changelog_path}")
    for version in plan.added_versions:
        release = next(item for item in plan.releases if item.version == version)
        tag = release.tag or version
        source_text = release.sources[0].name if release.sources else "unknown"
        if source_text == "commits":
            commit_entries = [
                entry for entry in release.entries if entry.source == "commits"
            ]
            if commit_entries:
                emit(
                    ctx,
                    text=(
                        f"  add {version} from {len(commit_entries)} commit{'s' if len(commit_entries) != 1 else ''} through tag {tag}"
                    ),
                )
                continue
        emit(ctx, text=f"  add {version} from tag {tag}")
    for version in plan.merged_versions:
        release = next(item for item in plan.releases if item.version == version)
        count = len(release.entries)
        emit(
            ctx,
            text=(
                f"  merge {count} new entr{'y' if count == 1 else 'ies'} into {version}"
            ),
        )
    for version in plan.skipped_versions:
        emit(ctx, text=f"  skip {version} already present")
    for tag in plan.skipped_tags:
        emit(
            ctx,
            text=(
                f"  skip {tag} not {version_scheme_label(ctx.changelog.get_versioning_scheme())} compatible"
            ),
        )

    if args.dry_run:
        added = len(plan.added_versions)
        merged = len(plan.merged_versions)
        message = f"would update {ctx.changelog.get_file_path()} with {added} version section{'' if added == 1 else 's'}"
        if merged:
            message += (
                f" and merge into {merged} existing version{'' if merged == 1 else 's'}"
            )
        logger.info("Dry-run: %s", message)
        emit(
            ctx,
            text=f"Dry run: {message}",
            json_key="dry_run_message",
            json_value=message,
        )
        return

    services.apply_changelog_backfill(ctx.changelog, plan)


def backfill_unreleased(args: argparse.Namespace, ctx: CliContext) -> None:
    """Seeds [Unreleased] from commits since the latest release tag."""

    changelog = ctx.changelog
    result = services.backfill_unreleased(
        changelog,
        since=args.since,
        commit_schema=getattr(args, "commit_schema", "auto"),
        dry_run=args.dry_run,
        max_commits=getattr(args, "max_commits", None),
    )

    ctx.json_payload["unreleased_added"] = result.added
    ctx.json_payload["since"] = args.since

    if not result.added:
        emit(
            ctx,
            text="No new [Unreleased] entries from commits",
            json_key="unreleased_added",
            json_value=[],
        )
        return

    if args.dry_run:
        for entry in result.added:
            emit(ctx, text=f"would add: [{entry['change_type']}] {entry['message']}")
        print_dry_run(
            ctx,
            f"would seed {len(result.added)} [Unreleased] entr{'y' if len(result.added) == 1 else 'ies'} in {changelog.get_file_path()}",
        )
        return

    for entry in result.added:
        emit(ctx, text=f"added: [{entry['change_type']}] {entry['message']}")


# ----------------------------------------------------------------------
# validate --all
# ----------------------------------------------------------------------


def run_validate_all(
    args: argparse.Namespace, ctx: CliContext, config_path: str
) -> int:
    """Runs `validate` against every component in the config."""

    formatter, fmt_options = resolve_formatter(args, config_path)
    results = services.validate_components(
        config_path,
        fix=getattr(args, "fix", False),
        dry_run=args.dry_run,
        changed_only=getattr(args, "changed_only", False),
        formatter=formatter,
        fmt_options=fmt_options,
    )

    failures = 0
    summaries = []
    for result in results:
        if result.status == "error":
            failures += 1
            summaries.append(
                {
                    "component": result.component,
                    "path": result.path,
                    "status": "error",
                    "message": result.message,
                }
            )
            continue
        if result.status == "ok":
            verb = "would fix" if args.dry_run else "fixed"
            for entry in result.applied:
                emit(ctx, text=f"[{result.component}] {verb}: {entry}")
        summaries.append(
            {
                "component": result.component,
                "path": result.path,
                "status": result.status,
            }
        )

    ctx.json_payload["components"] = summaries
    return 1 if failures else 0


# ----------------------------------------------------------------------
# credentials
# ----------------------------------------------------------------------

_SERVICE_KEY_MAP = {"github": "github_token", "gitlab": "gitlab_token"}
_SERVICE_LABEL_MAP = {"github": "GitHub", "gitlab": "GitLab"}


def command_credentials(args: argparse.Namespace, ctx: CliContext) -> None:
    """Manages API tokens stored in the OS keyring."""
    from changelogmanager.credentials import (
        check_token,  # noqa: PLC0415
        clear_token,
        set_token,
    )

    sub = args.credentials_command

    if sub == "check":
        lines = []
        for svc_arg, svc_key in _SERVICE_KEY_MAP.items():
            label = _SERVICE_LABEL_MAP[svc_arg]
            present = check_token(svc_key)
            status = "configured" if present else "not set"
            lines.append({"service": svc_arg, "status": status})
            emit(ctx, text=f"{label} token: {status}")
        ctx.json_payload["tokens"] = lines
        return

    service_arg: str = args.service
    service_key = _SERVICE_KEY_MAP[service_arg]
    label = _SERVICE_LABEL_MAP[service_arg]

    if sub == "set":
        import getpass  # noqa: PLC0415

        token = getpass.getpass(prompt=f"{label} token: ")
        if not token.strip():
            raise logging.Error(message="Token must not be empty")
        set_token(service_key, token.strip())
        emit(
            ctx,
            text=f"{label} token stored in OS keyring",
            json_key="stored",
            json_value=service_arg,
        )

    elif sub == "clear":
        removed = clear_token(service_key)
        if removed:
            emit(
                ctx,
                text=f"{label} token removed from OS keyring",
                json_key="cleared",
                json_value=service_arg,
            )
        else:
            emit(
                ctx,
                text=f"{label} token was not set",
                json_key="cleared",
                json_value=None,
            )


# ----------------------------------------------------------------------
# gui
# ----------------------------------------------------------------------


def command_gui(_args: argparse.Namespace, _ctx: CliContext) -> None:
    """Launch the Tkinter GUI (handler used only as a fallback path)."""

    from changelogmanager.gui import run_gui  # pylint: disable=import-outside-toplevel

    raise SystemExit(run_gui())
