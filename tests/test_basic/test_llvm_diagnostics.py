from io import StringIO

from changelogmanager._llvm_diagnostics import Error, Info, Range, Warning, formatters
from changelogmanager._llvm_diagnostics import messages as diagnostics_messages
from changelogmanager._llvm_diagnostics.parser import diagnostics_messages_from_file
from changelogmanager._llvm_diagnostics.utils import (
    TextFormat,
    format_string,
    strip_ansi_escape_chars,
)


def test_range_end_and_hash_are_stable():
    value = Range(start=2, range=4)

    assert value.end() == 6
    assert hash(value) == hash((2, 4))


def test_message_report_uses_configured_formatter(monkeypatch):
    class PlainFormatter:
        def format(self, message):
            return f"{message.level.name}:{message.message}"

    original = formatters.get_config()
    formatters.config(PlainFormatter())
    stderr = StringIO()
    monkeypatch.setattr(diagnostics_messages, "stderr", stderr)
    try:
        Error(message="boom").report()
    finally:
        formatters.config(original)

    assert stderr.getvalue().strip() == "ERROR:boom"


def test_llvm_formatter_includes_indicator_ranges_and_expectations():
    message = Error(
        file_path="src/module.py",
        line="value = broken\n",
        line_number=Range(3),
        column_number=Range(9, 3),
        message="bad value",
        expectations="expected replacement",
    )

    formatted = formatters.Llvm().format(message)

    assert "src/module.py:3:9:" in formatted
    assert "bad value" in formatted
    assert "^" in formatted
    assert "~~" in formatted
    assert "expected replacement" in formatted


def test_github_formatter_includes_line_and_column_ranges():
    message = Warning(
        file_path="src/module.py",
        line="broken\n",
        line_number=Range(4, 2),
        column_number=Range(7, 3),
        message="careful",
    )

    formatted = formatters.GitHub().format(message)

    assert formatted == (
        "::warning file=src/module.py,line=4,endLine=6,col=7,endColumn=10::careful"
    )


def test_utils_format_and_strip_ansi():
    colored = format_string("hello", TextFormat.RED)

    assert colored.startswith("\033[31mhello")
    assert strip_ansi_escape_chars(colored) == "hello"


def test_parser_extracts_diagnostic_messages_from_log_file(tmp_path):
    diagnostics_file = tmp_path / "diagnostics.log"
    diagnostics_file.write_text(
        format_string("src/file.py:3:2: error: boom\n", TextFormat.RED)
        + "src/file.py:4:5: warning: heads up\n"
        + "src/file.py:8:1: note: extra context\n"
        + "this line should be ignored\n",
        encoding="utf-8",
    )

    messages = list(diagnostics_messages_from_file(str(diagnostics_file)))

    assert [type(message) for message in messages] == [Error, Warning, Info]
    assert messages[0].file_path == "src/file.py"
    assert messages[0].message == "boom"
    assert messages[1].message == "heads up"
    assert messages[2].line_number.start == 8
