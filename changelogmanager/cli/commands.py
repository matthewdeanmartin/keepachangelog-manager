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
    serialize_config_toml,
    write_configuration,
)
from changelogmanager.github import (
    GitHub as GitHub,
)  # noqa: PLC0414 (re-exported; patched in tests)
from changelogmanager.runtime_logging import VERBOSE, get_logger
from changelogmanager.schema_validation import DEFAULT_SCHEMA_VERSION
from changelogmanager.services import build_updated_config  # re-exported for the GUI
from changelogmanager.skill_bundle import SKILL_NAME, export_skill
from changelogmanager.versioning import version_scheme_label

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

    logger.info("Running release command for %s", ctx.changelog.get_file_path())
    changelog = ctx.changelog
    bump_versions = bool(getattr(args, "bump_versions", False))
    pyproject_only = bool(getattr(args, "pyproject_only", False))

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

    # Stage the release (no write yet) so we can compute the version for the
    # confirmation prompt, but defer the validity check for --bump-versions to
    # the service so behaviour matches the dry-run path.
    if bump_versions:
        from changelogmanager.version_bumper import jiggle_available  # noqa: PLC0415

        if not jiggle_available():
            raise logging.Error(
                message="--bump-versions requires jiggle-version. Install it with: pip install 'keepachangelog-manager-fork[jiggle]'"
            )

    changelog.release(args.override_version)
    new_version = str(next(iter(changelog.get())))

    if not args.yes:
        if ctx.json_output or ctx.quiet or not prompts.interactive_enabled():
            raise logging.Error(
                file_path=changelog.get_file_path(),
                message=(
                    "Refusing to release without --yes (non-interactive). Pass --yes to confirm or --dry-run to preview."
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

    if bump_versions:
        from changelogmanager.version_bumper import bump_version_files  # noqa: PLC0415

        bumped = bump_version_files(new_version, pyproject_only=pyproject_only)
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


def command_add(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to add a new message to the CHANGELOG.md."""

    logger.info("Running add command for %s", ctx.changelog.get_file_path())
    changelog_entry = prompts.prompt_for_missing_add_arguments(
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

    if args.dry_run:
        print_dry_run(
            ctx,
            f"would open or update PR head={args.head} base={args.base} in {args.repository}",
        )
        ctx.json_payload.update(
            {"repository": args.repository, "head": args.head, "base": args.base}
        )
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

    if args.dry_run:
        future_version = changelog.suggest_future_version()
        print_dry_run(
            ctx,
            f"would create or update GitLab release v{future_version} in {args.project}",
        )
        ctx.json_payload["version"] = str(future_version)
        ctx.json_payload["project"] = args.project
        return

    from changelogmanager.gitlab import GitLab  # noqa: PLC0415

    gitlab = GitLab(project=args.project, token=token, gitlab_url=args.gitlab_url)
    release = gitlab.create_release(changelog=changelog, ref=args.ref)
    tag_name = str(release.get("tag_name", ""))
    links = release.get("_links")
    web_url = str(links.get("self", "") if isinstance(links, dict) else "").strip()
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


def command_backfill(args: argparse.Namespace, ctx: CliContext) -> None:
    """Backfills missing changelog versions from existing release history."""

    logger.info(
        "Running backfill command for %s from source %s",
        ctx.changelog.get_file_path(),
        args.source,
    )
    services.validate_backfill_options(
        source=args.source,
        strategy=args.strategy,
        missing_only=args.missing_only,
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
# gui
# ----------------------------------------------------------------------


def command_gui(_args: argparse.Namespace, _ctx: CliContext) -> None:
    """Launch the Tkinter GUI (handler used only as a fallback path)."""

    from changelogmanager.gui import run_gui  # pylint: disable=import-outside-toplevel

    raise SystemExit(run_gui())
