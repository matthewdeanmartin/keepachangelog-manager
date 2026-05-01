# SPDX-License-Identifier: Apache-2.0; see changelogmanager/_llvm_diagnostics/LICENSE.md.
# Vendored from llvm_diagnostics 3.0.1 with local import path adjustments.

"""Logging parser"""

import os
import re

import changelogmanager._llvm_diagnostics as llvm_diagnostics
from changelogmanager._llvm_diagnostics import utils

DIAGNOSTICS_HEADER = re.compile(
    r"[a-zA-Z\.\_\/\0-9]+:[0-9]+:[0-9]+:\ (?:error|warning|note): .*"
)


def diagnostics_messages_from_file(file_path: str):
    """Returns Diagnostic Messages derived from the provided logging file"""
    with open(file_path, "r", encoding="UTF-8") as file_obj:
        for line in file_obj:
            _stripped = utils.strip_ansi_escape_chars(line)
            _element = re.search(DIAGNOSTICS_HEADER, _stripped)
            if _element:
                _element = _element.group().strip(" ")
                (
                    _file_path,
                    _line_number,
                    _column_number,
                    _level,
                    _message,
                ) = _element.split(":", 4)

                level = llvm_diagnostics.Level[_level.strip(" ").upper()]

                _message_class_type = llvm_diagnostics.Info

                if level == llvm_diagnostics.Level.ERROR:
                    _message_class_type = llvm_diagnostics.Error
                elif level == llvm_diagnostics.Level.WARNING:
                    _message_class_type = llvm_diagnostics.Warning

                yield _message_class_type(
                    file_path=_file_path,
                    line_number=llvm_diagnostics.Range(int(_line_number)),
                    column_number=llvm_diagnostics.Range(int(_column_number)),
                    message=_message.rstrip(os.linesep).strip(" "),
                )
