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
    resolve_config_file,
)
from changelogmanager.file_updates import atomic_write_text, rollback_file_updates
from changelogmanager.release_scope import ReleaseScope
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
    scope: ReleaseScope | None = None,
) -> ReleaseResult:
    """Releases [Unreleased] and optionally bumps version files.

    The caller is responsible for any interactive confirmation gate before
    invoking this (the confirmation is a UI concern). When ``write`` is False or
    ``dry_run`` is True, no files are modified.
    """
    logger.info(
        "Releasing changelog %s (override=%s, bump_versions=%s, pyproject_only=%s, dry_run=%s, write=%s)",
        changelog.get_file_path(),
        override_version or "<auto>",
        bump_versions,
        pyproject_only,
        dry_run,
        write,
    )

    if scope and bump_versions:
        scope.require_version_files()
        from changelogmanager.version_bumper import plan_version_files

        plan_version_files(
            project_root=scope.root,
            version_files=scope.version_files,
            pyproject_only=pyproject_only,
        )
    if scope and override_version:
        override_version = scope.version(override_version)
    # Version bumping is built in (vendored), so --bump-versions needs no extra
    # dependency or availability check.
    original_data = deepcopy(changelog.changelog)
    changelog.release(override_version)
    new_version = str(next(iter(changelog.get())))
    logger.info(
        "Prepared release %s for %s",
        new_version,
        changelog.get_file_path(),
    )

    result = ReleaseResult(
        version=new_version,
        dry_run=dry_run,
        pyproject_only=pyproject_only,
    )
    if dry_run or not write:
        logger.info(
            "Skipping file writes for release %s (dry_run=%s, write=%s)",
            new_version,
            dry_run,
            write,
        )
        return result

    from changelogmanager.version_bumper import plan_version_files

    try:
        targets = [Path(changelog.get_file_path())]
        if bump_versions:
            targets.extend(
                plan_version_files(
                    project_root=scope.root if scope else None,
                    version_files=scope.version_files if scope else None,
                    pyproject_only=pyproject_only,
                )
            )
        with rollback_file_updates(targets):
            logger.info("Writing released changelog to %s", changelog.get_file_path())
            changelog.write_to_file()

            if bump_versions:
                from changelogmanager.version_bumper import (
                    bump_version_files,
                )  # noqa: PLC0415

                logger.info(
                    "Bumping companion version files to %s (pyproject_only=%s)",
                    new_version,
                    pyproject_only,
                )
                bumped = bump_version_files(
                    new_version,
                    pyproject_only=pyproject_only,
                    project_root=scope.root if scope else None,
                    version_files=scope.version_files if scope else None,
                    versioning_scheme=changelog.versioning_scheme,
                )
                result.bumped_files = [str(p) for p in bumped]
                logger.debug(
                    "Bumped files for release %s: %s",
                    new_version,
                    ", ".join(result.bumped_files) or "<none>",
                )
    except Exception:
        changelog.changelog = original_data
        raise

    return result


# ----------------------------------------------------------------------
# from-commits / unreleased seeding
# ----------------------------------------------------------------------


def git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise FileNotFoundError("git executable not found on PATH")
    return git


def gh_executable() -> str | None:
    """Returns the path to the ``gh`` CLI, or *None* if it is not on PATH."""
    return shutil.which("gh")


