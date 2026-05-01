# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Configuration Management"""

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

import yaml

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.runtime_logging import VERBOSE, get_logger

try:
    import tomllib  # type: ignore[import-not-found]

    _HAS_TOMLLIB = True
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[import-not-found,no-redef]

        _HAS_TOMLLIB = True
    except ImportError:
        tomllib = None  # type: ignore[assignment]
        _HAS_TOMLLIB = False


CONFIG_FILE_CANDIDATES = (
    ".changelogmanager.yml",
    ".changelogmanager.yaml",
    "changelogmanager.yml",
    "changelogmanager.yaml",
)
PYPROJECT_FILE = "pyproject.toml"
DEFAULT_CONFIG_FILE = CONFIG_FILE_CANDIDATES[0]

DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "components": [{"name": "default", "changelog": "CHANGELOG.md"}],
        "validation": {"enforce_preamble": False},
        "commits": {"style": "conventional"},
        "versioning": {"scheme": "semver"},
    }
}

VERSIONING_SCHEMES: dict[str, dict[str, str]] = {
    "semver": {
        "label": "Semantic Versioning",
        "markdown": "[Semantic Versioning](https://semver.org/spec/v2.0.0.html)",
        "keyword": "semantic versioning",
    },
    "pep440": {
        "label": "PEP 440",
        "markdown": "[PEP 440](https://peps.python.org/pep-0440/)",
        "keyword": "pep 440",
    },
    "calver": {
        "label": "Calendar Versioning",
        "markdown": "[Calendar Versioning](https://calver.org/)",
        "keyword": "calendar versioning",
    },
}

COMMIT_STYLE_LABELS = {
    "conventional": "Conventional Commits",
    "gitmoji": "Gitmoji",
    "component-is-substring": "Component is substring",
}

logger = get_logger(__name__)


def validate_configuration(file_path: str, config: Mapping[str, Any]) -> None:
    """Verifies if the provided configuration file is accoriding to expectations"""
    logger.log(VERBOSE, "Validating configuration structure from %s", file_path)
    if not config.get("project") or not config["project"].get("components"):
        raise logging.Error(
            file_path=file_path, message="Incorrect Project configuration format!"
        )

    for component in config["project"]["components"]:
        if not component.get("name") or not component.get("changelog"):
            raise logging.Error(
                file_path=file_path, message="Incorrect Component configuration format!"
            )


