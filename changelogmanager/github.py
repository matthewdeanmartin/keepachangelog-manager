# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""GitHub"""

import os
from collections.abc import Mapping, Sequence
from enum import Enum
from textwrap import dedent
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import orjson

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.runtime_logging import VERBOSE, get_logger

RELEASES_CHUNK_SIZE = 100
GITHUB_API_VERSION = "2026-03-10"
logger = get_logger(__name__)


class HttpMethods(Enum):
    """Http Methods"""

    GET = "GET"
    POST = "POST"
    PATCH = "PATCH"
    DELETE = "DELETE"


class GitHub:
    """GitHub"""

    def __init__(self, repository: str, token: str) -> None:
        """Constructor"""

        self.repository = repository
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": GITHUB_API_VERSION,
        }
        logger.info("Initialized GitHub client for repository %s", repository)

    def github_request(
        self, api: str, method: HttpMethods, data: Optional[Mapping[str, Any]] = None
    ) -> Optional[Any]:
        url = f"https://api.github.com/repos/{self.repository}/{api}"
        request_data: Optional[bytes] = None
        headers = dict(self.headers)
        if method is HttpMethods.GET and data:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(data)}"
        elif data:
            request_data = orjson.dumps(data)
            headers["Content-Type"] = "application/json"

        logger.info("Calling GitHub API %s %s", method.value, url)
        if data:
            logger.log(
                VERBOSE, "GitHub API payload for %s %s: %s", method.value, url, data
            )

        request = Request(
            method=method.value,
            url=url,
            data=request_data,
            headers=headers,
        )

        response = b""
        try:
            with urlopen(request) as resp:  # nosec
                response = resp.read()

            if not response:
                logger.warning(
                    "GitHub API %s %s returned an empty response", method.value, url
                )
                return None

            logger.log(
                VERBOSE,
                "GitHub API %s %s returned %d bytes",
                method.value,
                url,
                len(response),
            )
            return orjson.loads(response)
        except HTTPError as http_error:
            response_body = http_error.read().decode(errors="replace").strip()
            logger.error(
                "GitHub API request failed for %s %s (HTTP %s)",
                method.value,
                url,
                http_error.code,
            )
            raise logging.Error(message=dedent(f"""
                Failure during GitHub request:
                  URL:    {url}
                  Method: {method.value}
                  Status: {http_error.code} {http_error.reason}
                  Data:   {data}
                  Body:   {response_body or '<empty>'}""")) from http_error
        except URLError as url_error:
            logger.error("GitHub API request failed for %s %s", method.value, url)
            raise logging.Error(message=dedent(f"""
                Failure during GitHub request:
                  URL:    {url}
                  Method: {method.value}
                  Data:   {data}""")) from url_error

    def get_releases(self) -> Sequence[dict[str, Any]]:
        """Retrieves available releases"""
        logger.info("Fetching releases for %s", self.repository)
        releases: list[dict[str, Any]] = []
        index = 1

        while True:
            data = self.github_request(
                method=HttpMethods.GET,
                api="releases",
                data={
                    "per_page": RELEASES_CHUNK_SIZE,
                    "page": index,
                },
            )

            if not data:
                break

            releases.extend(data)

            if len(data) < RELEASES_CHUNK_SIZE:
                break

            index = index + 1

        return releases

    def delete_draft_releases(self) -> None:
        """Deletes all releases marked as 'Draft'"""
        logger.info("Deleting draft releases for %s", self.repository)

        releases = self.get_releases()

        for rel in releases:
            if rel.get("draft"):
                self.delete_release(rel)

    def delete_release(self, release: Mapping[str, Any]) -> None:
        """Deletes a release"""
        logger.warning(
            "Deleting draft release %s from %s",
            release.get("id"),
            self.repository,
        )

        self.github_request(
            method=HttpMethods.DELETE, api=f"releases/{release.get('id')}"
        )

    def get_pull_requests(self, head: str, base: str) -> Sequence[dict[str, Any]]:
        """Returns open PRs matching head branch and base branch."""
        logger.info(
            "Checking for existing PRs head=%s base=%s in %s",
            head,
            base,
            self.repository,
        )
        data = self.github_request(
            method=HttpMethods.GET,
            api="pulls?"
            + urlencode(
                {
                    "state": "open",
                    "head": f"{self.repository.split('/')[0]}:{head}",
                    "base": base,
                }
            ),
        )
        if not isinstance(data, list):
            return []
        return data

    def create_pull_request(
        self,
        *,
        head: str,
        base: str,
        title: str,
        body: str,
    ) -> Mapping[str, Any]:
        """Creates a PR, or updates the title/body if one already exists for that branch."""
        logger.info(
            "Creating or updating PR head=%s base=%s in %s",
            head,
            base,
            self.repository,
        )
        existing = self.get_pull_requests(head=head, base=base)
        if existing:
            pr = existing[0]
            pr_number = pr["number"]
            logger.info("Updating existing PR #%d", pr_number)
            response = self.github_request(
                method=HttpMethods.PATCH,
                api=f"pulls/{pr_number}",
                data={"title": title, "body": body},
            )
        else:
            response = self.github_request(
                method=HttpMethods.POST,
                api="pulls",
                data={"head": head, "base": base, "title": title, "body": body},
            )

        if not isinstance(response, Mapping):
            raise logging.Error(message="GitHub did not return PR details")
        return response

    def create_release(self, changelog: Changelog, draft: bool) -> Mapping[str, Any]:
        """Creates a new release on GitHub"""
        logger.info(
            "Creating %s GitHub release for %s",
            "draft" if draft else "published",
            self.repository,
        )

        def generate_release_notes(release: Mapping[str, Any]) -> str:
            body = "## What's changed" + os.linesep + os.linesep
            body += os.linesep.join(
                [
                    f"### :{category.emoji}: {category.title}"
                    + os.linesep
                    + os.linesep.join(
                        [f"* {message}" for message in release[identifier]]
                    )
                    for identifier, category in CATEGORIES.items()
                    if identifier in release
                ]
            )
            return body

        version = f"v{changelog.suggest_future_version()}"
        logger.info("Preparing GitHub release payload for version %s", version)
        response = self.github_request(
            method=HttpMethods.POST,
            api="releases",
            data={
                "tag_name": version,
                "name": f"Release {version}",
                "draft": draft,
                "body": generate_release_notes(changelog.get(UNRELEASED_ENTRY)),
            },
        )
        if not isinstance(response, Mapping):
            raise logging.Error(
                message=f"GitHub did not return release details for {version}"
            )
        return response
