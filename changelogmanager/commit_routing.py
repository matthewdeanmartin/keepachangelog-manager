# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Route git commits to components by the files they touch.

A component may declare ``match`` globs in config. A commit is attributed to a
component when any file it touches matches that component's globs. A component with
no ``match`` globs is the fallback for commits that match nothing.
"""

from __future__ import annotations

import fnmatch
import shutil
import subprocess  # nosec
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache, cached_property
from pathlib import Path
from typing import Any

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.release_scope import ReleaseScope, release_scope
from changelogmanager.runtime_logging import VERBOSE, get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class ComponentHistory:
    """The release namespace and file routing used by one component's history."""

    release: ReleaseScope
    components: Sequence[Mapping[str, Any]]

    @property
    def cwd(self) -> str:
        return str(self.release.root)

    def owns(self, files: Sequence[str]) -> bool:
        return self.release.component in route_commit(files, self.routing_components)

    @cached_property
    def routing_components(self) -> Sequence[Mapping[str, Any]]:
        validate_routing_components(self.components, config_path=self.cwd)
        return self.components


def component_history(config: str | None, component: str) -> ComponentHistory | None:
    if not config:
        return None
    from changelogmanager.config import get_components_from_config

    components = get_components_from_config(config)
    return ComponentHistory(release_scope(config, component), components)


@dataclass(frozen=True)
class CommitWithFiles:
    """A commit subject together with the repository paths it touched."""

    subject: str
    files: tuple[str, ...]
    sha: str = ""


def git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise logging.Error(message="git executable not found on PATH")
    return git


def git_log_with_files(
    since: str | None, *, cwd: str | Path | None = None, until: str = "HEAD"
) -> list[CommitWithFiles]:
    """Returns non-merge commits (subject + touched files) since a ref.

    Uses a record separator so multi-file commits parse unambiguously.
    """

    cmd = [
        git_executable(),
        "log",
        "--no-merges",
        "--name-only",
        "--pretty=format:\x1ecommit\x1e%H%x1f%s",
    ]
    if since:
        cmd.append(f"{since}..{until}")
    elif until != "HEAD":
        cmd.append(until)
    logger.info("Collecting commits with files since %s", since or "<all>")
    try:
        result = subprocess.run(  # nosec B603
            cmd, check=True, capture_output=True, text=True, cwd=cwd
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as exc:
        logger.error("git log --name-only failed: %s", exc)
        raise logging.Error(message=f"git log failed: {exc}") from exc

    return parse_log_with_files(result.stdout)


def parse_log_with_files(output: str) -> list[CommitWithFiles]:
    """Parses ``git log --name-only`` output delimited by our record separator."""

    commits: list[CommitWithFiles] = []
    # Each record starts with "\x1ecommit\x1e<subject>" then file lines.
    for chunk in output.split("\x1ecommit\x1e"):
        if not chunk.strip():
            continue
        lines = chunk.splitlines()
        header = lines[0].strip() if lines else ""
        sha, separator, subject = header.partition("\x1f")
        if not separator:
            subject, sha = header, ""
        files = tuple(line.strip() for line in lines[1:] if line.strip())
        if subject:
            commits.append(CommitWithFiles(subject=subject, files=files, sha=sha))
    return commits


def component_match_globs(component: Mapping[str, object]) -> list[str]:
    """Returns the normalized ``match`` glob list for a component (possibly empty)."""

    match = component.get("match")
    if isinstance(match, str):
        return [match]
    if isinstance(match, (list, tuple)):
        return [str(item) for item in match if str(item).strip()]
    return []


def file_matches(path: str, globs: Sequence[str]) -> bool:
    """Case-sensitive repository globs: * matches one segment, ** zero or more."""
    parts = tuple(path.replace("\\", "/").split("/"))

    def matches(pattern: tuple[str, ...]) -> bool:
        @cache
        def walk(i: int, j: int) -> bool:
            if j == len(pattern):
                return i == len(parts)
            if pattern[j] == "**":
                return walk(i, j + 1) or (i < len(parts) and walk(i + 1, j))
            return (
                i < len(parts)
                and fnmatch.fnmatchcase(parts[i], pattern[j])
                and walk(i + 1, j + 1)
            )

        return walk(0, 0)

    return any(matches(tuple(glob.replace("\\", "/").split("/"))) for glob in globs)


def route_commit(
    files: Sequence[str], components: Sequence[Mapping[str, object]]
) -> set[str]:
    """Returns the names of components a commit (by its files) is attributed to.

    A commit lands in every component whose ``match`` globs hit one of its files.
    If it matches no glob-bearing component, it lands in the fallback component
    (the one without ``match``), if any.
    """

    matched: set[str] = set()
    for component in components:
        globs = component_match_globs(component)
        if not globs:
            continue
        if any(file_matches(path, globs) for path in files):
            name = component.get("name")
            if isinstance(name, str):
                matched.add(name)

    if matched:
        return matched

    fallbacks = [
        str(component.get("name"))
        for component in components
        if not component_match_globs(component) and component.get("name")
    ]
    return {fallbacks[0]} if fallbacks else set()


def validate_routing_components(
    components: Sequence[Mapping[str, object]], *, config_path: str
) -> None:
    """Ensures at most one fallback (match-less) component exists for routing."""

    fallbacks = [c for c in components if not component_match_globs(c)]
    if len(fallbacks) > 1:
        names = ", ".join(str(c.get("name")) for c in fallbacks)
        raise logging.Error(
            file_path=config_path,
            message=(
                f"Commit routing needs at most one fallback component (without 'match'); found multiple: {names}"
            ),
        )
    logger.log(VERBOSE, "Routing components validated (%d total)", len(components))
