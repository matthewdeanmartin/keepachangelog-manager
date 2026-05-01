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

RELEASES_CHUNK_SIZE = 100


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

    def __github_request(
        self, api: str, method: HttpMethods, data: Optional[Mapping[str, Any]] = None
    ) -> Optional[Any]:
        url = f"https://api.github.com/repos/{self.__repository}/{api}"

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
                return None

            return json.loads(response)
        except URLError as url_error:
            raise logging.Error(
                message=dedent(
                    f"""
                Failure during GitHub request:
                  URL:    {url}
                  Method: {method.value}
                  Data:   {data}"""
                )
            ) from url_error

    def get_releases(self) -> Sequence[dict[str, Any]]:
        """Retrieves available releases"""
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

        releases = self.get_releases()

        for rel in releases:
            if rel.get("draft"):
                self.delete_release(rel)

    def delete_release(self, release: Mapping[str, Any]) -> None:
        """Deletes a release"""

        self.__github_request(
            method=HttpMethods.DELETE, api=f"releases/{release.get('id')}"
        )

    def create_release(self, changelog: Changelog, draft: bool) -> None:
        """Creates a new release on GitHub"""

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
