# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Backfill changelog entries from existing release history."""

from __future__ import annotations

import subprocess  # nosec
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from semantic_version import Version  # type: ignore

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.runtime_logging import VERBOSE, get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class BackfillSource:
    """Provenance for a backfilled release or entry."""

    name: str
    identifier: str
    url: str | None = None


@dataclass(frozen=True)
class BackfillEntry:
    """Normalized entry before rendering into Keep a Changelog data."""

    change_type: str
    text: str
    source: str
    url: str | None = None
    confidence: str = "medium"


@dataclass
class BackfillRelease:
    """Normalized release before rendering into Keep a Changelog data."""

    version: str
    date: str | None
    tag: str | None
    title: str | None
    body: str | None
    entries: list[BackfillEntry]
    sources: list[BackfillSource] = field(default_factory=list)


@dataclass(frozen=True)
class BackfillPlan:
    """A conservative plan describing what backfill will add or skip."""

    changelog_path: str
    releases: list[BackfillRelease]
    added_versions: list[str]
    skipped_versions: list[str]
    skipped_tags: list[str]
    sources: list[str]
    dry_run: bool

    def to_json(self) -> dict[str, Any]:
        """Returns the Phase 1 JSON report shape."""

        return {
            "added_versions": self.added_versions,
            "skipped_versions": self.skipped_versions,
            "skipped_tags": self.skipped_tags,
            "sources": self.sources,
            "dry_run": self.dry_run,
        }


def normalize_tag_version(tag: str) -> str:
    """Normalizes a release tag for version matching."""

    return tag[1:] if tag.startswith("v") else tag


def discover_tag_releases(
    *,
    since: str | None = None,
    until: str | None = None,
    cwd: str | None = None,
) -> tuple[list[BackfillRelease], list[str]]:
    """Discovers local git tags and returns normalized releases plus skipped tags."""

    logger.info("Discovering local tags for backfill")
    try:
        result = subprocess.run(  # nosec B603
            [
                _git_executable(),
                "for-each-ref",
                "--sort=creatordate",
                "--format=%(refname:short)%09%(creatordate:short)",
                "refs/tags",
            ],
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise logging.Error(message=f"git tag discovery failed: {exc}") from exc

    rows = [line.split("\t", 1) for line in result.stdout.splitlines() if line.strip()]
    if since or until:
        rows = _filter_tag_rows(rows, since=since, until=until)

    releases: list[BackfillRelease] = []
    skipped: list[str] = []
    for row in rows:
        tag = row[0].strip()
        date = row[1].strip() or None if len(row) > 1 else None
        version = normalize_tag_version(tag)
        try:
            Version(version)
        except ValueError:
            logger.warning("Skipping non-SemVer tag during backfill: %s", tag)
            skipped.append(tag)
            continue
        releases.append(
            BackfillRelease(
                version=version,
                date=date,
                tag=tag,
                title=None,
                body=None,
                entries=[
                    BackfillEntry(
                        change_type="changed",
                        text=(
                            "Release notes unavailable; backfilled from tag "
                            f"`{tag}`."
                        ),
                        source="tags",
                        confidence="low",
                    )
                ],
                sources=[BackfillSource(name="tags", identifier=tag)],
            )
        )

    releases.sort(key=lambda release: Version(release.version), reverse=True)
    logger.info(
        "Discovered %d SemVer tag release(s) for backfill; skipped %d tag(s)",
        len(releases),
        len(skipped),
    )
    return releases, skipped


def plan_tag_backfill(
    changelog: Changelog,
    *,
    since: str | None = None,
    until: str | None = None,
    missing_only: bool = True,
    dry_run: bool = False,
) -> BackfillPlan:
    """Builds a conservative local tag backfill plan."""

    releases, skipped_tags = discover_tag_releases(since=since, until=until)
    existing_versions = {
        str(version)
        for version in changelog.get()
        if str(version) != UNRELEASED_ENTRY
    }

    planned: list[BackfillRelease] = []
    added_versions: list[str] = []
    skipped_versions: list[str] = []
    for release in releases:
        if missing_only and release.version in existing_versions:
            skipped_versions.append(release.version)
            continue
        planned.append(release)
        added_versions.append(release.version)

    return BackfillPlan(
        changelog_path=changelog.get_file_path(),
        releases=planned,
        added_versions=added_versions,
        skipped_versions=skipped_versions,
        skipped_tags=skipped_tags,
        sources=["tags"],
        dry_run=dry_run,
    )


def apply_backfill_plan(changelog: Changelog, plan: BackfillPlan) -> None:
    """Applies a backfill plan to an in-memory changelog."""

    if not plan.releases:
        return

    current = OrderedDict(changelog.get())
    unreleased = current.pop(UNRELEASED_ENTRY, None)
    for release in plan.releases:
        current[release.version] = _release_to_changelog_entry(release)

    sorted_releases = sorted(
        current.items(),
        key=lambda item: Version(str(item[0])),
        reverse=True,
    )
    updated: OrderedDict[str, Any] = OrderedDict()
    if unreleased is not None:
        updated[UNRELEASED_ENTRY] = unreleased
    for version, release in sorted_releases:
        updated[str(version)] = release

    changelog.set_data(dict(updated))


def _release_to_changelog_entry(release: BackfillRelease) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "metadata": {
            "version": release.version,
            "release_date": release.date,
        }
    }
    for backfill_entry in release.entries:
        entry.setdefault(backfill_entry.change_type, []).append(backfill_entry.text)
    return entry


def _filter_tag_rows(
    rows: Sequence[list[str]], *, since: str | None, until: str | None
) -> list[list[str]]:
    start = _find_tag_boundary(rows, since) if since else 0
    end = _find_tag_boundary(rows, until) if until else len(rows) - 1
    if start > end:
        return []
    return [list(row) for row in rows[start : end + 1]]


def _find_tag_boundary(rows: Sequence[list[str]], target: str | None) -> int:
    if target is None:
        return 0
    normalized = normalize_tag_version(target)
    for index, row in enumerate(rows):
        tag = row[0].strip()
        if tag == target or normalize_tag_version(tag) == normalized:
            return index
    raise logging.Error(message=f"Tag boundary not found: {target}")


def _git_executable() -> str:
    git = Path("git")
    logger.log(VERBOSE, "Using git executable %s", git)
    return str(git)
