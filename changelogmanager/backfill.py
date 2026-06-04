# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Backfill changelog entries from existing release history."""

from __future__ import annotations

import re
import subprocess  # nosec
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.runtime_logging import VERBOSE, get_logger
from changelogmanager.versioning import parse_version, version_scheme_label

logger = get_logger(__name__)

CommitParser = Callable[[str], Optional[tuple[str, str]]]

CONVENTIONAL_RE = re.compile(
    r"^(?P<type>[a-zA-Z]+)(?:\([^)]+\))?(?P<breaking>!)?:\s*(?P<subject>.+)$"
)
CONVENTIONAL_TO_KAC = {
    "added": "added",
    "feat": "added",
    "feature": "added",
    "fixed": "fixed",
    "fix": "fixed",
    "bug": "fixed",
    "changed": "changed",
    "perf": "changed",
    "refactor": "changed",
    "docs": "changed",
    "style": "changed",
    "test": "changed",
    "tests": "changed",
    "build": "changed",
    "ci": "changed",
    "chore": "changed",
    "revert": "changed",
    "deprecate": "deprecated",
    "deprecated": "deprecated",
    "remove": "removed",
    "removed": "removed",
    "security": "security",
    "sec": "security",
}
KEEPACHANGELOG_RE = re.compile(
    r"^(?:\[(?P<bracket>added|changed|deprecated|removed|fixed|security)\]|"
    r"(?P<prefix>added|changed|deprecated|removed|fixed|security))"
    r"\s*(?::|-|])?\s*(?P<subject>.+)$",
    re.IGNORECASE,
)
GITMOJI_TO_KAC = {
    "✨": "added",
    ":sparkles:": "added",
    "🚀": "added",
    ":rocket:": "added",
    "🐛": "fixed",
    ":bug:": "fixed",
    "🩹": "fixed",
    ":adhesive_bandage:": "fixed",
    "🔒": "security",
    ":lock:": "security",
    "👮": "security",
    ":cop:": "security",
    "♻️": "changed",
    "♻": "changed",
    ":recycle:": "changed",
    "⚡": "changed",
    ":zap:": "changed",
    "💥": "removed",
    ":boom:": "removed",
    "🗑️": "removed",
    "🗑": "removed",
    ":wastebasket:": "removed",
    "🚨": "deprecated",
    ":rotating_light:": "deprecated",
    "⚠️": "deprecated",
    "⚠": "deprecated",
    ":warning:": "deprecated",
}
GITMOJI_RE = re.compile(
    r"^(?P<emoji>:\w[\w_+-]*:|[^\w\s])\s*(?P<subject>.+)$",
    re.UNICODE,
)


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


@dataclass(frozen=True)
class GitTag:
    """Local git tag metadata used by backfill adapters."""

    tag: str
    date: str | None
    version: str


@dataclass(frozen=True)
class GitCommit:
    """Local git commit metadata used by commit parsers."""

    sha: str
    subject: str


def normalize_tag_version(tag: str) -> str:
    """Normalizes a release tag for version matching."""

    return tag[1:] if tag.startswith("v") else tag


def classify_commit_subject(
    subject: str, *, schema: str = "auto"
) -> tuple[str, str] | None:
    """Maps a commit subject onto (change_type, message) using a parser registry."""

    parsers = commit_parsers_for_schema(schema)
    for parser in parsers:
        parsed = parser(subject)
        if parsed is not None:
            return parsed
    return None


def commit_parsers_for_schema(schema: str) -> list[CommitParser]:
    """Returns parser callables for a commit-message schema name."""

    registry: dict[str, list[CommitParser]] = {
        "conventional": [parse_conventional_commit],
        "gitmoji": [parse_gitmoji_commit],
        "keepachangelog": [parse_keepachangelog_commit],
        "auto": [
            parse_conventional_commit,
            parse_gitmoji_commit,
            parse_keepachangelog_commit,
        ],
    }
    try:
        return registry[schema]
    except KeyError as exc:
        raise logging.Error(message=f"Unknown commit schema '{schema}'") from exc


def parse_conventional_commit(subject: str) -> tuple[str, str] | None:
    """Parses Conventional Commit subjects."""

    match = CONVENTIONAL_RE.match(subject)
    if not match:
        return None
    commit_type = match.group("type").lower()
    body = clean_commit_message(match.group("subject"))
    if not body:
        return None
    if bool(match.group("breaking")):
        return ("removed", body)
    return (CONVENTIONAL_TO_KAC.get(commit_type, "changed"), body)


