# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Shared GUI state: paths, config selection, and the live Changelog model.

A single :class:`AppState` instance is threaded through every screen so that an
edit on one screen (or a config change) is visible to the others after a reload.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.config import (
    auto_detect_config,
    get_preamble_keywords,
    get_validation_options,
    get_versioning_scheme,
)
from changelogmanager.runtime_logging import get_logger
from changelogmanager.versioning import detect_versioning_scheme_from_file

logger = get_logger(__name__)

DEFAULT_CHANGELOG = "CHANGELOG.md"

# Environment variables that signal we are running inside CI. The releases screen
# uses this to decide whether to default to a safe dry-run.
CI_ENV_VARS: tuple[str, ...] = ("CI", "GITHUB_ACTIONS", "GITLAB_CI")


def running_in_ci() -> bool:
    """Returns True when any known CI environment variable is set."""

    return any(os.environ.get(name) for name in CI_ENV_VARS)


class AppState:  # pylint: disable=too-many-instance-attributes
    """Mutable, shared state for the GUI."""

    def __init__(self) -> None:
        self.input_file: str = DEFAULT_CHANGELOG
        self.config_path: str | None = auto_detect_config()
        self.component: str = "default"
        self.error_format: str = "llvm"
        self.dry_run: bool = not running_in_ci()
        self.changelog: Changelog | None = None
        self.load_error: str | None = None

        # Screens register here to be told when the model is reloaded.
        self.listeners: list[Callable[[], None]] = []

        self.reload()

    # ------------------------------------------------------------------
    # Reload notifications
    # ------------------------------------------------------------------
    def add_listener(self, callback: Callable[[], None]) -> None:
        """Registers a callback fired after every successful (or failed) reload."""

        self.listeners.append(callback)

    def notify(self) -> None:
        for callback in self.listeners:
            callback()

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------
    def resolve_versioning_scheme(self, file_path: str) -> str:
        """Mirrors cli.resolve_versioning_scheme for the GUI's loaded config."""

        if self.config_path:
            return get_versioning_scheme(self.config_path)
        return detect_versioning_scheme_from_file(file_path) or get_versioning_scheme(
            self.config_path
        )

    def reload(self) -> None:
        """(Re)loads the changelog from disk into the shared model.

        On any failure ``changelog`` is set to an empty model and ``load_error``
        carries a human-readable reason; screens render that instead of crashing.
        """

        path = self.input_file
        self.load_error = None
        try:
            if not Path(path).is_file():
                self.load_error = f"{path} does not exist yet"
                self.changelog = Changelog(file_path=path)
                logger.info("Changelog %s missing; using empty model", path)
                self.notify()
                return

            enforce_preamble = bool(
                get_validation_options(self.config_path).get("enforce_preamble", False)
            )
            preamble_keywords = get_preamble_keywords(self.config_path)
            scheme = self.resolve_versioning_scheme(path)
            data = ChangelogReader(
                file_path=path,
                enforce_preamble=enforce_preamble,
                preamble_keywords=preamble_keywords,
                versioning_scheme=scheme,
            ).read()
            self.changelog = Changelog(
                file_path=path,
                changelog=data,
                versioning_scheme=scheme,
            )
            logger.info("Loaded changelog %s into shared state", path)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # The reader raises diagnostic exceptions on malformed files; keep the
            # GUI alive and surface the message.
            self.load_error = str(getattr(exc, "message", exc)) or repr(exc)
            self.changelog = Changelog(file_path=path)
            logger.warning("Failed to load changelog %s: %s", path, self.load_error)
        self.notify()

    def raw_text(self) -> str:
        """Returns the raw on-disk changelog text, or '' when unreadable."""

        try:
            return Path(self.input_file).read_text(encoding="utf-8")
        except OSError:
            return ""
