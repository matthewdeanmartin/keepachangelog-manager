# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Configuration Management"""

import os
import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.runtime_logging import VERBOSE, get_logger

if TYPE_CHECKING:  # pragma: no cover - typing only
    from changelogmanager.message_lint import LintOptions

try:
    import tomllib  # type: ignore

    HAS_TOMLLIB = True
except ImportError:  # Python < 3.11
    try:
        import tomli as tomllib  # type: ignore

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
CONFIG_CACHE_DISABLE_ENV = "CHANGELOGMANAGER_DISABLE_CONFIG_CACHE"

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
        "pypi": {},
        "tasks": {},
        "fragments": {},
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
UNWRAPPED_TABLES = (
    "versioning",
    "validation",
    "defaults",
    "github",
    "gitlab",
    "pypi",
    "tasks",
    "fragments",
)

logger = get_logger(__name__)
_RAW_TOML_CACHE: dict[str, dict[str, Any]] = {}
_LOADED_CONFIG_CACHE: dict[str, dict[str, Any]] = {}


def clear_configuration_cache() -> None:
    """Clears cached TOML/config reads for tests or same-process rewrites."""

    _RAW_TOML_CACHE.clear()
    _LOADED_CONFIG_CACHE.clear()


def _configuration_cache_enabled() -> bool:
    value = os.environ.get(CONFIG_CACHE_DISABLE_ENV, "")
    return value.lower() not in {"1", "true", "yes", "on"}


def _configuration_cache_key(path: Path) -> str:
    return str(path.resolve(strict=False))


def _get_cached_copy(
    cache: dict[str, dict[str, Any]], path: Path
) -> Optional[dict[str, Any]]:
    if not _configuration_cache_enabled():
        return None
    cached = cache.get(_configuration_cache_key(path))
    return deepcopy(cached) if cached is not None else None


def _store_cached_value(
    cache: dict[str, dict[str, Any]], path: Path, value: Mapping[str, Any]
) -> None:
    if not _configuration_cache_enabled():
        return
    cache[_configuration_cache_key(path)] = deepcopy(dict(value))


def _clear_configuration_cache_for_path(path: Path) -> None:
    key = _configuration_cache_key(path)
    _RAW_TOML_CACHE.pop(key, None)
    _LOADED_CONFIG_CACHE.pop(key, None)


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
    cached = _get_cached_copy(_LOADED_CONFIG_CACHE, path)
    if cached is not None:
        logger.log(VERBOSE, "Using cached configuration from %s", path)
        return cached
    logger.info("Loading configuration from %s", path)
    loaded = load_pyproject(path) if path.name == PYPROJECT_FILE else load_toml(path)
    _store_cached_value(_LOADED_CONFIG_CACHE, path, loaded)
    return deepcopy(loaded)


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
    cached = _get_cached_copy(_RAW_TOML_CACHE, path)
    if cached is not None:
        logger.log(VERBOSE, "Using cached TOML configuration from %s", path)
        return cached
    logger.log(VERBOSE, "Reading TOML configuration from %s", path)
    if tomllib is None:
        raise RuntimeError("tomllib is unexpectedly None")
    with path.open("rb") as file_handle:
        data = dict(tomllib.load(file_handle))
    _store_cached_value(_RAW_TOML_CACHE, path, data)
    return deepcopy(data)


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
            data = read_toml(pyproject_path)
        except (OSError, ValueError, logging.Error):
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


def get_component_tasks_file(config: Optional[str], component: str) -> Optional[str]:
    """Returns the ``tasks_file`` declared for ``component``, if any.

    Returns ``None`` when there is no config, the component is unknown, or the
    component has no ``tasks_file`` key — callers then fall back to the global
    ``[tasks].file`` setting or task-file discovery. Unlike
    :func:`get_component_from_config` this never raises on a missing component, so
    the tasks commands degrade gracefully to the default task file.
    """

    if not config:
        return None
    try:
        component_config = get_component_from_config(config=config, component=component)
    except (logging.Error, OSError):
        logger.warning(
            "Could not resolve component %s for tasks_file lookup", component
        )
        return None
    tasks_file = component_config.get("tasks_file")
    if tasks_file in (None, ""):
        return None
    return str(tasks_file)


def get_components_from_config(config: str) -> list[dict[str, Any]]:
    """Retrieves all components from the configuration file"""

    logger.info("Loading all configured components from %s", config)
    configuration = wrap_unwrapped_schema(load_configuration(config))
    validate_configuration(config, configuration)
    components: list[dict[str, Any]] = configuration.get("project", {}).get(
        "components", []
    )
    return components


def add_component_to_config(
    config_path: str,
    name: str,
    changelog: str,
    *,
    tasks_file: Optional[str] = None,
) -> dict[str, Any]:
    """Adds a new component to ``config_path`` and writes it back.

    Loads the effective configuration (creating a default if the file is absent),
    appends a ``{name, changelog}`` component (optionally carrying a per-component
    ``tasks_file``), and serializes it through :func:`write_configuration` so the
    on-disk shape matches what the rest of the code expects. Returns the appended
    component.

    Raises :class:`logging.Error` when ``name``/``changelog`` are blank or a
    component with the same name already exists (case-sensitive, matching how
    ``get_component_from_config`` looks names up).
    """

    name = name.strip()
    changelog = changelog.strip()
    if not name or not changelog:
        raise logging.Error(
            file_path=config_path,
            message="Component name and changelog path are both required",
        )

    config = get_effective_configuration(
        config_path if Path(config_path).is_file() else None
    )
    project = dict(config.get("project", {}) or {})
    components = list(project.get("components", []) or [])

    if any(existing.get("name") == name for existing in components):
        raise logging.Error(
            file_path=config_path,
            message=f"A component named {name!r} already exists",
        )

    component: dict[str, Any] = {"name": name, "changelog": changelog}
    if tasks_file and tasks_file.strip():
        component["tasks_file"] = tasks_file.strip()
    components.append(component)
    project["components"] = components
    config["project"] = project

    write_configuration(config_path, config)
    logger.info("Added component %s (%s) to %s", name, changelog, config_path)
    return component


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


