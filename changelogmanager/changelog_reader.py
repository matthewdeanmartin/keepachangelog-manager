# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Changelog Reader"""

from __future__ import annotations

import datetime
import difflib
from collections import OrderedDict
from collections.abc import Generator, Mapping, Sequence
from pathlib import Path
from typing import Any, cast

import changelogmanager.llvm_diagnostics as logging
from changelogmanager import _re_compat as re2
from changelogmanager.change_types import (
    DEFAULT_CHANGELOG_FILE,
    TYPES_OF_CHANGE,
    UNRELEASED_ENTRY,
)
from changelogmanager.runtime_logging import VERBOSE, get_logger
from changelogmanager.schema_validation import validate_changelog_mapping
from changelogmanager.vendor import keepachangelog
from changelogmanager.versioning import (
    detect_versioning_scheme_from_file,
    normalize_scheme,
    parse_version,
    version_scheme_expectation,
    version_scheme_label,
)

PREAMBLE_KEYWORDS = ("keep a changelog", "semantic versioning")
logger = get_logger(__name__)

# Pre-compiled regexes for performance using re2
VERSION_TAG_RE = re2.compile(r"\[(.*)\](.*)")
METADATA_RE = re2.compile(r" - (.*)")
DATE_RE = re2.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
HEADING_RE = re2.compile(r"^(#{1,6}) (.*)")
ENTRY_RE = re2.compile(r"(\s*)[-+*] (.*)")
HEADING_BODY_RE = re2.compile(r"^(#{1,6}) (.*)$")
ENTRY_BODY_RE = re2.compile(r"^(\s*)[-+*] (.*)$")
UNRELEASED_CASE_RE = re2.compile(r"(?i)^unreleased$")
BRACKETED_UNRELEASED_RE = re2.compile(r"(?i)^\[unreleased\]$")
VERSION_PATTERN_STR = r"v?[0-9A-Za-z]+(?:[._!+-]?[0-9A-Za-z]+)*"
BARE_VERSION_RE = re2.compile(rf"^({VERSION_PATTERN_STR})(.*)$")
BRACKETED_VERSION_RE = re2.compile(rf"^\[({VERSION_PATTERN_STR})\](.*)$")
NORMALIZED_DATE_RE = re2.compile(r"^- (\d{4})[/.](\d{2})[/.](\d{2})$")

# Matches a "compare" style version link, e.g.
#   https://github.com/acme/proj/compare/v0.1.0...v0.2.0
#   https://gitlab.com/acme/proj/-/compare/0.1.0...0.2.0
# Capturing: (base)(prefix)(from-version)(...)(prefix)(to-version)
COMPARE_LINK_RE = re2.compile(
    r"^(?P<base>.*?/(?:-/)?compare/)"
    r"(?P<from_prefix>v)?(?P<from_ver>.+?)"
    r"(?P<sep>\.\.\.?|%5[Bb]?\.\.\.)"
    r"(?P<to_prefix>v)?(?P<to_ver>.+?)$"
)
# Matches a GitHub "releases/tag" style link, e.g.
#   https://github.com/acme/proj/releases/tag/v0.1.0
TAG_LINK_RE = re2.compile(r"^(?P<base>.*?/releases/tag/)(?P<prefix>v)?(?P<ver>.+?)$")


def derive_unreleased_url(
    released_links: Sequence[tuple[str, str]], latest_version: str
) -> str | None:
    """Derive an ``[Unreleased]:`` compare URL from existing released link refs.

    ``released_links`` is an ordered (newest-first) sequence of
    ``(version, url)`` pairs taken from the released versions' ``metadata['url']``.
    ``latest_version`` is the most-recent *released* version string (no ``v`` prefix).

    The host/repo base, the compare-URL shape, and the tag prefix (e.g. ``v``) are
    all detected from the existing links instead of using a hardcoded template, so
    a hand-curated ``v``-prefixed convention is preserved. The unreleased target is
    always ``HEAD`` (branch-agnostic). Returns ``None`` when no usable link shape is
    found (e.g. a brand-new changelog with no released link refs).
    """

    for _version, url in released_links:
        compare = COMPARE_LINK_RE.match(url)
        if compare:
            base = compare.group("base")
            prefix = compare.group("to_prefix") or compare.group("from_prefix") or ""
            return f"{base}{prefix}{latest_version}...HEAD"

    # No compare link available; fall back to a tag link's base + prefix to
    # synthesise a compare URL on the same host/repo.
    for _version, url in released_links:
        tag = TAG_LINK_RE.match(url)
        if tag:
            prefix = tag.group("prefix") or ""
            # …/releases/tag/<x>  ->  …/compare/<vlatest>...HEAD
            base = tag.group("base").rsplit("/releases/tag/", 1)[0]
            return f"{base}/compare/{prefix}{latest_version}...HEAD"

    return None


