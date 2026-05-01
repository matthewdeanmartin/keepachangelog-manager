# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Shared stdlib logging setup for runtime diagnostics."""

from __future__ import annotations

import logging
import sys

VERBOSE = 15
LOGGER_NAME = "changelogmanager"


def _install_verbose_level() -> None:
    if logging.getLevelName(VERBOSE) != "VERBOSE":
        logging.addLevelName(VERBOSE, "VERBOSE")

    if hasattr(logging.Logger, "verbose"):
        return

    def verbose(self: logging.Logger, message: str, *args: object, **kwargs: object) -> None:
        if self.isEnabledFor(VERBOSE):
            self._log(VERBOSE, message, args, **kwargs)

    logging.Logger.verbose = verbose  # type: ignore[attr-defined]


def get_logger(name: str) -> logging.Logger:
    """Returns a configured logger within the changelogmanager namespace."""

    _install_verbose_level()
    return logging.getLogger(name)


def configure_runtime_logging(*, info: bool, verbose: bool) -> None:
    """Configures stderr logging for runtime diagnostics."""

    _install_verbose_level()
    namespace_logger = logging.getLogger(LOGGER_NAME)
    namespace_logger.handlers.clear()
    namespace_logger.propagate = False

    if not info and not verbose:
        namespace_logger.addHandler(logging.NullHandler())
        namespace_logger.setLevel(logging.CRITICAL + 1)
        return

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(levelname)s] %(name)s: %(message)s"))
    namespace_logger.addHandler(handler)
    namespace_logger.setLevel(VERBOSE if verbose else logging.INFO)
