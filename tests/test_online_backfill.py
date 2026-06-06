# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tests for online backfill sources (github-releases, pypi)."""

import os

import pytest

from changelogmanager.backfill import (
    BackfillRelease,
    _merge_releases,
    discover_github_releases,
    discover_pypi_releases,
)
from changelogmanager.services import validate_backfill_options

# ---------------------------------------------------------------------------
# validate_backfill_options — source acceptance
# ---------------------------------------------------------------------------


def test_validate_accepts_local() -> None:
    validate_backfill_options(
        source="local", strategy="conservative", missing_only=True
    )


def test_validate_accepts_tags() -> None:
    validate_backfill_options(source="tags", strategy="conservative", missing_only=True)


def test_validate_accepts_commits() -> None:
    validate_backfill_options(
        source="commits", strategy="conservative", missing_only=True
    )


def test_validate_accepts_all_without_repository() -> None:
    # all without repository is allowed at validation time; plan_backfill warns at runtime
    validate_backfill_options(source="all", strategy="conservative", missing_only=True)


def test_validate_accepts_github_releases_with_repository() -> None:
    validate_backfill_options(
        source="github-releases",
        strategy="conservative",
        missing_only=True,
        repository="owner/repo",
    )


def test_validate_rejects_github_releases_without_repository() -> None:
    import changelogmanager.llvm_diagnostics as logging

    with pytest.raises(logging.Error, match="--repository"):
        validate_backfill_options(
            source="github-releases",
            strategy="conservative",
            missing_only=True,
            repository=None,
        )


def test_validate_rejects_unknown_source() -> None:
    import changelogmanager.llvm_diagnostics as logging

    with pytest.raises(logging.Error, match="Unknown backfill source"):
        validate_backfill_options(
            source="banana", strategy="conservative", missing_only=True
        )


def test_validate_accepts_github_prs_with_repository() -> None:
    # github-prs is now implemented; should no longer raise
    validate_backfill_options(
        source="github-prs",
        strategy="conservative",
        missing_only=True,
        repository="owner/repo",
    )


def test_validate_rejects_pypi_without_package() -> None:
    import changelogmanager.llvm_diagnostics as logging

    with pytest.raises(logging.Error, match="--package"):
        validate_backfill_options(
            source="pypi", strategy="conservative", missing_only=True
        )


def test_validate_accepts_pypi_with_package() -> None:
    validate_backfill_options(
        source="pypi", strategy="conservative", missing_only=True, package="my-package"
    )


# ---------------------------------------------------------------------------
# discover_github_releases — mocked
# ---------------------------------------------------------------------------


def test_discover_github_releases_returns_releases(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_releases_for_backfill=mocker.MagicMock(
                return_value=[
                    {"version": "v1.2.0", "body": "Some changes", "date": "2024-01-15"},
                    {"version": "v1.1.0", "body": "Bug fixes", "date": "2024-01-01"},
                ]
            )
        ),
    )
    releases, skipped = discover_github_releases("owner/repo", "tok")
    assert len(releases) == 2
    assert releases[0].version == "1.2.0"
    assert releases[1].version == "1.1.0"
    assert skipped == []


def test_discover_github_releases_strips_v_prefix(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_releases_for_backfill=mocker.MagicMock(
                return_value=[{"version": "v2.0.0", "body": "", "date": "2024-03-01"}]
            )
        ),
    )
    releases, _ = discover_github_releases("owner/repo", None)
    assert releases[0].version == "2.0.0"
    assert releases[0].tag == "v2.0.0"


def test_discover_github_releases_skips_non_semver(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_releases_for_backfill=mocker.MagicMock(
                return_value=[
                    {"version": "not-a-version", "body": "", "date": None},
                    {"version": "v1.0.0", "body": "ok", "date": "2024-01-01"},
                ]
            )
        ),
    )
    releases, skipped = discover_github_releases("owner/repo", "tok")
    assert len(releases) == 1
    assert len(skipped) == 1
    assert skipped[0] == "not-a-version"


def test_discover_github_releases_uses_fallback_entry_for_empty_body(
    mocker: pytest.MonkeyPatch,
) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_releases_for_backfill=mocker.MagicMock(
                return_value=[{"version": "v1.0.0", "body": "", "date": "2024-01-01"}]
            )
        ),
    )
    releases, _ = discover_github_releases("owner/repo", "tok")
    assert "backfilled from GitHub release" in releases[0].entries[0].text


def test_discover_github_releases_uses_body_as_entry(
    mocker: pytest.MonkeyPatch,
) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_releases_for_backfill=mocker.MagicMock(
                return_value=[
                    {
                        "version": "v1.0.0",
                        "body": "Fixed the thing",
                        "date": "2024-01-01",
                    }
                ]
            )
        ),
    )
    releases, _ = discover_github_releases("owner/repo", "tok")
    assert releases[0].entries[0].text == "Fixed the thing"
    assert releases[0].entries[0].source == "github-releases"


def test_discover_github_releases_source_url(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.github.GitHub",
        return_value=mocker.MagicMock(
            get_releases_for_backfill=mocker.MagicMock(
                return_value=[
                    {"version": "v3.0.0", "body": "stuff", "date": "2024-06-01"}
                ]
            )
        ),
    )
    releases, _ = discover_github_releases("owner/repo", "tok")
    assert (
        releases[0].sources[0].url
        == "https://github.com/owner/repo/releases/tag/v3.0.0"
    )


# ---------------------------------------------------------------------------
# _merge_releases
# ---------------------------------------------------------------------------


