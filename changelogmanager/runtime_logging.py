# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Shared stdlib logging setup for runtime diagnostics."""

from __future__ import annotations

import logging
import sys
from collections.abc import Mapping
from typing import Any

VERBOSE = 15
LOGGER_NAME = "changelogmanager"


def _coerce_log_kwargs(
    kwargs: Mapping[str, object],
) -> tuple[Any, bool, int, Mapping[str, object] | None]:
    unknown = set(kwargs) - {"exc_info", "stack_info", "stacklevel", "extra"}
    if unknown:
        raise TypeError(f"Unexpected logging keyword arguments: {sorted(unknown)!r}")

    exc_info_value = kwargs.get("exc_info")
    if isinstance(exc_info_value, (tuple, BaseException, bool)) or exc_info_value is None:
        exc_info: Any = exc_info_value
    else:
        raise TypeError("exc_info must be a bool, exception, or exc_info tuple")

    stack_info_value = kwargs.get("stack_info")
    if stack_info_value is None:
        stack_info = False
    elif isinstance(stack_info_value, bool):
        stack_info = stack_info_value
    else:
        raise TypeError("stack_info must be a bool")

    stacklevel_value = kwargs.get("stacklevel")
    if stacklevel_value is None:
        stacklevel = 1
    elif isinstance(stacklevel_value, int):
        stacklevel = stacklevel_value
    else:
        raise TypeError("stacklevel must be an int")

    extra_value = kwargs.get("extra")
    if extra_value is None:
        extra = None
    elif isinstance(extra_value, Mapping):
        extra = extra_value
    else:
        raise TypeError("extra must be a mapping")

    return exc_info, stack_info, stacklevel, extra


def _install_verbose_level() -> None:
    if logging.getLevelName(VERBOSE) != "VERBOSE":
        logging.addLevelName(VERBOSE, "VERBOSE")

    if hasattr(logging.Logger, "verbose"):
        return

    def verbose(
        self: logging.Logger, message: str, *args: object, **kwargs: object
    ) -> None:
        if self.isEnabledFor(VERBOSE):
            exc_info, stack_info, stacklevel, extra = _coerce_log_kwargs(kwargs)
            self.log(
                VERBOSE,
                message,
                *args,
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=stacklevel,
                extra=extra,
            )

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