def normalize_configuration(config: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Returns a config with defaults applied while preserving unknown keys."""

    logger.log(VERBOSE, "Normalizing configuration with defaults")
    normalized = deepcopy(DEFAULT_CONFIG)
    if isinstance(config, Mapping):
        _merge_mappings(normalized, config)
    return normalized


def load_configuration(config_path: str) -> dict[str, Any]:
    """Loads a configuration file (YAML or pyproject.toml)."""

    path = Path(config_path)
    logger.info("Loading configuration from %s", path)
    if path.name == PYPROJECT_FILE or path.suffix == ".toml":
        return _load_pyproject(path)
    return _load_yaml(path)


def _load_yaml(path: Path) -> dict[str, Any]:
    logger.log(VERBOSE, "Reading YAML configuration from %s", path)
    with path.open(encoding="UTF-8") as file_handle:
        data = yaml.safe_load(file_handle)
    if not isinstance(data, dict):
        raise logging.Error(
            file_path=str(path), message="Configuration file is not a mapping"
        )
    return data


def _load_pyproject(path: Path) -> dict[str, Any]:
    if not _HAS_TOMLLIB:
        raise logging.Error(
            file_path=str(path),
            message=(
                "pyproject.toml configuration requires Python 3.11+ "
                "(tomllib unavailable)"
            ),
        )
    logger.log(VERBOSE, "Reading pyproject configuration from %s", path)
    with path.open("rb") as file_handle:
        data = tomllib.load(file_handle)
    tool_section = data.get("tool", {}).get("changelogmanager")
    if not tool_section:
        raise logging.Error(
            file_path=str(path),
            message="No [tool.changelogmanager] section found in pyproject.toml",
        )
    return tool_section


def auto_detect_config(start_dir: Optional[Path] = None) -> Optional[str]:
    """Searches the current working directory for a configuration file.

    Returns the path of the first match, or None if no config is found.
    Order: .changelogmanager.yml/.yaml, then pyproject.toml (only if it has a
    [tool.changelogmanager] section).
    """

    base = Path(start_dir) if start_dir else Path.cwd()
    logger.log(VERBOSE, "Auto-detecting configuration from %s", base)

    for candidate in CONFIG_FILE_CANDIDATES:
        candidate_path = base / candidate
        if candidate_path.is_file():
            logger.info("Auto-detected configuration file %s", candidate_path)
            return str(candidate_path)

    pyproject_path = base / PYPROJECT_FILE
    if pyproject_path.is_file() and _HAS_TOMLLIB:
        try:
            with pyproject_path.open("rb") as file_handle:
                data = tomllib.load(file_handle)
        except (OSError, ValueError):
            logger.warning(
                "Failed to inspect %s while auto-detecting config", pyproject_path
            )
            return None
        if data.get("tool", {}).get("changelogmanager"):
            logger.info("Auto-detected configuration file %s", pyproject_path)
            return str(pyproject_path)
    logger.log(VERBOSE, "No configuration file detected in %s", base)
    return None


def get_effective_configuration(config_path: Optional[str]) -> dict[str, Any]:
    """Loads config with defaults applied; falls back to defaults when absent."""

    if not config_path:
        logger.info("Using built-in default configuration")
        return normalize_configuration(None)
    logger.log(VERBOSE, "Resolving effective configuration from %s", config_path)
    return normalize_configuration(load_configuration(config_path))


def get_component_from_config(config: str, component: str) -> dict[str, Any]:
    """Retrieves a specific component from the configuration file"""
    logger.info("Resolving component '%s' from %s", component, config)
    configuration = load_configuration(config)

    validate_configuration(config, configuration)

    project = configuration.get("project", {})

    def filter_component(
        components: Sequence[dict[str, Any]], name: str
    ) -> dict[str, Any]:
        for component in components:
            if component.get("name") == name:
                return component

        raise logging.Error(file_path=config, message=f"Unknown component name: {name}")

    return filter_component(project.get("components", []), component)


def get_components_from_config(config: str) -> list[dict[str, Any]]:
    """Retrieves all components from the configuration file"""

    logger.info("Loading all configured components from %s", config)
    configuration = load_configuration(config)
    validate_configuration(config, configuration)
    components: list[dict[str, Any]] = configuration.get("project", {}).get(
        "components", []
    )
    return components


def get_validation_options(config: Optional[str]) -> dict[str, Any]:
    """Returns optional validation knobs from the configuration file.

    Recognised keys (under ``project.validation``):
      enforce_preamble: bool (default False)
    """

    if not config:
        logger.log(VERBOSE, "No configuration file provided for validation options")
        return {}
    try:
        configuration = load_configuration(config)
    except (logging.Error, OSError):
        logger.warning("Unable to load validation options from %s", config)
        return {}
    project = configuration.get("project", {}) or {}
    validation = project.get("validation", {}) or {}
    if not isinstance(validation, dict):
        return {}
    return validation


def get_commit_style(config: Optional[str]) -> str:
    """Returns the configured commit parsing style."""

    logger.log(VERBOSE, "Resolving commit style from %s", config or "<defaults>")
    configuration = get_effective_configuration(config)
    commits = configuration.get("project", {}).get("commits", {}) or {}
    style = commits.get("style", DEFAULT_CONFIG["project"]["commits"]["style"])
    if style not in COMMIT_STYLE_LABELS:
        return DEFAULT_CONFIG["project"]["commits"]["style"]
    return str(style)


def get_versioning_scheme(config: Optional[str]) -> str:
    """Returns the configured versioning scheme."""

    logger.log(VERBOSE, "Resolving versioning scheme from %s", config or "<defaults>")
    configuration = get_effective_configuration(config)
    versioning = configuration.get("project", {}).get("versioning", {}) or {}
    scheme = versioning.get("scheme", DEFAULT_CONFIG["project"]["versioning"]["scheme"])
    if scheme not in VERSIONING_SCHEMES:
        return DEFAULT_CONFIG["project"]["versioning"]["scheme"]
    return str(scheme)


def get_versioning_label(scheme: str) -> str:
    """Returns a human label for a versioning scheme."""

    return VERSIONING_SCHEMES.get(scheme, VERSIONING_SCHEMES["semver"])["label"]


def get_versioning_markdown(scheme: str) -> str:
    """Returns markdown used in the changelog preamble for a scheme."""

    return VERSIONING_SCHEMES.get(scheme, VERSIONING_SCHEMES["semver"])["markdown"]


def get_preamble_keywords(config: Optional[str]) -> tuple[str, ...]:
    """Returns preamble keywords expected for the configured versioning scheme."""

    scheme = get_versioning_scheme(config)
    keyword = VERSIONING_SCHEMES.get(scheme, VERSIONING_SCHEMES["semver"])["keyword"]
    logger.log(VERBOSE, "Using preamble keywords for versioning scheme %s", scheme)
    return ("keep a changelog", keyword)


def default_config_path_for_format(config_format: str) -> str:
    """Returns the default path for a chosen config format."""

    return PYPROJECT_FILE if config_format == "pyproject" else DEFAULT_CONFIG_FILE


def config_format_from_path(config_path: str) -> str:
    """Returns the config storage format implied by a file path."""

    path = Path(config_path)
    if path.name == PYPROJECT_FILE or path.suffix == ".toml":
        return "pyproject"
    return "yaml"


def write_configuration(config_path: str, config: Mapping[str, Any]) -> None:
    """Writes configuration to YAML or pyproject.toml."""

    path = Path(config_path)
    logger.info("Writing configuration to %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if config_format_from_path(config_path) == "pyproject":
        _write_pyproject(path, config)
        return
    _write_yaml(path, config)


def _merge_mappings(base: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            _merge_mappings(base[key], value)
            continue
        base[key] = deepcopy(value)
    return base


def _write_yaml(path: Path, config: Mapping[str, Any]) -> None:
    logger.log(VERBOSE, "Serializing YAML configuration to %s", path)
    with path.open("w", encoding="UTF-8") as file_handle:
        yaml.safe_dump(dict(config), file_handle, sort_keys=False, allow_unicode=True)


def _write_pyproject(path: Path, config: Mapping[str, Any]) -> None:
    logger.log(VERBOSE, "Serializing pyproject configuration to %s", path)
    content = path.read_text(encoding="UTF-8") if path.is_file() else ""
    section = _serialize_pyproject_section(config)
    updated = _replace_pyproject_section(content, section)
    path.write_text(updated, encoding="UTF-8")


def _replace_pyproject_section(content: str, section: str) -> str:
    lines = content.splitlines(keepends=True)
    start = None
    end = None

    for index, line in enumerate(lines):
        if re.match(r"^\[tool\.changelogmanager\]\s*$", line.strip()):
            start = index
            end = len(lines)
            for candidate in range(index + 1, len(lines)):
                stripped = lines[candidate].strip()
                if not stripped.startswith("["):
                    continue
                if stripped.startswith("[tool.changelogmanager") or stripped.startswith(
                    "[[tool.changelogmanager"
                ):
                    continue
                end = candidate
                break
            break

    if start is None or end is None:
        prefix = content.rstrip()
        if prefix:
            return f"{prefix}\n\n{section}"
        return section

    before = "".join(lines[:start]).rstrip()
    after = "".join(lines[end:]).lstrip("\n")
    merged = section if not before else f"{before}\n\n{section}"
    if after:
        return f"{merged}\n\n{after}"
    return merged


def _serialize_pyproject_section(config: Mapping[str, Any]) -> str:
    project = config.get("project", {}) or {}
    validation = project.get("validation", {}) or {}
    commits = project.get("commits", {}) or {}
    versioning = project.get("versioning", {}) or {}
    components = project.get("components", []) or []

    lines = [
        "[tool.changelogmanager]",
        "[tool.changelogmanager.project]",
        "",
        "[tool.changelogmanager.project.validation]",
        f"enforce_preamble = {_toml_bool(bool(validation.get('enforce_preamble', False)))}",
        "",
        "[tool.changelogmanager.project.commits]",
        f"style = {_toml_string(str(commits.get('style', 'conventional')))}",
        "",
        "[tool.changelogmanager.project.versioning]",
        f"scheme = {_toml_string(str(versioning.get('scheme', 'semver')))}",
    ]

    for component in components:
        lines.extend(
            [
                "",
                "[[tool.changelogmanager.project.components]]",
                f"name = {_toml_string(str(component.get('name', 'default')))}",
                f"changelog = {_toml_string(str(component.get('changelog', 'CHANGELOG.md')))}",
            ]
        )

    return "\n".join(lines) + "\n"


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"