MESSAGE_LINT_SCHEMAS = ("auto", "conventional", "gitmoji", "keepachangelog")


def get_message_lint_options(config: Optional[str]) -> "LintOptions":
    """Returns commit-message lint settings as a resolved ``LintOptions``.

    Reads ``project.validation.message_lint``; recognised keys:
      enabled: bool                         (default False)
      schema: auto|conventional|gitmoji|keepachangelog (default "auto")
      allow_unknown_conventional_types: bool (default False)
      allow_skip_types: bool                (default True)
      exempt_patterns: list[str]            (regexes; default merge/revert/...)

    A bad ``schema`` value or an exempt pattern that does not compile is a
    configuration error surfaced as :class:`logging.Error` rather than a crash
    mid-hook.
    """

    # Imported here to avoid a config -> message_lint -> backfill import cycle at
    # module load; the lint core imports nothing from config.
    from changelogmanager.message_lint import (  # noqa: PLC0415
        DEFAULT_EXEMPT_PATTERNS,
        LintOptions,
    )

    validation = get_validation_options(config)
    raw = validation.get("message_lint")
    if not isinstance(raw, Mapping):
        return LintOptions()

    schema = raw.get("schema", "auto")
    if not isinstance(schema, str) or schema not in MESSAGE_LINT_SCHEMAS:
        raise logging.Error(
            file_path=config,
            message=(
                f"Invalid message_lint.schema {schema!r}; "
                f"choose one of {', '.join(MESSAGE_LINT_SCHEMAS)}"
            ),
        )

    patterns_raw = raw.get("exempt_patterns")
    if patterns_raw is None:
        exempt_patterns = DEFAULT_EXEMPT_PATTERNS
    elif isinstance(patterns_raw, Sequence) and not isinstance(patterns_raw, str):
        exempt_patterns = tuple(str(item) for item in patterns_raw)
    else:
        raise logging.Error(
            file_path=config,
            message="message_lint.exempt_patterns must be a list of regex strings",
        )

    for pattern in exempt_patterns:
        try:
            re.compile(pattern)
        except re.error as exc:
            raise logging.Error(
                file_path=config,
                message=f"Invalid message_lint.exempt_patterns regex {pattern!r}: {exc}",
            ) from exc

    return LintOptions(
        enabled=bool(raw.get("enabled", False)),
        schema=schema,
        allow_unknown_conventional_types=bool(
            raw.get("allow_unknown_conventional_types", False)
        ),
        allow_skip_types=bool(raw.get("allow_skip_types", True)),
        exempt_patterns=exempt_patterns,
    )


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

    return get_project_table(config, "defaults")


def get_github_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the [github] table (per-repo remote defaults)."""

    return get_project_table(config, "github")


def get_gitlab_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the [gitlab] table (per-repo remote defaults)."""

    return get_project_table(config, "gitlab")


def get_pypi_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the [pypi] table (package defaults for PyPI backfill)."""

    return get_project_table(config, "pypi")


def get_tasks_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the [tasks] table."""

    return get_project_table(config, "tasks")


def get_fragments_options(config: Optional[str]) -> dict[str, Any]:
    """Returns the [fragments] table."""

    return get_project_table(config, "fragments")


def get_project_table(config: Optional[str], table: str) -> dict[str, Any]:
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


def get_initial_version(config: Optional[str]) -> Optional[str]:
    """Returns the configured first-release version, if any.

    Read from ``[versioning].initial_version``. ``None`` means "use the
    scheme default" (``0.0.1`` for semver). Set it to e.g. ``0.1.0`` to start a
    project's first release there instead.
    """

    configuration = get_effective_configuration(config)
    versioning = configuration.get("project", {}).get("versioning", {}) or {}
    value = versioning.get("initial_version")
    if value in (None, ""):
        return None
    return str(value)


def get_skip_ci(config: Optional[str]) -> bool:
    """Whether generated release commit messages should include ``[skip ci]``.

    Read from ``[defaults].skip_ci``. Defaults to ``True`` (the historical
    behaviour); set it to ``false`` so version-bump commit messages do not
    suppress CI.
    """

    defaults = get_defaults_options(config)
    value = defaults.get("skip_ci", True)
    return bool(value)


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
    else:
        write_standalone_toml(path, config)
    _clear_configuration_cache_for_path(path)


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
        ("pypi", "pypi"),
        ("tasks", "tasks"),
        ("fragments", "fragments"),
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
        fragment_directory = component.get("fragment_directory")
        if fragment_directory:
            lines.append(f"fragment_directory = {toml_string(str(fragment_directory))}")
        tasks_file = component.get("tasks_file")
        if tasks_file:
            lines.append(f"tasks_file = {toml_string(str(tasks_file))}")

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
