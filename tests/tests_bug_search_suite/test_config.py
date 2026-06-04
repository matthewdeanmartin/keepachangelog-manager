"""Bug-hunting tests for config.py — TOML config loading and validation."""

from pathlib import Path

import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.config import get_component_from_config, validate_configuration

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def write_config(path: Path, content: str) -> str:
    p = path / "changelogmanager.toml"
    p.write_text(content, encoding="utf-8")
    return str(p)


# Standalone TOML (unwrapped schema)
VALID_CONFIG = """\
[[components]]
name = "default"
changelog = "CHANGELOG.md"

[[components]]
name = "service-a"
changelog = "service-a/CHANGELOG.md"
"""


# validate_configuration operates on the internal wrapped shape ({"project": ...}).
VALID_WRAPPED = {
    "project": {
        "components": [
            {"name": "default", "changelog": "CHANGELOG.md"},
            {"name": "service-a", "changelog": "service-a/CHANGELOG.md"},
        ]
    }
}
MISSING_PROJECT_KEY = {"components": [{"name": "default", "changelog": "CHANGELOG.md"}]}
MISSING_COMPONENTS_KEY = {"project": {"description": "No components here"}}
COMPONENT_MISSING_NAME = {"project": {"components": [{"changelog": "CHANGELOG.md"}]}}
COMPONENT_MISSING_CHANGELOG = {"project": {"components": [{"name": "default"}]}}


# ---------------------------------------------------------------------------
# validate_configuration
# ---------------------------------------------------------------------------


class TestValidateConfiguration:
    def test_valid_config_does_not_raise(self, tmp_path):
        validate_configuration(str(tmp_path / "config.toml"), VALID_WRAPPED)

    def test_missing_project_key_raises(self, tmp_path):
        with pytest.raises(logging.Error, match="configuration format"):
            validate_configuration(str(tmp_path / "config.toml"), MISSING_PROJECT_KEY)

    def test_missing_components_key_raises(self, tmp_path):
        with pytest.raises(logging.Error, match="configuration format"):
            validate_configuration(
                str(tmp_path / "config.toml"), MISSING_COMPONENTS_KEY
            )

    def test_component_missing_name_raises(self, tmp_path):
        with pytest.raises(logging.Error, match="Component configuration"):
            validate_configuration(str(tmp_path / "config.toml"), COMPONENT_MISSING_NAME)

    def test_component_missing_changelog_raises(self, tmp_path):
        with pytest.raises(logging.Error, match="Component configuration"):
            validate_configuration(
                str(tmp_path / "config.toml"), COMPONENT_MISSING_CHANGELOG
            )

    def test_empty_config_raises(self, tmp_path):
        with pytest.raises((logging.Error, AttributeError, TypeError)):
            validate_configuration(str(tmp_path / "config.toml"), {})

    def test_none_config_raises(self, tmp_path):
        with pytest.raises((logging.Error, AttributeError, TypeError)):
            validate_configuration(str(tmp_path / "config.toml"), None)


# ---------------------------------------------------------------------------
# get_component_from_config
# ---------------------------------------------------------------------------


class TestGetComponentFromConfig:
    def test_returns_correct_component(self, tmp_path):
        p = write_config(tmp_path, VALID_CONFIG)
        result = get_component_from_config(config=p, component="default")
        assert result["name"] == "default"
        assert result["changelog"] == "CHANGELOG.md"

    def test_returns_second_component(self, tmp_path):
        p = write_config(tmp_path, VALID_CONFIG)
        result = get_component_from_config(config=p, component="service-a")
        assert result["changelog"] == "service-a/CHANGELOG.md"

    def test_unknown_component_raises(self, tmp_path):
        p = write_config(tmp_path, VALID_CONFIG)
        with pytest.raises(logging.Error, match="Unknown component"):
            get_component_from_config(config=p, component="nonexistent")

    def test_missing_config_file_raises(self, tmp_path):
        with pytest.raises((FileNotFoundError, OSError)):
            get_component_from_config(
                config=str(tmp_path / "missing.toml"), component="default"
            )

    def test_single_component_config(self, tmp_path):
        config = """\
[[components]]
name = "only"
changelog = "only/CHANGELOG.md"
"""
        p = write_config(tmp_path, config)
        result = get_component_from_config(config=p, component="only")
        assert result["name"] == "only"

    def test_component_name_is_case_sensitive(self, tmp_path):
        p = write_config(tmp_path, VALID_CONFIG)
        with pytest.raises(logging.Error):
            get_component_from_config(config=p, component="Default")

    def test_empty_components_list_raises(self, tmp_path):
        # An empty components list fails validate_configuration ("Incorrect Project
        # configuration format!") before even trying to find the component, so the
        # error message is about config format, not "Unknown component".
        config = """\
components = []
"""
        p = write_config(tmp_path, config)
        with pytest.raises(logging.Error, match="configuration format"):
            get_component_from_config(config=p, component="default")
