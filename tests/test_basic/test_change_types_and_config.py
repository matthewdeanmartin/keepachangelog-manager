import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, TYPES_OF_CHANGE, VersionCore
from changelogmanager.config import (
    auto_detect_config,
    get_component_from_config,
    get_effective_configuration,
    get_format_options,
    get_github_options,
    get_gitlab_options,
    get_preamble_keywords,
    get_versioning_scheme,
    get_versioning_label,
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
    assert "[validation]\nenforce_preamble = true\nformat = \"auto\"" in rendered
    assert '[defaults]\nerror_format = "github"\nbump_versions = true' in rendered
    assert '[github]\nrepository = "octo/example"' in rendered
    assert '[gitlab]\nproject = 123\nurl = "https://gitlab.example.com"' in rendered
    assert 'match = ["api/**", "shared/*"]' in rendered


def test_replace_pyproject_section_replaces_only_changelogmanager_block():
    content = (
        "[build-system]\n"
        "requires = [\"hatchling\"]\n\n"
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
