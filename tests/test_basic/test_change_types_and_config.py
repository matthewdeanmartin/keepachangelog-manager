import pytest

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, TYPES_OF_CHANGE, VersionCore
from changelogmanager.config import get_component_from_config, validate_configuration


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
