# SPDX-License-Identifier: MIT

"""Slim vendored subset of Colin-b/keepachangelog.

This copy intentionally keeps only the parser/serializer surface that
changelogmanager uses internally:

* ``to_dict(..., show_unreleased=True|False)``
* ``from_dict(...)``

Upstream project: https://github.com/Colin-b/keepachangelog
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from contextlib import suppress
from os import PathLike
from pathlib import Path
from typing import Any

from changelogmanager.versioning import parse_version, version_metadata

__all__ = ["from_dict", "to_dict"]

PREAMBLE = """# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).\n"""
LINK_PATTERN = re.compile(r"^\[(.*)\]: (.*)$")
INITIAL_SEMANTIC_VERSION = {
    "major": 0,
    "minor": 0,
    "patch": 0,
    "prerelease": None,
    "buildmetadata": None,
}
SEMANTIC_VERSIONING = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:[-\.]?(?P<prerelease>(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+(?P<buildmetadata>[0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


def unlink(value: str) -> str:
    return value.lstrip("[").rstrip("]")


def extract_date(value: str | None) -> str | None:
    if not value:
        return None
    return value.lstrip(" -(").rstrip(" )")


def semantic_version(version: str) -> dict[str, Any]:
    if not version:
        return INITIAL_SEMANTIC_VERSION.copy()
    match = SEMANTIC_VERSIONING.fullmatch(version)
    if match is None:
        raise ValueError(version)
    return {
        key: int(value) if key in {"major", "minor", "patch"} else value
        for key, value in match.groupdict().items()
    }


def supported_version_metadata(version: str) -> dict[str, Any]:
    if not version:
        return {"semantic_version": INITIAL_SEMANTIC_VERSION.copy()}
    for scheme in ("semver", "calver", "pep440"):
        with suppress(ValueError):
            return version_metadata(parse_version(version, scheme))
    raise ValueError(version)


def add_release(changes: dict[str, dict[str, Any]], line: str) -> dict[str, Any]:
    release_line = line[3:].lower().strip()
    version, release_date = (
        release_line.split(" ", maxsplit=1)
        if " " in release_line
        else (release_line, None)
    )
    version = unlink(version)
    metadata: dict[str, Any] = {
        "version": version,
        "release_date": extract_date(release_date),
    }
    with suppress(ValueError):
        metadata.update(supported_version_metadata(version))
    return changes.setdefault(version, {"metadata": metadata})


def add_category(release: dict[str, Any], line: str) -> list[str]:
    category = line[4:].lower().strip()
    existing_category = release.get(category)
    if existing_category is None:
        new_category: list[str] = []
        release[category] = new_category
        return new_category
    if not isinstance(existing_category, list):
        raise TypeError(f"Expected list[str] category content for {category!r}")
    return existing_category


def add_information(category: list[str], line: str) -> None:
    category.append(line.lstrip(" *-").rstrip(" -"))


def parse_to_dict(
    change_log: Iterable[str], show_unreleased: bool
) -> dict[str, dict[str, Any]]:
    changes: dict[str, dict[str, Any]] = {}
    urls: dict[str, str] = {}
    current_release: dict[str, Any] = {}
    category: list[str] = []

    for raw_line in change_log:
        line = raw_line.strip(" \n")

        if line.startswith("## "):
            current_release = add_release(changes, line)
            category = current_release.setdefault("uncategorized", [])
        elif line.startswith("### "):
            category = add_category(current_release, line)
        elif match := LINK_PATTERN.fullmatch(line):
            urls[match.group(1).lower()] = match.group(2)
        elif line:
            add_information(category, line)

    for version, url in urls.items():
        changes.setdefault(version, {"metadata": {"version": version}})["metadata"][
            "url"
        ] = url

    unreleased_version: str | None = None
    for version, current_release in changes.items():
        metadata = current_release["metadata"]
        if not current_release.get("uncategorized"):
            current_release.pop("uncategorized", None)
        if ("release_date" in metadata) and not metadata["release_date"]:
            unreleased_version = version

    if not show_unreleased and unreleased_version is not None:
        changes.pop(unreleased_version, None)

    return changes


def to_dict(
    changelog_path: str | PathLike[str] | Iterable[str],
    *,
    show_unreleased: bool = False,
) -> dict[str, dict[str, Any]]:
    """Convert a Keep a Changelog markdown document into a dictionary."""

    if isinstance(changelog_path, (str, PathLike)):
        with Path(changelog_path).open(encoding="utf-8") as change_log:
            return parse_to_dict(change_log, show_unreleased)
    return parse_to_dict(changelog_path, show_unreleased)


def from_dict(changes: dict[str, dict[str, Any]]) -> str:
    """Render the changelog dictionary back to markdown."""

    content = PREAMBLE

    for current_release in changes.values():
        metadata = current_release["metadata"]
        content += f"\n## [{metadata['version'].capitalize()}]"

        if metadata.get("release_date"):
            content += f" - {metadata['release_date']}"

        uncategorized = current_release.get("uncategorized", [])
        for category_content in uncategorized:
            content += f"\n* {category_content}"
        if uncategorized:
            content += "\n"

        for category_name, category_content in current_release.items():
            if category_name in ["metadata", "uncategorized"]:
                continue

            content += f"\n### {category_name.capitalize()}"
            for categorized in category_content:
                content += f"\n- {categorized}"
            content += "\n"

    urls_content = []
    for current_release in changes.values():
        metadata = current_release["metadata"]
        if not metadata.get("url"):
            continue
        urls_content.append(f"[{metadata['version'].capitalize()}]: {metadata['url']}")

    if urls_content:
        content += "\n"
        content += "\n".join(urls_content)
        content += "\n"

    return content
