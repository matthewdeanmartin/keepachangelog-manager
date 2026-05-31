# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

import re

import changelogmanager.llvm_diagnostics as llvm_diagnostics
from changelogmanager.llvm_diagnostics import utils

ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def normalized_output(output: str) -> str:
    return utils.strip_ansi_escape_chars(output).replace("\r\n", "\n")


def test_warning_message_complete():
    expectation = """\
fake_file.py:10:15: warning: Value exceeds maximum, automatically capped to 100\n\
mPercentage = 105\n\
              ^~~\n\
              100\
"""
    output_text = str(
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

    assert normalized_output(output_text) == expectation


def test_error_message_no_expectation():
    expectation = """\
fake_file.py:10:15: error: Incorrect type assigned to mPercentage\n\
mPercentage = \"105\"\n\
              ^~~~~\
"""
    output_text = str(
        llvm_diagnostics.Error(
            file_path="fake_file.py",
            line_number=llvm_diagnostics.Range(start=10),
            column_number=llvm_diagnostics.Range(start=15, range=5),
            line='mPercentage = "105"',
            message="Incorrect type assigned to mPercentage",
        )
    )

    assert normalized_output(output_text) == expectation


def test_note_message_no_mismatch_and_exceptation():
    expectation = """\
fake_file.py:10:1: note: mPercentage is deprecated and will be removed in 2030\n\
mPercentage = 105\n\
^\
"""
    output_text = str(
        llvm_diagnostics.Info(
            file_path="fake_file.py",
            line_number=llvm_diagnostics.Range(start=10),
            column_number=llvm_diagnostics.Range(start=1),
            line="mPercentage = 105",
            message="mPercentage is deprecated and will be removed in 2030",
        )
    )

    assert normalized_output(output_text) == expectation


def test_note_message_minimal():
    expectation = "fake_file.py:1:1: note: Missing copyright information"
    output_text = str(
        llvm_diagnostics.Info(
            file_path="fake_file.py",
            message="Missing copyright information",
        )
    )

    assert normalized_output(output_text) == expectation
