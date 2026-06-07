# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Backfill changelog entries from existing release history."""

from __future__ import annotations

import re
import subprocess  # nosec
import unicodedata
from collections import OrderedDict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Optional

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.runtime_logging import VERBOSE, get_logger
from changelogmanager.versioning import parse_version, version_scheme_label

logger = get_logger(__name__)

CommitParser = Callable[[str], Optional[tuple[str, str]]]

#: Default ceiling on commits considered in a single backfill run. Beyond this a
#: changelog built from raw commits is unusable (thousands of bullet points) and
#: the in-memory commit/entry lists grow without bound, so backfill refuses
#: rather than silently producing garbage. ``0`` disables the guard entirely.
MAX_COMMITS_DEFAULT = 5000

#: Per-release ceiling on commit-derived entries. Even within the overall guard a
#: single release interval can contain far more commits than belong in one
#: changelog section; excess entries are dropped in favor of a summary line.
MAX_ENTRIES_PER_RELEASE = 200

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
    "revert": "changed",
    "deprecate": "deprecated",
    "deprecated": "deprecated",
    "remove": "removed",
    "removed": "removed",
    "security": "security",
    "sec": "security",
    # Non-user-facing types: excluded from KAC changelogs.
    "refactor": None,
    "docs": None,
    "style": None,
    "test": None,
    "tests": None,
    "build": None,
    "ci": None,
    "chore": None,
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
    r"^(?P<emoji>:\w[\w_+-]*:|[^\w\s]+)\s*(?P<subject>.+)$",
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
    """A conservative plan describing what backfill will add, merge, or skip."""

    changelog_path: str
    releases: list[BackfillRelease]
    added_versions: list[str]
    skipped_versions: list[str]
    skipped_tags: list[str]
    sources: list[str]
    dry_run: bool
    merged_versions: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        """Returns the Phase 1 JSON report shape."""

        report = {
            "added_versions": self.added_versions,
            "skipped_versions": self.skipped_versions,
            "skipped_tags": self.skipped_tags,
            "sources": self.sources,
            "dry_run": self.dry_run,
        }
        if self.merged_versions:
            report["merged_versions"] = self.merged_versions
        return report


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
    """Parses Conventional Commit subjects.

    Returns ``None`` for commit types that are not user-facing (docs, style,
    test, build, ci, chore, refactor) so they are excluded from the changelog.
    """

    match = CONVENTIONAL_RE.match(subject)
    if not match:
        return None
    commit_type = match.group("type").lower()
    body = clean_commit_message(match.group("subject"))
    if not body:
        return None
    if bool(match.group("breaking")):
        return ("removed", body)
    # Look up the KAC type; sentinel None means "skip this commit".
    kac_type = CONVENTIONAL_TO_KAC.get(commit_type, "changed")
    if kac_type is None:
        return None
    return (kac_type, body)


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

    cleaned = message.strip().strip("-:").strip()
    if any(
        not char.isspace() and not unicodedata.category(char).startswith("M")
        for char in cleaned
    ):
        return cleaned
    return ""


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
                            f"Release notes unavailable; backfilled from tag `{tag.tag}`."
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
    max_commits: int = MAX_COMMITS_DEFAULT,
) -> tuple[list[BackfillRelease], list[str]]:
    """Discovers releases from tag intervals and classifies commit subjects.

    Commits are gathered in a single ``git log`` pass and partitioned in Python
    by tag decoration, so the number of git subprocesses is independent of the
    tag count. ``max_commits`` guards against monster histories: when the walked
    range exceeds it the run is refused before commits are parsed.
    """

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
    tagged = [release for release in ascending if release.tag is not None]
    if not tagged:
        return [], skipped

    # Walk only up to the newest in-scope tag; commits after it are [Unreleased].
    newest_tag = tagged[-1].tag
    if newest_tag is None:
        return [], skipped
    enforce_commit_budget(newest_tag, max_commits=max_commits, cwd=cwd)

    commit_rows = git_log_all_decorated(newest_tag, cwd=cwd)
    commits_by_tag = partition_commits_by_tag(
        commit_rows,
        ascending_tags=[str(release.tag) for release in tagged if release.tag],
    )

    releases: list[BackfillRelease] = []
    for tag_release in tagged:
        tag = tag_release.tag
        if tag is None:
            continue
        commits = commits_by_tag.get(tag, [])
        entries = entries_from_commits(commits, commit_schema=commit_schema)
        entries = cap_release_entries(entries, len(commits))
        release = BackfillRelease(
            version=tag_release.version,
            date=tag_release.date,
            tag=tag,
            title=None,
            body=None,
            entries=entries or tag_release.entries,
            sources=[
                BackfillSource(name="commits", identifier=tag),
                *tag_release.sources,
            ],
        )
        releases.append(release)

    releases.reverse()
    return releases, skipped


