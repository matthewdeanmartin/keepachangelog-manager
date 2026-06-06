# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tests for the github-prs backfill source."""

import os

import pytest

from changelogmanager.backfill import (
    BackfillRelease,
    _assign_version_by_date,
    discover_github_prs,
)
from changelogmanager.services import validate_backfill_options


# ---------------------------------------------------------------------------
# validate_backfill_options — github-prs
# ---------------------------------------------------------------------------


def test_validate_accepts_github_prs_with_repository() -> None:
    validate_backfill_options(
        source="github-prs",
        strategy="conservative",
        missing_only=True,
        repository="owner/repo",
    )


def test_validate_rejects_github_prs_without_repository() -> None:
    import changelogmanager.llvm_diagnostics as logging

    with pytest.raises(logging.Error, match="--repository"):
        validate_backfill_options(
            source="github-prs",
            strategy="conservative",
            missing_only=True,
            repository=None,
        )


# ---------------------------------------------------------------------------
# _assign_version_by_date
# ---------------------------------------------------------------------------


def test_assign_version_returns_earliest_enclosing_tag() -> None:
    timeline = [("2024-01-15", "1.0.0"), ("2024-03-01", "1.1.0"), ("2024-06-01", "2.0.0")]
    assert _assign_version_by_date("2024-01-10", timeline) == "1.0.0"
    assert _assign_version_by_date("2024-01-15", timeline) == "1.0.0"
    assert _assign_version_by_date("2024-02-20", timeline) == "1.1.0"
    assert _assign_version_by_date("2024-05-31", timeline) == "2.0.0"


def test_assign_version_returns_none_after_last_tag() -> None:
    timeline = [("2024-01-15", "1.0.0"), ("2024-03-01", "1.1.0")]
    assert _assign_version_by_date("2024-12-01", timeline) is None


def test_assign_version_empty_timeline_returns_none() -> None:
    assert _assign_version_by_date("2024-06-01", []) is None


# ---------------------------------------------------------------------------
# discover_github_prs — mocked
# ---------------------------------------------------------------------------


def _make_pr(title: str, merged_at: str, labels: list[str] | None = None, url: str | None = None) -> dict:
    return {
        "title": title,
        "merged_at": merged_at + "T12:00:00Z",
        "html_url": url or f"https://github.com/owner/repo/pull/1",
        "labels": [{"name": lbl} for lbl in (labels or [])],
    }


def test_discover_github_prs_groups_by_tag_date(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(
                return_value=[
                    _make_pr("Fix login bug", "2024-01-10", ["bug"]),
                    _make_pr("Add dark mode", "2024-02-20", ["enhancement"]),
                ]
            )
        ),
    )
    mocker.patch(
        "changelogmanager.backfill.discover_tags",
        return_value=[
            mocker.MagicMock(date="2024-01-15", version="1.0.0"),
            mocker.MagicMock(date="2024-03-01", version="1.1.0"),
        ],
    )
    releases, skipped = discover_github_prs("owner/repo", "tok")
    assert skipped == []
    versions = {r.version for r in releases}
    assert "1.0.0" in versions
    assert "1.1.0" in versions


def test_discover_github_prs_maps_bug_label_to_fixed(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(
                return_value=[_make_pr("Fix crash", "2024-01-10", ["bug"])]
            )
        ),
    )
    mocker.patch(
        "changelogmanager.backfill.discover_tags",
        return_value=[mocker.MagicMock(date="2024-01-15", version="1.0.0")],
    )
    releases, _ = discover_github_prs("owner/repo", "tok")
    assert releases[0].entries[0].change_type == "fixed"


def test_discover_github_prs_maps_enhancement_to_added(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(
                return_value=[_make_pr("Add feature X", "2024-01-10", ["enhancement"])]
            )
        ),
    )
    mocker.patch(
        "changelogmanager.backfill.discover_tags",
        return_value=[mocker.MagicMock(date="2024-01-15", version="1.0.0")],
    )
    releases, _ = discover_github_prs("owner/repo", "tok")
    assert releases[0].entries[0].change_type == "added"


def test_discover_github_prs_unknown_label_defaults_to_changed(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(
                return_value=[_make_pr("Refactor internals", "2024-01-10", ["internal"])]
            )
        ),
    )
    mocker.patch(
        "changelogmanager.backfill.discover_tags",
        return_value=[mocker.MagicMock(date="2024-01-15", version="1.0.0")],
    )
    releases, _ = discover_github_prs("owner/repo", "tok")
    assert releases[0].entries[0].change_type == "changed"


def test_discover_github_prs_drops_post_tag_prs(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(
                return_value=[_make_pr("Future feature", "2024-12-01")]
            )
        ),
    )
    mocker.patch(
        "changelogmanager.backfill.discover_tags",
        return_value=[mocker.MagicMock(date="2024-01-15", version="1.0.0")],
    )
    releases, _ = discover_github_prs("owner/repo", "tok")
    # PR after all tags → assigned to [Unreleased] → silently dropped
    assert releases == []


