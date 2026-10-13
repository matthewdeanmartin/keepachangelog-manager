"""Resolved component settings and read-only configuration inspection."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from changelogmanager import fragments
from changelogmanager.config import (
    get_component_from_config,
    get_components_from_config,
    get_effective_configuration,
    get_fragments_options,
    resolve_config_file,
)
from changelogmanager.release_scope import resolve_release_scopes


def resolve_fragment_directory(
    config: str | None, component: str, explicit: str | None = None
) -> Path:
    """CLI paths use cwd; component and global paths use the config directory."""
    settings: dict[str, Any] = (
        get_component_from_config(config, component) if config else {}
    )
    if explicit:
        return Path(explicit)
    options = get_fragments_options(config)
    directory = settings.get("fragment_directory") or options.get("directory")
    if directory:
        return Path(resolve_config_file(config, directory))
    root = Path(config).resolve().parent if config else Path.cwd()
    for candidate in fragments.FRAGMENT_DIR_CANDIDATES:
        path = root / candidate
        if path.is_dir():
            return path
    return root / fragments.FRAGMENT_DIR_CANDIDATES[0]


def inspect_components(config: str) -> list[dict[str, Any]]:
    """Expose effective paths, inherited settings, and readiness without mutations."""
    from changelogmanager.commit_routing import component_match_globs
    from changelogmanager.tasks import discover_task_file
    from changelogmanager.version_bumper import version_file_issue

    components = get_components_from_config(config)
    scopes = resolve_release_scopes(config, components)
    project = get_effective_configuration(config)["project"]
    inherited = {
        key: project.get(key, {})
        for key in ("versioning", "validation", "defaults", "tasks", "fragments")
    }
    for key, fields in (
        ("github", ("repository",)),
        ("gitlab", ("project", "url")),
        ("pypi", ("package",)),
    ):
        inherited[key] = {
            field: project.get(key, {})[field]
            for field in fields
            if field in project.get(key, {})
        }
    fallbacks = [item["name"] for item in components if not component_match_globs(item)]
    result = []
    for item in components:
        name = item["name"]
        scope = scopes[name]
        changelog = Path(resolve_config_file(config, item["changelog"])).resolve()
        tasks_file = item.get("tasks_file") or project.get("tasks", {}).get("file")
        tasks_path = (
            Path(resolve_config_file(config, tasks_file))
            if tasks_file
            else discover_task_file()
        )
        fragment_dir = resolve_fragment_directory(config, name).resolve()
        issues = []
        warnings = []
        bump_issues = []
        if not changelog.is_file():
            issues.append(f"Changelog file does not exist: {changelog}")
        if scope.monorepo and scope.version_files is None:
            bump_issues.append(
                "Version bumps require explicit version_files in a multi-component project"
            )
        for path in scope.version_files or ():
            issue = version_file_issue(path)
            if issue:
                bump_issues.append(issue)
        if scope.version_files is not None or project.get("defaults", {}).get(
            "bump_versions", False
        ):
            issues.extend(bump_issues)
        else:
            warnings.extend(bump_issues)
        routing_issues = (
            [
                f"Commit routing needs at most one fallback component (without 'match'); found multiple: {', '.join(fallbacks)}"
            ]
            if len(fallbacks) > 1
            else []
        )
        result.append(
            {
                "name": name,
                "changelog": str(changelog),
                "tasks_file": str(tasks_path.resolve()),
                "fragment_directory": str(fragment_dir),
                "fragment_source": (
                    "component"
                    if item.get("fragment_directory")
                    else (
                        "global"
                        if project.get("fragments", {}).get("directory")
                        else "discovery"
                    )
                ),
                "match": component_match_globs(item),
                "fallback": not component_match_globs(item),
                "version_files": (
                    [str(path) for path in scope.version_files]
                    if scope.version_files is not None
                    else None
                ),
                "version_file_selection": (
                    "explicit"
                    if scope.version_files is not None
                    else "required" if scope.monorepo else "automatic"
                ),
                "tag_template": scope.tag_template,
                "example_tag": scope.tag("0.1.0"),
                "release_branch_template": (
                    f"release/{name}/bump-{{version}}"
                    if scope.monorepo
                    else "release/bump-{version}"
                ),
                "inherited": inherited,
                "issues": issues,
                "warnings": warnings,
                "version_bump_ready": not bump_issues,
                "routing_issues": routing_issues,
            }
        )
    return result