def git_repo_from_remote(remote: str = "origin") -> str | None:
    """Infers ``owner/repo`` from the git remote URL (SSH or HTTPS).

    Returns *None* when git is unavailable or the remote URL cannot be parsed.
    """
    import re  # noqa: PLC0415

    try:
        result = subprocess.run(  # nosec B603
            [git_executable(), "remote", "get-url", remote],
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None

    url = result.stdout.strip()
    # SSH: git@github.com:owner/repo.git
    m = re.match(r"git@[^:]+:([^/]+/[^/.]+)(?:\.git)?$", url)
    if m:
        return m.group(1)
    # HTTPS: https://github.com/owner/repo.git  or  https://github.com/owner/repo
    m = re.match(r"https?://[^/]+/([^/]+/[^/.]+?)(?:\.git)?$", url)
    if m:
        return m.group(1)
    return None


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
    from changelogmanager.commit_routing import (
        route_commit,  # noqa: PLC0415
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
        path = resolve_config_file(config_path, str(component.get("changelog")))
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


_VALID_SOURCES = {
    "tags",
    "commits",
    "local",
    "all",
    "github-releases",
    "github-prs",
    "pypi",
}


def validate_backfill_options(
    *,
    source: str,
    strategy: str,
    missing_only: bool,
    repository: str | None = None,
    package: str | None = None,
) -> None:
    """Raises if the requested backfill option combination is unsupported."""

    if source not in _VALID_SOURCES:
        raise logging.Error(
            message=(
                f"Unknown backfill source '{source}'; valid choices are: "
                + ", ".join(sorted(_VALID_SOURCES))
            ),
        )

    if source in {"github-releases", "github-prs"} and not repository:
        raise logging.Error(
            message=f"--repository owner/repo is required when --source {source} is used",
        )

    if source == "pypi" and not package:
        raise logging.Error(
            message="--package name is required when --source pypi is used",
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
    repository: str | None = None,
    token: str | None = None,
    package: str | None = None,
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
        repository=repository,
        token=token,
        package=package,
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

    from changelogmanager.backfill import MAX_COMMITS_DEFAULT  # noqa: PLC0415
    from changelogmanager.backfill import plan_unreleased_backfill as _impl

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
        path = resolve_config_file(config_path, path)
        if changed is not None and Path(path).resolve() not in {
            Path(item).resolve() for item in changed
        }:
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
    if not Path(path).is_file():
        raise logging.Error(file_path=path, message="Changelog file does not exist")
    original_text = Path(path).read_text(encoding="UTF-8")

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
        atomic_write_text(Path(path), final_text)

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
    scope: ReleaseScope | None = None,
    version: str | None = None,
) -> GitHubReleaseResult:
    """Creates or updates a GitHub release from the changelog."""

    from changelogmanager.versioning import parse_version

    notes_version = UNRELEASED_ENTRY
    if version:
        raw_version = scope.version(version) if scope else version.removeprefix("v")
        try:
            selected = parse_version(raw_version, changelog.versioning_scheme)
        except ValueError as exc:
            raise logging.Error(
                message=f"Invalid {changelog.versioning_scheme} version: {raw_version}"
            ) from exc
        # Existing sections are published as-is; a new version uses Unreleased.
        notes_version = next(
            (
                key
                for key in changelog.get()
                if key != UNRELEASED_ENTRY
                and parse_version(key, changelog.versioning_scheme) == selected
            ),
            UNRELEASED_ENTRY,
        )
        if notes_version == UNRELEASED_ENTRY:
            preview = deepcopy(changelog)
            preview.release(str(selected))
    else:
        if not changelog.has_unreleased():
            return GitHubReleaseResult(skipped=True)
        selected = changelog.suggest_future_version()
    tag = scope.tag(str(selected)) if scope else f"v{selected}"
    if dry_run:
        return GitHubReleaseResult(
            dry_run=True,
            release_state="draft" if draft else "published",
            version=str(selected),
            tag_name=tag,
        )

    from changelogmanager.github import GitHub

    github = GitHub(repository=repository, token=token)
    options: dict[str, Any] = {"tag_name": tag} if scope else {}
    if version:
        options.update(version=str(selected), notes_version=notes_version)
    release = github.create_release(changelog=changelog, draft=draft, **options)
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


def _run_git(
    args: list[str], *, check: bool = True
) -> subprocess.CompletedProcess[str]:
    """Runs a git command, raising a diagnostic ``logging.Error`` on failure."""

    cmd = [git_executable(), *args]
    logger.info("Running git %s", " ".join(args))
    try:
        return subprocess.run(  # nosec B603
            cmd, check=check, capture_output=True, text=True
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        stderr = getattr(exc, "stderr", "") or ""
        raise logging.Error(
            message=f"git {args[0]} failed: {exc}\n{stderr}".rstrip(),
        ) from exc


@dataclass
class ReleaseBumpResult:
    """Outcome of a ``release-bump`` run.

    Captures everything the CI step needs to emit as job outputs: the resolved
    ``version``, the ``branch`` that was pushed, whether a commit was actually
    created (``committed``), and the opened PR (``pr_number`` / ``html_url``)
    when ``open_pr`` was requested.
    """

    version: str
    branch: str
    committed: bool = False
    skip_ci: bool = False
    pushed: bool = False
    pr_number: Any = None
    html_url: str | None = None
    dry_run: bool = False
    commit_sha: str | None = None
    changed_files: list[str] = field(default_factory=list)


def release_bump(
    *,
    changelog: Changelog,
    version: str,
    base: str,
    branch: str,
    repository: str,
    token: str | None = None,
    skip_ci: bool = True,
    open_pr: bool = False,
    pr_title: str | None = None,
    pr_body: str | None = None,
    pyproject_only: bool = False,
    dry_run: bool = False,
    scope: ReleaseScope | None = None,
) -> ReleaseBumpResult:
    """Bumps the changelog + version files, commits, pushes a branch, opens a PR.

    This is the presentation-free equivalent of the ~80 lines of shell that used
    to live in the ``bump`` job of ``release.yml``: it centralizes the branch,
    ``[skip ci]`` decision, ``--force-with-lease`` push and PR creation so the
    workflow shrinks to a single command and the behaviour is unit-testable.
    """

    normalized = scope.version(version) if scope else version.lstrip("v")

    if dry_run:
        release_changelog(
            changelog,
            normalized,
            bump_versions=True,
            pyproject_only=pyproject_only,
            dry_run=True,
            scope=scope,
        )
        return ReleaseBumpResult(
            version=normalized,
            branch=branch,
            skip_ci=skip_ci,
            dry_run=True,
        )

    if _run_git(["status", "--porcelain", "--untracked-files=no"]).stdout.strip():
        raise logging.Error(
            message="Release bump requires a clean working tree; commit or stash unrelated changes first"
        )

    # 1. Bump changelog + version files on disk (the only place versions are
    #    written into the repo).
    released = release_changelog(
        changelog,
        normalized,
        bump_versions=True,
        pyproject_only=pyproject_only,
        scope=scope,
    )

    # 2. Create the bump branch off HEAD (the caller checked out `base`).
    _run_git(["checkout", "-B", branch])

    # 3. Stage only the selected changelog and version files changed by the bump.
    _run_git(["add", "--", str(changelog.get_file_path()), *released.bumped_files])

    # 4. Nothing to commit means the version was already bumped; surface it.
    staged = _run_git(["diff", "--cached", "--quiet"], check=False)
    if staged.returncode == 0:
        raise logging.Error(
            message=(
                "No files changed after release --bump-versions; is the version "
                f"{normalized} already released?"
            ),
        )

    suffix = " [skip ci]" if skip_ci else ""
    _run_git(["commit", "-m", f"chore: release {normalized}{suffix}"])

    result = ReleaseBumpResult(
        version=normalized,
        branch=branch,
        committed=True,
        commit_sha=_run_git(["rev-parse", "HEAD"]).stdout.strip(),
        changed_files=[str(changelog.get_file_path()), *released.bumped_files],
        skip_ci=skip_ci,
    )

    # 5. Push with --force-with-lease when the branch already exists remotely so
    #    a re-run updates it instead of failing.
    remote = _run_git(["ls-remote", "--heads", "origin", branch], check=False)
    remote_sha = remote.stdout.split()[0] if remote.stdout.strip() else ""
    if remote_sha:
        _run_git(
            [
                "push",
                f"--force-with-lease=refs/heads/{branch}:{remote_sha}",
                "origin",
                f"HEAD:refs/heads/{branch}",
            ]
        )
    else:
        _run_git(["push", "origin", f"HEAD:refs/heads/{branch}"])
    result.pushed = True

    # 6. Optionally open the release PR, reusing the github-pr code path.
    if open_pr:
        if not token:
            raise logging.Error(
                message="--open-pr requires a GitHub token (pass --github-token or set GITHUB_TOKEN)",
            )
        title = pr_title or f"chore: release {normalized}"
        if skip_ci and "[skip ci]" not in title:
            title = f"{title} [skip ci]"
        body = pr_body or f"Automated release PR for **{normalized}**."
        pr = github_pull_request(
            repository=repository,
            token=token,
            head=branch,
            base=base,
            title=title,
            body=body,
        )
        result.pr_number = pr.pr_number
        result.html_url = pr.html_url

    return result


@dataclass
class ReleaseRollbackResult:
    """Outcome of a ``release-rollback`` run.

    Records which pieces actually existed and were removed so the caller can
    report a partial rollback (e.g. the git tag was gone but the GitHub release
    was still present).
    """

    tag: str
    release_deleted: bool = False
    release_missing: bool = False
    local_tag_deleted: bool = False
    remote_tag_deleted: bool = False
    dry_run: bool = False


def release_rollback(
    *,
    tag: str,
    repository: str,
    token: str | None,
    delete_release: bool = True,
    delete_local_tag: bool = True,
    delete_remote_tag: bool = True,
    remote: str = "origin",
    dry_run: bool = False,
) -> ReleaseRollbackResult:
    """Rolls back a failed release: deletes the GitHub release and the git tag.

    Prefers the ``gh`` CLI when it is available (no token needed in that case).
    Falls back to the GitHub REST API when ``gh`` is absent and *token* is set.

    The presentation-free equivalent of the manual::

        gh release delete <tag> -y --repo <repo>
        git tag -d <tag>
        git push --delete <remote> <tag>

    Each step is independently guarded so a missing release or tag is reported
    rather than aborting the whole rollback.
    """
    result = ReleaseRollbackResult(tag=tag, dry_run=dry_run)

    # 1. GitHub release. In dry-run we make no network calls at all (so no token
    # is required) and simply report the intent to delete.
    if delete_release and dry_run:
        logger.info("Would delete GitHub release %s from %s", tag, repository)
        result.release_deleted = True
    elif delete_release:
        gh = gh_executable()
        if gh:
            # Prefer the gh CLI — no explicit token required (gh uses its own auth).
            cmd = [gh, "release", "delete", tag, "--yes"]
            if repository:
                cmd += ["--repo", repository]
            logger.info("Running gh release delete %s", tag)
            proc = subprocess.run(cmd, capture_output=True, text=True)  # nosec B603
            if proc.returncode == 0:
                result.release_deleted = True
            else:
                stderr = proc.stderr.strip()
                # gh exits non-zero with "not found" wording when the release is absent
                if "not found" in stderr.lower() or "could not find" in stderr.lower():
                    result.release_missing = True
                    logger.warning(
                        "No GitHub release found for tag %s in %s", tag, repository
                    )
                else:
                    raise logging.Error(
                        message=f"gh release delete failed: {stderr or proc.stdout.strip()}",
                    )
        else:
            # Fall back to the REST API.
            from changelogmanager.github import GitHub  # noqa: PLC0415

            if not token:
                raise logging.Error(
                    message=(
                        "Deleting the GitHub release requires either the gh CLI on PATH "
                        "or a token (pass --github-token or set GITHUB_TOKEN)"
                    ),
                )
            github = GitHub(repository=repository, token=token)
            release = github.find_release_by_tag(tag)
            if release is None:
                result.release_missing = True
                logger.warning(
                    "No GitHub release found for tag %s in %s", tag, repository
                )
            else:
                github.delete_release(release)
                result.release_deleted = True

    # 2. Local git tag (ignore "not found" so rollback is idempotent).
    if delete_local_tag:
        if dry_run:
            logger.info("Would delete local git tag %s", tag)
            result.local_tag_deleted = True
        else:
            deleted = _run_git(["tag", "-d", tag], check=False)
            result.local_tag_deleted = deleted.returncode == 0
            if not result.local_tag_deleted:
                logger.warning("Local git tag %s not found (already deleted?)", tag)

    # 3. Remote git tag.
    if delete_remote_tag:
        if dry_run:
            logger.info("Would delete remote git tag %s from %s", tag, remote)
            result.remote_tag_deleted = True
        else:
            deleted = _run_git(["push", "--delete", remote, tag], check=False)
            result.remote_tag_deleted = deleted.returncode == 0
            if not result.remote_tag_deleted:
                logger.warning(
                    "Remote git tag %s not found on %s (already deleted?)", tag, remote
                )

    return result


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
    scope: ReleaseScope | None = None,
) -> GitLabReleaseResult:
    """Creates or updates a GitLab release from the changelog."""

    if not changelog.has_unreleased():
        return GitLabReleaseResult(skipped=True)

    if dry_run:
        future_version = changelog.suggest_future_version()
        return GitLabReleaseResult(
            dry_run=True,
            version=str(future_version),
            tag_name=scope.tag(str(future_version)) if scope else f"v{future_version}",
        )

    from changelogmanager.gitlab import GitLab  # noqa: PLC0415

    gitlab = GitLab(project=project, token=token, gitlab_url=gitlab_url)
    release = gitlab.create_release(
        changelog=changelog,
        ref=ref,
        **(
            {"tag_name": scope.tag(str(changelog.suggest_future_version()))}
            if scope
            else {}
        ),
    )
    links = release.get("_links")
    web_url = str(links.get("self", "") if isinstance(links, Mapping) else "").strip()
    return GitLabReleaseResult(
        tag_name=str(release.get("tag_name", "")),
        web_url=web_url or None,
    )
