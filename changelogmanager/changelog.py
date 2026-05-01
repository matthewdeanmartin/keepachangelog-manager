# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog"""

import html
import json
import re
from collections import OrderedDict
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import keepachangelog  # type: ignore
import yaml
from semantic_version import Version  # type: ignore

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import (
    CATEGORIES,
    DEFAULT_CHANGELOG_FILE,
    UNRELEASED_ENTRY,
    VersionCore,
)
from changelogmanager.config import get_versioning_markdown
from changelogmanager.runtime_logging import VERBOSE, get_logger

INITIAL_VERSION = Version("0.0.1")
logger = get_logger(__name__)


def _require_string_entries(
    entries: object, *, file_path: str, change_type: str
) -> list[str]:
    if not isinstance(entries, list) or not all(isinstance(entry, str) for entry in entries):
        raise logging.Error(
            file_path=file_path,
            message=f"Invalid '{change_type}' entries in [Unreleased]",
        )
    return entries


class Changelog:
    """Changelog"""

    def __init__(
        self,
        file_path: str = DEFAULT_CHANGELOG_FILE,
        changelog: Optional[dict[str, Any]] = None,
        versioning_scheme: str = "semver",
    ) -> None:
        """Constructor"""
        self.__changelog_file_path = file_path
        self.__changelog = changelog if changelog else {}
        self.__versioning_scheme = versioning_scheme
        logger.log(
            VERBOSE,
            "Initialized changelog object for %s with %d version entries",
            self.__changelog_file_path,
            len(self.__changelog),
        )

    def get_file_path(self) -> str:
        """Returns the path to the changelog file"""
        return self.__changelog_file_path

    def set_data(self, data: dict[str, Any]) -> None:
        """Replaces the in-memory changelog data (used by autofix)."""
        logger.info(
            "Replacing in-memory changelog data for %s with %d version entries",
            self.__changelog_file_path,
            len(data),
        )
        self.__changelog = data

    def add(self, change_type: str, message: str) -> None:
        """Adds a new message to the specified change identifier in the Changelog"""
        logger.info(
            "Adding unreleased entry of type '%s' to %s",
            change_type,
            self.__changelog_file_path,
        )

        changelog: OrderedDict[str, Any] = OrderedDict(self.__changelog.copy())

        changelog.setdefault(
            UNRELEASED_ENTRY,
            {
                "metadata": {
                    "version": UNRELEASED_ENTRY,
                    "release_date": None,
                }
            },
        )
        changelog[UNRELEASED_ENTRY].setdefault(change_type, [])
        changelog[UNRELEASED_ENTRY][change_type].append(message)

        # Ensure that the new entry is on top
        changelog.move_to_end(UNRELEASED_ENTRY, last=False)

        self.__changelog = dict(changelog)

    def list_unreleased(self) -> list[tuple[str, int, str]]:
        """Lists every entry in [Unreleased] as (change_type, index, message)."""

        logger.log(
            VERBOSE, "Listing unreleased entries for %s", self.__changelog_file_path
        )
        unreleased = self.__changelog.get(UNRELEASED_ENTRY, {})
        result: list[tuple[str, int, str]] = []
        for change_type, messages in unreleased.items():
            if change_type == "metadata":
                continue
            if not isinstance(messages, list):
                continue
            for index, message in enumerate(messages):
                result.append((change_type, index, message))
        return result

    def remove(self, change_type: str, index: int) -> str:
        """Removes the entry at ``index`` for ``change_type`` from [Unreleased]."""
        logger.info(
            "Removing unreleased entry %s[%d] from %s",
            change_type,
            index,
            self.__changelog_file_path,
        )

        if UNRELEASED_ENTRY not in self.__changelog:
            raise logging.Error(
                file_path=self.get_file_path(),
                message="Unable to remove without [Unreleased] section",
            )
        unreleased = self.__changelog[UNRELEASED_ENTRY]
        entries = _require_string_entries(
            unreleased.get(change_type),
            file_path=self.get_file_path(),
            change_type=change_type,
        )
        if not entries:
            raise logging.Error(
                file_path=self.get_file_path(),
                message=f"No '{change_type}' entries in [Unreleased]",
            )
        if index < 0 or index >= len(entries):
            raise logging.Error(
                file_path=self.get_file_path(),
                message=(
                    f"Index {index} out of range for '{change_type}' "
                    f"(0..{len(entries) - 1})"
                ),
            )
        removed = entries.pop(index)
        if not entries:
            del unreleased[change_type]
        return removed

    def edit(
        self,
        change_type: str,
        index: int,
        new_message: Optional[str] = None,
        new_change_type: Optional[str] = None,
    ) -> None:
        """Edits an entry in [Unreleased]; can also recategorise it."""
        logger.info(
            "Editing unreleased entry %s[%d] in %s",
            change_type,
            index,
            self.__changelog_file_path,
        )

        if UNRELEASED_ENTRY not in self.__changelog:
            raise logging.Error(
                file_path=self.get_file_path(),
                message="Unable to edit without [Unreleased] section",
            )
        unreleased = self.__changelog[UNRELEASED_ENTRY]
        entries = _require_string_entries(
            unreleased.get(change_type),
            file_path=self.get_file_path(),
            change_type=change_type,
        )
        if not entries:
            raise logging.Error(
                file_path=self.get_file_path(),
                message=f"No '{change_type}' entries in [Unreleased]",
            )
        if index < 0 or index >= len(entries):
            raise logging.Error(
                file_path=self.get_file_path(),
                message=(
                    f"Index {index} out of range for '{change_type}' "
                    f"(0..{len(entries) - 1})"
                ),
            )

        message = new_message if new_message is not None else entries[index]

        if new_change_type and new_change_type != change_type:
            if new_change_type not in CATEGORIES:
                raise logging.Error(
                    file_path=self.get_file_path(),
                    message=f"Unknown change type '{new_change_type}'",
                )
            entries.pop(index)
            if not entries:
                del unreleased[change_type]
            unreleased.setdefault(new_change_type, []).append(message)
        else:
            entries[index] = message

    def exists(self) -> bool:
        """Verifies if the Changelog file exists"""
        exists = Path(self.__changelog_file_path).is_file()
        logger.log(
            VERBOSE,
            "Checked whether changelog exists at %s: %s",
            self.__changelog_file_path,
            exists,
        )
        return exists

    def get(self, version: Optional[str] = None) -> Mapping[str, Any]:
        """Returns the specified version"""
        logger.log(
            VERBOSE,
            "Retrieving changelog data from %s for version %s",
            self.__changelog_file_path,
            version or "<all>",
        )

        if not version:
            return self.__changelog

        if str(version) not in self.__changelog:
            raise logging.Warning(
                file_path=self.get_file_path(),
                message=f"Version '{version}' not available in the Changelog",
            )

        res: Mapping[str, Any] = self.__changelog[str(version)]
        return res

    def release(self, override_version: Optional[str] = None) -> None:
        """Releases the Unreleased version"""
        logger.info(
            "Preparing release for %s with override version %s",
            self.__changelog_file_path,
            override_version or "<auto>",
        )

        if UNRELEASED_ENTRY not in self.__changelog:
            raise logging.Error(
                file_path=self.get_file_path(),
                message="Unable to release without [Unreleased] section",
            )

        # Strip `v` from the provided version tag
        if override_version and override_version.startswith("v"):
            override_version = override_version[1:]

        try:
            _version = (
                Version(override_version)
                if override_version
                else self.suggest_future_version()
            )
        except ValueError as exc_info:
            _message = f"Version '{override_version}' is not SemVer compliant"
            logger.error(
                "Rejected invalid release version %s for %s",
                override_version,
                self.__changelog_file_path,
            )
            raise logging.Error(message=_message) from exc_info

        if str(_version) in self.get():
            raise logging.Error(
                file_path=self.get_file_path(),
                message=f"Unable to release an already released version '{_version}'",
            )

        if not self.__has_only_unreleased_version() and _version < self.version():
            raise logging.Error(
                file_path=self.get_file_path(),
                message=(
                    "Unable to release a version older than the last release "
                    f"'{self.version()}'"
                ),
            )

        def update_unreleased_version(
            changelog_in: dict[str, Any], new_version: Version
        ) -> OrderedDict[str, Any]:
            changelog_out = OrderedDict(changelog_in.copy())
            changelog_out[str(new_version)] = changelog_out.pop(UNRELEASED_ENTRY)
            changelog_out[str(new_version)]["metadata"] = {
                "version": str(new_version),
                "release_date": datetime.now().strftime("%Y-%m-%d"),
                "semantic_version": {
                    "buildmetadata": None,
                    "major": new_version.major,
                    "minor": new_version.minor,
                    "patch": new_version.patch,
                    "prerelease": None,
                },
            }

            # Ensure that the new entry is on top
            changelog_out.move_to_end(str(new_version), last=False)

            return changelog_out

        self.__changelog = dict(update_unreleased_version(self.__changelog, _version))
        logger.info("Prepared release %s for %s", _version, self.__changelog_file_path)

    def version(self) -> Version:
        """Returns the last released version"""
        logger.log(
            VERBOSE, "Calculating current version for %s", self.__changelog_file_path
        )
        if len(self.__changelog) == 0:
            raise logging.Warning(
                file_path=self.get_file_path(), message="No versions available"
            )

        if UNRELEASED_ENTRY in self.__changelog:
            if len(self.__changelog) <= 1:
                raise logging.Warning(
                    file_path=self.get_file_path(),
                    message="Only an Unreleased version is available",
                )

            return Version(list(self.__changelog)[1])

        return Version(list(self.__changelog)[0])

    def previous_version(self) -> Version:
        """Returns the previously released version"""
        logger.log(
            VERBOSE,
            "Calculating previous released version for %s",
            self.__changelog_file_path,
        )

        if len(self.__changelog) <= 1:
            raise logging.Warning(
                file_path=self.get_file_path(), message="No previous versions available"
            )

        if UNRELEASED_ENTRY in self.__changelog:
            if len(self.__changelog) <= 2:
                raise logging.Warning(
                    file_path=self.get_file_path(),
                    message="No previous versions available",
                )

            return Version(list(self.__changelog)[2])

        return Version(list(self.__changelog)[1])

    def suggest_future_version(self) -> Version:
        """Suggests a future version based on the [Unreleased]-changes"""
        logger.info("Suggesting future version for %s", self.__changelog_file_path)

        if self.__has_only_unreleased_version():
            return INITIAL_VERSION

        def determine_version(
            unreleased: Mapping[str, Any], prev_version: Version
        ) -> Version:
            bump_type = VersionCore.PATCH
            for identifier, category in CATEGORIES.items():
                if identifier in unreleased and category.bump.value > bump_type.value:
                    bump_type = category.bump

            if bump_type == VersionCore.MAJOR:
                return prev_version.next_major()

            if bump_type == VersionCore.MINOR:
                return prev_version.next_minor()

            return prev_version.next_patch()

        return determine_version(self.get(UNRELEASED_ENTRY), self.version())

    def write_to_json(self, file: str, version: Optional[str] = None) -> None:
        """Stores the Changelog file in JSON format"""
        logger.info(
            "Writing JSON export for %s to %s", self.__changelog_file_path, file
        )

        with Path(file).open("w", encoding="UTF-8") as file_handle:
            file_handle.write(self.to_json(version=version))

    def to_json(self, version: Optional[str] = None) -> str:
        """Returns the Changelog file in JSON format"""
        logger.log(
            VERBOSE,
            "Rendering JSON export for %s (%s)",
            self.__changelog_file_path,
            version or "<all>",
        )

        content = self.get(version=version)
        json_data = [value for _, value in content.items()]
        return json.dumps(json_data, indent=4)

    def write_to_yaml(self, file: str, version: Optional[str] = None) -> None:
        """Stores the Changelog file in YAML format."""
        logger.info(
            "Writing YAML export for %s to %s", self.__changelog_file_path, file
        )

        with Path(file).open("w", encoding="UTF-8") as file_handle:
            file_handle.write(self.to_yaml(version=version))

    def to_yaml(self, version: Optional[str] = None) -> str:
        """Returns the Changelog file in YAML format."""
        logger.log(
            VERBOSE,
            "Rendering YAML export for %s (%s)",
            self.__changelog_file_path,
            version or "<all>",
        )

        content = self.get(version=version)
        yaml_data = [value for _, value in content.items()]
        result: str = yaml.safe_dump(yaml_data, sort_keys=False, allow_unicode=True)
        return result

    def write_to_html(self, file: str, version: Optional[str] = None) -> None:
        """Stores the Changelog file in HTML format."""
        logger.info(
            "Writing HTML export for %s to %s", self.__changelog_file_path, file
        )

        with Path(file).open("w", encoding="UTF-8") as file_handle:
            file_handle.write(self.to_html(version=version))

    def to_html(self, version: Optional[str] = None) -> str:
        """Returns the Changelog file rendered as HTML."""
        logger.log(
            VERBOSE,
            "Rendering HTML export for %s (%s)",
            self.__changelog_file_path,
            version or "<all>",
        )

        content = self.get(version=version)
        parts: list[str] = [
            "<!DOCTYPE html>",
            '<html><head><meta charset="utf-8"><title>Changelog</title></head>',
            "<body>",
            "<h1>Changelog</h1>",
        ]
        for ver, release in content.items():
            metadata = release.get("metadata", {}) if isinstance(release, dict) else {}
            release_date = metadata.get("release_date")
            heading = html.escape(str(ver))
            if release_date:
                heading += f" - {html.escape(str(release_date))}"
            parts.append(f"<h2>{heading}</h2>")
            for change_type, category in CATEGORIES.items():
                entries = (
                    release.get(change_type) if isinstance(release, dict) else None
                )
                if not entries:
                    continue
                parts.append(f"<h3>{html.escape(category.title)}</h3>")
                parts.append("<ul>")
                for entry in entries:
                    parts.append(f"<li>{html.escape(str(entry))}</li>")
                parts.append("</ul>")
        parts.append("</body></html>")
        return "\n".join(parts) + "\n"

    def write_to_file(self) -> None:
        """Updates CHANGELOG.md based on the Keep a Changelog standard"""
        logger.info("Writing changelog file %s", self.__changelog_file_path)

        with Path(self.__changelog_file_path).open(
            "w", encoding="UTF-8"
        ) as file_handle:
            file_handle.write(str(self))

    def __has_only_unreleased_version(self) -> bool:
        """Returns True when the changelog only contains an Unreleased version"""
        return UNRELEASED_ENTRY in self.__changelog and len(self.__changelog) == 1

    def __str__(self) -> str:
        """String representation"""

        rendered = str(keepachangelog.from_dict(self.__changelog))
        return self.__render_preamble(rendered)

    def __render_preamble(self, rendered: str) -> str:
        if self.__versioning_scheme == "semver":
            return rendered

        logger.log(
            VERBOSE,
            "Rewriting Keep a Changelog preamble for versioning scheme %s",
            self.__versioning_scheme,
        )
        replacement = (
            "and this project adheres to "
            f"{get_versioning_markdown(self.__versioning_scheme)}."
        )
        semver_preamble = (
            r"and this project adheres to "
            r"\[Semantic Versioning\]\(https://semver\.org/spec/v2\.0\.0\.html\)\."
        )
        return re.sub(
            semver_preamble,
            replacement,
            rendered,
            count=1,
        )
