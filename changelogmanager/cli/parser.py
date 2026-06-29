# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Argument parser construction for the changelogmanager CLI."""

from __future__ import annotations

import argparse

from changelogmanager.change_types import ALL_TYPES_OF_CHANGE, TYPES_OF_CHANGE
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # add an entry to [Unreleased]
  changelogmanager add --change-type added --message "Support dark mode"

  # validate and autofix common issues
  changelogmanager validate --fix

  # release [Unreleased] non-interactively
  changelogmanager release --yes

  # release and sync pyproject.toml version in one step
  changelogmanager release --bump-versions --yes

  # print the next version that would be released
  changelogmanager version --reference future

  # seed [Unreleased] from git commit history
  changelogmanager from-commits

  # create a GitHub draft release from [Unreleased]
  changelogmanager github-release --repository owner/repo
""",
    )
    parser.add_argument("--config", default=None, help="Configuration file")
    parser.add_argument(
        "--component", default="default", help="Name of the component to update"
    )
    parser.add_argument(
        "-f",
        "--error-format",
        choices=["llvm", "github"],
        # Default is None (not "llvm") so config_resolve can tell an explicit
        # -f from the absence of one. With no flag and no config value, the
        # format is autodetected (github inside GitHub Actions, else llvm).
        default=None,
        help="Type of formatting to apply to error messages (default: autodetect)",
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
        "create",
        help="Command to create a new (empty) CHANGELOG.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # create CHANGELOG.md in the current directory
  changelogmanager create

  # preview what would be created without writing
  changelogmanager create --dry-run
""",
    )
    add_dry_run_argument(create_parser)
    create_parser.set_defaults(handler=commands.command_create)

    config_parser = subparsers.add_parser(
        "config",
        help="Show or initialize changelogmanager configuration",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # show effective configuration and where it came from
  changelogmanager config

  # interactively create or update configuration
  changelogmanager config init

  # show config for a specific config file
  changelogmanager --config changelogmanager.toml config
""",
    )
    config_parser.set_defaults(handler=commands.command_config)
    config_subparsers = config_parser.add_subparsers(dest="config_command")
    config_init_parser = config_subparsers.add_parser(
        "init",
        help="Create or update configuration interactively",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # create pyproject.toml config interactively (defaults to semver)
  changelogmanager config init

  # write config to a standalone file instead
  changelogmanager --config changelogmanager.toml config init
""",
    )
    config_init_parser.set_defaults(handler=commands.command_config_init)

    skill_parser = subparsers.add_parser(
        "skill",
        help="Export bundled AI skill files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  changelogmanager skill export
  changelogmanager skill export --path .github/skills
""",
    )
    skill_subparsers = skill_parser.add_subparsers(dest="skill_command", required=True)
    skill_export_parser = skill_subparsers.add_parser(
        "export",
        help="Export the bundled changelogmanager skill",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # prompt for a target directory (Copilot / Claude locations offered)
  changelogmanager skill export

  # export to a specific path
  changelogmanager skill export --path .github/skills

  # preview without writing
  changelogmanager skill export --path .github/skills --dry-run
""",
    )
    skill_export_parser.add_argument(
        "--path",
        default=None,
        help="Directory that should receive the exported skill folder",
    )
    add_dry_run_argument(skill_export_parser)
    skill_export_parser.set_defaults(handler=commands.command_skill_export)

    version_parser = subparsers.add_parser(
        "version",
        help="Command to retrieve versions from a CHANGELOG.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # print the most recently released version
  changelogmanager version

  # print the version before the current one
  changelogmanager version --reference previous

  # print what the next release would be based on [Unreleased] change types
  changelogmanager version --reference future

  # capture the future version into a shell variable
  NEXT=$(changelogmanager --json version --reference future | jq -r '.version')
""",
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
        "validate",
        help="Command to validate the CHANGELOG.md for inconsistencies",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # validate and report errors
  changelogmanager validate

  # validate with GitHub Actions inline annotations
  changelogmanager --error-format github validate

  # autofix safe layout issues without writing (preview)
  changelogmanager validate --fix --dry-run

  # autofix and write
  changelogmanager validate --fix

  # enforce the strictest community standard (hard errors)
  changelogmanager validate --strict

  # bring a changelog up to the strict standard in one pass
  changelogmanager validate --fix --strict --no-format

  # validate all components declared in config
  changelogmanager --config changelogmanager.toml validate --all

  # validate only components whose changelog changed in git
  changelogmanager --config changelogmanager.toml validate --all --changed-only
""",
    )
    validate_parser.add_argument(
        "--fix",
        action="store_true",
        default=False,
        help="Apply autofixes for safe layout and structural changelog issues",
    )
    validate_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help=(
            "Enforce the strictest community standard: treat missing version link "
            "references, ordering/empty/duplicate warnings, and a missing canonical "
            "preamble as hard errors (non-zero exit). Combine with --fix to bring a "
            "changelog up to standard in one pass."
        ),
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
        "release",
        help="Release changes added to [Unreleased] block",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # preview what would be released (no writes)
  changelogmanager release --dry-run

  # release non-interactively (required in CI)
  changelogmanager release --yes

  # release with an explicit version instead of the auto-calculated one
  changelogmanager release --override-version 2.0.0 --yes

  # release and update pyproject.toml + __version__ strings in one step
  changelogmanager release --bump-versions --yes

  # same but skip Python source files, only update pyproject.toml
  changelogmanager release --bump-versions --pyproject-only --yes
