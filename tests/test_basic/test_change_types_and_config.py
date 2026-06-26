import pytest

import changelogmanager.config as config_module
import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, TYPES_OF_CHANGE, VersionCore
from changelogmanager.config import (
    add_component_to_config,
    auto_detect_config,
    clear_configuration_cache,
    get_component_from_config,
    get_component_tasks_file,
    get_components_from_config,
    get_effective_configuration,
    get_format_options,
    get_github_options,
    get_gitlab_options,
    get_preamble_keywords,
    get_validation_options,
    get_versioning_label,
    get_versioning_scheme,
    replace_pyproject_section,
    serialize_config_toml,
    validate_configuration,
    write_configuration,
)


def test_change_types_expose_expected_metadata():
    assert TYPES_OF_CHANGE == [
        "added",
        "changed",
        "deprecated",
        "removed",
        "fixed",
        "security",
    ]
    assert CATEGORIES["added"].title == "New Features"
    assert CATEGORIES["removed"].bump is VersionCore.MAJOR
    assert CATEGORIES["security"].emoji == "closed_lock_with_key"


@pytest.mark.parametrize(
    ("config", "message"),
    [
        ({}, "Incorrect Project configuration format!"),
        (
            {"project": {"components": [{"name": "api"}]}},
            "Incorrect Component configuration format!",
        ),
    ],
)
def test_validate_configuration_rejects_invalid_shapes(config, message):
    with pytest.raises(logging.Error, match=message):
        validate_configuration("config.toml", config)


def test_get_component_from_config_returns_named_component(tmp_path):
    config_file = tmp_path / "changelogmanager.toml"
    config_file.write_text(
        "[[components]]\n"
        'name = "api"\n'
        'changelog = "docs/API_CHANGELOG.md"\n'
        "\n"
        "[[components]]\n"
        'name = "ui"\n'
        'changelog = "docs/UI_CHANGELOG.md"\n',
        encoding="utf-8",
    )

    component = get_component_from_config(str(config_file), "ui")

    assert component == {"name": "ui", "changelog": "docs/UI_CHANGELOG.md"}


def test_get_component_from_config_rejects_unknown_component(tmp_path):
    config_file = tmp_path / "changelogmanager.toml"
    config_file.write_text(
        "[[components]]\n" 'name = "api"\n' 'changelog = "docs/API_CHANGELOG.md"\n',
        encoding="utf-8",
    )

    with pytest.raises(logging.Error, match="Unknown component name: worker"):
        get_component_from_config(str(config_file), "worker")


def test_effective_configuration_defaults_without_file():
    config = get_effective_configuration(None)

    assert config["project"]["components"] == [
        {"name": "default", "changelog": "CHANGELOG.md"}
    ]
    assert config["project"]["versioning"]["scheme"] == "semver"
    # commits.style is gone; the dead knob no longer appears in the defaults.
    assert "commits" not in config["project"]


def test_write_configuration_round_trips_standalone_and_pyproject(tmp_path):
    config = {
        "project": {
            "components": [{"name": "api", "changelog": "docs/API_CHANGELOG.md"}],
            "validation": {"enforce_preamble": True},
            "versioning": {"scheme": "pep440"},
        }
    }

    toml_path = tmp_path / "changelogmanager.toml"
    pyproject_path = tmp_path / "pyproject.toml"

    write_configuration(str(toml_path), config)
    write_configuration(str(pyproject_path), config)

    assert (
        get_effective_configuration(str(toml_path))["project"]["validation"][
            "enforce_preamble"
        ]
        is True
    )
    assert (
        get_effective_configuration(str(pyproject_path))["project"]["versioning"][
            "scheme"
        ]
        == "pep440"
    )


def test_preamble_keywords_follow_configured_versioning(tmp_path):
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        "[[components]]\n"
        'name = "default"\n'
        'changelog = "CHANGELOG.md"\n'
        "\n"
        "[versioning]\n"
        'scheme = "calver"\n',
        encoding="utf-8",
    )

    assert get_versioning_scheme(str(config_path)) == "calver"
    assert get_preamble_keywords(str(config_path)) == (
        "keep a changelog",
        "calendar versioning",
    )


