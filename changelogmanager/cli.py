# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog Manager."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Optional, Sequence

import inquirer

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import TYPES_OF_CHANGE, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.config import get_component_from_config
from changelogmanager.github import GitHub

VERSION_REFERENCES = ["previous", "current", "future"]


@dataclass
class CliContext:
    """CLI context shared across commands."""

    changelog: Changelog


def print_dry_run(message: str) -> None:
    """Reports that a command ran in dry-run mode."""

    print(f"Dry run: {message}")


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

    logging.config(
        logging.formatters.Llvm()
        if error_format == "llvm"
        else logging.formatters.GitHub()
    )


def load_changelog(config: Optional[str], component: str, input_file: str) -> Changelog:
    """Loads the changelog configured for this invocation."""

    if config:
        component_config = get_component_from_config(config=config, component=component)
        file_path = component_config.get("changelog")
    else:
        file_path = input_file

    changelog = ChangelogReader(file_path=file_path).read()
    return Changelog(file_path=file_path, changelog=changelog)


def command_create(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to create a new (empty) CHANGELOG.md."""

    changelog = ctx.changelog

    if changelog.exists():
        raise logging.Info(
            file_path=changelog.get_file_path(), message="File already exists"
        )

    if args.dry_run:
        print_dry_run(f"would create {changelog.get_file_path()}")
        return

    changelog.write_to_file()


def command_version(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to retrieve versions from a CHANGELOG.md."""

    changelog = ctx.changelog

    if args.reference == "current":
        print(changelog.version())

    if args.reference == "previous":
        print(changelog.previous_version())

    if args.reference == "future":
        print(changelog.suggest_future_version())


def command_validate(_: argparse.Namespace, __: CliContext) -> None:
    """Command to validate the CHANGELOG.md for inconsistencies."""


def command_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Release changes added to [Unreleased] block."""

    changelog = ctx.changelog
    changelog.release(args.override_version)

    if args.dry_run:
        print_dry_run(f"would release {changelog.get_file_path()}")
        return

    changelog.write_to_file()


def command_to_json(args: argparse.Namespace, ctx: CliContext) -> None:
    """Exports the contents of the CHANGELOG.md to a JSON file."""

    changelog = ctx.changelog

    if args.dry_run:
        changelog.to_json()
        print_dry_run(f"would write JSON output to {args.file_name}")
        return

    changelog.write_to_json(file=args.file_name)


def prompt_for_missing_add_arguments(
    change_type: Optional[str], message: Optional[str]
) -> dict[str, str]:
    """Prompts for any missing add arguments."""

    changelog_entry: dict[str, str] = {}
    prompts = []

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

    changelog_entry.setdefault("change_type", change_type)
    changelog_entry.setdefault("message", message)
    changelog_entry.setdefault("confirm", "Yes")
    return changelog_entry


def command_add(args: argparse.Namespace, ctx: CliContext) -> None:
    """Command to add a new message to the CHANGELOG.md."""

    changelog_entry = prompt_for_missing_add_arguments(
        change_type=args.change_type, message=args.message
    )

    changelog = ctx.changelog
    changelog.add(
        change_type=changelog_entry["change_type"], message=changelog_entry["message"]
    )

    if changelog_entry["confirm"] == "Yes":
        if args.dry_run:
            print_dry_run(f"would update {changelog.get_file_path()}")
            return

        changelog.write_to_file()


def command_github_release(args: argparse.Namespace, ctx: CliContext) -> None:
    """Creates or updates a GitHub release from the changelog."""

    changelog = ctx.changelog

    if args.dry_run:
        changelog.get(UNRELEASED_ENTRY)
        future_version = changelog.suggest_future_version()
        release_state = "draft" if args.draft else "published"
        print_dry_run(
            "would create or update "
            f"{release_state} GitHub release v{future_version} in {args.repository}"
        )
        return

    github = GitHub(repository=args.repository, token=args.github_token)
    github.delete_draft_releases()
    github.create_release(changelog=changelog, draft=args.draft)


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

    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser(
        "create", help="Command to create a new (empty) CHANGELOG.md"
    )
    add_dry_run_argument(create_parser)
    create_parser.set_defaults(handler=command_create)

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

    github_release_parser = subparsers.add_parser(
        "github-release",
        help="Deletes draft GitHub releases and creates a new one",
    )
    github_release_parser.add_argument(
        "-r", "--repository", required=True, help="Repository"
    )
    github_release_parser.add_argument(
        "-t", "--github-token", required=True, help="Github Token"
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

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint."""

    parser = build_parser()

    try:
        args = parser.parse_args(argv)
        configure_logging(args.error_format)
        context = CliContext(
            changelog=load_changelog(
                config=args.config,
                component=args.component,
                input_file=args.input_file,
            )
        )
        args.handler(args, context)
        return 0
    except (logging.Info, logging.Warning) as exc_info:
        exc_info.report()
        return 0
    except logging.Error as exc_info:
        exc_info.report()
        return 1
    except SystemExit as exc_info:
        return exc_info.code if isinstance(exc_info.code, int) else 1
