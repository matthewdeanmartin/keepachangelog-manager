"""Property-based tests for backfill helpers and invariants."""

from __future__ import annotations

import string
from collections import OrderedDict

from hypothesis import given
from hypothesis import strategies as st

from changelogmanager import backfill
from changelogmanager.change_types import TYPES_OF_CHANGE, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.versioning import parse_version


def render_case(text, style):
    if style == "upper":
        return text.upper()
    if style == "title":
        return text.title()
    return text


def toggle_v_prefix(tag, use_prefix):
    normalized = backfill.normalize_tag_version(tag)
    return f"v{normalized}" if use_prefix else normalized


word = st.text(alphabet=string.ascii_letters + string.digits, min_size=1, max_size=12)
body_text = st.builds(
    lambda head, middle, tail: f"{head}{middle}{tail}",
    head=word,
    middle=st.text(
        alphabet=string.ascii_letters + string.digits + " /._-",
        max_size=24,
    ),
    tail=word,
)
boundary_noise = st.builds(
    lambda left_ws, marks, right_ws: f"{left_ws}{marks}{right_ws}",
    left_ws=st.text(alphabet=" \t", max_size=2),
    marks=st.text(alphabet="-:", max_size=3),
    right_ws=st.text(alphabet=" \t", max_size=2),
)
semver_strategy = st.builds(
    lambda major, minor, patch: f"{major}.{minor}.{patch}",
    major=st.integers(min_value=0, max_value=20),
    minor=st.integers(min_value=0, max_value=20),
    patch=st.integers(min_value=0, max_value=20),
)


@st.composite
def tag_rows_and_bounds(draw):
    versions = draw(st.lists(semver_strategy, min_size=1, max_size=6, unique=True))
    tags = [toggle_v_prefix(version, draw(st.booleans())) for version in versions]
    rows = [[tag, f"2024-01-{index + 1:02d}"] for index, tag in enumerate(tags)]
    start = draw(st.integers(min_value=0, max_value=len(rows) - 1))
    end = draw(st.integers(min_value=start, max_value=len(rows) - 1))
    since = toggle_v_prefix(rows[start][0], draw(st.booleans()))
    until = toggle_v_prefix(rows[end][0], draw(st.booleans()))
    return rows, start, end, since, until


class TestCommitParsers:
    @given(version=semver_strategy)
    def test_normalize_tag_version_is_idempotent(self, version):
        assert backfill.normalize_tag_version(version) == version
        assert backfill.normalize_tag_version(f"v{version}") == version
        assert (
            backfill.normalize_tag_version(
                backfill.normalize_tag_version(f"v{version}")
            )
            == version
        )

    @given(body=body_text, prefix=boundary_noise, suffix=boundary_noise)
    def test_clean_commit_message_strips_only_boundary_noise(
        self, body, prefix, suffix
    ):
        assert backfill.clean_commit_message(f"{prefix}{body}{suffix}") == body

    @given(
        commit_type=st.sampled_from(sorted(backfill.CONVENTIONAL_TO_KAC)),
        body=body_text,
        prefix=boundary_noise,
        suffix=boundary_noise,
        breaking=st.booleans(),
        scoped=st.booleans(),
    )
    def test_parse_conventional_commit_maps_known_types(
        self, commit_type, body, prefix, suffix, breaking, scoped
    ):
        scope = "(api)" if scoped else ""
        bang = "!" if breaking else ""
        subject = f"{commit_type}{scope}{bang}: {prefix}{body}{suffix}"
        kac_type = backfill.CONVENTIONAL_TO_KAC[commit_type]
        if breaking:
            # Breaking changes always map to "removed" regardless of type.
            assert backfill.parse_conventional_commit(subject) == ("removed", body)
        elif kac_type is None:
            # Non-user-facing types are skipped (return None).
            assert backfill.parse_conventional_commit(subject) is None
        else:
            assert backfill.parse_conventional_commit(subject) == (kac_type, body)

    @given(
        commit_type=st.text(
            alphabet=string.ascii_lowercase, min_size=1, max_size=12
        ).filter(lambda value: value not in backfill.CONVENTIONAL_TO_KAC),
        body=body_text,
        prefix=boundary_noise,
        suffix=boundary_noise,
    )
    def test_parse_conventional_commit_defaults_unknown_types_to_changed(
        self, commit_type, body, prefix, suffix
    ):
        subject = f"{commit_type}: {prefix}{body}{suffix}"
        assert backfill.parse_conventional_commit(subject) == ("changed", body)

    @given(
        change_type=st.sampled_from(
            ["added", "changed", "deprecated", "removed", "fixed", "security"]
        ),
        body=body_text,
        prefix=boundary_noise,
        suffix=boundary_noise,
        style=st.sampled_from(["lower", "upper", "title"]),
        bracketed=st.booleans(),
        separator=st.sampled_from([": ", "- ", " "]),
    )
    def test_parse_keepachangelog_commit_is_case_insensitive(
        self, change_type, body, prefix, suffix, style, bracketed, separator
    ):
        label = render_case(change_type, style)
        prefix_text = f"[{label}]" if bracketed else label
        subject = f"{prefix_text}{separator}{prefix}{body}{suffix}"
        assert backfill.parse_keepachangelog_commit(subject) == (change_type, body)

    @given(
        emoji=st.sampled_from(sorted(backfill.GITMOJI_TO_KAC)),
        body=body_text,
        prefix=boundary_noise,
        suffix=boundary_noise,
    )
    def test_parse_gitmoji_commit_maps_known_prefixes(
        self, emoji, body, prefix, suffix
    ):
        subject = f"{emoji} {prefix}{body}{suffix}"
        assert backfill.parse_gitmoji_commit(subject) == (
            backfill.GITMOJI_TO_KAC[emoji],
            body,
        )


