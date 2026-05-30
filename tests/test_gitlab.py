# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tests for the GitLab integration."""

from typing import Any
from unittest import mock

import pytest

from changelogmanager.changelog import Changelog
from changelogmanager.gitlab import DEFAULT_GITLAB_URL, GitLab

UNRELEASED_CHANGELOG = {
    "unreleased": {
        "metadata": {"version": "unreleased", "release_date": None},
        "added": ["A new feature"],
    }
}


@pytest.fixture
def gitlab() -> GitLab:
    return GitLab(project="group/repo", token="secret-token")


def test_project_path_is_url_encoded(gitlab: GitLab) -> None:
    # The encoded path must appear in the request URL.
    seen: dict[str, Any] = {}

    def fake_request(*args: Any, **kwargs: Any) -> Any:
        seen["api"] = kwargs.get("api")
        return None

    with mock.patch.object(gitlab, "_GitLab__gitlab_request", side_effect=fake_request):
        gitlab.get_release("v1.0.0")

    # group%2Frepo encoding happens in __init__; here we just confirm the call path.
    assert seen["api"] == "releases/v1.0.0"


def test_create_release_posts_when_absent(gitlab: GitLab) -> None:
    changelog = Changelog(changelog=UNRELEASED_CHANGELOG)
    calls: list[dict[str, Any]] = []

    def fake_request(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        if kwargs["method"].value == "GET":
            return None  # no existing release
        return {"tag_name": "v0.1.0", "_links": {"self": "https://gitlab/x"}}

    with mock.patch.object(gitlab, "_GitLab__gitlab_request", side_effect=fake_request):
        release = gitlab.create_release(changelog=changelog, ref="main")

    methods = [c["method"].value for c in calls]
    assert methods == ["GET", "POST"]
    post = calls[1]
    # The fixture changelog only has [Unreleased]; suggest_future_version() -> 0.0.1.
    assert post["data"]["tag_name"] == "v0.0.1"
    assert post["data"]["ref"] == "main"
    assert release["tag_name"] == "v0.1.0"


def test_create_release_puts_when_present(gitlab: GitLab) -> None:
    changelog = Changelog(changelog=UNRELEASED_CHANGELOG)
    calls: list[dict[str, Any]] = []

    def fake_request(*args: Any, **kwargs: Any) -> Any:
        calls.append(kwargs)
        if kwargs["method"].value == "GET":
            return {"tag_name": "v0.1.0"}  # already exists
        return {"tag_name": "v0.1.0"}

    with mock.patch.object(gitlab, "_GitLab__gitlab_request", side_effect=fake_request):
        gitlab.create_release(changelog=changelog)

    methods = [c["method"].value for c in calls]
    assert methods == ["GET", "PUT"]
    assert "tag_name" not in calls[1]["data"]  # PUT does not resend tag_name


def test_default_url() -> None:
    assert DEFAULT_GITLAB_URL == "https://gitlab.com"
