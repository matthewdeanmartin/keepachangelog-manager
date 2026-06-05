# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Presentation-free orchestration for changelog operations.

This module is the shared business-logic layer between the CLI and the Tkinter
GUI. Functions here perform the actual changelog mutations and the decisions
around them, and return small result dataclasses describing what happened. They
do **no** terminal I/O (no ``print``/``inquirer``) and accept no ``argparse``
namespaces, so any front-end can drive them.

The CLI command handlers (``changelogmanager.cli.commands``) are thin wrappers
that resolve arguments, call into here, and render the results.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec
import tempfile
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.config import (
    get_components_from_config,
    get_preamble_keywords,
    get_validation_options,
    get_versioning_scheme,
)
from changelogmanager.runtime_logging import VERBOSE, get_logger

logger = get_logger(__name__)


# ----------------------------------------------------------------------
# config init (pure config transform; also used by the GUI directly)
# ----------------------------------------------------------------------


def build_updated_config(
    base_config: Mapping[str, Any], answers: Mapping[str, Any]
) -> dict[str, Any]:
    """Returns a copy of ``base_config`` with the prompt ``answers`` applied."""

    logger.log(VERBOSE, "Building updated configuration from prompt answers")
    updated = deepcopy(dict(base_config))
    project = dict(updated.get("project", {}) or {})
    validation = dict(project.get("validation", {}) or {})
    versioning = dict(project.get("versioning", {}) or {})

    validation["enforce_preamble"] = bool(answers["enforce_preamble"])
    versioning["scheme"] = answers["versioning_scheme"]

    project["validation"] = validation
    project["versioning"] = versioning

    if answers["prompted_components"]:
        project["components"] = [
            {
                "name": str(answers["component_name"]).strip() or "default",
                "changelog": str(answers["changelog_path"]).strip() or "CHANGELOG.md",
            }
        ]

    updated["project"] = project
    return updated


# ----------------------------------------------------------------------
# release
# ----------------------------------------------------------------------


@dataclass
class ReleaseResult:
    """Outcome of releasing the [Unreleased] block."""

    version: str
    dry_run: bool
    bumped_versions: bool = False
    pyproject_only: bool = False
    bumped_files: list[str] = field(default_factory=list)


def release_changelog(
    changelog: Changelog,
    override_version: str | None,
    *,
    bump_versions: bool = False,
    pyproject_only: bool = False,
    dry_run: bool = False,
    write: bool = True,
) -> ReleaseResult:
    """Releases [Unreleased] and optionally bumps version files.

    The caller is responsible for any interactive confirmation gate before
    invoking this (the confirmation is a UI concern). When ``write`` is False or
    ``dry_run`` is True, no files are modified.
    """

    if bump_versions:
        from changelogmanager.version_bumper import jiggle_available  # noqa: PLC0415

        if not jiggle_available():
            raise logging.Error(
                message="--bump-versions requires jiggle-version. Install it with: pip install 'keepachangelog-manager-fork[jiggle]'"
            )

    changelog.release(override_version)
    new_version = str(next(iter(changelog.get())))

    result = ReleaseResult(
        version=new_version,
        dry_run=dry_run,
        bumped_versions=bump_versions,
        pyproject_only=pyproject_only,
    )
    if dry_run or not write:
        return result

    changelog.write_to_file()

    if bump_versions:
        from changelogmanager.version_bumper import bump_version_files  # noqa: PLC0415

        bumped = bump_version_files(new_version, pyproject_only=pyproject_only)
        result.bumped_files = [str(p) for p in bumped]

    return result


# ----------------------------------------------------------------------
# from-commits / unreleased seeding
# ----------------------------------------------------------------------


def git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git executable not found on PATH")
    return git


