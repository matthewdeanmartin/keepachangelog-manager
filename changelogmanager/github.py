# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""GitHub"""

import json
import os
from collections.abc import Mapping, Sequence
from enum import Enum
from textwrap import dedent
from typing import Any, Optional
from urllib.error import URLError
from urllib.request import Request, urlopen

import changelogmanager._llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.runtime_logging import VERBOSE, get_logger

RELEASES_CHUNK_SIZE = 100
logger = get_logger(__name__)


class HttpMethods(Enum):
    """Http Methods"""

    GET = "GET"
    POST = "POST"
    DELETE = "DELETE"


class GitHub:
    """GitHub"""

    def __init__(self, repository: str, token: str) -> None:
        """Constructor"""

        self.__repository = repository
        self.__headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}",
        }
        logger.info("Initialized GitHub client for repository %s", repository)

    def __github_request(
        self, api: str, method: HttpMethods, data: Optional[Mapping[str, Any]] = None
    ) -> Optional[Any]:
        url = f"https://api.github.com/repos/{self.__repository}/{api}"
        logger.info("Calling GitHub API %s %s", method.value, url)
        if data:
            logger.log(VERBOSE, "GitHub API payload for %s %s: %s", method.value, url, data)

        request = Request(
            method=method.value,
            url=url,
            data=json.dumps(data).encode() if data else None,
            headers=self.__headers,
        )

        response = ""
        try:
            with urlopen(request) as resp:  # nosec
                response = resp.read().decode()

            if not response:
                logger.warning("GitHub API %s %s returned an empty response", method.value, url)
                return None

            logger.log(VERBOSE, "GitHub API %s %s returned %d bytes", method.value, url, len(response))
            return json.loads(response)
        except URLError as url_error:
            logger.error("GitHub API request failed for %s %s", method.value, url)
            raise logging.Error(message=dedent(f"""
                Failure during GitHub request:
                  URL:    {url}
                  Method: {method.value}
                  Data:   {data}""")) from url_error

    def get_releases(self) -> Sequence[dict[str, Any]]:
        """Retrieves available releases"""
        logger.info("Fetching releases for %s", self.__repository)
        releases: list[dict[str, Any]] = []
        index = 1

        while True:
            data = self.__github_request(
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
        logger.info("Deleting draft releases for %s", self.__repository)

        releases = self.get_releases()

        for rel in releases:
            if rel.get("draft"):
                self.delete_release(rel)

    def delete_release(self, release: Mapping[str, Any]) -> None:
        """Deletes a release"""
        logger.warning(
            "Deleting draft release %s from %s",
            release.get("id"),
            self.__repository,
        )

        self.__github_request(
            method=HttpMethods.DELETE, api=f"releases/{release.get('id')}"
        )

    def create_release(self, changelog: Changelog, draft: bool) -> None:
        """Creates a new release on GitHub"""
        logger.info(
            "Creating %s GitHub release for %s",
            "draft" if draft else "published",
            self.__repository,
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
        self.__github_request(
            method=HttpMethods.POST,
            api="releases",
            data={
                "tag_name": version,
                "name": f"Release {version}",
                "draft": draft,
                "body": generate_release_notes(changelog.get(UNRELEASED_ENTRY)),
            },
        )
