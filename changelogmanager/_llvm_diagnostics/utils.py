# SPDX-License-Identifier: Apache-2.0; see changelogmanager/_llvm_diagnostics/LICENSE.md.
# Vendored from llvm_diagnostics 3.0.1 with local import path adjustments.

"""Utilities"""

import re
from enum import Enum, auto

_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


class TextFormat(Enum):
    """ANSI Code text formatting"""

    BOLD = 1

    RED = 31
    BLUE = 34
    LIGHT_GREEN = 92
    CYAN = 94


def format_string(string: str, color: TextFormat) -> str:
    """Applies ANSI code formatting to string"""
    return f"\033[{color.value}m{string}\033[0m"


def strip_ansi_escape_chars(string: str) -> str:
    """Removes all ANSI code characters from string"""
    return _ANSI_ESCAPE.sub("", string)


class Level(Enum):
    """Diagnostics Level"""

    ERROR = auto()
    WARNING = auto()
    NOTE = auto()