def git_log_since(since: str | None) -> list[str]:
    """Returns commit subjects since a ref (or all if since is None)."""

    cmd = [git_executable(), "log", "--no-merges", "--pretty=%s"]
    if since:
        cmd.append(f"{since}..HEAD")
    logger.info("Running git log command with since=%s", since or "<all>")
    try:
        result = subprocess.run(  # nosec B603
            cmd, check=True, capture_output=True, text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.error("git log failed: %s", exc)
        raise logging.Error(
            message=f"git log failed: {exc}",
        ) from exc
    logger.info("Collected %d git commit subject(s)", len(result.stdout.splitlines()))
    return [line for line in result.stdout.splitlines() if line.strip()]


def last_release_tag() -> str | None:
    logger.log(VERBOSE, "Looking up last release tag with git describe")
    try:
        result = subprocess.run(  # nosec B603
            [git_executable(), "describe", "--tags", "--abbrev=0"],
            check=True,
            capture_output=True,
            text=True,
        )
        tag = result.stdout.strip() or None
        logger.info("Resolved last release tag: %s", tag or "<none>")
        return tag
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Unable to determine the last release tag")
        return None


def git_log_with_files(since: str | None) -> list[Any]:
    """Returns commits (with touched files) since a ref. Module-level so tests can patch it."""

    from changelogmanager.commit_routing import (
        git_log_with_files as _impl,
    )  # noqa: PLC0415

    return _impl(since)


def classify_commit(subject: str) -> tuple[str, str] | None:
    """Maps a commit subject onto (change_type, message). Returns None to skip."""

    from changelogmanager.backfill import classify_commit_subject  # noqa: PLC0415

    logger.log(VERBOSE, "Classifying commit subject: %s", subject)
    return classify_commit_subject(subject, schema="auto")


def existing_unreleased_keys(changelog: Changelog) -> set[tuple[str, str]]:
    """Returns (change_type, normalized_message) keys already in [Unreleased]."""

    existing: set[tuple[str, str]] = set()
    data = changelog.get()
    unreleased = data.get(UNRELEASED_ENTRY, {}) if UNRELEASED_ENTRY in data else {}
    for change_type, entries in unreleased.items():
        if change_type == "metadata" or not isinstance(entries, list):
            continue
        for entry in entries:
            existing.add((change_type, str(entry).strip().lower()))
    return existing


def apply_classified_to_changelog(
    changelog: Changelog, classified: Sequence[tuple[str, str]]
) -> list[dict[str, str]]:
    """Adds classified (change_type, message) pairs, skipping existing dupes."""

    existing = existing_unreleased_keys(changelog)
    added: list[dict[str, str]] = []
    to_add: list[tuple[str, str]] = []
    for change_type, message in classified:
        key = (change_type, message.strip().lower())
        if key in existing:
            continue
        existing.add(key)
        to_add.append((change_type, message))
        added.append({"change_type": change_type, "message": message})
    changelog.add_many(to_add)
    return added


@dataclass
class FromCommitsResult:
    """Outcome of seeding [Unreleased] from commits for a single changelog."""

    added: list[dict[str, str]]
    skipped: int
    since: str | None
    no_commits: bool = False
    skipped_subjects: list[str] = field(default_factory=list)


def seed_unreleased_from_commits(
    changelog: Changelog,
    *,
    since: str | None,
    commit_schema: str = "auto",
    strict: bool = False,
    dry_run: bool = False,
) -> FromCommitsResult:
    """Classifies commits since ``since`` and adds them to [Unreleased]."""

    from changelogmanager.backfill import classify_commit_subject  # noqa: PLC0415

    subjects = git_log_since(since)
    if not subjects:
        return FromCommitsResult(added=[], skipped=0, since=since, no_commits=True)

    classified: list[tuple[str, str]] = []
    skipped = 0
    skipped_subjects: list[str] = []
    for subject in subjects:
        result = classify_commit_subject(subject, schema=commit_schema)
        if result is None:
            if strict:
                skipped += 1
                skipped_subjects.append(subject)
                continue
            classified.append(("changed", subject))
        else:
            classified.append(result)

    added = apply_classified_to_changelog(changelog, classified)
    if added and not dry_run:
        changelog.write_to_file()

    return FromCommitsResult(
        added=added,
        skipped=skipped,
        since=since,
        skipped_subjects=skipped_subjects,
    )


@dataclass
class ComponentSeedResult:
    """Per-component result of routing commits across components."""

    component: str
    path: str
    added: list[dict[str, str]]


@dataclass
class ComponentsSeedResult:
    """Outcome of routing commits across every configured component."""

    components: list[ComponentSeedResult]
    skipped: int
    since: str | None
    no_commits: bool = False


def seed_components_from_commits(
    config_path: str | None,
    *,
    since: str | None,
    commit_schema: str = "auto",
    strict: bool = False,
    dry_run: bool = False,
) -> ComponentsSeedResult:
    """Routes commits to components by touched files and seeds each [Unreleased]."""

    if not config_path:
        raise logging.Error(
            message=(
                "--all requires a configuration file (use --config or place changelogmanager.toml in cwd)"
            ),
        )
    from changelogmanager.backfill import classify_commit_subject  # noqa: PLC0415
    from changelogmanager.commit_routing import (  # noqa: PLC0415
        route_commit,
        validate_routing_components,
    )

    components = get_components_from_config(config_path)
    validate_routing_components(components, config_path=config_path)

    commits = git_log_with_files(since)
    if not commits:
        return ComponentsSeedResult(
            components=[], skipped=0, since=since, no_commits=True
        )

    versioning_scheme = get_versioning_scheme(config_path)
    enforce_preamble = bool(
        get_validation_options(config_path).get("enforce_preamble", False)
    )
    preamble_keywords = get_preamble_keywords(config_path)

    per_component: dict[str, list[tuple[str, str]]] = {
        str(component.get("name")): [] for component in components
    }
    skipped = 0
    for commit in commits:
        classified = classify_commit_subject(commit.subject, schema=commit_schema)
        if classified is None:
            if strict:
                skipped += 1
                continue
            classified = ("changed", commit.subject)
        targets = route_commit(commit.files, components)
        for name in targets:
            per_component.setdefault(name, []).append(classified)

    results: list[ComponentSeedResult] = []
    for component in components:
        name = str(component.get("name"))
        path = str(component.get("changelog"))
        changelog = Changelog(
            file_path=path,
            changelog=ChangelogReader(
                file_path=path,
                enforce_preamble=enforce_preamble,
                preamble_keywords=preamble_keywords,
                versioning_scheme=versioning_scheme,
            ).read(),
            versioning_scheme=versioning_scheme,
        )
        added = apply_classified_to_changelog(changelog, per_component.get(name, []))
        if added and not dry_run:
            changelog.write_to_file()
        results.append(ComponentSeedResult(component=name, path=path, added=added))

    return ComponentsSeedResult(components=results, skipped=skipped, since=since)


# ----------------------------------------------------------------------
# backfill
# ----------------------------------------------------------------------


def validate_backfill_options(
    *, source: str, strategy: str, missing_only: bool
) -> None:
    """Raises if the requested backfill option combination is unsupported."""

    if source not in {"tags", "commits", "all"}:
        raise logging.Error(
            message=(
                f"Backfill source '{source}' is not implemented yet; local sources are tags, commits, and all"
            ),
        )
    if strategy == "replace":
        raise logging.Error(
            message=(
                "Backfill strategy 'replace' is not supported: changelog entries "
                "have no stable identity, so replacing them is unsafe. Use "
                "'merge' to additively fill gaps in existing versions."
            ),
        )
    if not missing_only and strategy != "merge":
        raise logging.Error(
            message=(
                "Backfill into existing versions requires --strategy merge; the conservative strategy only adds missing versions"
            ),
        )


def plan_changelog_backfill(
    changelog: Changelog,
    *,
    source: str,
    since: str | None,
    until: str | None,
    missing_only: bool,
    dry_run: bool,
    commit_schema: str,
    strategy: str,
    max_commits: int | None = None,
) -> Any:
    """Returns a backfill plan (see :func:`changelogmanager.backfill.plan_backfill`)."""

    from changelogmanager.backfill import (  # noqa: PLC0415
        MAX_COMMITS_DEFAULT,
        plan_backfill,
    )

    return plan_backfill(
        changelog,
        source=source,
        since=since,
        until=until,
        missing_only=missing_only,
        dry_run=dry_run,
        commit_schema=commit_schema,
        strategy=strategy,
        max_commits=MAX_COMMITS_DEFAULT if max_commits is None else max_commits,
    )


def apply_changelog_backfill(changelog: Changelog, plan: Any) -> None:
    """Applies a backfill plan and writes the changelog when anything changed."""

    from changelogmanager.backfill import apply_backfill_plan  # noqa: PLC0415

    apply_backfill_plan(changelog, plan)
    if plan.added_versions or plan.merged_versions:
        changelog.write_to_file()


@dataclass
class UnreleasedBackfillResult:
    """Outcome of seeding [Unreleased] from commits since the last release tag."""

    added: list[dict[str, str]]
    since: str | None


def plan_unreleased_backfill(
    changelog: Changelog,
    *,
    since: str | None,
    commit_schema: str = "auto",
    max_commits: int | None = None,
) -> list[Any]:
    """Module-level wrapper so tests can patch services.plan_unreleased_backfill."""

    from changelogmanager.backfill import (  # noqa: PLC0415
        MAX_COMMITS_DEFAULT,
    )
    from changelogmanager.backfill import (
        plan_unreleased_backfill as _impl,
    )

    return _impl(
        changelog,
        since=since,
        commit_schema=commit_schema,
        max_commits=MAX_COMMITS_DEFAULT if max_commits is None else max_commits,
    )


def backfill_unreleased(
    changelog: Changelog,
    *,
    since: str | None,
    commit_schema: str = "auto",
    dry_run: bool = False,
    max_commits: int | None = None,
) -> UnreleasedBackfillResult:
    """Seeds [Unreleased] from commits since the latest release tag."""

    entries = plan_unreleased_backfill(
        changelog,
        since=since,
        commit_schema=commit_schema,
        max_commits=max_commits,
    )
    added = [
        {"change_type": entry.change_type, "message": entry.text} for entry in entries
    ]

    if added and not dry_run:
        changelog.add_many([(e["change_type"], e["message"]) for e in added])
        changelog.write_to_file()

    return UnreleasedBackfillResult(added=added, since=since)


# ----------------------------------------------------------------------
# validate --all
# ----------------------------------------------------------------------


def changed_files() -> set[str]:
    """Returns paths changed vs HEAD (staged+unstaged+untracked)."""

    logger.log(VERBOSE, "Inspecting git status for changed files")
    try:
        result = subprocess.run(  # nosec B603
            [git_executable(), "status", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        logger.warning("Unable to determine changed files from git status")
        return set()
    files: set[str] = set()
    for line in result.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        # Handle rename "old -> new"
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        files.add(str(Path(path).as_posix()))
    logger.info("Detected %d changed file(s) from git status", len(files))
    return files


@dataclass
class ComponentValidation:
    """Per-component validate result."""

    component: str
    path: str
    status: str  # "ok" | "skipped" | "error"
    applied: list[str] = field(default_factory=list)
    message: str | None = None


def validate_components(
    config_path: str,
    *,
    fix: bool,
    dry_run: bool,
    changed_only: bool,
    formatter: Any,
    fmt_options: dict[str, Any],
) -> list[ComponentValidation]:
    """Validates (and optionally fixes) every component in the config.

    Returns a structured result per component. Errors are captured into the
    result (status="error") rather than raised, so the caller can render and
    decide the exit code. The diagnostic is also reported via ``err.report()``
    so its file/line context still surfaces.
    """

    logger.info("Running validate --all using %s", config_path)
    components = get_components_from_config(config_path)
    changed = changed_files() if changed_only else None

    enforce_preamble = bool(
        get_validation_options(config_path).get("enforce_preamble", False)
    )
    preamble_keywords = get_preamble_keywords(config_path)
    versioning_scheme = get_versioning_scheme(config_path)

    results: list[ComponentValidation] = []
    for component in components:
        path = component.get("changelog")
        name = component.get("name")
        if not isinstance(path, str) or not isinstance(name, str):
            raise logging.Error(
                file_path=config_path,
                message="Each component must define string 'name' and 'changelog' values",
            )
        if changed is not None and Path(path).as_posix() not in changed:
            logger.info("Skipping unchanged component %s at %s", name, path)
            results.append(
                ComponentValidation(component=name, path=path, status="skipped")
            )
            continue
        try:
            applied = validate_one_component(
                path=path,
                fix=fix,
                dry_run=dry_run,
                enforce_preamble=enforce_preamble,
                preamble_keywords=preamble_keywords,
                versioning_scheme=versioning_scheme,
                formatter=formatter,
                fmt_options=fmt_options,
            )
            results.append(
                ComponentValidation(
                    component=name, path=path, status="ok", applied=applied
                )
            )
        except logging.Error as err:
            logger.error(
                "Component validation failed for %s at %s: %s", name, path, err.message
            )
            err.report()
            results.append(
                ComponentValidation(
                    component=name,
                    path=path,
                    status="error",
                    message=err.message,
                )
            )
    return results


def validate_one_component(  # pylint: disable=too-many-locals
    *,
    path: str,
    fix: bool,
    dry_run: bool,
    enforce_preamble: bool,
    preamble_keywords: Any,
    versioning_scheme: str,
    formatter: Any,
    fmt_options: dict[str, Any],
) -> list[str]:
    """Validates a single component, returning the list of applied fix labels."""

    # Read the file once; pass the text through the pipeline to avoid re-reads.
    original_text = (
        Path(path).read_text(encoding="UTF-8") if Path(path).is_file() else ""
    )

    if not fix:
        reader = ChangelogReader(
            file_path=path,
            enforce_preamble=enforce_preamble,
            preamble_keywords=preamble_keywords,
            versioning_scheme=versioning_scheme,
        )
        reader.read(text=original_text)
        return []

    raw_reader = ChangelogReader(
        file_path=path,
        enforce_preamble=enforce_preamble,
        preamble_keywords=preamble_keywords,
        versioning_scheme=versioning_scheme,
    )
    fixed_text, raw_applied = raw_reader.autofix_text(text=original_text)
    working_text = fixed_text if raw_applied else original_text

    # Validate fixed text via a temp file before touching the real file.
    temp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="UTF-8",
            suffix=".md",
            dir=str(Path(path).resolve().parent),
            delete=False,
        ) as temp_handle:
            temp_handle.write(working_text)
            temp_path = temp_handle.name

        temp_reader = ChangelogReader(
            file_path=temp_path,
            enforce_preamble=enforce_preamble,
            preamble_keywords=preamble_keywords,
            versioning_scheme=versioning_scheme,
        )
        data = temp_reader.read(text=working_text)
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    # Use the original path reader for autofix (it knows the canonical path).
    reader = ChangelogReader(
        file_path=path,
        enforce_preamble=enforce_preamble,
        preamble_keywords=preamble_keywords,
        versioning_scheme=versioning_scheme,
    )
    fixed, applied = reader.autofix(data)
    cl = Changelog(
        file_path=path,
        changelog=fixed,
        versioning_scheme=versioning_scheme,
    )
    format_entry = ""
    if formatter is not None:
        pre = cl.render()
        post = cl.render(formatter=formatter, format_options=fmt_options)
        if post != pre:
            format_entry = f"formatted {path} with mdformat"
    all_applied = raw_applied + applied + ([format_entry] if format_entry else [])

    if all_applied and not dry_run:
        # Commit atomically: write final result and validate via temp first.
        final_text = cl.render(
            formatter=formatter if format_entry else None,
            format_options=fmt_options if format_entry else None,
        )
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="UTF-8",
                suffix=".md",
                dir=str(Path(path).resolve().parent),
                delete=False,
            ) as temp_handle:
                temp_handle.write(final_text)
                temp_path = temp_handle.name
            verify_reader = ChangelogReader(
                file_path=temp_path,
                enforce_preamble=enforce_preamble,
                preamble_keywords=preamble_keywords,
                versioning_scheme=versioning_scheme,
            )
            verify_reader.read(text=final_text)
        finally:
            if temp_path:
                Path(temp_path).unlink(missing_ok=True)
        Path(path).write_text(final_text, encoding="UTF-8")

    return all_applied


# ----------------------------------------------------------------------
# github / gitlab
# ----------------------------------------------------------------------


@dataclass
class GitHubReleaseResult:
    """Outcome of a github-release run."""

    skipped: bool = False
    dry_run: bool = False
    release_state: str | None = None
    tag_name: str | None = None
    html_url: str | None = None
    release_id: Any = None
    version: str | None = None


def github_release(
    changelog: Changelog,
    *,
    repository: str,
    token: str,
    draft: bool,
    dry_run: bool = False,
) -> GitHubReleaseResult:
    """Creates or updates a GitHub release from the changelog."""

    if not changelog.has_unreleased():
        return GitHubReleaseResult(skipped=True)

    if dry_run:
        future_version = changelog.suggest_future_version()
        return GitHubReleaseResult(
            dry_run=True,
            release_state="draft" if draft else "published",
            version=str(future_version),
        )

    from changelogmanager.github import GitHub  # noqa: PLC0415

    github = GitHub(repository=repository, token=token)
    github.delete_draft_releases()
    release = github.create_release(changelog=changelog, draft=draft)
    release_state = "draft" if bool(release.get("draft", draft)) else "published"
    return GitHubReleaseResult(
        release_state=release_state,
        tag_name=str(release.get("tag_name", "")),
        html_url=str(release.get("html_url", "")).strip() or None,
        release_id=release.get("id"),
    )


@dataclass
class GitHubPRResult:
    """Outcome of a github-pr run."""

    dry_run: bool = False
    pr_number: Any = None
    html_url: str | None = None


def github_pull_request(
    *,
    repository: str,
    token: str,
    head: str,
    base: str,
    title: str,
    body: str,
    dry_run: bool = False,
) -> GitHubPRResult:
    """Opens or updates a GitHub pull request for the changelog update."""

    if dry_run:
        return GitHubPRResult(dry_run=True)

    from changelogmanager.github import GitHub  # noqa: PLC0415

    github = GitHub(repository=repository, token=token)
    pr = github.create_pull_request(head=head, base=base, title=title, body=body)
    return GitHubPRResult(
        pr_number=pr.get("number"),
        html_url=str(pr.get("html_url", "")).strip() or None,
    )


@dataclass
class GitLabReleaseResult:
    """Outcome of a gitlab-release run."""

    skipped: bool = False
    dry_run: bool = False
    tag_name: str | None = None
    web_url: str | None = None
    version: str | None = None


def gitlab_release(
    changelog: Changelog,
    *,
    project: str,
    token: str,
    gitlab_url: str,
    ref: str,
    dry_run: bool = False,
) -> GitLabReleaseResult:
    """Creates or updates a GitLab release from the changelog."""

    if not changelog.has_unreleased():
        return GitLabReleaseResult(skipped=True)

    if dry_run:
        future_version = changelog.suggest_future_version()
        return GitLabReleaseResult(dry_run=True, version=str(future_version))

    from changelogmanager.gitlab import GitLab  # noqa: PLC0415

    gitlab = GitLab(project=project, token=token, gitlab_url=gitlab_url)
    release = gitlab.create_release(changelog=changelog, ref=ref)
    links = release.get("_links")
    web_url = str(links.get("self", "") if isinstance(links, Mapping) else "").strip()
    return GitLabReleaseResult(
        tag_name=str(release.get("tag_name", "")),
        web_url=web_url or None,
    )