def test_serialize_config_toml_includes_optional_tables_and_match_globs():
    config = {
        "project": {
            "components": [
                {
                    "name": "api",
                    "changelog": "docs/API_CHANGELOG.md",
                    "match": ["api/**", "shared/*"],
                }
            ],
            "validation": {
                "enforce_preamble": True,
                "format": "auto",
            },
            "versioning": {"scheme": "calver"},
            "defaults": {"error_format": "github", "bump_versions": True},
            "github": {"repository": "octo/example"},
            "gitlab": {"project": 123, "url": "https://gitlab.example.com"},
        }
    }

    rendered = serialize_config_toml(config, prefix="")

    assert '[versioning]\nscheme = "calver"' in rendered
    assert '[validation]\nenforce_preamble = true\nformat = "auto"' in rendered
    assert '[defaults]\nerror_format = "github"\nbump_versions = true' in rendered
    assert '[github]\nrepository = "octo/example"' in rendered
    assert '[gitlab]\nproject = 123\nurl = "https://gitlab.example.com"' in rendered
    assert 'match = ["api/**", "shared/*"]' in rendered


def test_add_component_to_config_appends_and_persists(tmp_path):
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        '[[components]]\nname = "default"\nchangelog = "CHANGELOG.md"\n',
        encoding="utf-8",
    )
    clear_configuration_cache()

    added = add_component_to_config(str(config_path), "api", "docs/API.md")
    assert added == {"name": "api", "changelog": "docs/API.md"}

    clear_configuration_cache()
    names = [c["name"] for c in get_components_from_config(str(config_path))]
    assert names == ["default", "api"]
    component = get_component_from_config(str(config_path), "api")
    assert component["changelog"] == "docs/API.md"


def test_add_component_to_config_creates_default_when_file_absent(tmp_path):
    config_path = tmp_path / "changelogmanager.toml"
    clear_configuration_cache()

    add_component_to_config(str(config_path), "svc", "svc/CHANGELOG.md")

    assert config_path.is_file()
    clear_configuration_cache()
    names = [c["name"] for c in get_components_from_config(str(config_path))]
    # The built-in default component plus the new one.
    assert "default" in names
    assert "svc" in names


def test_add_component_to_config_rejects_duplicate_and_blank(tmp_path):
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        '[[components]]\nname = "default"\nchangelog = "CHANGELOG.md"\n',
        encoding="utf-8",
    )
    clear_configuration_cache()

    with pytest.raises(logging.Error):
        add_component_to_config(str(config_path), "default", "CHANGELOG.md")
    with pytest.raises(logging.Error):
        add_component_to_config(str(config_path), "  ", "CHANGELOG.md")


def test_add_component_to_config_persists_tasks_file(tmp_path):
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        '[[components]]\nname = "default"\nchangelog = "CHANGELOG.md"\n',
        encoding="utf-8",
    )
    clear_configuration_cache()

    added = add_component_to_config(
        str(config_path), "api", "docs/API.md", tasks_file="docs/API_TASKS.md"
    )
    assert added == {
        "name": "api",
        "changelog": "docs/API.md",
        "tasks_file": "docs/API_TASKS.md",
    }

    clear_configuration_cache()
    component = get_component_from_config(str(config_path), "api")
    assert component["tasks_file"] == "docs/API_TASKS.md"


def test_get_component_tasks_file_resolution(tmp_path):
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        '[[components]]\nname = "default"\nchangelog = "CHANGELOG.md"\n\n'
        '[[components]]\nname = "api"\nchangelog = "api/CHANGELOG.md"\n'
        'tasks_file = "api/TASKS.md"\n',
        encoding="utf-8",
    )
    clear_configuration_cache()

    # Component carrying tasks_file returns it.
    assert get_component_tasks_file(str(config_path), "api") == "api/TASKS.md"
    # Component without tasks_file returns None (caller falls back to default).
    assert get_component_tasks_file(str(config_path), "default") is None
    # Unknown component degrades gracefully to None (never raises).
    assert get_component_tasks_file(str(config_path), "nope") is None
    # No config at all -> None.
    assert get_component_tasks_file(None, "api") is None


def test_serialize_config_toml_includes_component_tasks_file():
    config = {
        "project": {
            "components": [
                {
                    "name": "api",
                    "changelog": "api/CHANGELOG.md",
                    "tasks_file": "api/TASKS.md",
                }
            ],
        }
    }

    rendered = serialize_config_toml(config, prefix="")

    assert 'tasks_file = "api/TASKS.md"' in rendered