def _make_release(version: str, text: str, source: str = "tags") -> BackfillRelease:
    from changelogmanager.backfill import BackfillEntry, BackfillSource

    return BackfillRelease(
        version=version,
        date="2024-01-01",
        tag=f"v{version}",
        title=None,
        body=None,
        entries=[BackfillEntry(change_type="changed", text=text, source=source)],
        sources=[BackfillSource(name=source, identifier=f"v{version}")],
    )


def test_merge_releases_deduplicates_same_text() -> None:
    r1 = _make_release("1.0.0", "Fix the bug", "tags")
    r2 = _make_release("1.0.0", "Fix the bug", "github-releases")
    merged = _merge_releases([r1], [r2])
    assert len(merged) == 1
    assert len(merged[0].entries) == 1


def test_merge_releases_keeps_distinct_entries() -> None:
    r1 = _make_release("1.0.0", "Fix the bug", "tags")
    r2 = _make_release("1.0.0", "Add new feature", "github-releases")
    merged = _merge_releases([r1], [r2])
    assert len(merged) == 1
    assert len(merged[0].entries) == 2


def test_merge_releases_combines_distinct_versions() -> None:
    r1 = _make_release("1.0.0", "First")
    r2 = _make_release("2.0.0", "Second")
    merged = _merge_releases([r1], [r2])
    assert {r.version for r in merged} == {"1.0.0", "2.0.0"}


# ---------------------------------------------------------------------------
# discover_pypi_releases — mocked
# ---------------------------------------------------------------------------


def test_discover_pypi_releases_returns_releases(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.pypi.get_pypi_releases",
        return_value=[
            {"version": "1.2.0", "date": "2024-03-01"},
            {"version": "1.1.0", "date": "2024-02-01"},
        ],
    )
    releases, skipped = discover_pypi_releases("my-package")
    assert len(releases) == 2
    assert releases[0].version == "1.2.0"
    assert releases[1].version == "1.1.0"
    assert skipped == []


def test_discover_pypi_releases_skips_non_semver(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.pypi.get_pypi_releases",
        return_value=[
            {"version": "not-valid", "date": None},
            {"version": "2.0.0", "date": "2024-01-01"},
        ],
    )
    releases, skipped = discover_pypi_releases("my-package")
    assert len(releases) == 1
    assert skipped == ["not-valid"]


def test_discover_pypi_releases_source_is_pypi(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.pypi.get_pypi_releases",
        return_value=[{"version": "1.0.0", "date": "2024-01-01"}],
    )
    releases, _ = discover_pypi_releases("my-package")
    assert releases[0].entries[0].source == "pypi"
    assert releases[0].sources[0].name == "pypi"


def test_discover_pypi_releases_url_contains_package_and_version(
    mocker: pytest.MonkeyPatch,
) -> None:
    mocker.patch(
        "changelogmanager.pypi.get_pypi_releases",
        return_value=[{"version": "3.1.4", "date": "2024-05-01"}],
    )
    releases, _ = discover_pypi_releases("my-package")
    assert "my-package" in releases[0].sources[0].url
    assert "3.1.4" in releases[0].sources[0].url


def test_discover_pypi_releases_tag_is_none(mocker: pytest.MonkeyPatch) -> None:
    mocker.patch(
        "changelogmanager.pypi.get_pypi_releases",
        return_value=[{"version": "1.0.0", "date": "2024-01-01"}],
    )
    releases, _ = discover_pypi_releases("my-package")
    assert releases[0].tag is None


# ---------------------------------------------------------------------------
# get_pypi_releases unit tests
# ---------------------------------------------------------------------------


def test_get_pypi_releases_parses_response(mocker: pytest.MonkeyPatch) -> None:
    import io

    from changelogmanager.pypi import get_pypi_releases

    payload = {
        "releases": {
            "1.0.0": [{"upload_time": "2024-01-15T12:00:00"}],
            "2.0.0": [{"upload_time": "2024-06-01T08:00:00"}],
            "0.9.0": [],  # no files — should be skipped
        }
    }
    import orjson

    mock_resp = mocker.MagicMock()
    mock_resp.read.return_value = orjson.dumps(payload)
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = mocker.MagicMock(return_value=False)
    mocker.patch("changelogmanager.pypi.urlopen", return_value=mock_resp)

    releases = get_pypi_releases("my-package")
    versions = [r["version"] for r in releases]
    assert "1.0.0" in versions
    assert "2.0.0" in versions
    assert "0.9.0" not in versions
    assert releases[0]["date"] == "2024-06-01"  # sorted newest-first


def test_get_pypi_releases_raises_on_http_error(mocker: pytest.MonkeyPatch) -> None:
    import urllib.error

    import changelogmanager.llvm_diagnostics as logging
    from changelogmanager.pypi import get_pypi_releases

    mocker.patch(
        "changelogmanager.pypi.urlopen",
        side_effect=urllib.error.HTTPError(
            url=None, code=404, msg="Not Found", hdrs=None, fp=None
        ),
    )
    with pytest.raises(logging.Error, match="404"):
        get_pypi_releases("nonexistent-package")


# ---------------------------------------------------------------------------
# Integration smoke tests (require network)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not os.environ.get("GITHUB_TOKEN"), reason="no GITHUB_TOKEN in environment"
)
def test_discover_github_releases_real() -> None:
    releases, skipped = discover_github_releases(
        "matthewdeanmartin/keepachangelog-manager",
        os.environ["GITHUB_TOKEN"],
    )
    assert isinstance(releases, list)
    assert all(hasattr(r, "version") for r in releases)
