# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Configuration Management"""

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import Any, Optional

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.runtime_logging import VERBOSE, get_logger

try:
    import tomllib  # type: ignore[import-not-found]

    HAS_TOMLLIB = True
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore[import-not-found]

        HAS_TOMLLIB = True
    except ImportError:
        tomllib = None
        HAS_TOMLLIB = False


CONFIG_FILE_CANDIDATES = (
    "changelogmanager.toml",
    ".changelogmanager.toml",
)
PYPROJECT_FILE = "pyproject.toml"
DEFAULT_CONFIG_FILE = CONFIG_FILE_CANDIDATES[0]
DEFAULT_VERSIONING_SCHEME = "semver"

# Internal normalized config keeps everything under "project" so the existing
# readers (get_versioning_scheme, get_validation_options, ...) are unchanged.
# The on-disk TOML schema is "unwrapped" (top-level tables) and is mapped into
# this shape on load. A legacy "project" table is also accepted (back-compat).
DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "components": [{"name": "default", "changelog": "CHANGELOG.md"}],
        "validation": {"enforce_preamble": False},
        "versioning": {"scheme": DEFAULT_VERSIONING_SCHEME},
        "defaults": {},
        "github": {},
        "gitlab": {},
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

# Top-level TOML tables that make up the unwrapped on-disk schema. These are the
# keys lifted into the internal "project" namespace on load.
UNWRAPPED_TABLES = ("versioning", "validation", "defaults", "github", "gitlab")

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


def wrap_unwrapped_schema(config: Mapping[str, Any]) -> dict[str, Any]:
    """Maps the on-disk TOML schema onto the internal ``project.*`` namespace.

    Accepts either the unwrapped schema (top-level ``versioning``, ``validation``,
    ``defaults``, ``github``, ``gitlab``, ``components``) or a legacy ``project``
    table (back-compat). Returns a mapping shaped like ``{"project": {...}}``.
    """

    # Legacy form: already wrapped under "project". Flatten by lifting it out.
    if "project" in config and isinstance(config["project"], Mapping):
        legacy_project = dict(config["project"])
        # A legacy config may still carry the dead "commits" table; drop it.
        legacy_project.pop("commits", None)
        return {"project": legacy_project}

    project: dict[str, Any] = {}
    for table in UNWRAPPED_TABLES:
        value = config.get(table)
        if isinstance(value, Mapping):
            project[table] = dict(value)
    if "components" in config:
        project["components"] = config["components"]
    return {"project": project}