""",
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
            "Bump the version in pyproject.toml (and Python source __version__ vars) to match the released version."
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
        "to-json",
        help="Exports the contents of the CHANGELOG.md to a JSON file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # export to CHANGELOG.json (default)
  changelogmanager to-json

  # export to a custom file
  changelogmanager to-json --file-name dist/changelog.json

  # validate the export format without writing
  changelogmanager to-json --dry-run
""",
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
        "to-html",
        help="Exports the contents of the CHANGELOG.md to an HTML file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # export to CHANGELOG.html (default)
  changelogmanager to-html

  # export to a custom file
  changelogmanager to-html --file-name docs/changelog.html

  # validate without writing
  changelogmanager to-html --dry-run
""",
    )
    to_html_parser.add_argument(
        "--file-name", default="CHANGELOG.html", help="Filename of the HTML output"
    )
    add_dry_run_argument(to_html_parser)
    to_html_parser.set_defaults(handler=commands.command_to_html)

    add_parser = subparsers.add_parser(
        "add",
        help="Command to add a new message to the CHANGELOG.md",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # add an entry interactively (prompts for type and message)
  changelogmanager add

  # add non-interactively
  changelogmanager add --change-type added --message "Support dark mode"
  changelogmanager add --change-type fixed --message "Prevent crash on empty input"
  changelogmanager add --change-type security --message "Upgrade dependency with CVE"

  # write the entry to changelog.d instead of [Unreleased]
  changelogmanager add --change-type added --message "Support dark mode" --fragment

  # preview without writing
  changelogmanager add --change-type added --message "New feature" --dry-run
""",
    )
    add_parser.add_argument(
        "-t",
        "--change-type",
        choices=TYPES_OF_CHANGE,
        help="Type of the change",
    )
    add_parser.add_argument("-m", "--message", help="Changelog entry")
    add_parser.add_argument(
        "--fragment",
        nargs="?",
        const=True,
        default=None,
        metavar="SLUG",
        help=(
            "Write or update a changelog fragment instead of [Unreleased]. "
            "Pass an optional slug to choose the fragment filename."
        ),
    )
    add_parser.add_argument(
        "--fragment-dir",
        default=None,
        help="Directory for --fragment output (default: changelog.d)",
    )
    add_dry_run_argument(add_parser)
    add_parser.set_defaults(handler=commands.command_add)

    tasks_parser = subparsers.add_parser(
        "tasks",
        help="Manage a lightweight TASKS.md file",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  changelogmanager tasks list
  changelogmanager tasks add fixed "Preserve links during promotion"
  changelogmanager tasks check 12
  changelogmanager tasks promote
""",
    )
    tasks_subparsers = tasks_parser.add_subparsers(dest="tasks_command", required=True)

    tasks_list_parser = tasks_subparsers.add_parser("list", help="List parsed tasks")
    tasks_list_parser.add_argument("--tasks-file", default=None, help="Task file path")
    tasks_list_parser.set_defaults(handler=commands.command_tasks)

    tasks_add_parser = tasks_subparsers.add_parser("add", help="Add a task")
    tasks_add_parser.add_argument("change_type", choices=TYPES_OF_CHANGE)
    tasks_add_parser.add_argument("message")
    tasks_add_parser.add_argument("--tasks-file", default=None, help="Task file path")
    tasks_add_parser.set_defaults(handler=commands.command_tasks)

    tasks_check_parser = tasks_subparsers.add_parser("check", help="Mark a task done")
    tasks_check_parser.add_argument("selector", help="Task line number or exact text")
    tasks_check_parser.add_argument("--tasks-file", default=None, help="Task file path")
    tasks_check_parser.set_defaults(handler=commands.command_tasks)

    tasks_uncheck_parser = tasks_subparsers.add_parser(
        "uncheck", help="Mark a task not done"
    )
    tasks_uncheck_parser.add_argument("selector", help="Task line number or exact text")
    tasks_uncheck_parser.add_argument(
        "--tasks-file", default=None, help="Task file path"
    )
    tasks_uncheck_parser.set_defaults(handler=commands.command_tasks)

    tasks_validate_parser = tasks_subparsers.add_parser(
        "validate", help="Validate a task file"
    )
    tasks_validate_parser.add_argument(
        "--tasks-file", default=None, help="Task file path"
    )
    tasks_validate_parser.set_defaults(handler=commands.command_tasks)

    tasks_promote_parser = tasks_subparsers.add_parser(
        "promote", help="Move checked tasks into [Unreleased]"
    )
    tasks_promote_parser.add_argument(
        "--tasks-file", default=None, help="Task file path"
    )
    tasks_promote_parser.add_argument(
        "--keep",
        action="store_true",
        default=False,
        help="Leave promoted tasks in TASKS.md",
    )
    add_dry_run_argument(tasks_promote_parser)
    tasks_promote_parser.set_defaults(handler=commands.command_tasks)

    tasks_assemble_parser = tasks_subparsers.add_parser(
        "assemble",
        help="Assemble tickets/*.md fragments into TASKS.md",
    )
    tasks_assemble_parser.add_argument(
        "--tickets-dir", default=None, help="Directory of task fragments"
    )
    tasks_assemble_parser.add_argument(
        "--tasks-file", default=None, help="Output TASKS.md path"
    )
    tasks_assemble_parser.add_argument(
        "--rich",
        action="store_true",
        default=False,
        help="Emit the grouped (Status -> Category) view with nested bodies",
    )
    add_dry_run_argument(tasks_assemble_parser)
    tasks_assemble_parser.set_defaults(handler=commands.command_tasks)

    tasks_new_parser = tasks_subparsers.add_parser(
        "new", help="Scaffold a new task fragment in tickets/"
    )
    tasks_new_parser.add_argument("summary", help="Short task summary (the H1 title)")
    tasks_new_parser.add_argument(
        "--category",
        choices=ALL_TYPES_OF_CHANGE,
        default="added",
        help="Fragment category (default: added)",
    )
    tasks_new_parser.add_argument(
        "--tickets-dir", default=None, help="Directory of task fragments"
    )
    tasks_new_parser.set_defaults(handler=commands.command_tasks)

    tasks_fragments_parser = tasks_subparsers.add_parser(
        "fragments", help="Lint task fragments in tickets/"
    )
    tasks_fragments_subparsers = tasks_fragments_parser.add_subparsers(
        dest="tasks_fragments_command", required=True
    )
    tasks_fragments_lint_parser = tasks_fragments_subparsers.add_parser(
        "lint", help="Report fragment head problems without writing"
    )
    tasks_fragments_lint_parser.add_argument(
        "--tickets-dir", default=None, help="Directory of task fragments"
    )
    tasks_fragments_lint_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit non-zero when any fragment has lint warnings",
    )
    tasks_fragments_lint_parser.set_defaults(handler=commands.command_tasks)

    fragments_parser = subparsers.add_parser(
        "fragments",
        help="Manage changelog fragment files",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  changelogmanager fragments list
  changelogmanager fragments add added "Support TASKS.md"
  changelogmanager fragments collect
""",
    )
    fragments_subparsers = fragments_parser.add_subparsers(
        dest="fragments_command", required=True
    )

    fragments_list_parser = fragments_subparsers.add_parser(
        "list", help="List pending fragments"
    )
    fragments_list_parser.add_argument(
        "--fragment-dir", default=None, help="Fragment directory"
    )
    fragments_list_parser.set_defaults(handler=commands.command_fragments)

    fragments_add_parser = fragments_subparsers.add_parser(
        "add", help="Create or update a fragment"
    )
    fragments_add_parser.add_argument("change_type", choices=TYPES_OF_CHANGE)
    fragments_add_parser.add_argument("message")
    fragments_add_parser.add_argument("--slug", default=None, help="Fragment slug")
    fragments_add_parser.add_argument(
        "--fragment-dir", default=None, help="Fragment directory"
    )
    fragments_add_parser.set_defaults(handler=commands.command_fragments)

    fragments_validate_parser = fragments_subparsers.add_parser(
        "validate", help="Validate fragment files"
    )
    fragments_validate_parser.add_argument(
        "--fragment-dir", default=None, help="Fragment directory"
    )
    fragments_validate_parser.set_defaults(handler=commands.command_fragments)

    fragments_collect_parser = fragments_subparsers.add_parser(
        "collect", help="Move pending fragments into the changelog"
    )
    fragments_collect_parser.add_argument(
        "--fragment-dir", default=None, help="Fragment directory"
    )
    fragments_collect_parser.add_argument(
        "--consume",
        choices=["archive", "delete", "keep"],
        default=None,
        help="What to do with collected fragments",
    )
    add_dry_run_argument(fragments_collect_parser)
    fragments_collect_parser.set_defaults(handler=commands.command_fragments)

    remove_parser = subparsers.add_parser(
        "remove",
        help="Removes an entry from [Unreleased]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # list all [Unreleased] entries with their indices
  changelogmanager remove --list

  # print just the total count of [Unreleased] entries
  changelogmanager remove --count

  # remove a specific entry (use --list first to find the index)
  changelogmanager remove --change-type added --index 0

  # preview without writing
  changelogmanager remove --change-type fixed --index 1 --dry-run
""",
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
    remove_parser.add_argument(
        "--count",
        action="store_true",
        default=False,
        help="Print the total number of [Unreleased] entries as a plain integer",
    )
    add_dry_run_argument(remove_parser)
    remove_parser.set_defaults(handler=commands.command_remove)

    edit_parser = subparsers.add_parser(
        "edit",
        help="Edits an existing entry in [Unreleased]",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # edit interactively (prompts for entry selection and new message)
  changelogmanager edit

  # update the text of a specific entry
  changelogmanager edit --change-type added --index 0 --message "Revised description"

  # move an entry into a different change-type bucket
  changelogmanager edit --change-type changed --index 0 --new-change-type fixed

  # update text and change type in one command
  changelogmanager edit --change-type added --index 1 --message "Fix typo" --new-change-type fixed

  # preview without writing
  changelogmanager edit --change-type added --index 0 --message "Preview edit" --dry-run
""",
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # create a draft GitHub release from [Unreleased] (default)
  changelogmanager github-release --repository owner/repo

  # publish the release immediately instead of leaving it as a draft
  changelogmanager github-release --repository owner/repo --release

  # preview without calling GitHub
  changelogmanager github-release --repository owner/repo --dry-run

  # typical GitHub Actions step (token comes from GITHUB_TOKEN env var)
  changelogmanager github-release --repository "$GITHUB_REPOSITORY"
""",
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # open a PR from a release branch to main
  changelogmanager github-pr \\
    --repository owner/repo \\
    --head release/bump-123 \\
    --base main \\
    --title "chore: release 1.2.0"

  # preview without calling GitHub
  changelogmanager github-pr \\
    --repository owner/repo \\
    --head release/bump-123 \\
    --base main \\
    --dry-run
""",
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
        "--skip-ci",
        dest="skip_ci",
        default=None,
        action="store_true",
        help=(
            "Append [skip ci] to the PR title so merging it does not trigger a "
            "CI run (conserves build minutes). Defaults to [defaults].skip_ci "
            "in config."
        ),
    )
    github_pr_parser.add_argument(
        "--no-skip-ci",
        dest="skip_ci",
        action="store_false",
        help="Do not append [skip ci] to the PR title (overrides config).",
    )
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # preview backfill from local git tags and commits (no network)
  changelogmanager backfill --source local --dry-run

  # backfill from local history
  changelogmanager backfill --source local

  # backfill from all sources including GitHub releases and merged PRs
  changelogmanager backfill --source all --repository owner/repo

  # backfill from PyPI release history
  changelogmanager backfill --source pypi --package my-package-name

  # limit to a version range
  changelogmanager backfill --source local --since v1.0.0 --until v2.0.0

  # also seed [Unreleased] from commits since the latest tag
  changelogmanager backfill --source local --include-unreleased

  # additively fill entries into existing versions (idempotent)
  changelogmanager backfill --source local --strategy merge --no-missing-only
