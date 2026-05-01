# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog"""

import json
import os
from collections import OrderedDict
from datetime import datetime
from typing import Any, Dict, Mapping, Optional

import keepachangelog  # type: ignore
from semantic_version import Version  # type: ignore

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import (CATEGORIES, DEFAULT_CHANGELOG_FILE,
                                           UNRELEASED_ENTRY, VersionCore)

INITIAL_VERSION = Version("0.0.1")


class Changelog:
    """Changelog"""

    def __init__(
        self,
        file_path: str = DEFAULT_CHANGELOG_FILE,
        changelog: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Constructor"""
        self.__changelog_file_path = file_path
        self.__changelog = changelog if changelog else {}

    def get_file_path(self) -> str:
        """Returns the path to the changelog file"""
        return self.__changelog_file_path

    def add(self, change_type: str, message: str) -> None:
        """Adds a new message to the specified change identifier in the Changelog"""

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

    def exists(self) -> bool:
        """Verifies if the Changelog file exists"""
        return os.path.isfile(self.__changelog_file_path)

    def get(self, version: Optional[str] = None) -> Mapping[str, Any]:
        """Returns the specified version"""

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
            raise logging.Error(message=_message) from exc_info

        if str(_version) in self.get().keys():
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
            changelog_in: Dict[str, Any], new_version: Version
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

    def version(self) -> Version:
        """Returns the last released version"""
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

        if self.__has_only_unreleased_version():
            return INITIAL_VERSION

        def determine_version(unreleased: Mapping[str, Any], prev_version: Version) -> Version:
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

        with open(file, "w", encoding="UTF-8") as file_handle:
            file_handle.write(self.to_json(version=version))

    def to_json(self, version: Optional[str] = None) -> str:
        """Returns the Changelog file in JSON format"""

        content = self.get(version=version)
        json_data = [value for _, value in content.items()]
        return json.dumps(json_data, indent=4)

    def write_to_file(self) -> None:
        """Updates CHANGELOG.md based on the Keep a Changelog standard"""

        with open(self.__changelog_file_path, "w", encoding="UTF-8") as file_handle:
            file_handle.write(str(self))

    def __has_only_unreleased_version(self) -> bool:
        """Returns True when the changelog only contains an Unreleased version"""
        return UNRELEASED_ENTRY in self.__changelog and len(self.__changelog) == 1

    def __str__(self) -> str:
        """String representation"""

        return str(keepachangelog.from_dict(self.__changelog))