def test_replace_pyproject_section_replaces_only_changelogmanager_block():
    content = (
        "[build-system]\n"
        'requires = ["hatchling"]\n\n'
        "[tool.changelogmanager]\n"
        "old = true\n\n"
        "[tool.ruff]\n"
        "line-length = 160\n"
    )
    section = (
        "[tool.changelogmanager]\n"
        "\n"
        "[tool.changelogmanager.versioning]\n"
        'scheme = "pep440"\n'
    )

    updated = replace_pyproject_section(content, section)

    assert "old = true" not in updated
    assert "[build-system]" in updated
    assert "[tool.ruff]" in updated
    assert updated.count("[tool.changelogmanager]") == 1
    assert 'scheme = "pep440"' in updated


def test_config_helpers_read_optional_tables_and_invalid_versioning(tmp_path):
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        "[versioning]\n"
        'scheme = "not-a-scheme"\n'
        "\n"
        "[validation]\n"
        "enforce_preamble = false\n"
        'format = "auto"\n'
        'formatter = "mdformat"\n'
        "\n"
        "[defaults]\n"
        'error_format = "github"\n'
        "\n"
        "[github]\n"
        'repository = "octo/example"\n'
        "\n"
        "[gitlab]\n"
        'project = "group/project"\n'
        "\n"
        "[[components]]\n"
        'name = "default"\n'
        'changelog = "CHANGELOG.md"\n',
        encoding="utf-8",
    )

    assert get_versioning_scheme(str(config_path)) == "semver"
    assert get_versioning_label("bogus") == "Semantic Versioning"
    assert get_format_options(str(config_path)) == {
        "format": "auto",
        "formatter": "mdformat",
        "mdformat_options": {},
    }
    assert get_github_options(str(config_path)) == {"repository": "octo/example"}
    assert get_gitlab_options(str(config_path)) == {"project": "group/project"}


def test_auto_detect_config_ignores_invalid_pyproject(tmp_path):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text("[tool.changelogmanager\nbroken = true\n", encoding="utf-8")

    assert auto_detect_config(tmp_path) is None


def test_config_reads_are_cached_across_helper_calls(tmp_path, monkeypatch):
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        "[[components]]\n"
        'name = "default"\n'
        'changelog = "CHANGELOG.md"\n'
        "\n"
        "[versioning]\n"
        'scheme = "calver"\n',
        encoding="utf-8",
    )

    clear_configuration_cache()
    load_calls = 0
    original_load = config_module.tomllib.load

    def counting_load(file_handle):
        nonlocal load_calls
        load_calls += 1
        return original_load(file_handle)

    monkeypatch.setattr(config_module.tomllib, "load", counting_load)

    assert get_component_from_config(str(config_path), "default") == {
        "name": "default",
        "changelog": "CHANGELOG.md",
    }
    assert get_validation_options(str(config_path)) == {}
    assert get_versioning_scheme(str(config_path)) == "calver"
    assert get_preamble_keywords(str(config_path)) == (
        "keep a changelog",
        "calendar versioning",
    )
    assert load_calls == 1


def test_auto_detected_pyproject_reuses_cached_toml_read(tmp_path, monkeypatch):
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[tool.changelogmanager]\n"
        "\n"
        "[tool.changelogmanager.versioning]\n"
        'scheme = "pep440"\n'
        "\n"
        "[[tool.changelogmanager.components]]\n"
        'name = "default"\n'
        'changelog = "CHANGELOG.md"\n',
        encoding="utf-8",
    )

    clear_configuration_cache()
    load_calls = 0
    original_load = config_module.tomllib.load

    def counting_load(file_handle):
        nonlocal load_calls
        load_calls += 1
        return original_load(file_handle)

    monkeypatch.setattr(config_module.tomllib, "load", counting_load)

    detected = auto_detect_config(tmp_path)

    assert detected == str(pyproject)
    assert get_versioning_scheme(detected) == "pep440"
    assert load_calls == 1


def test_config_cache_can_be_disabled_for_testing(tmp_path, monkeypatch):
    config_path = tmp_path / "changelogmanager.toml"
    config_path.write_text(
        "[[components]]\n" 'name = "default"\n' 'changelog = "CHANGELOG.md"\n',
        encoding="utf-8",
    )

    clear_configuration_cache()
    monkeypatch.setenv(config_module.CONFIG_CACHE_DISABLE_ENV, "1")
    load_calls = 0
    original_load = config_module.tomllib.load

    def counting_load(file_handle):
        nonlocal load_calls
        load_calls += 1
        return original_load(file_handle)

    monkeypatch.setattr(config_module.tomllib, "load", counting_load)

    assert get_versioning_scheme(str(config_path)) == "semver"
    assert get_versioning_scheme(str(config_path)) == "semver"
    assert load_calls == 2
