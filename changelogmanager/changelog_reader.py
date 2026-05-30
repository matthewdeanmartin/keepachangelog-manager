# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog Reader"""

import datetime
import difflib
import re
from collections import OrderedDict
from collections.abc import Generator, Mapping, Sequence
from pathlib import Path
from typing import Any, Optional

import keepachangelog  # type: ignore
from semantic_version import Version  # type: ignore

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import (
    DEFAULT_CHANGELOG_FILE,
    TYPES_OF_CHANGE,
    UNRELEASED_ENTRY,
)
from changelogmanager.runtime_logging import VERBOSE, get_logger

PREAMBLE_KEYWORDS = ("keep a changelog", "semantic versioning")
logger = get_logger(__name__)


class ChangelogReader:
    """Changelog Reader"""

    def __init__(
        self,
        file_path: str = DEFAULT_CHANGELOG_FILE,
        enforce_preamble: bool = False,
        preamble_keywords: Optional[Sequence[str]] = None,
    ) -> None:
        """Constructor"""

        self.__file_path = file_path
        self.__enforce_preamble = enforce_preamble
        self.__preamble_keywords = tuple(
            keyword.lower() for keyword in (preamble_keywords or PREAMBLE_KEYWORDS)
        )
        logger.log(
            VERBOSE,
            "Initialized changelog reader for %s (enforce_preamble=%s)",
            self.__file_path,
            self.__enforce_preamble,
        )

    def read(self) -> dict[str, Any]:
        """Reads the CHANGELOG.md file and checks for validity"""
        logger.info("Reading changelog from %s", self.__file_path)

        if not Path(self.__file_path).is_file():
            logger.warning(
                "Changelog file %s does not exist; returning empty data",
                self.__file_path,
            )
            return {}

        errors = self.validate_layout()

        if errors:
            logger.error(
                "Detected %d layout errors while reading %s", errors, self.__file_path
            )
            raise logging.Error(
                file_path=self.__file_path,
                message=f"{errors} errors detected in the layout",
            )

        changelog: dict[str, Any] = keepachangelog.to_dict(
            self.__file_path, show_unreleased=True
        )

        self.validate_contents(changelog)
        logger.info(
            "Loaded changelog %s with %d version entries",
            self.__file_path,
            len(changelog),
        )

        return changelog

    def __validate_change_heading(
        self, line_number: int, line: str, depth: int, content: str
    ) -> Generator[logging.Error, None, None]:
        """Check if acceptable keywords are present"""

        accepted_types = [change_type.title() for change_type in TYPES_OF_CHANGE]

        if content not in accepted_types:
            friendly_types = ", ".join(accepted_types)

            # Offer a "did you mean" suggestion for near-miss spellings/casing.
            suggestion = self.__closest_change_type(content)
            expectations = (
                f"Did you mean '### {suggestion}'?"
                if suggestion
                else f"Use one of: {friendly_types}"
            )

            yield logging.Error(
                file_path=self.__file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(start=depth + 2, range=len(content)),
                message=(
                    f"Incompatible change type provided, MUST be one of: {friendly_types}"
                ),
                expectations=expectations,
            )

    @staticmethod
    def __closest_change_type(content: str) -> Optional[str]:
        """Return the canonical change type that ``content`` most likely meant.

        Catches casing mistakes (``ADDED``) and minor typos (``Chnaged``) so we
        can show a "Did you mean ...?" hint. Returns ``None`` when nothing is
        close enough to confidently suggest.
        """

        accepted_types = [change_type.title() for change_type in TYPES_OF_CHANGE]

        # Exact match on lower-case handles casing-only mistakes.
        for candidate in accepted_types:
            if candidate.lower() == content.strip().lower():
                return candidate

        matches = difflib.get_close_matches(
            content.strip().lower(),
            [candidate.lower() for candidate in accepted_types],
            n=1,
            cutoff=0.7,
        )
        if matches:
            return matches[0].title()
        return None

    def __validate_version_heading(
        self, line_number: int, line: str, depth: int, content: str
    ) -> Generator[logging.Error, None, None]:
        # Check if version tag ([x.y.z]) is present
        match = re.compile(r"\[(.*)\](.*)").match(content)

        if not match:
            # A very common mistake: writing a change section ("## Changed")
            # with two hashes instead of three. Detect that and point the user
            # at the real fix instead of the confusing "Missing version tag".
            change_type = self.__closest_change_type(content)
            if change_type:
                yield logging.Error(
                    file_path=self.__file_path,
                    line=line,
                    line_number=logging.Range(start=line_number),
                    column_number=logging.Range(start=1, range=depth),
                    message=(
                        f"'{content}' is a change section but is at heading "
                        f"level {depth} (##); change sections MUST be level 3 (###)"
                    ),
                    expectations=f"Use '### {change_type}' instead of '## {content}'",
                )
                return

            yield logging.Error(
                file_path=self.__file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(start=depth + 2, range=len(content)),
                message="Missing version tag",
                expectations="Use the form '## [1.2.3] - 2022-12-31' or '## [Unreleased]'",
            )
            return

        version_str = match.group(1)

        if version_str == UNRELEASED_ENTRY.title():
            return

        # Verify that the version is valid SemVer syntax
        try:
            version = Version(version_str)
        except ValueError:
            yield logging.Error(
                file_path=self.__file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(
                    start=line.find("[") + 2, range=len(version_str)
                ),
                message=f"Incompatible version '{version_str}' specified, MUST be SemVer compliant",
                expectations="Use MAJOR.MINOR.PATCH, e.g. '1.2.3' (see https://semver.org)",
            )
            return

        # Validate the availability of meta data (' - ')
        match = re.compile(r" - (.*)").match(match.group(2))

        if not match:
            yield logging.Error(
                file_path=self.__file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(
                    start=line.find("]") + 3,
                ),
                message=f"Missing metadata ('-') for release version '{version}'",
                expectations=f"Add a release date, e.g. '## [{version}] - 2022-12-31'",
            )
            return

        release_date = match.group(1)

        # Verify that a date is present ('####-##-##')
        match = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}").match(release_date)

        if not match:
            yield logging.Error(
                file_path=self.__file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(
                    start=line.find(" - ") + 4,
                ),
                message=(
                    f"Incompatible release date for release version '{version}', MUST be 'yyyy-mm-dd'"  # pylint: disable=C0301
                ),
                expectations=f"Use an ISO date, e.g. '## [{version}] - 2022-12-31'",
            )
            return

        # Verify that the date is according to ISO standard
        try:
            datetime.datetime.strptime(release_date, "%Y-%m-%d")
        except ValueError:
            yield logging.Error(
                file_path=self.__file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(
                    start=line.find(" - ") + 4, range=len(release_date)
                ),
                message=(
                    f"Incompatible release date for release version '{version}', MUST be 'yyyy-mm-dd'"  # pylint: disable=C0301
                ),
                expectations=(
                    f"'{release_date}' is not a real calendar date; "
                    "use a valid ISO date like '2022-12-31'"
                ),
            )

    def __validate_heading(
        self, line_number: int, line: str
    ) -> Generator[logging.Error, None, None]:
        match = re.compile(r"^(#{1,6}) (.*)").match(line)

        if not match:
            # Not a header, no validation required.
            return

        depth = len(match.group(1))
        content = match.group(2)

        # KeepaChangelog only allows for three levels of depth
        if depth > 3:
            yield logging.Error(
                file_path=self.__file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(start=line.find("#") + 4, range=depth - 3),
                message="Heading depth is too high, MUST be less or equal to 3",
                expectations=(
                    "Keep a Changelog uses '# Changelog', "
                    "'## [version] - date', and '### Change type' only"
                ),
            )
            return

        # Validate the format: ## [1.2.3] - 2022-12-31
        if depth == 2:
            yield from self.__validate_version_heading(
                line_number=line_number, line=line, depth=depth, content=content
            )

        # Validate the format: ### Added
        if depth == 3:
            yield from self.__validate_change_heading(
                line_number=line_number, line=line, depth=depth, content=content
            )

    def __validate_entry(
        self, line_number: int, line: str
    ) -> Generator[logging.Error, None, None]:
        match = re.compile(r"(\s*)[-+*] (.*)").match(line)

        if not match:
            # Not an entry, no validation required.
            return

        indent = match.group(1)
        entry = match.group(2)

        if indent:
            yield logging.Error(
                file_path=self.__file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(start=1, range=len(indent)),
                message="Sub-lists are not permitted in changelog entries",
                expectations=(
                    "Remove the leading indentation so the entry is a "
                    "top-level '- ' bullet"
                ),
            )
            return

        rules = [
            {
                "pattern": r"^(#{1,6}) .*",
                "error": "Block quotes are not permitted in changelog entries",
                "hint": "Remove the heading marker; entries are plain '- ' bullets",
            },
            {
                "pattern": r"^([0-9]+\.) .*",
                "error": "Numbered lists are not permitted in changelog entries",
                "hint": "Use a '- ' bullet instead of a numbered '1.' list",
            },
            {
                "pattern": r"^([+*-]) .*",
                "error": "Sub-lists are not permitted in changelog entries",
                "hint": "Use a single '- ' bullet per entry; no nested bullets",
            },
            {
                "pattern": r"^([>]+) .*",
                "error": "Block quotes are not permitted in changelog entries",
                "hint": "Remove the '>' block-quote marker; entries are plain text",
            },
        ]

        for rule in rules:
            match = re.compile(rule["pattern"]).match(entry)
            if match:
                yield logging.Error(
                    file_path=self.__file_path,
                    line=line,
                    line_number=logging.Range(start=line_number),
                    column_number=logging.Range(start=3, range=len(match.group(1))),
                    message=rule["error"],
                    expectations=rule["hint"],
                )

    def __validate_preamble(self) -> list[logging.Error]:
        """Optional check that the first non-blank lines mention KaC + SemVer."""

        if not self.__enforce_preamble:
            logger.log(VERBOSE, "Skipping preamble validation for %s", self.__file_path)
            return []

        try:
            content = Path(self.__file_path).read_text(encoding="UTF-8")
        except OSError:
            logger.warning(
                "Unable to read %s while validating preamble", self.__file_path
            )
            return []

        head = content.lower()[:1024]
        missing = [kw for kw in self.__preamble_keywords if kw not in head]
        if not missing:
            logger.log(VERBOSE, "Preamble validation passed for %s", self.__file_path)
            return []
        logger.warning(
            "Preamble validation failed for %s; missing %s",
            self.__file_path,
            ", ".join(missing),
        )
        return [
            logging.Error(
                file_path=self.__file_path,
                message=(
                    "Missing canonical Keep a Changelog preamble; "
                    f"expected references to: {', '.join(missing)}"
                ),
            )
        ]

    def validate_layout(self) -> int:
        """Validates the changelog file according to KeepAChangelog conventions"""

        logger.info("Validating changelog layout for %s", self.__file_path)
        line_number = 1
        errors: list[logging.Error] = []
        with Path(self.__file_path).open(encoding="UTF-8") as file_handle:
            for line in file_handle:
                errors.extend(list(self.__validate_heading(line_number, line)))
                errors.extend(list(self.__validate_entry(line_number, line)))
                line_number += 1

        errors.extend(self.__validate_preamble())

        for error in errors:
            error.report()

        logger.info(
            "Finished layout validation for %s with %d error(s)",
            self.__file_path,
            len(errors),
        )
        return len(errors)

    def autofix_text(self) -> tuple[str, list[str]]:
        """Returns raw Markdown with safe layout fixes applied.

        These fixes run before parsing, so they only handle line-local changes
        that preserve the intended changelog structure.
        """

        path = Path(self.__file_path)
        text = path.read_text(encoding="UTF-8")
        fixed_lines: list[str] = []
        applied: list[str] = []

        for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
            fixed, line_applied = self.__autofix_line(line)
            fixed_lines.append(fixed)
            for message in line_applied:
                applied.append(f"Line {line_number}: {message}")

        fixed_text = "".join(fixed_lines)
        if self.__enforce_preamble:
            fixed_text, preamble_applied = self.__autofix_preamble(fixed_text)
            applied.extend(preamble_applied)

        logger.info(
            "Raw-text autofix for %s produced %d change(s)",
            self.__file_path,
            len(applied),
        )
        return fixed_text, applied

    def __autofix_line(self, line: str) -> tuple[str, list[str]]:
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        applied: list[str] = []

        heading = re.compile(r"^(#{1,6}) (.*)$").match(body)
        if heading:
            hashes = heading.group(1)
            content = heading.group(2)
            depth = len(hashes)

            if depth == 2:
                change_type = self.__closest_change_type(content)
                if change_type:
                    return f"### {change_type}{newline}", [
                        f"Changed '## {content}' to '### {change_type}'"
                    ]

                fixed_content, version_applied = self.__autofix_version_content(
                    content
                )
                if version_applied:
                    return f"## {fixed_content}{newline}", version_applied

            if depth == 3:
                change_type = self.__closest_change_type(content)
                if change_type and content != change_type:
                    return f"### {change_type}{newline}", [
                        f"Changed '### {content}' to '### {change_type}'"
                    ]

            return line, []

        entry = re.compile(r"^(\s*)[-+*] (.*)$").match(body)
        if not entry:
            return line, []

        indent = entry.group(1)
        entry_text = entry.group(2)
        if indent:
            applied.append("Removed leading indentation from changelog entry")

        fixed_entry = entry_text
        for pattern, message in (
            (r"^#{1,6}\s+(.*)$", "Removed heading marker from changelog entry"),
            (r"^[0-9]+\.\s+(.*)$", "Removed numbered-list marker from changelog entry"),
            (r"^[-+*]\s+(.*)$", "Removed nested-list marker from changelog entry"),
            (r"^>+\s+(.*)$", "Removed block-quote marker from changelog entry"),
        ):
            marker = re.compile(pattern).match(fixed_entry)
            if marker:
                fixed_entry = marker.group(1)
                applied.append(message)
                break

        if not applied:
            return line, []
        return f"- {fixed_entry}{newline}", applied

    def __autofix_version_content(self, content: str) -> tuple[str, list[str]]:
        fixed = content.strip()
        applied: list[str] = []

        unreleased_match = re.compile(r"^unreleased$", re.IGNORECASE).match(fixed)
        if unreleased_match:
            return f"[{UNRELEASED_ENTRY.title()}]", [
                "Added brackets around Unreleased heading"
            ]

        bare_version = re.compile(
            r"^(v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)(.*)$"
        ).match(fixed)
        if bare_version:
            fixed = f"[{bare_version.group(1)}]{bare_version.group(2)}"
            applied.append("Added brackets around release version")

        bracketed = re.compile(r"^\[(v?\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?)\](.*)$").match(
            fixed
        )
        if not bracketed:
            return content, []

        version = bracketed.group(1)
        suffix = bracketed.group(2).strip()
        if version.startswith("v"):
            version = version[1:]
            applied.append("Removed leading 'v' from release version")

        if suffix and not suffix.startswith("- "):
            suffix = f"- {suffix.lstrip('-').strip()}"
            applied.append("Added metadata '-' separator to release heading")

        date_match = re.compile(r"^- (\d{4})[/.](\d{2})[/.](\d{2})$").match(suffix)
        if date_match:
            candidate = "- " + "-".join(date_match.groups())
            try:
                datetime.datetime.strptime(candidate[2:], "%Y-%m-%d")
            except ValueError:
                pass
            else:
                suffix = candidate
                applied.append("Normalized release date separators")

        fixed = f"[{version}]"
        if suffix:
            fixed = f"{fixed} {suffix}"

        if not applied:
            return content, []
        return fixed, applied

    def __autofix_preamble(self, text: str) -> tuple[str, list[str]]:
        head = text.lower()[:1024]
        missing = [kw for kw in self.__preamble_keywords if kw not in head]
        if not missing:
            return text, []

        keywords = " and ".join(keyword.title() for keyword in self.__preamble_keywords)
        preamble = f"All notable changes follow {keywords}.\n"
        lines = text.splitlines(keepends=True)
        for index, line in enumerate(lines):
            if line.strip().lower() == "# changelog":
                insert_at = index + 1
                if insert_at < len(lines) and lines[insert_at].strip():
                    lines.insert(insert_at, "\n")
                    insert_at += 1
                lines.insert(insert_at, preamble)
                return "".join(lines), ["Inserted canonical changelog preamble"]

        return preamble + "\n" + text, ["Inserted canonical changelog preamble"]

    def validate_contents(self, changelog: Mapping[str, Any]) -> None:
        """Validates the contents of the CHANGELOG.md file"""
        logger.info("Validating changelog contents for %s", self.__file_path)

        is_first_entry = True
        prev_version: Optional[Version] = None

        for version, release in changelog.items():
            if version == UNRELEASED_ENTRY:
                if not is_first_entry:
                    logging.Warning(
                        file_path=self.__file_path,
                        message="Unreleased version should be on top of the CHANGELOG.md file",
                    ).report()
            else:
                new_version = Version(version)
                if prev_version and prev_version <= new_version:
                    logging.Warning(
                        file_path=self.__file_path,
                        message=(
                            f"Versions are incorrectly ordered: "
                            f"{prev_version} -> {new_version}"
                        ),
                    ).report()

                prev_version = new_version

            self.__validate_release_contents(version, release)

            is_first_entry = False

    def __validate_release_contents(
        self, version: str, release: Mapping[str, Any]
    ) -> None:
        """Validates per-release content: empty sections + duplicate entries."""

        if not isinstance(release, Mapping):
            logger.warning(
                "Skipping non-mapping release payload for version %s in %s",
                version,
                self.__file_path,
            )
            return

        change_sections = [
            (change_type, entries)
            for change_type, entries in release.items()
            if change_type != "metadata"
        ]

        # Empty version (no change sections at all).
        if not change_sections:
            logger.warning(
                "Version %s has no change sections in %s", version, self.__file_path
            )
            logging.Warning(
                file_path=self.__file_path,
                message=f"Version '{version}' has no change entries",
            ).report()
            return

        for change_type, entries in change_sections:
            if not isinstance(entries, list) or len(entries) == 0:
                logger.warning(
                    "Version %s has an empty '%s' section in %s",
                    version,
                    change_type,
                    self.__file_path,
                )
                logging.Warning(
                    file_path=self.__file_path,
                    message=(f"Version '{version}' has empty '{change_type}' section"),
                ).report()
                continue

            seen: dict[str, int] = {}
            for entry in entries:
                key = str(entry).strip().lower()
                seen[key] = seen.get(key, 0) + 1
            for key, count in seen.items():
                if count > 1:
                    logger.warning(
                        "Version %s has duplicate '%s' entries in %s",
                        version,
                        change_type,
                        self.__file_path,
                    )
                    logging.Warning(
                        file_path=self.__file_path,
                        message=(
                            f"Duplicate entry under '{change_type}' in version "
                            f"'{version}' ({count}x): '{key}'"
                        ),
                    ).report()

    def autofix(  # pylint: disable=too-many-locals,too-many-branches
        self, changelog: Mapping[str, Any]
    ) -> tuple[dict[str, Any], list[str]]:
        """Returns a normalised copy of ``changelog`` plus a list of changes applied.

        Currently fixes:
          * Lowercases unrecognised-cased change-type keys (e.g. ``Added`` -> ``added``).
          * Removes empty change-type sections.
          * Re-sorts releases so the newest released version comes first
            (preserving the [Unreleased] entry at the top).
          * De-duplicates identical entries within a section.
        """

        logger.info("Autofixing changelog data for %s", self.__file_path)
        applied: list[str] = []
        fixed: OrderedDict[str, Any] = OrderedDict()

        for version, release in changelog.items():
            if not isinstance(release, dict):
                fixed[version] = release
                continue

            new_release: dict[str, Any] = {}
            for change_type, entries in release.items():
                if change_type == "metadata":
                    new_release[change_type] = entries
                    continue

                canonical = change_type.lower()
                if canonical != change_type:
                    applied.append(
                        f"Renamed change type '{change_type}' -> '{canonical}' "
                        f"in version '{version}'"
                    )

                if canonical not in TYPES_OF_CHANGE:
                    new_release[canonical] = entries
                    continue

                if not isinstance(entries, list) or not entries:
                    applied.append(
                        f"Dropped empty '{canonical}' section in version '{version}'"
                    )
                    continue

                seen: set[str] = set()
                deduped: list[Any] = []
                for entry in entries:
                    key = str(entry).strip().lower()
                    if key in seen:
                        applied.append(
                            f"Removed duplicate entry under '{canonical}' "
                            f"in version '{version}': '{entry}'"
                        )
                        continue
                    seen.add(key)
                    deduped.append(entry)

                # Merge if both 'Added' and 'added' existed (canonical wins)
                if canonical in new_release and isinstance(
                    new_release[canonical], list
                ):
                    new_release[canonical].extend(deduped)
                else:
                    new_release[canonical] = deduped

            fixed[version] = new_release

        # Re-sort: keep [Unreleased] first, then released versions in descending order.
        unreleased = fixed.pop(UNRELEASED_ENTRY, None)
        try:
            sorted_releases = sorted(
                fixed.items(),
                key=lambda item: Version(item[0]),
                reverse=True,
            )
        except ValueError:
            sorted_releases = list(fixed.items())

        result: OrderedDict[str, Any] = OrderedDict()
        if unreleased is not None:
            result[UNRELEASED_ENTRY] = unreleased
        prev_keys = list(fixed.keys())
        new_keys = [key for key, _ in sorted_releases]
        if prev_keys != new_keys:
            applied.append("Reordered released versions in descending semver order")
        for key, value in sorted_releases:
            result[key] = value

        logger.info(
            "Autofix for %s produced %d change(s)",
            self.__file_path,
            len(applied),
        )
        return dict(result), applied
