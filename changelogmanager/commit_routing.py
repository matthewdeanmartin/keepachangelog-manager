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

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.runtime_logging import VERBOSE, get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CommitWithFiles:
    """A commit subject together with the repository paths it touched."""

    subject: str
    files: tuple[str, ...]


def git_executable() -> str:
    git = shutil.which("git")
    if git is None:
        raise logging.Error(message="git executable not found on PATH")
    return git


def git_log_with_files(since: str | None) -> list[CommitWithFiles]:
    """Returns non-merge commits (subject + touched files) since a ref.

    Uses a record separator so multi-file commits parse unambiguously.
    """

    cmd = [
        git_executable(),
        "log",
        "--no-merges",
        "--name-only",
        "--pretty=format:\x1ecommit\x1e%s",
    ]
    if since:
        cmd.append(f"{since}..HEAD")
    logger.info("Collecting commits with files since %s", since or "<all>")
    try:
        result = subprocess.run(  # nosec B603
            cmd, check=True, capture_output=True, text=True
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
        subject = lines[0].strip() if lines else ""
        files = tuple(line.strip() for line in lines[1:] if line.strip())
        if subject:
            commits.append(CommitWithFiles(subject=subject, files=files))
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
    """Returns True if ``path`` matches any glob.

    ``**`` is treated as "match across directory separators" by also testing the
    path with separators collapsed, so ``api/**`` matches ``api/x/y.py``.
    """

    posix = path.replace("\\", "/")
    for glob in globs:
        if fnmatch.fnmatch(posix, glob):
            return True
        # fnmatch does not special-case "**"; emulate recursive match.
        if "**" in glob:
            simplified = glob.replace("**/", "*/").replace("**", "*")
            if fnmatch.fnmatch(posix, simplified):
                return True
            # api/** should also match the directory root "api/anything".
            prefix = glob.split("**", 1)[0].rstrip("/")
            if prefix and (posix == prefix or posix.startswith(prefix + "/")):
                return True
    return False


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
                "Commit routing needs at most one fallback component "
                f"(without 'match'); found multiple: {names}"
            ),
        )
    logger.log(VERBOSE, "Routing components validated (%d total)", len(components))
