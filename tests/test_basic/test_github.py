from collections import OrderedDict
from urllib.error import URLError

import pytest

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.github import RELEASES_CHUNK_SIZE, GitHub, HttpMethods


def test_get_releases_paginates_until_partial_page(monkeypatch):
    github = GitHub("owner/repo", "token")
    pages = []

    def fake_request(self, api, method, data=None):
        pages.append((api, method, data["page"]))
        if data["page"] == 1:
            return [{"id": index} for index in range(RELEASES_CHUNK_SIZE)]
        return [{"id": 999}]

    monkeypatch.setattr(GitHub, "_GitHub__github_request", fake_request)

    releases = github.get_releases()

    assert len(releases) == RELEASES_CHUNK_SIZE + 1
    assert pages == [("releases", HttpMethods.GET, 1), ("releases", HttpMethods.GET, 2)]


def test_delete_draft_releases_only_deletes_drafts(monkeypatch):
    deleted = []
    github = GitHub("owner/repo", "token")

    monkeypatch.setattr(
        GitHub,
        "get_releases",
        lambda self: [{"id": 1, "draft": True}, {"id": 2, "draft": False}],
    )
    monkeypatch.setattr(
        GitHub, "delete_release", lambda self, release: deleted.append(release["id"])
    )

    github.delete_draft_releases()

    assert deleted == [1]


def test_create_release_posts_expected_payload(monkeypatch):
    captured = {}
    changelog = Changelog(
        changelog=OrderedDict(
            [
                (
                    UNRELEASED_ENTRY,
                    {
                        "metadata": {"version": UNRELEASED_ENTRY, "release_date": None},
                        "added": ["Feature"],
                        "fixed": ["Bug"],
                    },
                ),
                ("1.0.0", {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}}),
            ]
        )
    )

    monkeypatch.setattr(
        GitHub,
        "_GitHub__github_request",
        lambda self, api, method, data=None: captured.update(
            {"api": api, "method": method, "data": data}
        ),
    )

    GitHub("owner/repo", "token").create_release(changelog=changelog, draft=False)

    assert captured["api"] == "releases"
    assert captured["method"] is HttpMethods.POST
    assert captured["data"]["tag_name"] == "v1.1.0"
    assert captured["data"]["name"] == "Release v1.1.0"
    assert captured["data"]["draft"] is False
    assert "## What's changed" in captured["data"]["body"]
    assert "### :rocket: New Features" in captured["data"]["body"]
    assert "* Feature" in captured["data"]["body"]
    assert "### :bug: Bug Fixes" in captured["data"]["body"]
    assert "* Bug" in captured["data"]["body"]


def test_github_request_wraps_url_errors(monkeypatch):
    github = GitHub("owner/repo", "secret")

    monkeypatch.setattr(
        "changelogmanager.github.urlopen",
        lambda request: (_ for _ in ()).throw(URLError("boom")),
    )

    with pytest.raises(logging.Error) as exc_info:
        github._GitHub__github_request(
            api="releases", method=HttpMethods.GET, data={"page": 1}
        )

    assert "Failure during GitHub request:" in exc_info.value.message
    assert "https://api.github.com/repos/owner/repo/releases" in exc_info.value.message
    assert "Method: GET" in exc_info.value.message
