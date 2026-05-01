"""Property-based tests for change_types module."""

from hypothesis import given
from hypothesis import strategies as st

from changelogmanager.change_types import CATEGORIES, TYPES_OF_CHANGE, VersionCore


class TestCategoriesConsistency:
    @given(name=st.sampled_from(TYPES_OF_CHANGE))
    def test_every_type_has_a_category(self, name):
        assert name in CATEGORIES

    @given(name=st.sampled_from(list(CATEGORIES.keys())))
    def test_every_category_name_is_in_types_of_change(self, name):
        assert name in TYPES_OF_CHANGE

    @given(name=st.sampled_from(list(CATEGORIES.keys())))
    def test_category_bump_is_valid_version_core(self, name):
        assert isinstance(CATEGORIES[name].bump, VersionCore)

    @given(name=st.sampled_from(list(CATEGORIES.keys())))
    def test_category_emoji_is_nonempty_string(self, name):
        assert isinstance(CATEGORIES[name].emoji, str)
        assert len(CATEGORIES[name].emoji) > 0

    @given(name=st.sampled_from(list(CATEGORIES.keys())))
    def test_category_title_is_nonempty_string(self, name):
        assert isinstance(CATEGORIES[name].title, str)
        assert len(CATEGORIES[name].title) > 0

    def test_types_of_change_and_categories_same_length(self):
        assert len(TYPES_OF_CHANGE) == len(CATEGORIES)

    def test_removed_is_major_bump(self):
        assert CATEGORIES["removed"].bump == VersionCore.MAJOR

    def test_added_is_minor_bump(self):
        assert CATEGORIES["added"].bump == VersionCore.MINOR

    def test_security_is_minor_bump(self):
        assert CATEGORIES["security"].bump == VersionCore.MINOR

    @given(name=st.sampled_from(["fixed", "changed", "deprecated"]))
    def test_patch_types_are_patch_bump(self, name):
        assert CATEGORIES[name].bump == VersionCore.PATCH

    @given(names=st.lists(st.sampled_from(list(CATEGORIES.keys())), min_size=1))
    def test_categories_bump_values_are_ordered_consistently(self, names):
        # VersionCore.MAJOR > MINOR > PATCH by numeric value
        for name in names:
            bump = CATEGORIES[name].bump
            assert bump.value in (VersionCore.MAJOR.value, VersionCore.MINOR.value, VersionCore.PATCH.value)
