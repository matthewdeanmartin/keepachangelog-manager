# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Version parsing, ordering, and bumping across supported schemes."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from functools import total_ordering
from pathlib import Path
from typing import Any

from packaging.version import InvalidVersion
from packaging.version import Version as Pep440Version
from semantic_version import Version as SemverVersion

from changelogmanager.change_types import VersionCore

SUPPORTED_VERSIONING_SCHEMES = {"semver", "pep440", "calver"}
CALVER_PATTERN = re.compile(
    r"^(?P<year>\d{4}|\d{2})(?:[._-](?P<month>0?[1-9]|1[0-2]))?"
    r"(?:[._-](?P<day>0|0?[1-9]|[12]\d|3[01]))?"
    r"(?:[._-](?P<micro>\d+))?$"
)


@total_ordering
@dataclass(frozen=True)
class VersionValue:
    """Comparable wrapper that preserves the user's version text."""

    raw: str
    scheme: str
    parsed: Any
    sort_key: tuple[Any, ...]

    def __str__(self) -> str:
        return self.raw

    def __lt__(self, other: object) -> bool:
        other_value = coerce_same_scheme(other, self.scheme)
        return self.sort_key < other_value.sort_key

    def __eq__(self, other: object) -> bool:
        try:
            other_value = coerce_same_scheme(other, self.scheme)
        except ValueError:
            return False
        return self.sort_key == other_value.sort_key


def coerce_same_scheme(value: object, scheme: str) -> VersionValue:
    if isinstance(value, VersionValue):
        if value.scheme != scheme:
            raise ValueError(str(value))
        return value
    return parse_version(str(value), scheme)


def normalize_scheme(scheme: str | None) -> str:
    if scheme is not None and scheme in SUPPORTED_VERSIONING_SCHEMES:
        return scheme
    return "semver"


def version_scheme_label(scheme: str) -> str:
    return {
        "semver": "SemVer",
        "pep440": "PEP 440",
        "calver": "CalVer",
    }.get(scheme, "SemVer")


def version_scheme_expectation(scheme: str) -> str:
    return {
        "semver": "Use MAJOR.MINOR.PATCH, e.g. '1.2.3' (see https://semver.org)",
        "pep440": "Use a PEP 440 version, e.g. '1.2.3', '1.2rc1', or '2024.4'",
        "calver": "Use a calendar version, e.g. '2024.04.0' or '2024.04.30'",
    }.get(scheme, "Use MAJOR.MINOR.PATCH, e.g. '1.2.3' (see https://semver.org)")


def parse_version(version: str, scheme: str = "semver") -> VersionValue:
    scheme = normalize_scheme(scheme)
    if scheme == "semver":
        parsed = SemverVersion(version)
        return VersionValue(
            raw=str(parsed),
            scheme=scheme,
            parsed=parsed,
            sort_key=(
                parsed.major,
                parsed.minor,
                parsed.patch,
                tuple(parsed.prerelease or ()),
                tuple(parsed.build or ()),
            ),
        )
    if scheme == "pep440":
        try:
            parsed = Pep440Version(version)
        except InvalidVersion as exc:
            raise ValueError(version) from exc
        return VersionValue(
            raw=str(parsed), scheme=scheme, parsed=parsed, sort_key=(parsed,)
        )

    match = CALVER_PATTERN.fullmatch(version)
    if match is None:
        raise ValueError(version)
    groups = match.groupdict()
    year = int(groups["year"])
    if year < 100:
        year += 2000
    month = int(groups["month"] or 0)
    day = int(groups["day"] or 0)
    micro = int(groups["micro"] or 0)
    if day and not month:
        raise ValueError(version)
    if month and day:
        try:
            date(year, month, day)
        except ValueError as exc:
            raise ValueError(version) from exc
    return VersionValue(
        raw=version,
        scheme=scheme,
        parsed={"year": year, "month": month, "day": day, "micro": micro},
        sort_key=(year, month, day, micro),
    )


def version_metadata(version: VersionValue) -> dict[str, Any]:
    if version.scheme == "semver":
        parsed = version.parsed
        return {
            "semantic_version": {
                "buildmetadata": ".".join(parsed.build) if parsed.build else None,
                "major": parsed.major,
                "minor": parsed.minor,
                "patch": parsed.patch,
                "prerelease": (
                    ".".join(parsed.prerelease) if parsed.prerelease else None
                ),
            }
        }
    if version.scheme == "pep440":
        parsed = version.parsed
        return {
            "pep440_version": {
                "epoch": parsed.epoch,
                "release": list(parsed.release),
                "pre": list(parsed.pre) if parsed.pre else None,
                "post": parsed.post,
                "dev": parsed.dev,
                "local": parsed.local,
            }
        }
    parsed = version.parsed
    return {
        "calendar_version": {
            "year": parsed["year"],
            "month": parsed["month"] or None,
            "day": parsed["day"] or None,
            "micro": parsed["micro"] or None,
        }
    }


def initial_version(scheme: str) -> VersionValue:
    scheme = normalize_scheme(scheme)
    if scheme == "calver":
        today = date.today()
        return parse_version(f"{today.year}.{today.month:02d}.0", scheme)
    return parse_version("0.0.1", scheme)


def bump_version(previous: VersionValue, bump_type: VersionCore) -> VersionValue:
    if previous.scheme == "semver":
        parsed = previous.parsed
        if bump_type == VersionCore.MAJOR:
            return parse_version(str(parsed.next_major()), previous.scheme)
        if bump_type == VersionCore.MINOR:
            return parse_version(str(parsed.next_minor()), previous.scheme)
        return parse_version(str(parsed.next_patch()), previous.scheme)

    if previous.scheme == "pep440":
        release = list(previous.parsed.release)
        while len(release) < 3:
            release.append(0)
        if bump_type == VersionCore.MAJOR:
            release = [release[0] + 1, 0, 0]
        elif bump_type == VersionCore.MINOR:
            release = [release[0], release[1] + 1, 0]
        else:
            release = [release[0], release[1], release[2] + 1]
        return parse_version(".".join(str(part) for part in release), previous.scheme)

    today = date.today()
    parsed = previous.parsed
    micro = (
        parsed["micro"] + 1
        if (parsed["year"], parsed["month"]) == (today.year, today.month)
        else 0
    )
    if parsed["day"]:
        return parse_version(
            f"{today.year}.{today.month:02d}.{today.day:02d}.{micro}", previous.scheme
        )
    return parse_version(f"{today.year}.{today.month:02d}.0.{micro}", previous.scheme)


def detect_versioning_scheme_from_text(text: str) -> str | None:
    head = text.lower()[:1024]
    if "pep 440" in head or "pep440" in head:
        return "pep440"
    if "calendar versioning" in head or "calver" in head:
        return "calver"
    if "semantic versioning" in head or "semver" in head:
        return "semver"
    return None


def detect_versioning_scheme_from_file(file_path: str) -> str | None:
    try:
        with Path(file_path).open(encoding="UTF-8") as file_handle:
            return detect_versioning_scheme_from_text(file_handle.read(1024))
    except OSError:
        return None
