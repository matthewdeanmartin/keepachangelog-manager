# Copyright (c) 2022 - 2022 TomTom N.V.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Changelog Manager."""

from typing import Mapping, Optional

import inquirer

from click import group, option, pass_context, Choice, File
import llvm_diagnostics as logging

from changelogmanager.change_types import TYPES_OF_CHANGE, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.config import get_component_from_config
from changelogmanager.github import GitHub

VERSION_REFERENCES = ["previous", "current", "future"]


def dry_run_option(function):
    """Adds the dry-run option to a CLI command."""

    return option(
        "--dry-run",
        is_flag=True,
        default=False,
        help="Preview the command without modifying files or calling GitHub",
    )(function)


def print_dry_run(message: str) -> None:
    """Reports that a command ran in dry-run mode."""

    print(f"Dry run: {message}")


@group()
@option("--config", default=None, help="Configuration file")
@option("--component", default="default", help="Name of the component to update")
@option(
    "-f",
    "--error-format",
    type=Choice(["llvm", "github"]),
    default="llvm",
    help="Type of formatting to apply to error messages",
)
@option("--input-file", default="CHANGELOG.md", help="Changelog file to work with")
@pass_context
def main(
    ctx: Mapping,
    config: Optional[File],
    component: str,
    error_format: bool,
    input_file: str,
) -> int:
    """(Keep a) Changelog Manager"""

    # Pass changelog configuration to sub-commands
    ctx.ensure_object(dict)

    logging.config(
        logging.formatters.Llvm()
        if error_format == "llvm"
        else logging.formatters.GitHub()
    )

    if config:
        component = get_component_from_config(config=config, component=component)
        changelog = ChangelogReader(file_path=component.get("changelog")).read()
        ctx.obj["changelog"] = Changelog(
            file_path=component.get("changelog"), changelog=changelog
        )
    else:
        changelog = ChangelogReader(file_path=input_file).read()
        ctx.obj["changelog"] = Changelog(file_path=input_file, changelog=changelog)


@main.command()
@dry_run_option
@pass_context
def create(ctx: Mapping, dry_run: bool) -> None:
    """Command to create a new (empty) CHANGELOG.md"""
    changelog = ctx.obj["changelog"]

    if changelog.exists():
        raise logging.Info(
            file_path=changelog.get_file_path(), message="File already exists"
        )

    if dry_run:
        print_dry_run(f"would create {changelog.get_file_path()}")
        return

    changelog.write_to_file()


@main.command()
@option(
    "-r",
    "--reference",
    type=Choice(VERSION_REFERENCES),
    default="current",
    help="Which version to retrieve",
)
@dry_run_option
@pass_context
def version(ctx: Mapping, reference: str, dry_run: bool) -> None:
    """Command to retrieve versions from a CHANGELOG.md"""
    _ = dry_run

    changelog = ctx.obj["changelog"]

    if reference == "current":
        print(changelog.version())

    if reference == "previous":
        print(changelog.previous_version())

    if reference == "future":
        print(changelog.suggest_future_version())


@main.command()
@dry_run_option
@pass_context
def validate(_: Mapping, dry_run: bool) -> None:
    """Command to validate the CHANGELOG.md for inconsistencies"""
    _ = dry_run


@main.command()
@option(
    "--override-version",
    default=None,
    help="Version to release, defaults to auto-resolve",
)
@dry_run_option
@pass_context
def release(ctx: Mapping, override_version: Optional[str], dry_run: bool) -> None:
    """Release changes added to [Unreleased] block"""

    changelog = ctx.obj["changelog"]
    changelog.release(override_version)

    if dry_run:
        print_dry_run(f"would release {changelog.get_file_path()}")
        return

    changelog.write_to_file()


@main.command()
@option(
    "--file-name",
    default="CHANGELOG.json",
    help="Filename of the JSON output",
)
@dry_run_option
@pass_context
def to_json(ctx: Mapping, file_name: str, dry_run: bool) -> None:
    """Exports the contents of the CHANGELOG.md to a JSON file"""
    changelog = ctx.obj["changelog"]

    if dry_run:
        changelog.to_json()
        print_dry_run(f"would write JSON output to {file_name}")
        return

    changelog.write_to_json(file=file_name)


@main.command()
@option(
    "-t",
    "--change-type",
    type=Choice(TYPES_OF_CHANGE),
    help="Type of the change",
)
@option(
    "-m",
    "--message",
    help="Changelog entry",
)
@dry_run_option
@pass_context
def add(ctx: Mapping, change_type: str, message: str, dry_run: bool) -> None:
    """Command to add a new message to the CHANGELOG.md"""
    changelog_entry = {}

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

    if len(prompts) > 0:
        prompts.append(
            inquirer.List(
                "confirm",
                message="Apply changes to your CHANGELOG.md",
                choices=["Yes", "No"],
                default="Yes",
            )
        )
        changelog_entry = inquirer.prompt(prompts)

    changelog_entry.setdefault("change_type", change_type)
    changelog_entry.setdefault("message", message)
    changelog_entry.setdefault("confirm", "Yes")

    changelog = ctx.obj["changelog"]
    changelog.add(
        change_type=changelog_entry["change_type"], message=changelog_entry["message"]
    )

    if changelog_entry["confirm"] == "Yes":
        if dry_run:
            print_dry_run(f"would update {changelog.get_file_path()}")
            return

        changelog.write_to_file()


@main.command()
@option("-r", "--repository", required=True, help="Repository")
@option("-t", "--github-token", required=True, help="Github Token")
@option(
    "--draft/--release",
    default=True,
    help="Update/Create the GitHub Release in either Draft or Release state",
)
@dry_run_option
@pass_context
def github_release(
    ctx, repository: str, github_token: str, draft: bool, dry_run: bool
) -> None:
    """Deletes all releases marked as 'Draft' on GitHub and creates a new 'Draft'-release"""

    changelog = ctx.obj["changelog"]

    if dry_run:
        changelog.get(UNRELEASED_ENTRY)
        future_version = changelog.suggest_future_version()
        release_state = "draft" if draft else "published"
        print_dry_run(
            "would create or update "
            f"{release_state} GitHub release v{future_version} in {repository}"
        )
        return

    github = GitHub(repository=repository, token=github_token)
    github.delete_draft_releases()
    github.create_release(changelog=changelog, draft=draft)
