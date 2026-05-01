# SPDX-License-Identifier: Apache-2.0; see changelogmanager/_llvm_diagnostics/LICENSE.md.
# Vendored from llvm_diagnostics 3.0.1 with local import path adjustments.

"""Diagnostic Messages"""

from dataclasses import dataclass
from sys import stderr
from typing import Optional

from changelogmanager._llvm_diagnostics import formatters
from changelogmanager._llvm_diagnostics.utils import Level


@dataclass
class Range:
    """Diagnostics Range"""

    start: int = 1
    range: Optional[int] = None

    def end(self):
        """Returns the last index of the Range"""
        return self.start + self.range

    def __hash__(self):
        return hash((self.start, self.range))


@dataclass
class __Message(Exception):  # pylint: disable=C0103
    """Diagnostics Message"""

    message: str
    file_path: Optional[str] = None
    column_number: Range = Range()
    expectations: Optional[str] = None
    line: Optional[str] = None
    line_number: Range = Range()

    def report(self):
        """Formats the Diagnostics message and sends it to `stderr`"""
        print(self, file=stderr)

    def __str__(self):
        """Formats the Diagnostics message"""
        return formatters.get_config().format(message=self)


@dataclass
class Info(__Message):
    """Diagnostics Information"""

    level: Level = Level.NOTE


@dataclass
class Error(__Message):
    """Diagnostics Error"""

    level: Level = Level.ERROR


@dataclass
class Warning(__Message):  # pylint: disable=W0622
    """Diagnostics Warning"""

    level: Level = Level.WARNING