def test_discover_github_prs_uses_calendar_months_when_no_tags(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(
                return_value=[
                    _make_pr("Alpha feature", "2024-03-15"),
                    _make_pr("Beta fix", "2024-03-28"),
                ]
            )
        ),
    )
    mocker.patch("changelogmanager.backfill.discover_tags", return_value=[])
    releases, _ = discover_github_prs("owner/repo", None)
    assert len(releases) == 1
    assert releases[0].version == "2024-03"
    assert len(releases[0].entries) == 2


def test_discover_github_prs_deduplicates_same_title(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(
                return_value=[
                    _make_pr("Fix login bug", "2024-01-10", ["bug"]),
                    _make_pr("Fix login bug", "2024-01-11", ["bug"]),  # duplicate title
                ]
            )
        ),
    )
    mocker.patch(
        "changelogmanager.backfill.discover_tags",
        return_value=[mocker.MagicMock(date="2024-01-15", version="1.0.0")],
    )
    releases, _ = discover_github_prs("owner/repo", "tok")
    assert len(releases[0].entries) == 1


def test_discover_github_prs_source_name_is_github_prs(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(
                return_value=[_make_pr("Some change", "2024-01-10")]
            )
        ),
    )
    mocker.patch(
        "changelogmanager.backfill.discover_tags",
        return_value=[mocker.MagicMock(date="2024-01-15", version="1.0.0")],
    )
    releases, _ = discover_github_prs("owner/repo", "tok")
    assert releases[0].entries[0].source == "github-prs"
    assert releases[0].sources[0].name == "github-prs"


def test_discover_github_prs_returns_empty_for_no_prs(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_merged_prs=mocker.MagicMock(return_value=[])
        ),
    )
    mocker.patch(
        "changelogmanager.backfill.discover_tags",
        return_value=[mocker.MagicMock(date="2024-01-15", version="1.0.0")],
    )
    releases, skipped = discover_github_prs("owner/repo", "tok")
    assert releases == []
    assert skipped == []


# ---------------------------------------------------------------------------
# get_merged_prs unit test (GitHub client)
# ---------------------------------------------------------------------------


def test_get_merged_prs_filters_unmerged(mocker: pytest.MonkeyPatch) -> None:
    from changelogmanager.github import GitHub

    client = GitHub.__new__(GitHub)
    client.repository = "owner/repo"
    client.headers = {}
    mocker.patch.object(
        client,
        "_get_with_rate_check",
        return_value=[
            {"title": "Merged PR", "merged_at": "2024-03-01T10:00:00Z", "labels": [], "html_url": "http://x"},
            {"title": "Closed but not merged", "merged_at": None, "labels": [], "html_url": "http://y"},
        ],
    )
    prs = client.get_merged_prs()
    assert len(prs) == 1
    assert prs[0]["title"] == "Merged PR"


def test_get_merged_prs_date_filter_since(mocker: pytest.MonkeyPatch) -> None:
    from changelogmanager.github import GitHub

    client = GitHub.__new__(GitHub)
    client.repository = "owner/repo"
    client.headers = {}
    mocker.patch.object(
        client,
        "_get_with_rate_check",
        return_value=[
            {"title": "Old PR", "merged_at": "2023-06-01T10:00:00Z", "labels": [], "html_url": "http://a"},
            {"title": "New PR", "merged_at": "2024-03-01T10:00:00Z", "labels": [], "html_url": "http://b"},
        ],
    )
    prs = client.get_merged_prs(since_date="2024-01-01")
    assert len(prs) == 1
    assert prs[0]["title"] == "New PR"


def test_get_merged_prs_date_filter_until(mocker: pytest.MonkeyPatch) -> None:
    from changelogmanager.github import GitHub

    client = GitHub.__new__(GitHub)
    client.repository = "owner/repo"
    client.headers = {}
    mocker.patch.object(
        client,
        "_get_with_rate_check",
        return_value=[
            {"title": "Old PR", "merged_at": "2023-06-01T10:00:00Z", "labels": [], "html_url": "http://a"},
            {"title": "New PR", "merged_at": "2024-03-01T10:00:00Z", "labels": [], "html_url": "http://b"},
        ],
    )
    prs = client.get_merged_prs(until_date="2023-12-31")
    assert len(prs) == 1
    assert prs[0]["title"] == "Old PR"


# ---------------------------------------------------------------------------
# Integration smoke test (requires network)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not os.environ.get("GITHUB_TOKEN"), reason="no GITHUB_TOKEN in environment")
def test_discover_github_prs_real() -> None:
    releases, skipped = discover_github_prs(
        "matthewdeanmartin/keepachangelog-manager",
        os.environ["GITHUB_TOKEN"],
    )
    assert isinstance(releases, list)
    assert all(isinstance(r, BackfillRelease) for r in releases)