def partition_commits_by_tag(
    commit_rows: Sequence[tuple[str, list[str], str]],
    *,
    ascending_tags: Sequence[str],
) -> dict[str, list[GitCommit]]:
    """Assigns each commit to the release it belongs to from one decorated walk.

    ``commit_rows`` come newest-first (git log default). Walking newest→oldest we
    track the "current" release boundary: a commit decorated with a known tag
    becomes the boundary for itself and all older commits until an even older tag
    is reached. This reproduces the previous ``prev..current`` interval
    partition without one ``git log`` per tag.
    """

    tag_order = {tag: index for index, tag in enumerate(ascending_tags)}
    buckets: dict[str, list[GitCommit]] = {tag: [] for tag in ascending_tags}
    # Newest tag is the default owner for commits seen before any tag decoration
    # (e.g. the tag's own commit when --until lands mid-history).
    current_tag = ascending_tags[-1] if ascending_tags else None

    for sha, tags, subject in commit_rows:
        owning = [tag for tag in tags if tag in tag_order]
        if owning:
            # If several known tags point at this commit, the oldest one owns the
            # interval boundary going forward.
            current_tag = min(owning, key=lambda tag: tag_order[tag])
        if current_tag is None:
            continue
        buckets[current_tag].append(GitCommit(sha=sha, subject=subject))
    return buckets


def cap_release_entries(
    entries: list[BackfillEntry], commit_count: int
) -> list[BackfillEntry]:
    """Caps per-release entries, appending a summary line when truncated.

    Keeps changelog sections readable even when a single release interval spans
    far more commits than belong in one section.
    """

    if len(entries) <= MAX_ENTRIES_PER_RELEASE:
        return entries
    kept = entries[:MAX_ENTRIES_PER_RELEASE]
    dropped = commit_count - MAX_ENTRIES_PER_RELEASE
    kept.append(
        BackfillEntry(
            change_type="changed",
            text=(
                f"… and {dropped} more commit(s) in this release "
                "(truncated; narrow the range to capture them)."
            ),
            source="commits",
            confidence="low",
        )
    )
    return kept


