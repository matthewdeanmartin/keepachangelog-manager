# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

import re

import changelogmanager._llvm_diagnostics as llvm_diagnostics
from changelogmanager._llvm_diagnostics import utils

ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _normalized_output(output: str) -> str:
    return utils.strip_ansi_escape_chars(output).replace("\r\n", "\n")


def test_warning_message_complete():
    _expectation = """\
fake_file.py:10:15: warning: Value exceeds maximum, automatically capped to 100\n\
mPercentage = 105\n\
              ^~~\n\
              100\
"""
    _output = str(
        llvm_diagnostics.Error(
            file_path="fake_file.py",
            line_number=llvm_diagnostics.Range(start=10),
            column_number=llvm_diagnostics.Range(start=15, range=3),
            line="mPercentage = 105",
            expectations="100",
            level=llvm_diagnostics.Level.WARNING,
            message="Value exceeds maximum, automatically capped to 100",
        )
    )

    assert _normalized_output(_output) == _expectation


def test_error_message_no_expectation():
    _expectation = """\
fake_file.py:10:15: error: Incorrect type assigned to mPercentage\n\
mPercentage = \"105\"\n\
              ^~~~~\
"""
    _output = str(
        llvm_diagnostics.Error(
            file_path="fake_file.py",
            line_number=llvm_diagnostics.Range(start=10),
            column_number=llvm_diagnostics.Range(start=15, range=5),
            line='mPercentage = "105"',
            message="Incorrect type assigned to mPercentage",
        )
    )

    assert _normalized_output(_output) == _expectation


def test_note_message_no_mismatch_and_exceptation():
    _expectation = """\
fake_file.py:10:1: note: mPercentage is deprecated and will be removed in 2030\n\
mPercentage = 105\n\
^\
"""
    _output = str(
        llvm_diagnostics.Info(
            file_path="fake_file.py",
            line_number=llvm_diagnostics.Range(start=10),
            column_number=llvm_diagnostics.Range(start=1),
            line="mPercentage = 105",
            message="mPercentage is deprecated and will be removed in 2030",
        )
    )

    assert _normalized_output(_output) == _expectation


def test_note_message_minimal():
    _expectation = "fake_file.py:1:1: note: Missing copyright information"
    _output = str(
        llvm_diagnostics.Info(
            file_path="fake_file.py",
            message="Missing copyright information",
        )
    )

    assert _normalized_output(_output) == _expectation
