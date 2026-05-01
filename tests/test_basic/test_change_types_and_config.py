import pytest

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, TYPES_OF_CHANGE, VersionCore
from changelogmanager.config import (
    get_component_from_config,
    get_effective_configuration,
    get_preamble_keywords,
    get_versioning_scheme,
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
        validate_configuration("config.yml", config)


def test_get_component_from_config_returns_named_component(tmp_path):
    config_file = tmp_path / "components.yml"
    config_file.write_text(
        "project:\n"
        "  components:\n"
        "    - name: api\n"
        "      changelog: docs/API_CHANGELOG.md\n"
        "    - name: ui\n"
        "      changelog: docs/UI_CHANGELOG.md\n",
        encoding="utf-8",
    )

    component = get_component_from_config(str(config_file), "ui")

    assert component == {"name": "ui", "changelog": "docs/UI_CHANGELOG.md"}


def test_get_component_from_config_rejects_unknown_component(tmp_path):
    config_file = tmp_path / "components.yml"
    config_file.write_text(
        "project:\n"
        "  components:\n"
        "    - name: api\n"
        "      changelog: docs/API_CHANGELOG.md\n",
        encoding="utf-8",
    )

    with pytest.raises(logging.Error, match="Unknown component name: worker"):
        get_component_from_config(str(config_file), "worker")


def test_effective_configuration_defaults_without_file():
    config = get_effective_configuration(None)

    assert config["project"]["components"] == [
        {"name": "default", "changelog": "CHANGELOG.md"}
    ]
    assert config["project"]["commits"]["style"] == "conventional"
    assert config["project"]["versioning"]["scheme"] == "semver"


def test_write_configuration_round_trips_yaml_and_pyproject(tmp_path):
    config = {
        "project": {
            "components": [{"name": "api", "changelog": "docs/API_CHANGELOG.md"}],
            "validation": {"enforce_preamble": True},
            "commits": {"style": "gitmoji"},
            "versioning": {"scheme": "pep440"},
        }
    }

    yaml_path = tmp_path / ".changelogmanager.yml"
    pyproject_path = tmp_path / "pyproject.toml"

    write_configuration(str(yaml_path), config)
    write_configuration(str(pyproject_path), config)

    assert get_effective_configuration(str(yaml_path))["project"]["commits"]["style"] == "gitmoji"
    assert get_effective_configuration(str(pyproject_path))["project"]["versioning"]["scheme"] == "pep440"


def test_preamble_keywords_follow_configured_versioning(tmp_path):
    config_path = tmp_path / ".changelogmanager.yml"
    config_path.write_text(
        "project:\n"
        "  components:\n"
        "    - name: default\n"
        "      changelog: CHANGELOG.md\n"
        "  versioning:\n"
        "    scheme: calver\n",
        encoding="utf-8",
    )

    assert get_versioning_scheme(str(config_path)) == "calver"
    assert get_preamble_keywords(str(config_path)) == (
        "keep a changelog",
        "calendar versioning",
    )
