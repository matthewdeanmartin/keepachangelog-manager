# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Optional Markdown formatting pass for autofix output.

Discovery order:
  1. In-process ``import mdformat`` (fastest; used when the [format] extra is installed).
  2. Executable on PATH via ``shutil.which("mdformat")``, invoked via subprocess.
  3. Neither found — returns None; callers skip the pass silently.
"""

from __future__ import annotations

import shutil
import subprocess  # nosec B404
from typing import Any, Protocol, runtime_checkable

from changelogmanager.runtime_logging import VERBOSE, get_logger

logger = get_logger(__name__)


@runtime_checkable
class Formatter(Protocol):
    """Callable that accepts a Markdown string and returns a formatted string."""

    def __call__(self, text: str, options: dict[str, Any]) -> str: ...


class InProcessFormatter:
    def __call__(self, text: str, options: dict[str, Any]) -> str:
        import mdformat  # type: ignore[import-not-found]

        wrap = options.get("wrap", "keep")
        number = options.get("number", False)
        return str(mdformat.text(text, options={"wrap": wrap, "number": number}))


class SubprocessFormatter:
    def __init__(self, executable: str) -> None:
        self.exe = executable

    def __call__(self, text: str, options: dict[str, Any]) -> str:  # noqa: ARG002
        result = subprocess.run(  # nosec B603
            [self.exe, "-"],
            input=text,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return result.stdout


def discover_formatter() -> Formatter | None:
    """Returns the best available Formatter, or None if none is installed."""
    try:
        # pylint: disable=unused-import
        import mdformat  # noqa: F401 # type: ignore[import-not-found]

        logger.log(VERBOSE, "mdformat available in-process; using in-process formatter")
        return InProcessFormatter()
    except ImportError:
        pass

    exe = shutil.which("mdformat")
    if exe:
        logger.log(
            VERBOSE, "mdformat executable found at %s; using subprocess formatter", exe
        )
        return SubprocessFormatter(exe)

    logger.log(VERBOSE, "No mdformat formatter found; format pass will be skipped")
    return None


def format_markdown(
    text: str, formatter: Formatter, options: dict[str, Any] | None = None
) -> str:
    """Formats ``text`` using ``formatter`` and returns the result.

    Guarantees a trailing newline even when the formatter strips it.
    """
    result = formatter(text, options or {})
    if not result.endswith("\n"):
        result += "\n"
    return result
