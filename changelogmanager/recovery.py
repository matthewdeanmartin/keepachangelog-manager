"""Plan and resume failed-release recovery without rewriting shared history."""

from __future__ import annotations

import difflib
import hashlib
import json
import re
import subprocess  # nosec B404 - executable argv only; no shell interpolation
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import urlopen

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.file_updates import atomic_write_text, rollback_file_updates
from changelogmanager.release_scope import ReleaseScope


def git(*args: str) -> str:
    from changelogmanager.services import _run_git

    return _run_git(list(args)).stdout.strip()


def root_path() -> Path:
    return Path(git("rev-parse", "--show-toplevel")).resolve()


def safe_path(root: Path, name: str) -> Path:
    path = (root / name).resolve()
    if (
        not path.is_relative_to(root)
        or path == root
        or ".git" in {part.lower() for part in path.parts}
    ):
        raise logging.Error(message=f"Recovery path escapes the working tree: {name}")
    return path


def manifest_name(tag: str) -> str:
    return f".kaclm/releases/{hashlib.sha256(tag.encode()).hexdigest()}.json"


def record_manifest(
    *,
    tag: str,
    version: str,
    base_sha: str,
    changelog: str,
    files: list[str],
    scope: ReleaseScope,
    repository: str,
    release_id: str | None = None,
) -> Path:
    """Commit the provenance with the bump; its containing commit is the bump SHA."""
    root = root_path()

    def relative(value: str) -> str:
        return Path(value).resolve().relative_to(root).as_posix()

    path = safe_path(root, manifest_name(tag))
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(
        path,
        json.dumps(
            {
                "schema": 1,
                "tag": tag,
                "version": version,
                "base_sha": base_sha,
                "component": scope.component,
                "repository": repository,
                "release_id": release_id,
                "tag_sha": tag_sha(tag),
                "changelog": relative(changelog),
                "version_files": [relative(value) for value in files],
            },
            indent=2,
        )
        + "\n",
    )
    return path


def read_at(sha: str, name: str) -> str:
    from changelogmanager.services import _run_git

    return _run_git(["show", f"{sha}:{name}"]).stdout


def inverse_versions(before: str, after: str, current: str, name: str) -> str:
    """Invert only version assignments; merge against current to retain later edits."""
    old, new = before.splitlines(keepends=True), after.splitlines(keepends=True)
    replacements: list[tuple[str, str]] = []
    assignment = re.compile(
        r"^\s*(?:version|__version__)(?:\s*:\s*str)?\s*=\s*['\"][^'\"]+['\"]\s*(?:#.*)?$"
    )
    for kind, a, b, c, d in difflib.SequenceMatcher(a=old, b=new).get_opcodes():
        if kind == "equal":
            continue
        if (
            kind != "replace"
            or b - a != d - c
            or not all(assignment.match(line) for line in old[a:b] + new[c:d])
        ):
            raise logging.Error(
                message=f"Ambiguous bump in {name}: changes are not limited to version assignments"
            )
        replacements.extend(zip(old[a:b], new[c:d], strict=True))
    if not replacements or current == before:
        return current
    lines = current.splitlines(keepends=True)
    for previous, bumped in replacements:
        # Match only unique assignments, never an arbitrary matching dependency.
        if new.count(bumped) == 1 and lines.count(bumped) == 1:
            lines[lines.index(bumped)] = previous
        elif (
            old.count(previous) != 1
            or new.count(previous)
            or lines.count(previous) != 1
            or lines.count(bumped)
        ):
            raise logging.Error(
                message=f"Version restoration conflicts in {name}; resolve the changed version manually"
            )
    return "".join(lines)


def restore_notes(
    before: str, after: str, current: str, version: str, scheme: str
) -> str:
    reader = ChangelogReader(versioning_scheme=scheme)
    previous, released, present = (
        reader.read(text=value) for value in (before, after, current)
    )
    if version not in released or version in previous:
        raise logging.Error(
            message=f"Bump commit does not introduce changelog version {version}"
        )
    history = [key for key in present if key != "unreleased"]
    if version in history and history[0] != version:
        raise logging.Error(message="Cannot restore a release beneath a newer release")
    result = deepcopy(present)
    unreleased = result.setdefault(
        "unreleased", {"metadata": {"version": "unreleased"}}
    )
    entries = result.pop(version, None)
    if entries is None:
        # A manual heading restoration is safe only when the original notes survived.
        for category, values in released[version].items():
            if category != "metadata" and any(
                value not in unreleased.get(category, []) for value in values
            ):
                raise logging.Error(
                    message="Release section is absent and its entries are not all in Unreleased"
                )
    else:
        for category, values in entries.items():
            if category != "metadata":
                bucket = unreleased.setdefault(category, [])
                bucket.extend(value for value in values if value not in bucket)
    old_url = previous.get("unreleased", {}).get("metadata", {}).get("url")
    if old_url:
        unreleased.setdefault("metadata", {})["url"] = old_url
    ordered = {
        "unreleased": unreleased,
        **{key: value for key, value in result.items() if key != "unreleased"},
    }
    rendered = Changelog(changelog=ordered, versioning_scheme=scheme).render()
    violations = reader.strict_violations(reader.read(text=rendered), text=rendered)
    if violations:
        raise logging.Error(
            message="Recovered changelog is invalid: " + "; ".join(violations)
        )
    return current if present == ordered else rendered


