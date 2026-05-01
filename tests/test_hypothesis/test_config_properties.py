"""Property-based tests for config validation logic."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.config import validate_configuration

# ---------------------------------------------------------------------------
# Strategies
# ---------------------------------------------------------------------------

component_name = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N")),
    min_size=1,
    max_size=40,
)

changelog_path = st.builds(
    lambda name: f"path/to/{name}/CHANGELOG.md",
    name=component_name,
)

valid_component = st.fixed_dictionaries(
    {"name": component_name, "changelog": changelog_path}
)

valid_config = st.fixed_dictionaries(
    {
        "project": st.fixed_dictionaries(
            {"components": st.lists(valid_component, min_size=1, max_size=5)}
        )
    }
)


# ---------------------------------------------------------------------------
# Valid configs always pass
# ---------------------------------------------------------------------------


class TestValidConfigPasses:
    @given(config=valid_config)
    def test_valid_config_does_not_raise(self, config):
        validate_configuration("config.yaml", config)

    @given(components=st.lists(valid_component, min_size=1, max_size=5))
    def test_any_number_of_valid_components_passes(self, components):
        config = {"project": {"components": components}}
        validate_configuration("config.yaml", config)

    @given(name=component_name, path=changelog_path)
    def test_single_component_passes(self, name, path):
        config = {"project": {"components": [{"name": name, "changelog": path}]}}
        validate_configuration("config.yaml", config)


# ---------------------------------------------------------------------------
# Missing required keys always fail
# ---------------------------------------------------------------------------


class TestInvalidConfigFails:
    def test_empty_config_raises(self):
        with pytest.raises(logging.Error):
            validate_configuration("config.yaml", {})

    def test_missing_project_key_raises(self):
        with pytest.raises(logging.Error):
            validate_configuration("config.yaml", {"not_project": {}})

    def test_missing_components_raises(self):
        with pytest.raises(logging.Error):
            validate_configuration("config.yaml", {"project": {}})

    def test_empty_components_raises(self):
        with pytest.raises(logging.Error):
            validate_configuration("config.yaml", {"project": {"components": []}})

    @given(name=component_name)
    def test_component_missing_changelog_raises(self, name):
        config = {"project": {"components": [{"name": name}]}}
        with pytest.raises(logging.Error):
            validate_configuration("config.yaml", config)

    @given(path=changelog_path)
    def test_component_missing_name_raises(self, path):
        config = {"project": {"components": [{"changelog": path}]}}
        with pytest.raises(logging.Error):
            validate_configuration("config.yaml", config)

    @given(components=st.lists(valid_component, min_size=1, max_size=4))
    @settings(max_examples=30)
    def test_one_bad_component_among_valid_ones_raises(self, components):
        bad = {"changelog": "path/CHANGELOG.md"}  # missing name
        config = {"project": {"components": components + [bad]}}
        with pytest.raises(logging.Error):
            validate_configuration("config.yaml", config)