class TestTagFiltering:
    @given(data=tag_rows_and_bounds())
    def test_find_tag_boundary_accepts_prefixed_and_unprefixed_targets(self, data):
        rows, start, end, since, until = data
        assert backfill.find_tag_boundary(rows, since) == start
        assert backfill.find_tag_boundary(rows, until) == end

    @given(data=tag_rows_and_bounds())
    def test_filter_tag_rows_returns_requested_contiguous_slice(self, data):
        rows, start, end, since, until = data
        assert (
            backfill.filter_tag_rows(rows, since=since, until=until)
            == rows[start : end + 1]
        )

    @given(data=tag_rows_and_bounds())
    def test_filter_tag_rows_returns_empty_when_bounds_cross(self, data):
        rows, start, end, _, _ = data
        assert backfill.filter_tag_rows(
            rows,
            since=toggle_v_prefix(rows[end][0], True),
            until=toggle_v_prefix(rows[start][0], False),
        ) == ([] if end > start else [list(rows[start])])


class TestEntriesFromCommits:
    @given(
        bodies=st.lists(
            body_text, min_size=1, max_size=6, unique_by=lambda value: value.lower()
        )
    )
    def test_entries_from_conventional_commits_preserves_order_and_confidence(
        self, bodies
    ):
        commits = [
            backfill.GitCommit(sha=f"{index:040x}", subject=f"feat: {body}")
            for index, body in enumerate(bodies)
        ]

        entries = backfill.entries_from_commits(commits, commit_schema="conventional")

        assert [entry.change_type for entry in entries] == ["added"] * len(bodies)
        assert [entry.text for entry in entries] == bodies
        assert [entry.confidence for entry in entries] == ["medium"] * len(bodies)
        assert [entry.source for entry in entries] == ["commits"] * len(bodies)

    @given(
        bodies=st.lists(
            body_text, min_size=1, max_size=6, unique_by=lambda value: value.lower()
        )
    )
    def test_entries_from_commits_deduplicates_case_and_whitespace_variants(
        self, bodies
    ):
        commits = []
        for index, body in enumerate(bodies):
            commits.append(
                backfill.GitCommit(sha=f"{index:040x}", subject=f"fix: {body}")
            )
            commits.append(
                backfill.GitCommit(
                    sha=f"{index + len(bodies):040x}",
                    subject=f"fix:   {body.upper()}  ",
                )
            )

        entries = backfill.entries_from_commits(commits, commit_schema="conventional")

        assert [entry.change_type for entry in entries] == ["fixed"] * len(bodies)
        assert [entry.text for entry in entries] == bodies
        assert [entry.confidence for entry in entries] == ["medium"] * len(bodies)

    @given(bodies=st.lists(body_text, min_size=1, max_size=6, unique=True))
    def test_entries_from_unparsed_commits_fall_back_to_low_confidence_changed(
        self, bodies
    ):
        subjects = [f"misc {body}" for body in bodies]
        commits = [
            backfill.GitCommit(sha=f"{index:040x}", subject=subject)
            for index, subject in enumerate(subjects)
        ]

        entries = backfill.entries_from_commits(commits, commit_schema="auto")

        assert [entry.change_type for entry in entries] == ["changed"] * len(subjects)
        assert [entry.text for entry in entries] == subjects
        assert [entry.confidence for entry in entries] == ["low"] * len(subjects)