def plan_recovery(
    *,
    tag: str,
    scope: ReleaseScope,
    changelog: str,
    scheme: str,
    bump_commit: str | None,
    restore_unreleased: bool,
    restore_versions: bool,
) -> dict[str, Any]:
    root = root_path()
    name = Path(changelog).resolve().relative_to(root).as_posix()
    if git("status", "--porcelain", "--untracked-files=no"):
        raise logging.Error(
            message="Recovery requires a clean working tree; commit or stash local edits first"
        )
    manifest = safe_path(root, manifest_name(tag))
    data: dict[str, Any] = {}
    if not bump_commit:
        if not manifest.is_file():
            raise logging.Error(
                message="No release manifest found; specify --bump-commit SHA for this older release"
            )
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise logging.Error(message=f"Cannot read release manifest: {exc}") from exc
        if (
            not isinstance(data, dict)
            or data.get("schema") != 1
            or data.get("tag") != tag
            or data.get("component") != scope.component
            or data.get("changelog") != name
        ):
            raise logging.Error(
                message="Release manifest does not match the selected tag/component/changelog"
            )
        bump_commit = git("log", "-1", "--format=%H", "--", str(manifest))
    sha = git("rev-parse", "--verify", f"{bump_commit}^{{commit}}")
    parents = git("rev-list", "--parents", "-n", "1", sha).split()
    if len(parents) != 2:
        raise logging.Error(
            message="Select the original single-parent bump commit, not its merge commit"
        )
    base = parents[1]
    if data and data.get("base_sha") != base:
        raise logging.Error(message="Release manifest base differs from bump parent")
    git("merge-base", "--is-ancestor", sha, "HEAD")
    scope.require_version_files()
    version = scope.version(tag)
    # Prove the selected commit belongs to this release even for versions-only recovery.
    reader = ChangelogReader(versioning_scheme=scheme)
    previous = read_at(base, name)
    bumped = read_at(sha, name)
    if version not in reader.read(text=bumped) or version in reader.read(text=previous):
        raise logging.Error(message=f"Commit {sha} is not the bump for {tag}")
    changed = git("diff-tree", "--no-commit-id", "--name-only", "-r", sha).splitlines()
    if scope.version_files is not None:
        allowed = {
            path.resolve().relative_to(root).as_posix() for path in scope.version_files
        }
    else:
        from changelogmanager.version_bumper import plan_version_files

        allowed = {
            path.resolve().relative_to(root).as_posix()
            for path in plan_version_files(project_root=scope.root)
        }
        allowed.update(
            (scope.root.resolve() / item).relative_to(root).as_posix()
            for item in ("Cargo.toml", "Cargo.lock", "uv.lock")
        )
    files = []
    for filename in changed:
        if filename == name and restore_unreleased:
            path = safe_path(root, filename)
            current = path.read_text(encoding="utf-8")
            target = restore_notes(previous, bumped, current, version, scheme)
        elif filename in allowed and restore_versions:
            path = safe_path(root, filename)
            current = path.read_text(encoding="utf-8")
            target = inverse_versions(
                read_at(base, filename), read_at(sha, filename), current, filename
            )
        else:
            continue
        files.append(
            {
                "path": filename,
                "before": current,
                "after": target,
                "status": "planned" if current != target else "already_absent",
            }
        )
    return {
        "schema": 1,
        "tag": tag,
        "component": scope.component,
        "version": version,
        "bump_commit": sha,
        "base_sha": base,
        "head": git("rev-parse", "HEAD"),
        "root": str(root),
        "files": files,
        "actions": {},
        "release_id": data.get("release_id"),
        "recorded_tag_sha": data.get("tag_sha"),
        "recorded_repository": data.get("repository"),
    }


