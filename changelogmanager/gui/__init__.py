# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tkinter GUI for changelogmanager.

The public contract preserved from the previous single-module GUI is
``run_gui`` and the ``gui`` subcommand wiring (``add_gui_subcommand`` /
``gui_handler``); ``cli.py`` imports these from this package.
"""

from __future__ import annotations

import sys
from typing import Any

from changelogmanager.runtime_logging import get_logger

try:
    import tkinter as tk

    TK_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pylint: disable=broad-exception-caught  # pragma: no cover
    tk = None  # type: ignore[assignment]  # pylint: disable=invalid-name
    TK_IMPORT_ERROR = exc

logger = get_logger(__name__)

__all__ = ["run_gui", "add_gui_subcommand", "gui_handler"]


def run_gui() -> int:
    """Launch the Tkinter GUI. Returns a process exit code."""

    if TK_IMPORT_ERROR is not None or tk is None:
        logger.error("Tkinter is unavailable: %s", TK_IMPORT_ERROR)
        sys.stderr.write(
            "Error: tkinter is not available in this Python installation.\n"
            f"Details: {TK_IMPORT_ERROR}\n"
            "Install a Python build that includes tkinter (e.g. on Debian/Ubuntu:\n"
            "  sudo apt-get install python3-tk\n"
            "on macOS with pyenv: install Python with tk support;\n"
            "on Windows: use the python.org installer with the 'tcl/tk' option).\n"
        )
        return 1

    try:
        root = tk.Tk()
    except tk.TclError as exc:
        logger.error("Failed to initialize Tk display: %s", exc)
        sys.stderr.write(
            "Error: failed to initialize a Tk display.\n"
            f"Details: {exc}\n"
            "If you are running in a headless environment, set up a display\n"
            "(e.g. Xvfb) or run the CLI commands directly.\n"
        )
        return 1

    # Imported lazily so the tkinter-missing path above stays import-safe.
    from changelogmanager.gui.app import (
        AppController,
    )  # pylint: disable=import-outside-toplevel

    logger.info("Starting Tkinter main loop")
    AppController(root)
    root.mainloop()
    return 0


def add_gui_subcommand(subparsers: Any) -> None:
    """Register the 'gui' subcommand on an argparse subparsers object."""

    gui_parser = subparsers.add_parser("gui", help="Launch the Tkinter GUI")
    gui_parser.set_defaults(handler=gui_handler, is_gui=True)


def gui_handler(_args: Any, _ctx: Any) -> None:
    """Argparse handler for the 'gui' subcommand."""

    sys.exit(run_gui())