""",
    )
    backfill_parser.add_argument(
        "--source",
        choices=[
            "tags",
            "commits",
            "local",
            "github-releases",
            "github-prs",
            "pypi",
            "all",
        ],
        default="local",
        help=(
            "Source or source set to import from. "
            "local = tags + commits (no network). "
            "all = local + github-releases + github-prs (requires --repository). "
            "all without --repository falls back to local with a deprecation warning."
        ),
    )
    backfill_parser.add_argument(
        "--repository",
        default=None,
        help="GitHub repository in owner/repo format (e.g. owner/repo); required for github-releases and github-prs",
    )
    backfill_parser.add_argument(
        "--package",
        default=None,
        help="PyPI package name; required for --source pypi",
    )
    backfill_parser.add_argument(
        "-t",
        "--github-token",
        default=None,
        help="GitHub token (falls back to keyring then GITHUB_TOKEN env var)",
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # create or update a release for a project (prompts for token if not set)
  changelogmanager gitlab-release --project group/project

  # specify token explicitly
  changelogmanager gitlab-release --project group/project --gitlab-token "$GITLAB_TOKEN"

  # tag a specific commit
  changelogmanager gitlab-release --project group/project --ref "$CI_COMMIT_SHA"

  # self-hosted GitLab instance
  changelogmanager gitlab-release --project group/project --gitlab-url https://gitlab.example.com

  # preview without calling GitLab
  changelogmanager gitlab-release --project group/project --dry-run
""",
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
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # seed from commits since the last git tag (default)
  changelogmanager from-commits

  # seed from commits since a specific ref
  changelogmanager from-commits --since v1.2.0

  # walk the full git history instead of stopping at the last tag
  changelogmanager from-commits --all-history

  # skip commits that don't match the commit schema (no 'changed' fallback)
  changelogmanager from-commits --strict

  # route commits to each configured component by the files they touch
  changelogmanager --config changelogmanager.toml from-commits --all

  # preview without writing
  changelogmanager from-commits --dry-run