def tag_sha(tag: str, remote: str | None = None) -> str:
    from changelogmanager.services import _run_git

    git("check-ref-format", f"refs/tags/{tag}")
    if remote:
        output = git("ls-remote", "--refs", remote, f"refs/tags/{tag}")
        return output.split()[0] if output else ""
    result = _run_git(
        ["for-each-ref", "--format=%(refname) %(objectname)", f"refs/tags/{tag}"]
    )
    return next(
        (
            line.split()[1]
            for line in result.stdout.splitlines()
            if line.split()[0] == f"refs/tags/{tag}"
        ),
        "",
    )


def github_release(
    repository: str, tag: str, token: str | None, delete_id: Any = None
) -> dict[str, Any] | None:
    from changelogmanager.services import gh_executable

    gh = gh_executable()
    if not gh:
        from changelogmanager.github import GitHub

        if not token:
            raise logging.Error(
                message="GitHub cleanup requires gh authentication or a token"
            )
        client = GitHub(repository=repository, token=token)
        if delete_id is not None:
            client.delete_release({"id": delete_id})
            return None
        found = client.find_release_by_tag(tag)
        return dict(found) if found else None
    endpoint = f"repos/{repository}/releases/" + (
        str(delete_id) if delete_id is not None else "tags/" + quote(tag, safe="")
    )
    command = [gh, "api", endpoint]
    if delete_id is not None:
        command += ["--method", "DELETE"]
    result = subprocess.run(
        command, capture_output=True, text=True, check=False
    )  # nosec B603
    if result.returncode:
        if "HTTP 404" in result.stderr and delete_id is None:
            return None
        raise logging.Error(
            message=f"GitHub recovery request failed: {result.stderr.strip()}"
        )
    return json.loads(result.stdout) if result.stdout.strip() else None