ENTRY_RULES = [
    {
        "pattern": re2.compile(r"^(#{1,6}) .*"),
        "error": "Block quotes are not permitted in changelog entries",
        "hint": "Remove the heading marker; entries are plain '- ' bullets",
    },
    {
        "pattern": re2.compile(r"^([0-9]+\.) .*"),
        "error": "Numbered lists are not permitted in changelog entries",
        "hint": "Use a '- ' bullet instead of a numbered '1.' list",
    },
    {
        "pattern": re2.compile(r"^([+*-]) .*"),
        "error": "Sub-lists are not permitted in changelog entries",
        "hint": "Use a single '- ' bullet per entry; no nested bullets",
    },
    {
        "pattern": re2.compile(r"^([>]+) .*"),
        "error": "Block quotes are not permitted in changelog entries",
        "hint": "Remove the '>' block-quote marker; entries are plain text",
    },
]

AUTOFIX_PATTERNS = [
    (re2.compile(r"^#{1,6}\s+(.*)$"), "Removed heading marker from changelog entry"),
    (
        re2.compile(r"^[0-9]+\.\s+(.*)$"),
        "Removed numbered-list marker from changelog entry",
    ),
    (re2.compile(r"^[-+*]\s+(.*)$"), "Removed nested-list marker from changelog entry"),
    (re2.compile(r"^>+\s+(.*)$"), "Removed block-quote marker from changelog entry"),
]