""",
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

    lint_commits_parser = subparsers.add_parser(
        "lint-commits",
        help="Audit past commit subjects against the Keep a Changelog commit schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # audit commits since the last tag, listing only the unclassifiable ones
  changelogmanager lint-commits

  # audit the whole history
  changelogmanager lint-commits --all-history

  # show every commit with its classification
  changelogmanager lint-commits --show all

  # fail (exit 1) when any commit is unclassifiable (CI gate)
  changelogmanager lint-commits --strict

  # machine-readable report for a CI job
  changelogmanager --json lint-commits --all-history
""",
    )
    lint_commits_parser.add_argument(
        "--since",
        default=None,
        help="Git ref to start from; defaults to the last tag if any",
    )
    lint_commits_parser.add_argument(
        "--until",
        default=None,
        help="Git ref to stop at (default: HEAD)",
    )
    lint_commits_parser.add_argument(
        "--all-history",
        action="store_true",
        default=False,
        help="Audit full history rather than starting at the last tag",
    )
    lint_commits_parser.add_argument(
        "--commit-schema",
        choices=["auto", "conventional", "gitmoji", "keepachangelog"],
        default=None,
        help=(
            "Commit message schema to lint against; overrides the configured "
            "message_lint.schema (default: config or auto)"
        ),
    )
    lint_commits_parser.add_argument(
        "--show",
        choices=["fail", "skip", "pass", "all"],
        default="fail",
        help="Which commits to list: fail (default), skip, pass, or all",
    )
    lint_commits_parser.add_argument(
        "--strict",
        action="store_true",
        default=False,
        help="Exit 1 when any commit subject is unclassifiable",
    )
    lint_commits_parser.add_argument(
        "--max-commits",
        dest="max_commits",
        type=int,
        default=None,
        help=(
            "Refuse to audit when the walked range exceeds this many commits "
            "(default 5000); pass 0 to disable the guard"
        ),
    )
    add_dry_run_argument(lint_commits_parser)
    lint_commits_parser.set_defaults(handler=commands.command_lint_commits)

    rewrite_messages_parser = subparsers.add_parser(
        "rewrite-messages",
        help=(
            "Plan subject rewrites over UNPUSHED commits (apply not yet " "implemented)"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Scoped to unpushed commits only (@{upstream}..HEAD), so it can never touch
shared history. The plan path is read-only; --apply is not yet implemented.

examples:
  # show suggested rewrites for unclassifiable unpushed commits
  changelogmanager rewrite-messages

  # write the plan to a file you can review/edit
  changelogmanager rewrite-messages --plan-out rewrite-plan.tsv

  # machine-readable plan
  changelogmanager --json rewrite-messages

  # force every suggestion to use the 'Changed:' prefix
  changelogmanager rewrite-messages --auto-prefix changed

  # apply is intentionally disabled until full safeties exist:
  changelogmanager rewrite-messages --apply --yes   # -> not implemented (exit 1)
""",
    )
    rewrite_messages_parser.add_argument(
        "--commit-schema",
        choices=["auto", "conventional", "gitmoji", "keepachangelog"],
        default=None,
        help="Commit message schema to lint against (default: config or auto)",
    )
    rewrite_messages_parser.add_argument(
        "--plan-out",
        dest="plan_out",
        default=None,
        help="Write the rewrite plan (TSV) to this file instead of stdout",
    )
    rewrite_messages_parser.add_argument(
        "--auto-prefix",
        dest="auto_prefix",
        choices=TYPES_OF_CHANGE,
        default=None,
        help=(
            "Force every suggested subject to use this category prefix instead "
            "of guessing one from keywords"
        ),
    )
    rewrite_messages_parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help=(
            "Apply the rewrite (NOT YET IMPLEMENTED; requires --yes or an "
            "interactive confirmation, then fails fast)"
        ),
    )
    rewrite_messages_parser.add_argument(
        "-y",
        "--yes",
        action="store_true",
        default=False,
        help="Consent to apply non-interactively (for the future apply path)",
    )
    rewrite_messages_parser.add_argument(
        "--max-commits",
        dest="max_commits",
        type=int,
        default=None,
        help=(
            "Refuse when the unpushed range exceeds this many commits "
            "(default 5000); pass 0 to disable the guard"
        ),
    )
    rewrite_messages_parser.set_defaults(handler=commands.command_rewrite_messages)

    credentials_parser = subparsers.add_parser(
        "credentials",
        help="Manage stored API tokens in the OS keyring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  # store a GitHub token securely (prompts without echoing)
  changelogmanager credentials set github

  # store a GitLab token
  changelogmanager credentials set gitlab

  # check which tokens are currently configured
  changelogmanager credentials check

  # remove a stored token
  changelogmanager credentials clear github
""",
    )
    credentials_subparsers = credentials_parser.add_subparsers(
        dest="credentials_command", required=True
    )

    creds_set_parser = credentials_subparsers.add_parser(
        "set",
        help="Store a token in the OS keyring (prompts securely for the value)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  changelogmanager credentials set github
  changelogmanager credentials set gitlab
""",
    )
    creds_set_parser.add_argument(
        "service",
        choices=["github", "gitlab"],
        help="Which token to store",
    )
    creds_set_parser.set_defaults(handler=commands.command_credentials)

    creds_clear_parser = credentials_subparsers.add_parser(
        "clear",
        help="Remove a stored token from the OS keyring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  changelogmanager credentials clear github
  changelogmanager credentials clear gitlab
""",
    )
    creds_clear_parser.add_argument(
        "service",
        choices=["github", "gitlab"],
        help="Which token to remove",
    )
    creds_clear_parser.set_defaults(handler=commands.command_credentials)

    creds_check_parser = credentials_subparsers.add_parser(
        "check",
        help="Print which tokens are currently configured in the OS keyring",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  changelogmanager credentials check
""",
    )
    creds_check_parser.set_defaults(handler=commands.command_credentials)

    gui_parser = subparsers.add_parser(
        "gui",
        help="Launch the Tkinter GUI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  changelogmanager gui
""",
    )
    gui_parser.set_defaults(handler=commands.command_gui)

    return parser