def normalize_configuration(config: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Returns a config with defaults applied while preserving unknown keys."""

    logger.log(VERBOSE, "Normalizing configuration with defaults")
    normalized = deepcopy(DEFAULT_CONFIG)
    if isinstance(config, Mapping):
        merge_mappings(normalized, wrap_unwrapped_schema(config))
    return normalized


def load_configuration(config_path: str) -> dict[str, Any]:
    """Loads a TOML configuration file (pyproject.toml or standalone .toml)."""

    path = Path(config_path)
    logger.info("Loading configuration from %s", path)
    if path.name == PYPROJECT_FILE:
        return load_pyproject(path)
    return load_toml(path)


def read_toml(path: Path) -> dict[str, Any]:
    """Reads a TOML file, raising a friendly error when tomllib is unavailable."""

    if not HAS_TOMLLIB:
        raise logging.Error(
            file_path=str(path),
            message=(
                "TOML configuration requires Python 3.11+ or the 'tomli' package "
                "(tomllib unavailable)"
            ),
        )
    logger.log(VERBOSE, "Reading TOML configuration from %s", path)
    with path.open("rb") as file_handle:
        return dict(tomllib.load(file_handle))


def load_toml(path: Path) -> dict[str, Any]:
    """Loads a standalone changelogmanager TOML config (unwrapped schema)."""

    data = read_toml(path)
    if not data:
        raise logging.Error(file_path=str(path), message="Configuration file is empty")
    return data


def load_pyproject(path: Path) -> dict[str, Any]:
    data = read_toml(path)
    tool_section = data.get("tool", {}).get("changelogmanager")
    if not isinstance(tool_section, Mapping) or not tool_section:
        raise logging.Error(
            file_path=str(path),
            message="No [tool.changelogmanager] section found in pyproject.toml",
        )
    return dict(tool_section)


def auto_detect_config(start_dir: Optional[Path] = None) -> Optional[str]:
    """Searches the current working directory for a configuration file.

    Returns the path of the first match, or None if no config is found.
    Order: changelogmanager.toml, .changelogmanager.toml, then pyproject.toml
    (only if it has a [tool.changelogmanager] section).
    """

    base = Path(start_dir) if start_dir else Path.cwd()
    logger.log(VERBOSE, "Auto-detecting configuration from %s", base)

    for candidate in CONFIG_FILE_CANDIDATES:
        candidate_path = base / candidate
        if candidate_path.is_file():
            logger.info("Auto-detected configuration file %s", candidate_path)
            return str(candidate_path)

    pyproject_path = base / PYPROJECT_FILE
    if pyproject_path.is_file() and HAS_TOMLLIB:
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
    configuration = wrap_unwrapped_schema(load_configuration(config))

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
    configuration = wrap_unwrapped_schema(load_configuration(config))
    validate_configuration(config, configuration)
    components: list[dict[str, Any]] = configuration.get("project", {}).get(
        "components", []
    )
    return components


def get_format_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the format-pass settings from the configuration file.

    Recognised keys (under ``project.validation``):
      format: true | false | "auto"  (default "auto")
      formatter: str                 (reserved; only "mdformat" supported)
      mdformat_options: dict         (passed through to mdformat)
    """
    validation = get_validation_options(config)
    return {
        "format": validation.get("format", "auto"),
        "formatter": validation.get("formatter", "mdformat"),
        "mdformat_options": validation.get("mdformat_options") or {},
    }


def get_validation_options(config: Optional[str]) -> dict[str, Any]:
    """Returns optional validation knobs from the configuration file.

    Recognised keys (under ``project.validation``):
      enforce_preamble: bool (default False)
    """

    if not config:
        logger.log(VERBOSE, "No configuration file provided for validation options")
        return {}
    try:
        configuration = wrap_unwrapped_schema(load_configuration(config))
    except (logging.Error, OSError):
        logger.warning("Unable to load validation options from %s", config)
        return {}
    project = configuration.get("project", {}) or {}
    validation = project.get("validation", {}) or {}
    if not isinstance(validation, Mapping):
        return {}
    return dict(validation)


def get_defaults_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the [defaults] table used to back CLI flag defaults."""

    return _get_project_table(config, "defaults")


def get_github_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the [github] table (per-repo remote defaults)."""

    return _get_project_table(config, "github")


def get_gitlab_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the [gitlab] table (per-repo remote defaults)."""

    return _get_project_table(config, "gitlab")


def _get_project_table(config: Optional[str], table: str) -> dict[str, Any]:
    configuration = get_effective_configuration(config)
    value = configuration.get("project", {}).get(table, {}) or {}
    return dict(value) if isinstance(value, Mapping) else {}


def get_versioning_scheme(config: Optional[str]) -> str:
    """Returns the configured versioning scheme."""

    logger.log(VERBOSE, "Resolving versioning scheme from %s", config or "<defaults>")
    configuration = get_effective_configuration(config)
    versioning = configuration.get("project", {}).get("versioning", {}) or {}
    scheme = versioning.get("scheme", DEFAULT_VERSIONING_SCHEME)
    if not isinstance(scheme, str):
        return DEFAULT_VERSIONING_SCHEME
    if scheme not in VERSIONING_SCHEMES:
        return DEFAULT_VERSIONING_SCHEME
    return scheme


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
    """Returns the config storage format implied by a file path.

    ``pyproject`` for a pyproject.toml; ``toml`` for a standalone .toml file.
    """

    path = Path(config_path)
    if path.name == PYPROJECT_FILE:
        return "pyproject"
    return "toml"


def write_configuration(config_path: str, config: Mapping[str, Any]) -> None:
    """Writes configuration to pyproject.toml or a standalone .toml file."""

    path = Path(config_path)
    logger.info("Writing configuration to %s", path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if config_format_from_path(config_path) == "pyproject":
        write_pyproject(path, config)
        return
    write_standalone_toml(path, config)


def merge_mappings(base: dict[str, Any], updates: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in updates.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            merge_mappings(base[key], value)
            continue
        base[key] = deepcopy(value)
    return base


def write_standalone_toml(path: Path, config: Mapping[str, Any]) -> None:
    logger.log(VERBOSE, "Serializing standalone TOML configuration to %s", path)
    path.write_text(serialize_config_toml(config, prefix=""), encoding="UTF-8")


def write_pyproject(path: Path, config: Mapping[str, Any]) -> None:
    logger.log(VERBOSE, "Serializing pyproject configuration to %s", path)
    content = path.read_text(encoding="UTF-8") if path.is_file() else ""
    section = serialize_pyproject_section(config)
    updated = replace_pyproject_section(content, section)
    path.write_text(updated, encoding="UTF-8")


def replace_pyproject_section(content: str, section: str) -> str:
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


def serialize_pyproject_section(config: Mapping[str, Any]) -> str:
    """Serializes config as a [tool.changelogmanager] pyproject section."""

    return serialize_config_toml(config, prefix="tool.changelogmanager.")


def serialize_config_toml(config: Mapping[str, Any], *, prefix: str) -> str:
    """Renders config as TOML using the unwrapped schema.

    ``prefix`` is "" for a standalone file, or "tool.changelogmanager." for a
    pyproject section (so tables become ``[tool.changelogmanager.versioning]``).
    """

    project = config.get("project", {}) or {}
    validation = project.get("validation", {}) or {}
    versioning = project.get("versioning", {}) or {}
    components = project.get("components", []) or []

    lines: list[str] = []
    if prefix:
        # Anchor table so an empty section still produces [tool.changelogmanager].
        lines.append(f"[{prefix.rstrip('.')}]")

    def table(name: str) -> str:
        return f"[{prefix}{name}]"

    def array_table(name: str) -> str:
        return f"[[{prefix}{name}]]"

    lines.extend(
        [
            table("versioning"),
            f"scheme = {toml_string(str(versioning.get('scheme', 'semver')))}",
            "",
            table("validation"),
            f"enforce_preamble = "
            f"{toml_bool(bool(validation.get('enforce_preamble', False)))}",
        ]
    )

    fmt = validation.get("format")
    if fmt is not None:
        lines.append(f"format = {toml_scalar(fmt)}")

    for name, key in (
        ("defaults", "defaults"),
        ("github", "github"),
        ("gitlab", "gitlab"),
    ):
        values = project.get(key, {}) or {}
        if not isinstance(values, Mapping) or not values:
            continue
        lines.extend(["", table(name)])
        for option_key, option_value in values.items():
            lines.append(f"{option_key} = {toml_scalar(option_value)}")

    for component in components:
        lines.extend(
            [
                "",
                array_table("components"),
                f"name = {toml_string(str(component.get('name', 'default')))}",
                f"changelog = "
                f"{toml_string(str(component.get('changelog', 'CHANGELOG.md')))}",
            ]
        )
        match = component.get("match")
        if isinstance(match, (list, tuple)) and match:
            rendered = ", ".join(toml_string(str(item)) for item in match)
            lines.append(f"match = [{rendered}]")

    return "\n".join(lines) + "\n"


def toml_scalar(value: Any) -> str:
    """Renders a scalar (str/bool/int) as TOML."""

    if isinstance(value, bool):
        return toml_bool(value)
    if isinstance(value, int):
        return str(value)
    return toml_string(str(value))


def toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def toml_bool(value: bool) -> str:
    return "true" if value else "false"