def count_commits(revision: str, *, cwd: str | None = None) -> int:
    """Returns the number of non-merge commits in a revision range.

    Uses ``git rev-list --count`` which only counts objects and never
    materializes commit data, so it stays cheap even on monster histories. This
    is the cheap pre-flight used to refuse runaway backfills before any commit is
    parsed into memory.
    """

    cmd = [git_executable(), "rev-list", "--no-merges", "--count", revision]
    try:
        result = subprocess.run(  # nosec B603
            cmd,
            check=True,
            capture_output=True,
            text=True,
            cwd=cwd,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        raise logging.Error(message=f"git rev-list failed: {exc}") from exc
    text = result.stdout.strip()
    return int(text) if text else 0


def enforce_commit_budget(
    revision: str, *, max_commits: int, cwd: str | None = None
) -> int:
    """Refuses a backfill when ``revision`` holds more commits than allowed.

    Returns the counted commit total when within budget. A ``max_commits`` of
    ``0`` (or less) disables the guard. Raises a :class:`logging.Error` with
    actionable guidance otherwise so the CLI surfaces a clear message instead of
    emitting an unusable, thousands-of-entries changelog.
    """

    if max_commits <= 0:
        return count_commits(revision, cwd=cwd)
    total = count_commits(revision, cwd=cwd)
    if total > max_commits:
        raise logging.Error(
            message=(
                f"{total} commits in range {revision} exceeds the backfill limit "
                f"of {max_commits}. This would create an unusable changelog. "
                "Narrow the range with --since/--until, or pass --max-commits 0 "
                "to override."
            )
        )
    return total


def git_log_all_decorated(
    revision: str = "HEAD", *, cwd: str | None = None
) -> list[tuple[str, list[str], str]]:
    """Returns ``(sha, tag_names, subject)`` for every non-merge commit, once.

    A single ``git log`` walk decorated with ``%D`` replaces the previous
    per-tag ``git log`` fan-out: the whole history is partitioned in Python from
    one subprocess, so cost is O(1) in the number of tags rather than O(tags).
    ``tag_names`` are the (un-prefixed) tags pointing directly at each commit,
    in git's emitted order; most commits carry none.
    """

    cmd = [
        git_executable(),
        "log",
        "--no-merges",
        "--pretty=%H%x1f%D%x1f%s",
        revision,
    ]
    logger.info("Collecting all commits for backfill in one pass over %s", revision)
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

    rows: list[tuple[str, list[str], str]] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        sha, _, rest = line.partition("\x1f")
        decoration, _, subject = rest.partition("\x1f")
        rows.append((sha, parse_decoration_tags(decoration), subject.strip()))
    return rows


def parse_decoration_tags(decoration: str) -> list[str]:
    """Extracts tag names from a ``%D`` ref-decoration field.

    Git formats decorations as a comma-separated list where tags appear as
    ``tag: <name>``; branches and ``HEAD`` are ignored.
    """

    tags: list[str] = []
    for ref in decoration.split(","):
        ref = ref.strip()
        if ref.startswith("tag:"):
            tags.append(ref[len("tag:") :].strip())
    return tags


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
        str(version) for version in changelog.get() if str(version) != UNRELEASED_ENTRY
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
    """Applies a backfill plan to an in-memory changelog.

    New versions are inserted as fresh sections. For versions already present
    (merge strategy) the planned entries are appended to the existing section,
    preserving its metadata and previously recorded entries.
    """

    if not plan.releases:
        return

    current = OrderedDict(changelog.get())
    unreleased = current.pop(UNRELEASED_ENTRY, None)
    for release in plan.releases:
        existing = current.get(release.version)
        if isinstance(existing, Mapping):
            current[release.version] = merge_release_into_entry(existing, release)
        else:
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


GITHUB_LABEL_TO_KAC: dict[str, str] = {
    "bug": "fixed",
    "fix": "fixed",
    "enhancement": "added",
    "feature": "added",
    "breaking change": "changed",
    "deprecation": "deprecated",
    "security": "security",
    "removed": "removed",
}


def _assign_version_by_date(
    merged_date: str,
    tag_timeline: list[tuple[str, str]],
) -> str | None:
    """Returns the version whose tag date is the earliest on or after merged_date.

    ``tag_timeline`` is a list of ``(date, version)`` pairs sorted ascending by
    date.  Returns ``None`` when no tag follows the merged date (the PR belongs
    to ``[Unreleased]``).
    """
    for tag_date, version in tag_timeline:
        if tag_date >= merged_date:
            return version
    return None


def discover_github_prs(
    repository: str,
    token: str | None,
    *,
    since: str | None = None,
    until: str | None = None,
    versioning_scheme: str = "semver",
) -> tuple[list[BackfillRelease], list[str]]:
    """Fetches merged GitHub PRs and groups them into versions by date window.

    PRs are assigned to the earliest release tag whose date falls on or after the
    PR's merge date.  PRs merged after all known tags are assigned to a special
    ``__unreleased__`` bucket and silently dropped (the caller decides what to
    do with unreleased entries).  Non-semver tags are included in the timeline
    but skipped from the returned releases list (recorded in ``skipped``).
    """
    from changelogmanager.github import GitHub  # noqa: PLC0415

    client = GitHub(repository=repository, token=token or "")
    raw_prs = client.get_merged_prs(since_date=since, until_date=until)

    # Build a sorted tag timeline from local git tags.  Fall back to an empty
    # timeline when there are no tags (calendar-month grouping is used instead).
    local_tags = discover_tags()
    tag_timeline: list[tuple[str, str]] = []
    for gt in sorted(local_tags, key=lambda t: t.date or ""):
        if not gt.date:
            continue
        try:
            parse_version(gt.version, versioning_scheme)
        except ValueError:
            continue
        tag_timeline.append((gt.date, gt.version))

    use_calendar_months = not tag_timeline
    if use_calendar_months:
        logger.warning(
            "No local git tags found; grouping GitHub PRs into calendar-month "
            "synthetic versions (YYYY-MM). Switch to --source github-releases or "
            "add git tags to get proper version grouping."
        )

    # Group PRs by assigned version.
    buckets: dict[str, list[dict[str, Any]]] = {}
    for pr in raw_prs:
        merged_at: str = (pr.get("merged_at") or "")[:10]
        if not merged_at:
            continue
        version: str | None = (
            merged_at[:7]  # YYYY-MM
            if use_calendar_months
            else _assign_version_by_date(merged_at, tag_timeline)
        )

        if version is None:
            continue  # belongs to [Unreleased] — skip
        buckets.setdefault(version, []).append(pr)

    skipped: list[str] = []
    releases: list[BackfillRelease] = []
    for version, prs in buckets.items():
        if not use_calendar_months:
            try:
                parse_version(version, versioning_scheme)
            except ValueError:
                skipped.append(version)
                continue

        entries: list[BackfillEntry] = []
        seen: set[tuple[str, str]] = set()
        for pr in prs:
            title: str = (pr.get("title") or "").strip()
            if not title:
                continue
            labels: list[str] = [
                (lbl.get("name") or "").lower()
                for lbl in (pr.get("labels") or [])
                if isinstance(lbl, dict)
            ]
            change_type = "changed"
            for label in labels:
                if label in GITHUB_LABEL_TO_KAC:
                    change_type = GITHUB_LABEL_TO_KAC[label]
                    break
            key = (change_type, title.lower())
            if key in seen:
                continue
            seen.add(key)
            pr_url: str | None = pr.get("html_url")
            entries.append(
                BackfillEntry(
                    change_type=change_type,
                    text=title,
                    source="github-prs",
                    url=pr_url,
                    confidence="medium",
                )
            )

        if not entries:
            continue

        # Use the latest merge date in the bucket as the release date.
        dates = [
            (pr.get("merged_at") or "")[:10]
            for pr in prs
            if (pr.get("merged_at") or "")[:10]
        ]
        release_date: str | None = max(dates) if dates else None

        releases.append(
            BackfillRelease(
                version=version,
                date=release_date,
                tag=None,
                title=None,
                body=None,
                entries=entries,
                sources=[
                    BackfillSource(
                        name="github-prs",
                        identifier=version,
                        url=f"https://github.com/{repository}/pulls?q=is%3Apr+is%3Amerged",
                    )
                ],
            )
        )

    releases.sort(
        key=lambda r: r.version,
        reverse=True,
    )
    logger.info(
        "Discovered %d PR-based release group(s) for backfill; skipped %d",
        len(releases),
        len(skipped),
    )
    return releases, skipped


def discover_github_releases(
    repository: str,
    token: str | None,
    *,
    since: str | None = None,
    until: str | None = None,
    versioning_scheme: str = "semver",
) -> tuple[list[BackfillRelease], list[str]]:
    """Fetches GitHub Releases and returns normalized BackfillRelease list plus skipped tags."""
    from changelogmanager.github import GitHub  # noqa: PLC0415

    client = GitHub(repository=repository, token=token or "")
    raw = client.get_releases_for_backfill()

    releases: list[BackfillRelease] = []
    skipped: list[str] = []
    for item in raw:
        tag_name: str = item.get("version", "")
        version = normalize_tag_version(tag_name)
        try:
            parse_version(version, versioning_scheme)
        except ValueError:
            logger.warning(
                "Skipping GitHub release not %s compatible: %s",
                versioning_scheme,
                tag_name,
            )
            skipped.append(tag_name)
            continue

        if since and version < since:
            continue
        if until and version > until:
            continue

        body: str = item.get("body", "") or ""
        date: str | None = item.get("date")
        url = f"https://github.com/{repository}/releases/tag/{tag_name}"
        entries: list[BackfillEntry] = []
        if body.strip():
            entries.append(
                BackfillEntry(
                    change_type="changed",
                    text=body.strip(),
                    source="github-releases",
                    url=url,
                    confidence="medium",
                )
            )
        else:
            entries.append(
                BackfillEntry(
                    change_type="changed",
                    text=f"Release notes unavailable; backfilled from GitHub release `{tag_name}`.",
                    source="github-releases",
                    url=url,
                    confidence="low",
                )
            )
        releases.append(
            BackfillRelease(
                version=version,
                date=date,
                tag=tag_name,
                title=None,
                body=body,
                entries=entries,
                sources=[
                    BackfillSource(name="github-releases", identifier=tag_name, url=url)
                ],
            )
        )

    releases.sort(
        key=lambda r: parse_version(r.version, versioning_scheme),
        reverse=True,
    )
    logger.info(
        "Discovered %d GitHub release(s) for backfill; skipped %d",
        len(releases),
        len(skipped),
    )
    return releases, skipped


def discover_pypi_releases(
    package: str,
    *,
    since: str | None = None,
    until: str | None = None,
    versioning_scheme: str = "semver",
) -> tuple[list[BackfillRelease], list[str]]:
    """Fetches PyPI release history and returns normalized BackfillRelease list plus skipped."""
    from changelogmanager.pypi import get_pypi_releases  # noqa: PLC0415

    raw = get_pypi_releases(package)
    releases: list[BackfillRelease] = []
    skipped: list[str] = []
    for item in raw:
        version: str = item["version"]
        try:
            parse_version(version, versioning_scheme)
        except ValueError:
            logger.warning(
                "Skipping PyPI release not %s compatible: %s",
                versioning_scheme,
                version,
            )
            skipped.append(version)
            continue

        if since and version < since:
            continue
        if until and version > until:
            continue

        date: str | None = item.get("date")
        url = f"https://pypi.org/project/{package}/{version}/"
        releases.append(
            BackfillRelease(
                version=version,
                date=date,
                tag=None,
                title=None,
                body=None,
                entries=[
                    BackfillEntry(
                        change_type="changed",
                        text="Released on PyPI.",
                        source="pypi",
                        url=url,
                        confidence="low",
                    )
                ],
                sources=[BackfillSource(name="pypi", identifier=version, url=url)],
            )
        )

    releases.sort(
        key=lambda r: parse_version(r.version, versioning_scheme),
        reverse=True,
    )
    logger.info(
        "Discovered %d PyPI release(s) for backfill; skipped %d",
        len(releases),
        len(skipped),
    )
    return releases, skipped


def _merge_releases(*release_lists: list[BackfillRelease]) -> list[BackfillRelease]:
    """Merges multiple release lists, deduplicating by (version, section, text)."""
    by_version: dict[str, BackfillRelease] = {}
    for releases in release_lists:
        for release in releases:
            if release.version not in by_version:
                by_version[release.version] = release
                continue
            existing = by_version[release.version]
            seen: set[tuple[str, str]] = {
                (e.change_type, e.text.strip().lower()) for e in existing.entries
            }
            new_entries = [
                e
                for e in release.entries
                if (e.change_type, e.text.strip().lower()) not in seen
            ]
            merged_sources = existing.sources + [
                s for s in release.sources if s not in existing.sources
            ]
            by_version[release.version] = BackfillRelease(
                version=existing.version,
                date=existing.date or release.date,
                tag=existing.tag or release.tag,
                title=existing.title or release.title,
                body=existing.body or release.body,
                entries=existing.entries + new_entries,
                sources=merged_sources,
            )
    return list(by_version.values())


def plan_backfill(
    changelog: Changelog,
    *,
    source: str = "local",
    since: str | None = None,
    until: str | None = None,
    missing_only: bool = True,
    dry_run: bool = False,
    commit_schema: str = "auto",
    strategy: str = "conservative",
    max_commits: int = MAX_COMMITS_DEFAULT,
    repository: str | None = None,
    token: str | None = None,
    package: str | None = None,
) -> BackfillPlan:
    """Builds a backfill plan from the selected source set.

    Under ``strategy == "merge"`` together with ``missing_only=False`` versions
    already present in the changelog are not skipped; instead they are kept in the
    plan carrying only the entries that are not already recorded for that version.
    The merge is strictly additive: existing entries are never rewritten or
    removed. With the default ``missing_only=True`` only versions absent from the
    changelog are planned, regardless of strategy.
    """

    versioning_scheme = changelog.get_versioning_scheme()
    if source == "tags":
        releases, skipped_tags = discover_tag_releases(
            since=since,
            until=until,
            versioning_scheme=versioning_scheme,
        )
        sources = ["tags"]
    elif source == "commits":
        releases, skipped_tags = discover_commit_releases(
            since=since,
            until=until,
            versioning_scheme=versioning_scheme,
            commit_schema=commit_schema,
            max_commits=max_commits,
        )
        sources = ["commits"]
    elif source in {"local", "all"}:
        releases, skipped_tags = discover_commit_releases(
            since=since,
            until=until,
            versioning_scheme=versioning_scheme,
            commit_schema=commit_schema,
            max_commits=max_commits,
        )
        sources = ["tags", "commits"]
        if source == "all" and repository:
            gh_releases, gh_skipped = discover_github_releases(
                repository,
                token,
                since=since,
                until=until,
                versioning_scheme=versioning_scheme,
            )
            gh_prs, pr_skipped = discover_github_prs(
                repository,
                token,
                since=since,
                until=until,
                versioning_scheme=versioning_scheme,
            )
            releases = _merge_releases(releases, gh_releases, gh_prs)
            skipped_tags = skipped_tags + gh_skipped + pr_skipped
            sources = ["tags", "commits", "github-releases", "github-prs"]
        elif source == "all" and not repository:
            logger.warning(
                "backfill --source all without --repository falls back to local sources only; "
                "switch to --source local to suppress this warning"
            )
    elif source == "github-releases":
        if not repository:
            raise logging.Error(
                message="--repository owner/repo is required for --source github-releases"
            )
        releases, skipped_tags = discover_github_releases(
            repository,
            token,
            since=since,
            until=until,
            versioning_scheme=versioning_scheme,
        )
        sources = ["github-releases"]
    elif source == "pypi":
        if not package:
            raise logging.Error(message="--package name is required for --source pypi")
        releases, skipped_tags = discover_pypi_releases(
            package,
            since=since,
            until=until,
            versioning_scheme=versioning_scheme,
        )
        sources = ["pypi"]
    elif source == "github-prs":
        if not repository:
            raise logging.Error(
                message="--repository owner/repo is required for --source github-prs"
            )
        releases, skipped_tags = discover_github_prs(
            repository,
            token,
            since=since,
            until=until,
            versioning_scheme=versioning_scheme,
        )
        sources = ["github-prs"]
    else:
        raise logging.Error(
            message=(f"Backfill source '{source}' is not implemented yet"),
        )

    merging = strategy == "merge" and not missing_only
    existing = {
        str(version): release
        for version, release in changelog.get().items()
        if str(version) != UNRELEASED_ENTRY
    }
    planned: list[BackfillRelease] = []
    added_versions: list[str] = []
    merged_versions: list[str] = []
    skipped_versions: list[str] = []
    for release in releases:
        if release.version not in existing:
            planned.append(release)
            added_versions.append(release.version)
            continue
        if not merging:
            skipped_versions.append(release.version)
            continue
        new_entries = filter_existing_entries(
            release.entries, existing[release.version]
        )
        if not new_entries:
            skipped_versions.append(release.version)
            continue
        planned.append(replace(release, entries=new_entries))
        merged_versions.append(release.version)

    return BackfillPlan(
        changelog_path=changelog.get_file_path(),
        releases=planned,
        added_versions=added_versions,
        skipped_versions=skipped_versions,
        skipped_tags=skipped_tags,
        sources=sources,
        dry_run=dry_run,
        merged_versions=merged_versions,
    )


def filter_existing_entries(
    entries: Sequence[BackfillEntry], existing_release: Any
) -> list[BackfillEntry]:
    """Drops entries already recorded in an existing changelog version section.

    Matching is on (change type, normalized text), the same key used to
    deduplicate commit-derived entries, so re-running merge is idempotent.
    """

    recorded: set[tuple[str, str]] = set()
    if isinstance(existing_release, Mapping):
        for change_type, messages in existing_release.items():
            if change_type == "metadata" or not isinstance(messages, list):
                continue
            for message in messages:
                recorded.add((change_type, str(message).strip().lower()))

    kept: list[BackfillEntry] = []
    for entry in entries:
        key = (entry.change_type, entry.text.strip().lower())
        if key in recorded:
            continue
        recorded.add(key)
        kept.append(entry)
    return kept


def latest_release_tag(
    *, cwd: str | None = None, versioning_scheme: str = "semver"
) -> str | None:
    """Returns the most recent scheme-compatible tag, or None when there is none."""

    tags = discover_tags(cwd=cwd)
    compatible: list[GitTag] = []
    for tag in tags:
        try:
            parse_version(tag.version, versioning_scheme)
        except ValueError:
            continue
        compatible.append(tag)
    if not compatible:
        return None
    compatible.sort(key=lambda tag: parse_version(tag.version, versioning_scheme))
    return compatible[-1].tag


def plan_unreleased_backfill(
    changelog: Changelog,
    *,
    since: str | None = None,
    commit_schema: str = "auto",
    cwd: str | None = None,
    max_commits: int = MAX_COMMITS_DEFAULT,
) -> list[BackfillEntry]:
    """Returns new [Unreleased] entries derived from commits since the latest release.

    Entries already present in the changelog's [Unreleased] section (matched on
    change type + normalized text) are filtered out so the plan is additive only.
    ``max_commits`` guards the HEAD walk: when no tag exists the boundary is the
    repository root, so an unguarded walk would ingest the entire history.
    """

    versioning_scheme = changelog.get_versioning_scheme()
    boundary = since or latest_release_tag(cwd=cwd, versioning_scheme=versioning_scheme)
    revision = f"{boundary}..HEAD" if boundary else "HEAD"
    enforce_commit_budget(revision, max_commits=max_commits, cwd=cwd)
    commits = git_log_between(boundary, "HEAD", cwd=cwd)
    candidates = entries_from_commits(commits, commit_schema=commit_schema)

    existing: set[tuple[str, str]] = set()
    unreleased = changelog.get().get(UNRELEASED_ENTRY, {})
    if isinstance(unreleased, dict):
        for change_type, messages in unreleased.items():
            if change_type == "metadata" or not isinstance(messages, list):
                continue
            for message in messages:
                existing.add((change_type, str(message).strip().lower()))

    planned: list[BackfillEntry] = []
    for entry in candidates:
        key = (entry.change_type, entry.text.strip().lower())
        if key in existing:
            continue
        existing.add(key)
        planned.append(entry)
    logger.info(
        "Planned %d new [Unreleased] entr(y/ies) from commits since %s",
        len(planned),
        boundary or "<root>",
    )
    return planned


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


def merge_release_into_entry(
    existing: Mapping[str, Any], release: BackfillRelease
) -> dict[str, Any]:
    """Appends a backfilled release's entries to an existing version section.

    Existing metadata and entries are preserved verbatim; backfilled entries are
    only appended to the corresponding change-type bucket. A missing release date
    in the existing metadata is filled from the backfilled release when known.
    """

    merged: dict[str, Any] = {
        key: list(value) if isinstance(value, list) else value
        for key, value in existing.items()
    }
    metadata = dict(merged.get("metadata") or {})
    metadata.setdefault("version", release.version)
    if not metadata.get("release_date") and release.date:
        metadata["release_date"] = release.date
    merged["metadata"] = metadata

    for backfill_entry in release.entries:
        merged.setdefault(backfill_entry.change_type, []).append(backfill_entry.text)
    return merged


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
