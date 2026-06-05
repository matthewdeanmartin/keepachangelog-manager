# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Argument parser construction for the changelogmanager CLI."""

from __future__ import annotations

import argparse

from changelogmanager.change_types import TYPES_OF_CHANGE
from changelogmanager.cli import commands
from changelogmanager.gitlab import DEFAULT_GITLAB_URL
from changelogmanager.schema_validation import DEFAULT_SCHEMA_VERSION, SCHEMA_VERSIONS

VERSION_REFERENCES = ["previous", "current", "future"]


def add_dry_run_argument(parser: argparse.ArgumentParser) -> None:
    """Adds the shared dry-run option to a parser."""

    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Preview the command without modifying files or calling GitHub",
    )


def build_parser() -> (  # pylint: disable=too-many-locals,too-many-statements
    argparse.ArgumentParser
):
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
        # Default is None (not "CHANGELOG.md") so the loader can distinguish an
        # explicit --input-file from the built-in default. An explicit flag must win
        # over a config/component-derived changelog path; see resolve_changelog_file.
        "--input-file",
        default=None,
        help="Changelog file to work with (default: CHANGELOG.md)",
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
    create_parser.set_defaults(handler=commands.command_create)

    config_parser = subparsers.add_parser(
        "config", help="Show or initialize changelogmanager configuration"
    )
    config_parser.set_defaults(handler=commands.command_config)
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_init_parser = config_subparsers.add_parser(
        "init", help="Create or update configuration interactively"
    )
    config_init_parser.set_defaults(handler=commands.command_config_init)

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
    skill_export_parser.set_defaults(handler=commands.command_skill_export)

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
    version_parser.set_defaults(handler=commands.command_version)

    validate_parser = subparsers.add_parser(
        "validate", help="Command to validate the CHANGELOG.md for inconsistencies"
    )
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
    validate_parser.set_defaults(handler=commands.command_validate)

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
    release_parser.add_argument(
        "--bump-versions",
        dest="bump_versions",
        action="store_true",
        default=False,
        help=(
            "Bump the version in pyproject.toml (and Python source __version__ vars) to match the released version. Requires jiggle-version."
        ),
    )
    release_parser.add_argument(
        "--pyproject-only",
        dest="pyproject_only",
        action="store_true",
        default=False,
        help=(
            "When --bump-versions is set, only update pyproject.toml; skip Python source files containing __version__."
        ),
    )
    add_dry_run_argument(release_parser)
    release_parser.set_defaults(handler=commands.command_release)

    to_json_parser = subparsers.add_parser(
        "to-json", help="Exports the contents of the CHANGELOG.md to a JSON file"
    )
    to_json_parser.add_argument(
        "--file-name", default="CHANGELOG.json", help="Filename of the JSON output"
    )
    to_json_parser.add_argument(
        "--schema-version",
        choices=SCHEMA_VERSIONS,
        default=DEFAULT_SCHEMA_VERSION,
        help="KAG-Manager JSON schema version to validate the export against",
    )
    add_dry_run_argument(to_json_parser)
    to_json_parser.set_defaults(handler=commands.command_to_json)

    to_html_parser = subparsers.add_parser(
        "to-html", help="Exports the contents of the CHANGELOG.md to an HTML file"
    )
    to_html_parser.add_argument(
        "--file-name", default="CHANGELOG.html", help="Filename of the HTML output"
    )
    add_dry_run_argument(to_html_parser)
    to_html_parser.set_defaults(handler=commands.command_to_html)

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
    add_parser.set_defaults(handler=commands.command_add)

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
    remove_parser.set_defaults(handler=commands.command_remove)

    edit_parser = subparsers.add_parser(
        "edit", help="Edits an existing entry in [Unreleased]"
    )
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
    edit_parser.set_defaults(handler=commands.command_edit)

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
    github_release_parser.set_defaults(handler=commands.command_github_release)

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
    github_pr_parser.set_defaults(handler=commands.command_github_pr)

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
        help=(
            "Only add versions missing from the changelog; pass --no-missing-only with --strategy merge to also backfill entries into existing versions"
        ),
    )
    backfill_parser.add_argument(
        "--include-unreleased",
        action="store_true",
        default=False,
        help=(
            "Seed [Unreleased] from commits since the latest release tag instead of adding past version sections"
        ),
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
        help=(
            "Commit message schema for commit-derived entries; auto tries Conventional Commits, gitmoji, and Keep a Changelog flavored subjects"
        ),
    )
    backfill_parser.add_argument(
        "--max-commits",
        dest="max_commits",
        type=int,
        default=None,
        help=(
            "Refuse to backfill when the walked range exceeds this many commits "
            "(default 5000); pass 0 to disable the guard for monster repos"
        ),
    )
    add_dry_run_argument(backfill_parser)
    backfill_parser.set_defaults(handler=commands.command_backfill)

    gitlab_release_parser = subparsers.add_parser(
        "gitlab-release",
        help="Creates or updates a GitLab release from the changelog",
    )
    gitlab_release_parser.add_argument(
        "-p",
        "--project",
        default=None,
        help=(
            "GitLab project ID or path (e.g. group/project); prompted interactively if omitted"
        ),
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
    gitlab_release_parser.set_defaults(handler=commands.command_gitlab_release)

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
        help=(
            "Route commits to every configured component by the files they touch (uses each component's 'match' globs; requires a config file)"
        ),
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
        help=(
            "Commit message schema; auto tries Conventional Commits, gitmoji, and Keep a Changelog flavored subjects"
        ),
    )
    add_dry_run_argument(from_commits_parser)
    from_commits_parser.set_defaults(handler=commands.command_from_commits)

    gui_parser = subparsers.add_parser("gui", help="Launch the Tkinter GUI")
    gui_parser.set_defaults(handler=commands.command_gui)

    return parser
