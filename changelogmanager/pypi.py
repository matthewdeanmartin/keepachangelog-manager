# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""PyPI JSON API client for backfill."""

from __future__ import annotations

from textwrap import dedent
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

import orjson

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.runtime_logging import get_logger

PYPI_API = "https://pypi.org/pypi/{package}/json"

logger = get_logger(__name__)


def get_pypi_releases(package: str) -> list[dict[str, Any]]:
    """Returns list of {version, date} dicts sorted newest-first."""
    url = PYPI_API.format(package=package)
    logger.info("Fetching PyPI release history for %s", package)
    try:
        with urlopen(url) as resp:  # nosec
            data: dict[str, Any] = orjson.loads(resp.read())
    except HTTPError as exc:
        raise logging.Error(message=dedent(f"""
                PyPI request failed for package '{package}':
                  URL:    {url}
                  Status: {exc.code} {exc.reason}""")) from exc
    except URLError as exc:
        raise logging.Error(
            message=f"PyPI request failed for package '{package}': {url}"
        ) from exc

    releases: list[dict[str, Any]] = []
    for version, files in data.get("releases", {}).items():
        if not files:
            continue
        upload_time: str = files[0].get("upload_time", "")[:10]
        releases.append({"version": version, "date": upload_time or None})

    releases.sort(key=lambda r: r["version"], reverse=True)
    logger.info("Found %d PyPI releases for %s", len(releases), package)
    return releases
