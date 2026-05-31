# SPDX-License-Identifier: Apache-2.0; see changelogmanager/llvm_diagnostics/LICENSE.md.
# Vendored from llvm_diagnostics 3.0.1 with local import path adjustments.

"""Logging parser"""

import re
from collections.abc import Generator
from pathlib import Path
from typing import Union

import changelogmanager.llvm_diagnostics as llvm_diagnostics
from changelogmanager.llvm_diagnostics import utils

DIAGNOSTICS_HEADER = re.compile(
    r"[a-zA-Z\.\_\/\0-9]+:[0-9]+:[0-9]+:\ (?:error|warning|note): .*"
)


def diagnostics_messages_from_file(
    file_path: str,
) -> Generator[
    Union[llvm_diagnostics.Info, llvm_diagnostics.Error, llvm_diagnostics.Warning],
    None,
    None,
]:
    """Returns Diagnostic Messages derived from the provided logging file"""
    with Path(file_path).open(encoding="UTF-8") as file_obj:
        for line in file_obj:
            stripped = utils.strip_ansi_escape_chars(line)
            element = re.search(DIAGNOSTICS_HEADER, stripped)
            if element:
                element_str = element.group().strip(" ")
                (
                    parsed_file_path,
                    parsed_line_number,
                    parsed_column_number,
                    parsed_level,
                    msg,
                ) = element_str.split(":", 4)

                level = llvm_diagnostics.Level[parsed_level.strip(" ").upper()]

                message_class_type: Union[
                    type[llvm_diagnostics.Info],
                    type[llvm_diagnostics.Error],
                    type[llvm_diagnostics.Warning],
                ] = llvm_diagnostics.Info

                if level == llvm_diagnostics.Level.ERROR:
                    message_class_type = llvm_diagnostics.Error
                elif level == llvm_diagnostics.Level.WARNING:
                    message_class_type = llvm_diagnostics.Warning

                yield message_class_type(
                    file_path=parsed_file_path,
                    line_number=llvm_diagnostics.Range(int(parsed_line_number)),
                    column_number=llvm_diagnostics.Range(int(parsed_column_number)),
                    message=msg.rstrip("\n\r").strip(" "),
                )