def execute_recovery(
    plan: dict[str, Any],
    *,
    repository: str,
    token: str | None,
    remote: str,
    delete_release: bool,
    delete_local_tag: bool,
    delete_remote_tag: bool,
    commit: bool,
    push: bool,
    dry_run: bool,
    receipt: Path | None = None,
    check_pypi: str | None = None,
) -> dict[str, Any]:
    """Validate first, record progress after each step, and resume the exact plan."""
    if push and not commit:
        raise logging.Error(message="--push requires --commit")
    root = root_path()
    if str(root) != plan["root"]:
        raise logging.Error(message="Recovery receipt belongs to another checkout")
    if plan.get("recorded_repository") and repository != plan["recorded_repository"]:
        raise logging.Error(message="Repository differs from the release manifest")
    selected = {
        "files": True,
        "github": delete_release,
        "remote_tag": delete_remote_tag,
        "local_tag": delete_local_tag,
        "commit": commit,
        "push": push,
    }
    options = {
        "repository": repository,
        "remote": remote,
        "check_pypi": check_pypi,
        **selected,
    }
    if "options" in plan and plan["options"] != options:
        raise logging.Error(
            message="Resume with the same action flags, repository, and remote as the receipt"
        )
    plan["options"] = options
    actions = plan["actions"]
    for action, enabled in selected.items():
        actions.setdefault(action, "planned" if enabled else "skipped")
    if dry_run:
        plan["dry_run"] = True
        plan["publication_check"] = (
            "not checked (offline dry-run); deleting GitHub artifacts never unpublishes packages"
        )
        return plan
    plan.pop("dry_run", None)
    if push:
        git("symbolic-ref", "--short", "HEAD")
    receipt = receipt or Path(git("rev-parse", "--git-path", "kaclm/recovery")) / (
        hashlib.sha256(plan["tag"].encode()).hexdigest() + ".json"
    )
    receipt = receipt.resolve()
    git_dir = Path(git("rev-parse", "--absolute-git-dir")).resolve()
    if not receipt.is_relative_to(git_dir):
        raise logging.Error(
            message="Recovery receipts must be inside this checkout's git directory"
        )
    plan["receipt"] = str(receipt)
    expected_head = plan.get("commit_sha", plan["head"])
    if git("rev-parse", "HEAD") != expected_head:
        raise logging.Error(
            message="HEAD changed since recovery was planned; inspect the receipt before continuing"
        )
    staged = set(git("diff", "--cached", "--name-only").splitlines())
    planned_names = {item["path"] for item in plan["files"]}
    if staged and (actions.get("commit") != "failed" or staged - planned_names):
        raise logging.Error(message="Recovery requires an empty index")
    dirty = set(git("diff", "--name-only").splitlines())
    if dirty - planned_names:
        raise logging.Error(
            message="Commit or stash unrelated working-tree changes first"
        )
    for item in plan["files"]:
        current = safe_path(root, item["path"]).read_text(encoding="utf-8")
        permitted = (
            (item["after"],)
            if actions["files"] in {"succeeded", "already_absent"}
            else (item["before"], item["after"])
        )
        if current not in permitted:
            raise logging.Error(
                message=f"Recovery file changed since planning: {item['path']}"
            )

    def save() -> None:
        receipt.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(receipt, json.dumps(plan, indent=2) + "\n")

    # Inspect identities before any mutation; retries retain the original identities.
    if check_pypi:
        published = pypi_published(check_pypi, plan["version"])
        plan["publication_check"] = (
            f"{check_pypi} {plan['version']} is published on PyPI; use a NEW version for the next release"
            if published
            else f"No files currently published for {check_pypi} {plan['version']} on PyPI"
        )
    if delete_release and "github_id" not in plan:
        found = github_release(repository, plan["tag"], token)
        plan["github_id"] = found["id"] if found else None
        if (
            plan.get("release_id")
            and str(plan["github_id"]) != str(plan["release_id"])
            and found
        ):
            raise logging.Error(
                message="GitHub release ID differs from the recorded release"
            )
    for action, enabled, target in (
        ("remote_tag", delete_remote_tag, remote),
        ("local_tag", delete_local_tag, None),
    ):
        if enabled and action + "_sha" not in plan:
            plan[action + "_sha"] = tag_sha(plan["tag"], target)
            if (
                plan.get("recorded_tag_sha")
                and plan[action + "_sha"]
                and plan[action + "_sha"] != plan["recorded_tag_sha"]
            ):
                raise logging.Error(
                    message=f"{action} differs from the release manifest"
                )
    save()
    for action, enabled in selected.items():
        if not enabled or actions[action] in {"succeeded", "already_absent"}:
            continue
        try:
            state = "succeeded"
            if action == "files":
                paths = [safe_path(root, item["path"]) for item in plan["files"]]
                with rollback_file_updates(paths):
                    for path, item in zip(paths, plan["files"], strict=True):
                        atomic_write_text(path, item["after"])
                        item["status"] = (
                            "succeeded"
                            if item["before"] != item["after"]
                            else "already_absent"
                        )
                if all(item["before"] == item["after"] for item in plan["files"]):
                    state = "already_absent"
            elif action == "github":
                found = github_release(repository, plan["tag"], token)
                if not found:
                    state = "already_absent"
                elif found["id"] != plan["github_id"]:
                    raise logging.Error(message="GitHub release changed since planning")
                else:
                    github_release(
                        repository, plan["tag"], token, delete_id=found["id"]
                    )
            elif action in {"remote_tag", "local_tag"}:
                target = remote if action == "remote_tag" else None
                current = tag_sha(plan["tag"], target)
                if not current:
                    state = "already_absent"
                elif current != plan[action + "_sha"]:
                    raise logging.Error(message=f"{action} changed since planning")
                elif target:
                    ref = "refs/tags/" + plan["tag"]
                    git(
                        "push", f"--force-with-lease={ref}:{current}", remote, f":{ref}"
                    )
                else:
                    git("update-ref", "-d", "refs/tags/" + plan["tag"], current)
            elif action == "commit":
                names = [item["path"] for item in plan["files"]]
                if names:
                    git("add", "--", *names)
                if not git("diff", "--cached", "--name-only"):
                    state = "already_absent"
                else:
                    git("commit", "-m", f"chore: recover failed release {plan['tag']}")
                    plan["commit_sha"] = git("rev-parse", "HEAD")
            elif action == "push":
                branch = git("symbolic-ref", "--short", "HEAD")
                git("push", remote, f"HEAD:refs/heads/{branch}")
            actions[action] = state
            plan.pop("error", None)
            save()
        except (logging.Error, OSError) as exc:
            actions[action] = "failed"
            plan["error"] = str(exc)
            save()
            raise logging.Error(
                message=f"Recovery stopped at {action}; resume with --resume {receipt}: {exc}"
            ) from exc
    plan.setdefault(
        "publication_check",
        "Package publication is unchanged; check the package index before reusing this version",
    )
    save()
    return plan


def pypi_published(package: str, version: str) -> bool:
    """Inspect the exact version; an unavailable index is not evidence of absence."""
    from packaging.version import Version

    try:
        url = f"https://pypi.org/pypi/{quote(package, safe='')}/{quote(str(Version(version)), safe='')}/json"
        with urlopen(url, timeout=15) as response:  # nosec B310
            return bool(json.load(response).get("urls"))
    except HTTPError as exc:
        if exc.code == 404:
            return False
        raise logging.Error(
            message=f"PyPI publication check failed: HTTP {exc.code}"
        ) from exc
    except (URLError, OSError, ValueError) as exc:
        raise logging.Error(message=f"PyPI publication check failed: {exc}") from exc
