# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""GitHub"""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from enum import Enum
from textwrap import dedent
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import changelogmanager.llvm_diagnostics as logging
from changelogmanager import _json_compat as orjson
from changelogmanager.change_types import CATEGORIES, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.runtime_logging import VERBOSE, get_logger

RELEASES_CHUNK_SIZE = 100
GITHUB_API_VERSION = "2026-03-10"
logger = get_logger(__name__)

_RATE_LIMIT_WARN_THRESHOLD = 10


def _check_rate_limit(headers: Mapping[str, str], source: str) -> None:
    """Warns when rate-limit headroom is low; raises when exhausted."""
    remaining_raw = headers.get("X-RateLimit-Remaining") or headers.get(
        "RateLimit-Remaining"
    )
    if remaining_raw is None:
        return
    try:
        remaining = int(remaining_raw)
    except ValueError:
        return
    if remaining == 0:
        raise logging.Error(
            message=(
                f"{source} rate limit exhausted (0 requests remaining).\n"
                "  Tip: pass --github-token or run `changelogmanager credentials set github`\n"
                "  to get 5 000 requests/hour instead of 60."
            )
        )
    if remaining < _RATE_LIMIT_WARN_THRESHOLD:
        logger.warning("%s rate limit low: %d requests remaining", source, remaining)


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
        self, api: str, method: HttpMethods, data: Mapping[str, Any] | None = None
    ) -> Any | None:
        url = f"https://api.github.com/repos/{self.repository}/{api}"
        request_data: bytes | None = None
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

    def _get_with_rate_check(
        self, api: str, data: Mapping[str, Any] | None = None
    ) -> Any | None:
        """GET request that checks rate-limit headers before returning parsed body."""
        url = f"https://api.github.com/repos/{self.repository}/{api}"
        if data:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{urlencode(data)}"
        request = Request(
            method=HttpMethods.GET.value, url=url, headers=dict(self.headers)
        )
        try:
            with urlopen(request) as resp:  # nosec
                resp_headers: Mapping[str, str] = resp.headers
                _check_rate_limit(resp_headers, "GitHub")
                body = resp.read()
            if not body:
                return None
            return orjson.loads(body)
        except HTTPError as http_error:
            response_body = http_error.read().decode(errors="replace").strip()
            _check_rate_limit(dict(http_error.headers), "GitHub")
            raise logging.Error(
                message=(
                    f"GitHub API request failed: {url} HTTP {http_error.code} {http_error.reason}\n"
                    f"  {response_body or '<empty>'}"
                )
            ) from http_error
        except URLError as url_error:
            raise logging.Error(
                message=f"GitHub API request failed: {url}"
            ) from url_error

    def get_merged_prs(
        self,
        since_date: str | None = None,
        until_date: str | None = None,
    ) -> list[dict[str, Any]]:
        """Returns merged PRs targeting the default branch, optionally filtered by merge date.

        Fetches closed PRs sorted by ``updated`` descending and filters to only
        those with a non-null ``merged_at``.  Date filtering is done client-side
        because the GitHub API does not expose a ``merged_at`` filter parameter.
        """
        logger.info("Fetching merged PRs for backfill from %s", self.repository)
        prs: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._get_with_rate_check(
                "pulls",
                {
                    "state": "closed",
                    "sort": "updated",
                    "direction": "desc",
                    "per_page": RELEASES_CHUNK_SIZE,
                    "page": page,
                },
            )
            if not data:
                break
            for pr in data:
                merged_at: str | None = pr.get("merged_at")
                if not merged_at:
                    continue
                merge_date = merged_at[:10]
                if since_date and merge_date < since_date:
                    # PRs are sorted descending by updated_at, not merged_at, so
                    # we can't stop early — a recently-updated old PR could appear
                    # anywhere.  Keep scanning.
                    continue
                if until_date and merge_date > until_date:
                    continue
                prs.append(pr)
            if len(data) < RELEASES_CHUNK_SIZE:
                break
            page += 1
        logger.info("Fetched %d merged PRs from %s", len(prs), self.repository)
        return prs

    def get_releases_for_backfill(self) -> list[dict[str, Any]]:
        """Returns all releases shaped as {version, body, date} for backfill."""
        logger.info("Fetching releases for backfill from %s", self.repository)
        releases: list[dict[str, Any]] = []
        index = 1
        while True:
            data = self._get_with_rate_check(
                "releases",
                {"per_page": RELEASES_CHUNK_SIZE, "page": index},
            )
            if not data:
                break
            for rel in data:
                tag_name: str = rel.get("tag_name", "")
                body: str = rel.get("body", "") or ""
                published: str | None = rel.get("published_at")
                date: str | None = published[:10] if published else None
                releases.append({"version": tag_name, "body": body, "date": date})
            if len(data) < RELEASES_CHUNK_SIZE:
                break
            index += 1
        logger.info("Fetched %d releases from %s", len(releases), self.repository)
        return releases

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
            "Deleting release %s from %s",
            release.get("id"),
            self.repository,
        )

        self.github_request(
            method=HttpMethods.DELETE, api=f"releases/{release.get('id')}"
        )

    def find_release_by_tag(self, tag: str) -> Mapping[str, Any] | None:
        """Returns the release whose ``tag_name`` matches ``tag`` (draft or not).

        Matches with and without a leading ``v`` so ``v1.2.0`` finds a release
        tagged ``1.2.0`` and vice versa. Returns ``None`` when no release exists.
        """
        wanted = {tag, tag.lstrip("v"), f"v{tag.lstrip('v')}"}
        for rel in self.get_releases():
            if str(rel.get("tag_name", "")) in wanted:
                return rel
        return None

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