class TestReleaseRendering:
    @given(
        version=semver_strategy,
        date=st.one_of(st.none(), st.dates().map(str)),
        entry_specs=st.lists(
            st.tuples(st.sampled_from(TYPES_OF_CHANGE), body_text),
            min_size=1,
            max_size=8,
        ),
    )
    def test_release_to_changelog_entry_groups_texts_by_change_type(
        self, version, date, entry_specs
    ):
        release = backfill.BackfillRelease(
            version=version,
            date=date,
            tag=f"v{version}",
            title=None,
            body=None,
            entries=[
                backfill.BackfillEntry(
                    change_type=change_type,
                    text=text,
                    source="commits",
                )
                for change_type, text in entry_specs
            ],
        )

        rendered = backfill.release_to_changelog_entry(release)

        assert rendered["metadata"] == {"version": version, "release_date": date}
        for change_type in TYPES_OF_CHANGE:
            expected = [
                text for item_type, text in entry_specs if item_type == change_type
            ]
            if expected:
                assert rendered[change_type] == expected
            else:
                assert change_type not in rendered

    @given(
        versions=st.lists(semver_strategy, min_size=2, max_size=8, unique=True),
        split=st.integers(min_value=1, max_value=7),
    )
    def test_apply_backfill_plan_keeps_unreleased_first_and_sorts_releases(
        self, versions, split
    ):
        if split >= len(versions):
            split = len(versions) - 1
        existing_versions = versions[:split]
        planned_versions = versions[split:]

        changelog_data = OrderedDict(
            {
                UNRELEASED_ENTRY: {
                    "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
                    "added": ["pending"],
                }
            }
        )
        for version in existing_versions:
            changelog_data[version] = {
                "metadata": {"version": version, "release_date": "2024-01-01"}
            }
        changelog = Changelog(file_path="CHANGELOG.md", changelog=changelog_data)

        plan = backfill.BackfillPlan(
            changelog_path="CHANGELOG.md",
            releases=[
                backfill.BackfillRelease(
                    version=version,
                    date="2024-02-01",
                    tag=f"v{version}",
                    title=None,
                    body=None,
                    entries=[
                        backfill.BackfillEntry(
                            change_type="fixed",
                            text=f"fix {version}",
                            source="commits",
                        )
                    ],
                )
                for version in planned_versions
            ],
            added_versions=planned_versions,
            skipped_versions=[],
            skipped_tags=[],
            sources=["commits"],
            dry_run=False,
        )

        backfill.apply_backfill_plan(changelog, plan)

        keys = list(changelog.get().keys())
        expected_versions = sorted(
            versions,
            key=lambda version: parse_version(version, "semver"),
            reverse=True,
        )
        assert keys[0] == UNRELEASED_ENTRY
        assert keys[1:] == expected_versions
        assert changelog.get()[UNRELEASED_ENTRY]["added"] == ["pending"]
        for version in planned_versions:
            assert changelog.get()[version]["fixed"] == [f"fix {version}"]
