"""Component ownership of version files and release tag namespaces."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from string import Formatter
from typing import Any

import changelogmanager.llvm_diagnostics as logging


@dataclass(frozen=True)
class ReleaseScope:
    component: str = "default"
    root: Path = Path()
    version_files: tuple[Path, ...] | None = None
    tag_template: str = "v{version}"
    monorepo: bool = False

    def tag(self, version: str) -> str:
        return self.tag_template.format(component=self.component, version=version)

    def tag_parts(self) -> tuple[str, str]:
        prefix, suffix = self.tag_template.replace("{component}", self.component).split(
            "{version}"
        )
        return prefix, suffix

    def tag_pattern(self) -> str:
        prefix, suffix = self.tag_parts()
        return re.escape(prefix) + r"[0-9][0-9A-Za-z._!+-]*" + re.escape(suffix)

    def owns_tag(self, tag: str) -> bool:
        return re.fullmatch(self.tag_pattern(), tag) is not None

    def tag_glob(self) -> str:
        return self.tag_template.replace("{component}", self.component).replace(
            "{version}", "*"
        )

    def version(self, value: str) -> str:
        prefix, suffix = self.tag_parts()
        if re.fullmatch(self.tag_pattern(), value):
            return value[len(prefix) : len(value) - len(suffix) if suffix else None]
        if re.fullmatch(r"[0-9][0-9A-Za-z._!+-]*", value):
            return value
        raise logging.Error(
            message=f"Version/tag {value!r} does not match component {self.component!r} ({self.tag_template})"
        )

    def require_version_files(self) -> None:
        if self.monorepo and self.version_files is None:
            raise logging.Error(
                message=f"Component {self.component!r} requires explicit version_files in a multi-component project"
            )


def release_scope(config: str | None, component: str = "default") -> ReleaseScope:
    """Resolve paths from the config directory, never from an incidental working directory."""
    if not config:
        return ReleaseScope(root=Path.cwd())
    from changelogmanager.config import get_components_from_config

    scopes = resolve_release_scopes(config, get_components_from_config(config))
    if component not in scopes:
        raise logging.Error(message=f"Unknown component name: {component}")
    return scopes[component]


def resolve_release_scopes(
    config: str, components: Sequence[Mapping[str, Any]]
) -> dict[str, ReleaseScope]:
    """Validate release ownership without loading configuration recursively."""
    root = Path(config).resolve().parent
    scopes: dict[str, ReleaseScope] = {}
    owned: dict[Path, str] = {}
    tags: dict[str, str] = {}
    for item in components:
        name = item["name"]
        if name in scopes:
            raise logging.Error(
                file_path=config, message=f"Duplicate component name: {name}"
            )
        if len(components) > 1 and not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", name):
            raise logging.Error(
                message=f"Component {name!r} needs a simple identifier (letters, digits, hyphens, underscores) for release branches"
            )
        template = item.get(
            "tag_template",
            "{component}-v{version}" if len(components) > 1 else "v{version}",
        )
        try:
            fields = [
                field
                for literal, field, spec, conversion in Formatter().parse(template)
                if field is not None
            ]
            valid_fields = fields.count("version") == 1 and set(fields) <= {
                "version",
                "component",
            }
            plain_fields = all(
                not spec and not conversion
                for literal, field, spec, conversion in Formatter().parse(template)
            )
            sample = template.format(component=name, version="0.1.0")
            if (
                not valid_fields
                or not plain_fields
                or re.search(r"[\s~^:?*\[\\]|\.\.|@\{|//", sample)
            ):
                raise ValueError()
            if any(
                part.startswith(".") or part.endswith((".", ".lock")) or not part
                for part in sample.split("/")
            ):
                raise ValueError()
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise logging.Error(
                message=f"Invalid tag_template for component {name!r}: use {{version}} once and optionally {{component}}"
            ) from None
        if sample in tags:
            raise logging.Error(
                message=f"Components {tags[sample]!r} and {name!r} have colliding tag templates"
            )
        tags[sample] = name
        paths = None
        if "version_files" in item:
            values = item["version_files"]
            if (
                not isinstance(values, list)
                or not values
                or not all(isinstance(value, str) and value for value in values)
            ):
                raise logging.Error(
                    message=f"Component {name!r} version_files must be a nonempty list of paths"
                )
            resolved = []
            for value in values:
                path = (root / value).resolve()
                if Path(value).is_absolute() or not path.is_relative_to(root):
                    raise logging.Error(
                        message=f"Version file escapes the configuration directory: {value}"
                    )
                if path.name != "pyproject.toml" and path.suffix != ".py":
                    raise logging.Error(
                        message=f"Unsupported version file: {value}; use pyproject.toml or a Python file"
                    )
                if path in owned:
                    raise logging.Error(
                        message=f"Version file {value!r} is owned by both {owned[path]!r} and {name!r}"
                    )
                owned[path] = name
                resolved.append(path)
            paths = tuple(resolved)
        scope = ReleaseScope(name, root, paths, template, len(components) > 1)
        for other in scopes.values():
            prefix = max((scope.tag_parts()[0], other.tag_parts()[0]), key=len)
            suffix = max((scope.tag_parts()[1], other.tag_parts()[1]), key=len)
            witness = prefix + "0.1.0" + suffix
            if other.owns_tag(witness) and scope.owns_tag(witness):
                raise logging.Error(
                    file_path=config,
                    message=f"Components {other.component!r} and {name!r} have colliding tag templates",
                )
        scopes[name] = scope
    return scopes
