# SPDX-License-Identifier: Apache-2.0; see changelogmanager/llvm_diagnostics/LICENSE.md.
# Vendored from llvm_diagnostics 3.0.1 with local import path adjustments.

"""Diagnostic Message Formatters"""

import os
from typing import TYPE_CHECKING, Protocol

from changelogmanager.llvm_diagnostics import utils
from changelogmanager.llvm_diagnostics.utils import Level

if TYPE_CHECKING:
    from changelogmanager.llvm_diagnostics.messages import __Message

# pylint: disable=R0903


class DiagnosticsFormatter(Protocol):
    """Protocol Formatter class"""

    def format(self, message: "__Message") -> str:
        """Protocol method"""


class Llvm(DiagnosticsFormatter):
    """LLVM Diagnostics Formatter"""

    LEVEL_FORMAT = {
        Level.ERROR: utils.format_string(
            "error",
            utils.TextFormat.RED,
        ),
        Level.WARNING: utils.format_string(
            "warning",
            utils.TextFormat.CYAN,
        ),
        Level.NOTE: utils.format_string(
            "note",
            utils.TextFormat.LIGHT_GREEN,
        ),
    }

    def format(self, message: "__Message") -> str:
        """Formats the message into a LLVM Diagnostics compatible format"""

        msg = ""
        if message.file_path:
            msg = (
                f"{message.file_path}:{message.line_number.start}:"
                f"{message.column_number.start}: "
            )

        msg = utils.format_string(
            f"{msg}{self.LEVEL_FORMAT[message.level]}: {message.message}",
            utils.TextFormat.BOLD,
        )

        if not message.line:
            return msg

        indicator_color = (
            utils.TextFormat.LIGHT_GREEN
            if message.expectations
            else utils.TextFormat.RED
        )

        indicator = (
            message.line.rstrip(os.linesep)
            + os.linesep
            + " " * (message.column_number.start - 1)
            + utils.format_string("^", indicator_color)
        )

        if message.column_number.range:
            indicator += utils.format_string(
                "~" * (message.column_number.range - 1),
                indicator_color,
            )

        if message.expectations:
            indicator += (
                os.linesep
                + " " * (message.column_number.start - 1)
                + message.expectations
            )

        return msg + os.linesep + indicator


class GitHub(DiagnosticsFormatter):
    """GitHub Formatter"""

    LEVEL_FORMAT = {
        Level.ERROR: "error",
        Level.WARNING: "warning",
        Level.NOTE: "notice",
    }

    def format(self, message: "__Message") -> str:
        """Formats the message into a GitHub compatible Workflow command"""

        msg = f"::{self.LEVEL_FORMAT[message.level]}"

        if message.file_path:
            msg += f" file={message.file_path}"

        if message.line:
            msg += f",line={message.line_number.start}"
            if message.line_number.range:
                msg += f",endLine={message.line_number.end()}"

            msg += f",col={message.column_number.start}"
            if message.column_number.range:
                msg += f",endColumn={message.column_number.end()}"

        msg += f"::{message.message}"

        return msg


# Global configuration for handling message formatting
__GLOBAL_FORMATTER: DiagnosticsFormatter = Llvm()


def config(formatter: DiagnosticsFormatter) -> None:
    """Configure the formatter used"""
    global __GLOBAL_FORMATTER  # pylint: disable=W0603
    __GLOBAL_FORMATTER = formatter


def get_config() -> DiagnosticsFormatter:
    """Retrieve configured formatter"""
    return __GLOBAL_FORMATTER