def parse_keepachangelog_commit(subject: str) -> tuple[str, str] | None:
    """Parses Keep a Changelog-flavored subjects such as ``Added: thing``."""

    match = KEEPACHANGELOG_RE.match(subject)
    if not match:
        return None
    change_type = (match.group("bracket") or match.group("prefix")).lower()
    body = clean_commit_message(match.group("subject"))
    if not body:
        return None
    return (change_type, body)


def parse_gitmoji_commit(subject: str) -> tuple[str, str] | None:
    """Parses gitmoji subjects using emoji or ``:emoji_name:`` prefixes."""

    match = GITMOJI_RE.match(subject)
    if not match:
        return None
    emoji = match.group("emoji")
    change_type = GITMOJI_TO_KAC.get(emoji)
    if change_type is None:
        return None
    body = clean_commit_message(match.group("subject"))
    if not body:
        return None
    return (change_type, body)


def clean_commit_message(message: str) -> str:
    """Normalizes commit-derived changelog text without rewriting user intent."""

    return message.strip().strip("-:").strip()


def discover_tags(
    *,
    since: str | None = None,
    until: str | None = None,
    cwd: str | None = None,
) -> list[GitTag]:
    """Discovers local git tags in creatordate order."""

    logger.info("Discovering local tags for backfill")
    try:
        result = subprocess.run(  # nosec B603
            [
                git_executable(),
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
        rows = filter_tag_rows(rows, since=since, until=until)
    return [
        GitTag(
            tag=row[0].strip(),
            date=(row[1].strip() or None) if len(row) > 1 else None,
            version=normalize_tag_version(row[0].strip()),
        )
        for row in rows
    ]


def discover_tag_releases(
    *,
    since: str | None = None,
    until: str | None = None,
    cwd: str | None = None,
    versioning_scheme: str = "semver",
) -> tuple[list[BackfillRelease], list[str]]:
    """Discovers local git tags and returns normalized releases plus skipped tags."""

    releases: list[BackfillRelease] = []
    skipped: list[str] = []
    for tag in discover_tags(since=since, until=until, cwd=cwd):
        try:
            parse_version(tag.version, versioning_scheme)
        except ValueError:
            logger.warning(
                "Skipping tag during backfill that is not %s compatible: %s",
                version_scheme_label(versioning_scheme),
                tag.tag,
            )
            skipped.append(tag.tag)
            continue
        releases.append(
            BackfillRelease(
                version=tag.version,
                date=tag.date,
                tag=tag.tag,
                title=None,
                body=None,
                entries=[
                    BackfillEntry(
                        change_type="changed",
                        text=(
                            "Release notes unavailable; backfilled from tag "
                            f"`{tag.tag}`."
                        ),
                        source="tags",
                        confidence="low",
                    )
                ],
                sources=[BackfillSource(name="tags", identifier=tag.tag)],
            )
        )

    releases.sort(
        key=lambda release: parse_version(release.version, versioning_scheme),
        reverse=True,
    )
    logger.info(
        "Discovered %d %s tag release(s) for backfill; skipped %d tag(s)",
        len(releases),
        version_scheme_label(versioning_scheme),
        len(skipped),
    )
    return releases, skipped


def discover_commit_releases(
    *,
    since: str | None = None,
    until: str | None = None,
    cwd: str | None = None,
    versioning_scheme: str = "semver",
    commit_schema: str = "auto",
) -> tuple[list[BackfillRelease], list[str]]:
    """Discovers releases from tag intervals and classifies commit subjects."""

    tag_releases, skipped = discover_tag_releases(
        since=since,
        until=until,
        cwd=cwd,
        versioning_scheme=versioning_scheme,
    )
    ascending = sorted(
        tag_releases,
        key=lambda release: parse_version(release.version, versioning_scheme),
    )
    releases: list[BackfillRelease] = []
    previous_tag: str | None = None
    for tag_release in ascending:
        if tag_release.tag is None:
            continue
        commits = git_log_between(previous_tag, tag_release.tag, cwd=cwd)
        entries = entries_from_commits(commits, commit_schema=commit_schema)
        release = BackfillRelease(
            version=tag_release.version,
            date=tag_release.date,
            tag=tag_release.tag,
            title=None,
            body=None,
            entries=entries or tag_release.entries,
            sources=[
                BackfillSource(name="commits", identifier=tag_release.tag),
                *tag_release.sources,
            ],
        )
        releases.append(release)
        previous_tag = tag_release.tag

    releases.sort(
        key=lambda release: parse_version(release.version, versioning_scheme),
        reverse=True,
    )
    return releases, skipped


def git_log_between(
    previous_ref: str | None, current_ref: str, *, cwd: str | None = None
) -> list[GitCommit]:
    """Returns non-merge commits reachable in a release interval."""

    revision = f"{previous_ref}..{current_ref}" if previous_ref else current_ref
    cmd = [git_executable(), "log", "--no-merges", "--pretty=%H%x09%s", revision]
    logger.info("Collecting commits for backfill interval %s", revision)
    try:
        result = subprocess.run(  # nosec B603
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise logging.Error(message=f"git log failed: {exc}") from exc

    commits: list[GitCommit] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, _, subject = line.partition("\t")
        commits.append(GitCommit(sha=sha, subject=subject.strip()))
    return commits


def entries_from_commits(
    commits: Sequence[GitCommit], *, commit_schema: str = "auto"
) -> list[BackfillEntry]:
    """Converts commits into deduplicated backfill entries."""

    entries: list[BackfillEntry] = []
    seen: set[tuple[str, str]] = set()
    for commit in commits:
        parsed = classify_commit_subject(commit.subject, schema=commit_schema)
        if parsed is None:
            parsed = ("changed", commit.subject)
            confidence = "low"
        else:
            confidence = "medium"
        change_type, text = parsed
        key = (change_type, text.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        entries.append(
            BackfillEntry(
                change_type=change_type,
                text=text,
                source="commits",
                url=None,
                confidence=confidence,
            )
        )
    return entries


def plan_tag_backfill(
    changelog: Changelog,
    *,
    since: str | None = None,
    until: str | None = None,
    missing_only: bool = True,
    dry_run: bool = False,
) -> BackfillPlan:
    """Builds a conservative local tag backfill plan."""

    versioning_scheme = changelog.get_versioning_scheme()
    releases, skipped_tags = discover_tag_releases(
        since=since, until=until, versioning_scheme=versioning_scheme
    )
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
        current[release.version] = release_to_changelog_entry(release)

    sorted_releases = sorted(
        current.items(),
        key=lambda item: parse_version(str(item[0]), changelog.get_versioning_scheme()),
        reverse=True,
    )
    updated: OrderedDict[str, Any] = OrderedDict()
    if unreleased is not None:
        updated[UNRELEASED_ENTRY] = unreleased
    for version, release in sorted_releases:
        updated[str(version)] = release

    changelog.set_data(dict(updated))


def plan_backfill(
    changelog: Changelog,
    *,
    source: str = "all",
    since: str | None = None,
    until: str | None = None,
    missing_only: bool = True,
    dry_run: bool = False,
    commit_schema: str = "auto",
) -> BackfillPlan:
    """Builds a conservative backfill plan from the selected local source set."""

    versioning_scheme = changelog.get_versioning_scheme()
    if source == "tags":
        releases, skipped_tags = discover_tag_releases(
            since=since,
            until=until,
            versioning_scheme=versioning_scheme,
        )
        sources = ["tags"]
    elif source in {"commits", "all"}:
        releases, skipped_tags = discover_commit_releases(
            since=since,
            until=until,
            versioning_scheme=versioning_scheme,
            commit_schema=commit_schema,
        )
        sources = ["commits"] if source == "commits" else ["tags", "commits"]
    else:
        raise logging.Error(
            message=(
                f"Backfill source '{source}' is not implemented yet; "
                "local sources are tags, commits, and all"
            ),
        )

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
        sources=sources,
        dry_run=dry_run,
    )


def release_to_changelog_entry(release: BackfillRelease) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "metadata": {
            "version": release.version,
            "release_date": release.date,
        }
    }
    for backfill_entry in release.entries:
        entry.setdefault(backfill_entry.change_type, []).append(backfill_entry.text)
    return entry


def filter_tag_rows(
    rows: Sequence[list[str]], *, since: str | None, until: str | None
) -> list[list[str]]:
    start = find_tag_boundary(rows, since) if since else 0
    end = find_tag_boundary(rows, until) if until else len(rows) - 1
    if start > end:
        return []
    return [list(row) for row in rows[start : end + 1]]


def find_tag_boundary(rows: Sequence[list[str]], target: str | None) -> int:
    if target is None:
        return 0
    normalized = normalize_tag_version(target)
    for index, row in enumerate(rows):
        tag = row[0].strip()
        if tag == target or normalize_tag_version(tag) == normalized:
            return index
    raise logging.Error(message=f"Tag boundary not found: {target}")


def git_executable() -> str:
    git = Path("git")
    logger.log(VERBOSE, "Using git executable %s", git)
    return str(git)