class ChangelogReader:
    """Changelog Reader"""

    def __init__(
        self,
        file_path: str = DEFAULT_CHANGELOG_FILE,
        enforce_preamble: bool = False,
        preamble_keywords: Sequence[str] | None = None,
        versioning_scheme: str | None = None,
    ) -> None:
        """Constructor"""

        self.file_path = file_path
        self.enforce_preamble = enforce_preamble
        self.versioning_scheme_explicit = versioning_scheme is not None
        self.versioning_scheme = normalize_scheme(versioning_scheme)
        self.preamble_keywords = tuple(
            keyword.lower() for keyword in (preamble_keywords or PREAMBLE_KEYWORDS)
        )
        logger.log(
            VERBOSE,
            "Initialized changelog reader for %s (enforce_preamble=%s)",
            self.file_path,
            self.enforce_preamble,
        )

    def read(self, text: str | None = None) -> dict[str, Any]:
        """Reads the CHANGELOG.md file and checks for validity.

        Pass ``text`` to avoid a second disk read when the caller already holds
        the file contents (transaction-local caching).
        """
        logger.info("Reading changelog from %s", self.file_path)

        if text is None:
            if not Path(self.file_path).is_file():
                logger.warning(
                    "Changelog file %s does not exist; returning empty data",
                    self.file_path,
                )
                return {}
            text = Path(self.file_path).read_text(encoding="UTF-8")
        elif not text and not Path(self.file_path).is_file():
            return {}

        errors = self.validate_layout(text=text)

        if errors:
            logger.error(
                "Detected %d layout errors while reading %s", errors, self.file_path
            )
            raise logging.Error(
                file_path=self.file_path,
                message=f"{errors} errors detected in the layout",
            )

        changelog: dict[str, Any] = keepachangelog.to_dict(
            text.splitlines(keepends=True), show_unreleased=True
        )

        self.validate_contents(changelog)
        validate_changelog_mapping(changelog, file_path=self.file_path)
        logger.info(
            "Loaded changelog %s with %d version entries",
            self.file_path,
            len(changelog),
        )

        return changelog

    def validate_change_heading(
        self, line_number: int, line: str, depth: int, content: str
    ) -> Generator[logging.Error, None, None]:
        """Check if acceptable keywords are present"""

        accepted_types = [change_type.title() for change_type in TYPES_OF_CHANGE]

        if content not in accepted_types:
            friendly_types = ", ".join(accepted_types)

            # Offer a "did you mean" suggestion for near-miss spellings/casing.
            suggestion = self.closest_change_type(content)
            expectations = (
                f"Did you mean '### {suggestion}'?"
                if suggestion
                else f"Use one of: {friendly_types}"
            )

            yield logging.Error(
                file_path=self.file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(start=depth + 2, range=len(content)),
                message=(
                    f"Incompatible change type provided, MUST be one of: {friendly_types}"
                ),
                expectations=expectations,
            )

    @staticmethod
    def closest_change_type(content: str) -> str | None:
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

    def validate_version_heading(
        self, line_number: int, line: str, depth: int, content: str
    ) -> Generator[logging.Error, None, None]:
        # Check if version tag ([x.y.z]) is present
        match = VERSION_TAG_RE.match(content)

        if not match:
            # A very common mistake: writing a change section ("## Changed")
            # with two hashes instead of three. Detect that and point the user
            # at the real fix instead of the confusing "Missing version tag".
            change_type = self.closest_change_type(content)
            if change_type:
                yield logging.Error(
                    file_path=self.file_path,
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
                file_path=self.file_path,
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

        # Verify that the version is valid for the configured versioning scheme.
        try:
            version = parse_version(version_str, self.versioning_scheme)
        except ValueError:
            label = version_scheme_label(self.versioning_scheme)
            yield logging.Error(
                file_path=self.file_path,
                line=line,
                line_number=logging.Range(start=line_number),
                column_number=logging.Range(
                    start=line.find("[") + 2, range=len(version_str)
                ),
                message=f"Incompatible version '{version_str}' specified, MUST be {label} compliant",
                expectations=version_scheme_expectation(self.versioning_scheme),
            )
            return

        # Validate the availability of meta data (' - ')
        match = METADATA_RE.match(match.group(2))

        if not match:
            yield logging.Error(
                file_path=self.file_path,
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
        match = DATE_RE.match(release_date)

        if not match:
            yield logging.Error(
                file_path=self.file_path,
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
                file_path=self.file_path,
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

    def validate_heading(
        self, line_number: int, line: str
    ) -> Generator[logging.Error, None, None]:
        match = HEADING_RE.match(line)

        if not match:
            # Not a header, no validation required.
            return

        depth = len(match.group(1))
        content = match.group(2)

        # KeepaChangelog only allows for three levels of depth
        if depth > 3:
            yield logging.Error(
                file_path=self.file_path,
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
            yield from self.validate_version_heading(
                line_number=line_number, line=line, depth=depth, content=content
            )

        # Validate the format: ### Added
        if depth == 3:
            yield from self.validate_change_heading(
                line_number=line_number, line=line, depth=depth, content=content
            )

    def validate_entry(
        self, line_number: int, line: str
    ) -> Generator[logging.Error, None, None]:
        match = ENTRY_RE.match(line)

        if not match:
            # Not an entry, no validation required.
            return

        indent = match.group(1)
        entry = match.group(2)

        if indent:
            yield logging.Error(
                file_path=self.file_path,
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

        for rule in ENTRY_RULES:
            pattern = cast(Any, rule["pattern"])
            match = pattern.match(entry)
            if match:
                yield logging.Error(
                    file_path=self.file_path,
                    line=line,
                    line_number=logging.Range(start=line_number),
                    column_number=logging.Range(start=3, range=len(match.group(1))),
                    message=rule["error"],
                    expectations=rule["hint"],
                )

    def validate_preamble(self, text: str | None = None) -> list[logging.Error]:
        """Optional check that the first non-blank lines mention KaC + versioning."""

        if not self.enforce_preamble:
            logger.log(VERBOSE, "Skipping preamble validation for %s", self.file_path)
            return []

        if text is None:
            try:
                text = Path(self.file_path).read_text(encoding="UTF-8")
            except OSError:
                logger.warning(
                    "Unable to read %s while validating preamble", self.file_path
                )
                return []

        head = text.lower()[:1024]
        missing = [kw for kw in self.preamble_keywords if kw not in head]
        if not missing:
            logger.log(VERBOSE, "Preamble validation passed for %s", self.file_path)
            return []
        logger.warning(
            "Preamble validation failed for %s; missing %s",
            self.file_path,
            ", ".join(missing),
        )
        return [
            logging.Error(
                file_path=self.file_path,
                message=(
                    "Missing canonical Keep a Changelog preamble; "
                    f"expected references to: {', '.join(missing)}"
                ),
            )
        ]

    def validate_layout(self, text: str | None = None) -> int:
        """Validates the changelog file according to KeepAChangelog conventions.

        Pass ``text`` to skip the disk read when the caller already holds the
        file contents.
        """

        logger.info("Validating changelog layout for %s", self.file_path)
        if not self.versioning_scheme_explicit:
            detected = detect_versioning_scheme_from_file(self.file_path)
            if detected:
                self.versioning_scheme = detected
        line_number = 1
        errors: list[logging.Error] = []

        if text is None:
            lines: list[str] = (
                Path(self.file_path)
                .read_text(encoding="UTF-8")
                .splitlines(keepends=True)
            )
        else:
            lines = text.splitlines(keepends=True)

        for line in lines:
            errors.extend(list(self.validate_heading(line_number, line)))
            errors.extend(list(self.validate_entry(line_number, line)))
            line_number += 1

        errors.extend(self.validate_preamble(text=text))

        for error in errors:
            error.report()

        logger.info(
            "Finished layout validation for %s with %d error(s)",
            self.file_path,
            len(errors),
        )
        return len(errors)

    def count_layout_errors(self, text: str | None = None) -> int:
        """Returns the number of layout errors without reporting them.

        Used for before/after comparisons around write operations.
        """

        if not self.versioning_scheme_explicit:
            detected = detect_versioning_scheme_from_file(self.file_path)
            if detected:
                self.versioning_scheme = detected

        if text is None:
            try:
                raw = Path(self.file_path).read_text(encoding="UTF-8")
            except OSError:
                return 0
        else:
            raw = text
        lines = raw.splitlines(keepends=True)

        count = 0
        line_number = 1
        for line in lines:
            count += sum(1 for _ in self.validate_heading(line_number, line))
            count += sum(1 for _ in self.validate_entry(line_number, line))
            line_number += 1

        if self.enforce_preamble:
            head = raw.lower()[:1024]
            missing = [kw for kw in self.preamble_keywords if kw not in head]
            count += len(missing)

        return count

    def autofix_text(self, text: str | None = None) -> tuple[str, list[str]]:
        """Returns raw Markdown with safe layout fixes applied.

        Pass ``text`` to skip the disk read when the caller already holds the
        file contents. These fixes run before parsing, so they only handle
        line-local changes that preserve the intended changelog structure.
        """

        if text is None:
            text = Path(self.file_path).read_text(encoding="UTF-8")
        fixed_lines: list[str] = []
        applied: list[str] = []

        for line_number, line in enumerate(text.splitlines(keepends=True), start=1):
            fixed, line_applied = self.autofix_line(line)
            fixed_lines.append(fixed)
            for message in line_applied:
                applied.append(f"Line {line_number}: {message}")

        fixed_text = "".join(fixed_lines)
        if self.enforce_preamble:
            fixed_text, preamble_applied = self.autofix_preamble(fixed_text)
            applied.extend(preamble_applied)

        logger.info(
            "Raw-text autofix for %s produced %d change(s)",
            self.file_path,
            len(applied),
        )
        return fixed_text, applied

    def autofix_line(self, line: str) -> tuple[str, list[str]]:
        newline = "\n" if line.endswith("\n") else ""
        body = line[:-1] if newline else line
        applied: list[str] = []

        heading = HEADING_BODY_RE.match(body)
        if heading:
            hashes = heading.group(1)
            content = heading.group(2)
            depth = len(hashes)

            if depth == 2:
                change_type = self.closest_change_type(content)
                if change_type:
                    return f"### {change_type}{newline}", [
                        f"Changed '## {content}' to '### {change_type}'"
                    ]

                fixed_content, version_applied = self.autofix_version_content(content)
                if version_applied:
                    return f"## {fixed_content}{newline}", version_applied

            if depth == 3:
                change_type = self.closest_change_type(content)
                if change_type and content != change_type:
                    return f"### {change_type}{newline}", [
                        f"Changed '### {content}' to '### {change_type}'"
                    ]

            return line, []

        entry = ENTRY_BODY_RE.match(body)
        if not entry:
            return line, []

        indent = entry.group(1)
        entry_text = entry.group(2)
        if indent:
            applied.append("Removed leading indentation from changelog entry")

        fixed_entry = entry_text
        for pattern_re, message in AUTOFIX_PATTERNS:
            marker = pattern_re.match(fixed_entry)
            if marker:
                fixed_entry = marker.group(1)
                applied.append(message)
                break

        if not applied:
            return line, []
        return f"- {fixed_entry}{newline}", applied

    def autofix_version_content(self, content: str) -> tuple[str, list[str]]:
        fixed = content.strip()
        applied: list[str] = []

        unreleased_match = UNRELEASED_CASE_RE.match(fixed)
        if unreleased_match:
            return f"[{UNRELEASED_ENTRY.title()}]", [
                "Added brackets around Unreleased heading"
            ]

        bracketed_unreleased = BRACKETED_UNRELEASED_RE.match(fixed)
        if bracketed_unreleased and fixed != f"[{UNRELEASED_ENTRY.title()}]":
            return f"[{UNRELEASED_ENTRY.title()}]", [
                "Canonicalized Unreleased heading casing"
            ]

        bare_version = BARE_VERSION_RE.match(fixed)
        if bare_version:
            fixed = f"[{bare_version.group(1)}]{bare_version.group(2)}"
            applied.append("Added brackets around release version")

        bracketed = BRACKETED_VERSION_RE.match(fixed)
        if not bracketed:
            return content, []

        version = bracketed.group(1)
        suffix = bracketed.group(2).strip()
        if version.startswith("v") and self.versioning_scheme in {"semver", "pep440"}:
            version = version[1:]
            applied.append("Removed leading 'v' from release version")

        if suffix and not suffix.startswith("- "):
            suffix = f"- {suffix.lstrip('-').strip()}"
            applied.append("Added metadata '-' separator to release heading")

        date_match = NORMALIZED_DATE_RE.match(suffix)
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

    def autofix_preamble(self, text: str) -> tuple[str, list[str]]:
        head = text.lower()[:1024]
        missing = [kw for kw in self.preamble_keywords if kw not in head]
        if not missing:
            return text, []

        keywords = " and ".join(keyword.title() for keyword in self.preamble_keywords)
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
        logger.info("Validating changelog contents for %s", self.file_path)

        is_first_entry = True
        prev_version: Any | None = None

        for version, release in changelog.items():
            if version == UNRELEASED_ENTRY:
                if not is_first_entry:
                    logging.Warning(
                        file_path=self.file_path,
                        message="Unreleased version should be on top of the CHANGELOG.md file",
                    ).report()
            else:
                new_version = parse_version(version, self.versioning_scheme)
                if prev_version and prev_version <= new_version:
                    logging.Warning(
                        file_path=self.file_path,
                        message=(
                            f"Versions are incorrectly ordered: "
                            f"{prev_version} -> {new_version}"
                        ),
                    ).report()

                prev_version = new_version

            self.validate_release_contents(version, release)

            is_first_entry = False

        self.advise_missing_unreleased_url(changelog)

    def advise_missing_unreleased_url(self, changelog: Mapping[str, Any]) -> None:
        """Emit an actionable (non-error) advisory when ``[Unreleased]`` has entries
        and released versions carry link refs but no ``[Unreleased]:`` ref exists.

        Keep a Changelog treats version links as optional, so this never raises or
        changes the exit code — but strict consumers (upstream ``kacl-cli verify``)
        require the ref. The advisory names the exact line ``validate --fix`` would
        add so the user can satisfy those consumers.
        """

        backfill = self.unreleased_url_backfill(changelog)
        if backfill is None:
            return
        _version, url = backfill
        logging.Warning(
            file_path=self.file_path,
            message=(
                "[Unreleased] has entries and released versions are linked, but no "
                "[Unreleased] link reference was found. Strict consumers (e.g. "
                "'kacl-cli verify') require it. Run 'changelogmanager validate --fix' "
                f"to add: [Unreleased]: {url}"
            ),
        ).report()

    def strict_violations(
        self, changelog: Mapping[str, Any], text: str | None = None
    ) -> list[str]:
        """Returns strict-mode violations as human-readable messages.

        Strict mode promotes the strictest community-standard requirements to hard
        errors (the caller decides the exit code). Covered families:

          * **Version link references** — every released version, and a non-empty
            ``[Unreleased]``, must have a matching bottom-of-file link ref *when the
            changelog already links its versions* (i.e. ≥1 released version has a
            ``url``). A changelog that links no versions at all is left alone.
          * **Ordering / empty / duplicate** — the same conditions our default
            checks only *warn* about (versions out of order, ``[Unreleased]`` not on
            top, empty version/section, duplicate entries within a section).
          * **Canonical preamble** — the Keep a Changelog + SemVer preamble must be
            present (independent of the ``enforce_preamble`` config knob).
        """

        violations: list[str] = []

        # "Linked" if *any* version (released or Unreleased) carries a link ref:
        # a changelog that links some versions but not others is the gap strict
        # mode targets. A changelog that links nothing at all is left alone.
        versions_are_linked = any(
            isinstance(release, Mapping) and release.get("metadata", {}).get("url")
            for release in changelog.values()
        )

        # --- Version link references -------------------------------------
        if versions_are_linked:
            for version, release in changelog.items():
                if not isinstance(release, Mapping):
                    continue
                metadata = release.get("metadata", {})
                if metadata.get("url"):
                    continue
                has_entries = any(
                    change_type != "metadata" and isinstance(entries, list) and entries
                    for change_type, entries in release.items()
                )
                if version == UNRELEASED_ENTRY and not has_entries:
                    # An empty [Unreleased] needs no link.
                    continue
                label = version.capitalize() if version == UNRELEASED_ENTRY else version
                violations.append(
                    f"Version '{label}' is missing a link reference "
                    f"('[{label}]: ...'); strict mode requires every linked "
                    "version to have one"
                )

        # --- Ordering / empty / duplicate --------------------------------
        is_first_entry = True
        prev_version: Any | None = None
        for version, release in changelog.items():
            if version == UNRELEASED_ENTRY:
                if not is_first_entry:
                    violations.append(
                        "Unreleased version should be on top of the CHANGELOG.md file"
                    )
            else:
                new_version = parse_version(version, self.versioning_scheme)
                if prev_version and prev_version <= new_version:
                    violations.append(
                        f"Versions are incorrectly ordered: {prev_version} -> "
                        f"{new_version}"
                    )
                prev_version = new_version

            if isinstance(release, Mapping):
                violations.extend(self._release_content_violations(version, release))
            is_first_entry = False

        # --- Canonical preamble ------------------------------------------
        if text is None:
            try:
                text = Path(self.file_path).read_text(encoding="UTF-8")
            except OSError:
                text = ""
        head = text.lower()[:1024]
        if any(keyword not in head for keyword in PREAMBLE_KEYWORDS):
            violations.append(
                "Missing canonical Keep a Changelog preamble (references to "
                "Keep a Changelog and Semantic Versioning)"
            )

        return violations

    def _release_content_violations(
        self, version: str, release: Mapping[str, Any]
    ) -> list[str]:
        """Strict-mode mirror of ``validate_release_contents`` returning messages."""

        out: list[str] = []
        change_sections = [
            (change_type, entries)
            for change_type, entries in release.items()
            if change_type != "metadata"
        ]
        if not change_sections:
            if version != UNRELEASED_ENTRY:
                out.append(f"Version '{version}' has no change entries")
            return out

        for change_type, entries in change_sections:
            if not isinstance(entries, list) or len(entries) == 0:
                out.append(f"Version '{version}' has empty '{change_type}' section")
                continue
            seen: dict[str, int] = {}
            for entry in entries:
                key = str(entry).strip().lower()
                seen[key] = seen.get(key, 0) + 1
            for key, count in seen.items():
                if count > 1:
                    out.append(
                        f"Duplicate entry under '{change_type}' in version "
                        f"'{version}' ({count}x): '{key}'"
                    )
        return out

    def validate_release_contents(
        self, version: str, release: Mapping[str, Any]
    ) -> None:
        """Validates per-release content: empty sections + duplicate entries."""

        if not isinstance(release, Mapping):
            logger.warning(
                "Skipping non-mapping release payload for version %s in %s",
                version,
                self.file_path,
            )
            return

        change_sections = [
            (change_type, entries)
            for change_type, entries in release.items()
            if change_type != "metadata"
        ]

        # Empty version (no change sections at all).
        # An empty [Unreleased] is normal immediately after a release.
        if not change_sections:
            if version == UNRELEASED_ENTRY:
                return
            logger.warning(
                "Version %s has no change sections in %s", version, self.file_path
            )
            logging.Warning(
                file_path=self.file_path,
                message=f"Version '{version}' has no change entries",
            ).report()
            return

        for change_type, entries in change_sections:
            if not isinstance(entries, list) or len(entries) == 0:
                logger.warning(
                    "Version %s has an empty '%s' section in %s",
                    version,
                    change_type,
                    self.file_path,
                )
                logging.Warning(
                    file_path=self.file_path,
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
                        self.file_path,
                    )
                    logging.Warning(
                        file_path=self.file_path,
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

        logger.info("Autofixing changelog data for %s", self.file_path)
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
                key=lambda item: parse_version(item[0], self.versioning_scheme),
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
            applied.append(
                "Reordered released versions in descending "
                f"{version_scheme_label(self.versioning_scheme)} order"
            )
        for key, value in sorted_releases:
            result[key] = value

        self._backfill_unreleased_url(result, applied)

        logger.info(
            "Autofix for %s produced %d change(s)",
            self.file_path,
            len(applied),
        )
        return dict(result), applied

    def unreleased_url_backfill(
        self, changelog: Mapping[str, Any]
    ) -> tuple[str, str] | None:
        """Returns ``(unreleased_version, url)`` if a missing ``[Unreleased]:`` ref
        can and should be backfilled, else ``None``.

        Backfill is offered only when: an ``[Unreleased]`` section exists with
        entries, it has no ``url`` of its own, at least one *released* version
        carries a link ref, and a URL can be derived from those refs. This is the
        shared gate used by both the ``--fix`` backfill and the advisory warning.
        """

        unreleased = changelog.get(UNRELEASED_ENTRY)
        if not isinstance(unreleased, Mapping):
            return None
        if unreleased.get("metadata", {}).get("url"):
            return None
        # Require actual pending entries; don't decorate an empty Unreleased section.
        has_entries = any(
            change_type != "metadata" and isinstance(entries, list) and entries
            for change_type, entries in unreleased.items()
        )
        if not has_entries:
            return None

        released_links: list[tuple[str, str]] = []
        for version, release in changelog.items():
            if version == UNRELEASED_ENTRY or not isinstance(release, Mapping):
                continue
            url = release.get("metadata", {}).get("url")
            if url:
                released_links.append((version, url))
        if not released_links:
            return None

        # released_links is already newest-first (autofix sorts descending; the
        # advisory path passes the parsed dict which is authored newest-first).
        latest_version = released_links[0][0]
        url = derive_unreleased_url(released_links, latest_version)
        if url is None:
            return None
        return UNRELEASED_ENTRY, url

    def _backfill_unreleased_url(
        self,
        result: OrderedDict[str, Any],
        applied: list[str],
    ) -> None:
        """Adds a derived ``[Unreleased]:`` link ref to ``result`` in place."""

        backfill = self.unreleased_url_backfill(result)
        if backfill is None:
            return
        _version, url = backfill
        unreleased = result.get(UNRELEASED_ENTRY)
        if not isinstance(unreleased, dict):
            return
        unreleased.setdefault("metadata", {})["url"] = url
        applied.append(f"Added missing [Unreleased] link reference: {url}")
