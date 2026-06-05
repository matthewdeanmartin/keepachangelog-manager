# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""GitLab"""

from collections.abc import Mapping
from enum import Enum
from textwrap import dedent
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import orjson

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.change_types import CATEGORIES, UNRELEASED_ENTRY
from changelogmanager.changelog import Changelog
from changelogmanager.runtime_logging import VERBOSE, get_logger

DEFAULT_GITLAB_URL = "https://gitlab.com"
logger = get_logger(__name__)


class HttpMethods(Enum):
    """Http Methods"""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"


class GitLab:
    """GitLab Releases API client.

    Unlike GitHub, GitLab has no notion of a *draft* release. The ``github-release``
    delete-the-draft-then-recreate dance is therefore replaced by an idempotent
    upsert: if a release already exists for the computed tag we ``PUT`` an update,
    otherwise we ``POST`` a fresh release (letting GitLab create the tag from
    ``ref`` when it does not yet exist).
    """

    def __init__(
        self,
        project: str,
        token: str,
        gitlab_url: str = DEFAULT_GITLAB_URL,
    ) -> None:
        """Constructor.

        ``project`` may be a numeric project ID or a URL-encoded path such as
        ``group/subgroup/project``. ``token`` is sent both as ``PRIVATE-TOKEN``
        (personal/project access tokens) and ``JOB-TOKEN`` so a ``CI_JOB_TOKEN``
        works inside GitLab CI without extra configuration.
        """

        # Numeric IDs are passed through; paths must be URL-encoded ("%2F").
        self.project = project if project.isdigit() else quote(project, safe="")
        self.base = gitlab_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "PRIVATE-TOKEN": token,
            "JOB-TOKEN": token,
        }
        logger.info(
            "Initialized GitLab client for project %s at %s", project, self.base
        )

    def gitlab_request(
        self,
        api: str,
        method: HttpMethods,
        data: Optional[Mapping[str, Any]] = None,
    ) -> Optional[Any]:
        url = f"{self.base}/api/v4/projects/{self.project}/{api}"
        logger.info("Calling GitLab API %s %s", method.value, url)
        if data:
            logger.log(
                VERBOSE, "GitLab API payload for %s %s: %s", method.value, url, data
            )

        request = Request(
            method=method.value,
            url=url,
            data=orjson.dumps(data) if data else None,
            headers=self.headers,
        )

        try:
            with urlopen(request) as resp:  # nosec
                response = resp.read()
            if not response:
                logger.warning(
                    "GitLab API %s %s returned an empty response", method.value, url
                )
                return None
            logger.log(
                VERBOSE,
                "GitLab API %s %s returned %d bytes",
                method.value,
                url,
                len(response),
            )
            return orjson.loads(response)
        except HTTPError as http_error:
            # 404 on a release lookup simply means "does not exist yet".
            if http_error.code == 404 and method is HttpMethods.GET:
                logger.info(
                    "GitLab API %s %s returned 404 (not found)", method.value, url
                )
                return None
            logger.error(
                "GitLab API request failed for %s %s (HTTP %s)",
                method.value,
                url,
                http_error.code,
            )
            raise logging.Error(message=dedent(f"""
                Failure during GitLab request:
                  URL:    {url}
                  Method: {method.value}
                  Status: {http_error.code}
                  Data:   {data}""")) from http_error
        except URLError as url_error:
            logger.error("GitLab API request failed for %s %s", method.value, url)
            raise logging.Error(message=dedent(f"""
                Failure during GitLab request:
                  URL:    {url}
                  Method: {method.value}
                  Data:   {data}""")) from url_error

    def get_release(self, tag_name: str) -> Optional[Mapping[str, Any]]:
        """Returns the release for ``tag_name`` or ``None`` if absent."""
        logger.info("Fetching GitLab release for tag %s", tag_name)
        result = self.gitlab_request(
            method=HttpMethods.GET,
            api=f"releases/{quote(tag_name, safe='')}",
        )
        return result if isinstance(result, Mapping) else None

    def create_release(
        self, changelog: Changelog, ref: str = "HEAD"
    ) -> Mapping[str, Any]:
        """Creates or updates the GitLab release derived from the changelog.

        ``ref`` is the commit/branch the tag should point at when GitLab has to
        create the tag (ignored when the release already exists).
        """

        version = f"v{changelog.suggest_future_version()}"
        name = f"Release {version}"
        description = generate_release_notes(changelog.get(UNRELEASED_ENTRY))

        existing = self.get_release(version)
        if existing is not None:
            logger.info("Updating existing GitLab release %s", version)
            response = self.gitlab_request(
                method=HttpMethods.PUT,
                api=f"releases/{quote(version, safe='')}",
                data={"name": name, "description": description},
            )
        else:
            logger.info("Creating new GitLab release %s (ref=%s)", version, ref)
            response = self.gitlab_request(
                method=HttpMethods.POST,
                api="releases",
                data={
                    "tag_name": version,
                    "ref": ref,
                    "name": name,
                    "description": description,
                },
            )

        if not isinstance(response, Mapping):
            raise logging.Error(
                message=f"GitLab did not return release details for {version}"
            )
        return response


def generate_release_notes(release: Mapping[str, Any]) -> str:
    """Renders [Unreleased] entries as GitLab-flavoured Markdown."""

    body = "## What's changed\n\n"
    sections = []
    for identifier, category in CATEGORIES.items():
        if identifier not in release:
            continue
        lines = "\n".join(f"* {message}" for message in release[identifier])
        sections.append(f"### {category.title}\n{lines}")
    return body + "\n\n".join(sections)
