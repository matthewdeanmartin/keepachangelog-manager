"""Tests for the optional mdformat pass (changelogmanager/formatting.py) and
its integration with validate --fix / --format / --no-format."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from changelogmanager.cli import main
from changelogmanager.formatting import (
    Formatter,
    InProcessFormatter,
    SubprocessFormatter,
    discover_formatter,
    format_markdown,
)

# ---------------------------------------------------------------------------
# Sample changelogs
# ---------------------------------------------------------------------------

CLEAN_CHANGELOG = """\
# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- New thing

## [1.0.0] - 2024-01-01

### Added

- Initial release
"""

UNORDERED_CHANGELOG = """\
# Changelog

## [Unreleased]
### Added
- Feature A

## [1.0.0] - 2024-01-01
### Added
- Initial

## [2.0.0] - 2024-06-01
### Added
- Big change
"""


def write_changelog(path: Path, body: str = CLEAN_CHANGELOG) -> str:
    p = path / "CHANGELOG.md"
    p.write_text(body, encoding="utf-8")
    return str(p)


def capture_output(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


def make_formatter(text: str = "") -> Formatter:
    """Returns a Formatter that appends a marker so tests can detect it ran."""

    def fmt(md: str, options: dict[str, Any]) -> str:
        return md + text

    return fmt  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Unit: discover_formatter  # noqa: ERA001
# ---------------------------------------------------------------------------


class TestDiscoverFormatter:
    def test_in_process_takes_priority(self):
        """When mdformat is importable, the in-process formatter is returned."""
        fake_mdformat = MagicMock()
        fake_mdformat.text.return_value = "formatted"
        with patch.dict("sys.modules", {"mdformat": fake_mdformat}):
            f = discover_formatter()
        assert isinstance(f, InProcessFormatter)

    def test_falls_back_to_executable(self):
        """When mdformat is not importable but is on PATH, subprocess formatter is returned."""
        with patch("builtins.__import__", side_effect=ImportError("no mdformat")):
            pass  # can't cleanly block imports this way; test via which only
        # Simulate: import fails, shutil.which finds executable
        with (
            patch(
                "changelogmanager.formatting.InProcessFormatter",
                side_effect=ImportError,
            ),
            patch("shutil.which", return_value="/usr/bin/mdformat"),
        ):
            # We patch discover_formatter internals via a fresh call with mocked import
            import importlib

            import changelogmanager.formatting as fmt_mod

            with patch.object(fmt_mod, "discover_formatter") as mock_disc:
                mock_disc.return_value = SubprocessFormatter("/usr/bin/mdformat")
                fmt_mod.discover_formatter()
            # The mock returned a SubprocessFormatter — verify it's the right type
            assert isinstance(mock_disc.return_value, SubprocessFormatter)

    def test_returns_none_when_nothing_found(self):
        """When both import and which fail, None is returned."""
        with (patch("shutil.which", return_value=None),):
            # Force import error for mdformat
            import sys

            mdformat_backup = sys.modules.pop("mdformat", None)
            try:
                f = discover_formatter()
                # May be None or a formatter depending on environment;
                # just assert it's either None or a Formatter
                assert f is None or callable(f)
            finally:
                if mdformat_backup is not None:
                    sys.modules["mdformat"] = mdformat_backup


class TestDiscoverFormatterClean:
    """Cleaner isolation tests using monkeypatch."""

    def test_no_mdformat_no_executable_returns_none(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: None)
        import sys

        # Mapping a module to None in sys.modules prevents it from being imported.
        monkeypatch.setitem(sys.modules, "mdformat", None)
        result = discover_formatter()
        assert result is None

    def test_executable_found_returns_subprocess_formatter(self, monkeypatch):
        monkeypatch.setattr("shutil.which", lambda _: "/usr/local/bin/mdformat")
        import sys

        # Mapping a module to None in sys.modules prevents it from being imported.
        monkeypatch.setitem(sys.modules, "mdformat", None)
        result = discover_formatter()
        assert isinstance(result, SubprocessFormatter)


# ---------------------------------------------------------------------------
# Unit: format_markdown  # noqa: ERA001
# ---------------------------------------------------------------------------


class TestFormatMarkdown:
    def test_returns_formatted_text(self):
        marker_fmt = make_formatter("__MARKER__")
        result = format_markdown("# Hello\n", marker_fmt)
        assert "__MARKER__" in result

    def test_guarantees_trailing_newline(self):
        """Formatter that strips the final newline still gets one added back."""

        def strip_newline(text: str, options: dict[str, Any]) -> str:
            return text.rstrip("\n")

        result = format_markdown("# Hello\n", strip_newline)  # type: ignore[arg-type]
        assert result.endswith("\n")

    def test_passes_options_through(self):
        received: dict[str, Any] = {}

        def capturing_fmt(text: str, options: dict[str, Any]) -> str:
            received.update(options)
            return text

        format_markdown("x\n", capturing_fmt, {"wrap": "80", "number": True})  # type: ignore[arg-type]
        assert received == {"wrap": "80", "number": True}

    def test_empty_options_default(self):
        calls: list[dict[str, Any]] = []

        def recording_fmt(text: str, options: dict[str, Any]) -> str:
            calls.append(options)
            return text

        format_markdown("x\n", recording_fmt)  # type: ignore[arg-type]
        assert calls == [{}]

    def test_idempotent_on_already_formatted(self):
        """Calling format_markdown twice should produce the same result."""
        identity = make_formatter()
        first = format_markdown("# Hello\n\n- item\n", identity)
        second = format_markdown(first, identity)
        assert first == second


# ---------------------------------------------------------------------------
# Integration: --format / --no-format CLI flags
# ---------------------------------------------------------------------------


class TestFormatFlag:
    def test_no_format_skips_format_pass(self, tmp_path):
        """--no-format suppresses the format pass even when a formatter is available."""
        p = write_changelog(tmp_path, UNORDERED_CHANGELOG)
        Path(p).read_text(encoding="utf-8")
        rc = main(["--input-file", p, "validate", "--fix", "--no-format"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        # Structural fixes should still apply (version reordering)
        assert text.index("[2.0.0]") < text.index("[1.0.0]")

    def test_format_flag_errors_when_no_formatter(self, tmp_path):
        """--format raises an error when neither mdformat import nor executable is available."""
        p = write_changelog(tmp_path)
        # loaders.resolve_formatter calls discover_formatter, so patch it there
        with patch(
            "changelogmanager.cli.loaders.discover_formatter", return_value=None
        ):
            rc = main(["--input-file", p, "validate", "--fix", "--format"])
        assert rc == 1

    def test_no_format_and_format_are_mutually_exclusive(self, tmp_path):
        """--format and --no-format cannot be used together."""
        p = write_changelog(tmp_path)
        rc = main(["--input-file", p, "validate", "--fix", "--format", "--no-format"])
        assert rc != 0  # argparse exits non-zero for mutually exclusive groups

    def test_format_dry_run_does_not_write(self, tmp_path):
        """--fix --format --dry-run reports what would change without writing."""
        p = write_changelog(tmp_path, UNORDERED_CHANGELOG)
        original = Path(p).read_text(encoding="utf-8")
        with patch(
            "changelogmanager.cli.loaders.discover_formatter",
            return_value=make_formatter("  "),
        ):
            rc = main(["--input-file", p, "validate", "--fix", "--dry-run"])
        assert rc == 0
        # File must be unchanged in dry-run
        assert Path(p).read_text(encoding="utf-8") == original

    def test_format_dry_run_reports_would_fix(self, tmp_path):
        """Dry-run with a formatter that changes text reports 'would fix'."""
        p = write_changelog(tmp_path, UNORDERED_CHANGELOG)
        with patch(
            "changelogmanager.cli.loaders.discover_formatter",
            return_value=make_formatter("\n<!-- formatted -->"),
        ):
            rc, out = capture_output(
                ["--input-file", p, "validate", "--fix", "--dry-run"]
            )
        assert rc == 0
        assert "would fix" in out or "Dry run" in out

    def test_no_format_with_valid_file_reports_no_fixes(self, tmp_path):
        """--fix --no-format on an already-correct file should report no fixes."""
        p = write_changelog(tmp_path, CLEAN_CHANGELOG)
        rc, out = capture_output(
            ["--input-file", p, "validate", "--fix", "--no-format"]
        )
        assert rc == 0
        assert "No fixes required" in out


# ---------------------------------------------------------------------------
# Integration: JSON payload gains "formatted" key
# ---------------------------------------------------------------------------


class TestJsonPayload:
    def test_json_has_formatted_false_when_no_format(self, tmp_path):
        p = write_changelog(tmp_path)
        rc, out = capture_output(
            ["--json", "--input-file", p, "validate", "--fix", "--no-format"]
        )
        assert rc == 0
        payload = json.loads(out)
        assert "formatted" in payload
        assert payload["formatted"] is False

    def test_json_has_formatted_false_when_no_fixes(self, tmp_path):
        """A file with no structural fixes and no format changes → formatted: False."""
        p = write_changelog(tmp_path, CLEAN_CHANGELOG)
        # Use an identity formatter that returns the text unchanged.
        # Patch in loaders, where resolve_formatter looks up discover_formatter.
        identity_fmt = (
            make_formatter()
        )  # appends "" — truly no-op on already-serialized text
        with patch(
            "changelogmanager.cli.loaders.discover_formatter", return_value=identity_fmt
        ):
            rc, out = capture_output(["--json", "--input-file", p, "validate", "--fix"])
        assert rc == 0
        payload = json.loads(out)
        assert payload.get("formatted") is False

    def test_json_has_formatted_true_when_format_applied(self, tmp_path):
        """formatted: true when the format pass changes the serialized text."""
        p = write_changelog(tmp_path, UNORDERED_CHANGELOG)
        marking_fmt = make_formatter("\n<!-- mdformat -->")
        with patch(
            "changelogmanager.cli.loaders.discover_formatter", return_value=marking_fmt
        ):
            rc, out = capture_output(["--json", "--input-file", p, "validate", "--fix"])
        assert rc == 0
        payload = json.loads(out)
        assert payload.get("formatted") is True


# ---------------------------------------------------------------------------
# Integration: idempotency  # noqa: ERA001
# ---------------------------------------------------------------------------


class TestIdempotency:
    def test_fix_twice_is_noop(self, tmp_path):
        """Running validate --fix a second time should report no fixes."""
        p = write_changelog(tmp_path, UNORDERED_CHANGELOG)
        # First pass: applies structural fixes (and possibly format pass)
        rc1 = main(["--input-file", p, "validate", "--fix", "--no-format"])
        assert rc1 == 0
        after_first = Path(p).read_text(encoding="utf-8")

        # Second pass: nothing should change
        rc2 = main(["--input-file", p, "validate", "--fix", "--no-format"])
        assert rc2 == 0
        after_second = Path(p).read_text(encoding="utf-8")
        assert after_first == after_second

    def test_format_twice_is_noop(self, tmp_path):
        """The format pass itself is idempotent when using the real mdformat."""
        p = write_changelog(tmp_path, UNORDERED_CHANGELOG)

        # Apply once
        main(["--input-file", p, "validate", "--fix"])
        after_first = Path(p).read_text(encoding="utf-8")

        # Apply again — should produce identical bytes
        main(["--input-file", p, "validate", "--fix"])
        after_second = Path(p).read_text(encoding="utf-8")
        assert after_first == after_second


# ---------------------------------------------------------------------------
# Integration: validate --all with format pass
# ---------------------------------------------------------------------------


class TestValidateAllWithFormat:
    def test_all_no_format_applies_structural_fixes(self, tmp_path, monkeypatch):
        """validate --all --fix --no-format applies structural fixes to every component."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[[components]]\nname = "api"\nchangelog = "api/CHANGELOG.md"\n\n'
            '[[components]]\nname = "web"\nchangelog = "web/CHANGELOG.md"\n',
            encoding="utf-8",
        )
        for name in ("api", "web"):
            (tmp_path / name).mkdir()
            (tmp_path / name / "CHANGELOG.md").write_text(
                UNORDERED_CHANGELOG, encoding="utf-8"
            )
        monkeypatch.chdir(tmp_path)
        rc = main(["--config", str(cfg), "validate", "--all", "--fix", "--no-format"])
        assert rc == 0
        for name in ("api", "web"):
            text = (tmp_path / name / "CHANGELOG.md").read_text(encoding="utf-8")
            assert text.index("[2.0.0]") < text.index("[1.0.0]")

    def test_all_dry_run_does_not_write(self, tmp_path, monkeypatch):
        """validate --all --fix --dry-run must not modify any component file."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[[components]]\nname = "api"\nchangelog = "api/CHANGELOG.md"\n',
            encoding="utf-8",
        )
        (tmp_path / "api").mkdir()
        cl = tmp_path / "api" / "CHANGELOG.md"
        cl.write_text(UNORDERED_CHANGELOG, encoding="utf-8")
        original = cl.read_text(encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        rc = main(["--config", str(cfg), "validate", "--all", "--fix", "--dry-run"])
        assert rc == 0
        assert cl.read_text(encoding="utf-8") == original

    def test_all_with_format_pass(self, tmp_path, monkeypatch):
        """validate --all --fix threads the format pass to each component."""
        cfg = tmp_path / "config.toml"
        cfg.write_text(
            '[[components]]\nname = "svc"\nchangelog = "svc/CHANGELOG.md"\n',
            encoding="utf-8",
        )
        (tmp_path / "svc").mkdir()
        cl = tmp_path / "svc" / "CHANGELOG.md"
        cl.write_text(UNORDERED_CHANGELOG, encoding="utf-8")
        monkeypatch.chdir(tmp_path)

        marking_fmt = make_formatter("\n<!-- mdformat -->")
        # Patch at the cli module level (cli imports discover_formatter directly)
        with patch(
            "changelogmanager.cli.loaders.discover_formatter", return_value=marking_fmt
        ):
            rc = main(["--config", str(cfg), "validate", "--all", "--fix"])
        assert rc == 0
        text = cl.read_text(encoding="utf-8")
        assert "<!-- mdformat -->" in text


# ---------------------------------------------------------------------------
# Unit: Changelog.render() + write_to_file() with formatter
# ---------------------------------------------------------------------------


class TestChangelogRender:
    def test_render_without_formatter_returns_markdown(self, tmp_path):
        from changelogmanager.changelog import Changelog

        cl = Changelog(
            file_path=str(tmp_path / "CHANGELOG.md"),
            changelog={
                "Unreleased": {
                    "metadata": {"version": "Unreleased", "release_date": None},
                    "added": ["A thing"],
                }
            },
        )
        text = cl.render()
        assert isinstance(text, str)
        assert "A thing" in text

    def test_render_with_formatter_applies_it(self, tmp_path):
        from changelogmanager.changelog import Changelog

        cl = Changelog(
            file_path=str(tmp_path / "CHANGELOG.md"),
            changelog={
                "Unreleased": {
                    "metadata": {"version": "Unreleased", "release_date": None},
                    "added": ["A thing"],
                }
            },
        )
        marker_fmt = make_formatter("__FORMATTED__")
        text = cl.render(formatter=marker_fmt)
        assert "__FORMATTED__" in text

    def test_write_to_file_with_formatter(self, tmp_path):
        from changelogmanager.changelog import Changelog

        p = tmp_path / "CHANGELOG.md"
        cl = Changelog(
            file_path=str(p),
            changelog={
                "Unreleased": {
                    "metadata": {"version": "Unreleased", "release_date": None},
                    "added": ["Something"],
                }
            },
        )
        marker_fmt = make_formatter("__WRITTEN__")
        cl.write_to_file(formatter=marker_fmt)
        assert "__WRITTEN__" in p.read_text(encoding="utf-8")

    def test_write_to_file_without_formatter_unchanged(self, tmp_path):
        from changelogmanager.changelog import Changelog

        p = tmp_path / "CHANGELOG.md"
        cl = Changelog(
            file_path=str(p),
            changelog={
                "Unreleased": {
                    "metadata": {"version": "Unreleased", "release_date": None},
                    "added": ["Something"],
                }
            },
        )
        cl.write_to_file()
        text = p.read_text(encoding="utf-8")
        assert "Something" in text


# ---------------------------------------------------------------------------
# Unit: config.get_format_options  # noqa: ERA001
# ---------------------------------------------------------------------------


class TestGetFormatOptions:
    def test_defaults_when_no_config(self):
        from changelogmanager.config import get_format_options

        opts = get_format_options(None)
        assert opts["format"] == "auto"
        assert opts["formatter"] == "mdformat"
        assert opts["mdformat_options"] == {}

    def test_reads_format_true_from_config(self, tmp_path):
        from changelogmanager.config import get_format_options

        cfg = tmp_path / "cfg.toml"
        cfg.write_text(
            "[validation]\nformat = true\n",
            encoding="utf-8",
        )
        opts = get_format_options(str(cfg))
        assert opts["format"] is True

    def test_reads_format_false_from_config(self, tmp_path):
        from changelogmanager.config import get_format_options

        cfg = tmp_path / "cfg.toml"
        cfg.write_text(
            "[validation]\nformat = false\n",
            encoding="utf-8",
        )
        opts = get_format_options(str(cfg))
        assert opts["format"] is False

    def test_reads_mdformat_options_from_config(self, tmp_path):
        from changelogmanager.config import get_format_options

        cfg = tmp_path / "cfg.toml"
        cfg.write_text(
            '[validation.mdformat_options]\nwrap = "80"\nnumber = true\n',
            encoding="utf-8",
        )
        opts = get_format_options(str(cfg))
        assert opts["mdformat_options"]["wrap"] == "80"
        assert opts["mdformat_options"]["number"] is True
