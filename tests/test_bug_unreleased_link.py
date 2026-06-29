# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Regression tests for spec/bug_unreleased.md.

A changelog whose released versions carry bottom-of-file link references but
whose ``## [Unreleased]`` heading has no matching ``[Unreleased]:`` reference is
accepted by our (lenient) validator, but ``validate --fix`` must be able to add
the missing ref so the file passes strict upstream ``kacl-cli verify``.
"""

from __future__ import annotations

from pathlib import Path

from changelogmanager.changelog_reader import (
    ChangelogReader,
    derive_unreleased_url,
)
from changelogmanager.vendor import keepachangelog

# The exact reproduction fixture from spec/bug_unreleased.md.
FIXTURE = """\
# Changelog

## [Unreleased]

### Added

- A new thing

## [0.2.0] - 2026-01-02
### Added
- Second release

## [0.1.0] - 2026-01-01
### Added
- Initial release

[0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/acme/proj/releases/tag/v0.1.0
"""

EXPECTED_UNRELEASED = "https://github.com/acme/proj/compare/v0.2.0...HEAD"


def _read(text: str) -> dict:
    return keepachangelog.to_dict(text.splitlines(keepends=True), show_unreleased=True)


def test_derive_unreleased_url_prefers_compare_shape_and_tag_prefix():
    links = [
        ("0.2.0", "https://github.com/acme/proj/compare/v0.1.0...v0.2.0"),
        ("0.1.0", "https://github.com/acme/proj/releases/tag/v0.1.0"),
    ]
    assert derive_unreleased_url(links, "0.2.0") == EXPECTED_UNRELEASED


def test_derive_unreleased_url_no_v_prefix_preserved():
    links = [("0.2.0", "https://github.com/acme/proj/compare/0.1.0...0.2.0")]
    assert (
        derive_unreleased_url(links, "0.2.0")
        == "https://github.com/acme/proj/compare/0.2.0...HEAD"
    )


def test_derive_unreleased_url_falls_back_to_tag_base():
    links = [("0.1.0", "https://github.com/acme/proj/releases/tag/v0.1.0")]
    assert (
        derive_unreleased_url(links, "0.1.0")
        == "https://github.com/acme/proj/compare/v0.1.0...HEAD"
    )


def test_derive_unreleased_url_returns_none_without_links():
    assert derive_unreleased_url([], "0.2.0") is None


def test_autofix_backfills_unreleased_link():
    reader = ChangelogReader(versioning_scheme="semver")
    fixed, applied = reader.autofix(_read(FIXTURE))

    assert fixed["unreleased"]["metadata"]["url"] == EXPECTED_UNRELEASED
    assert any("[Unreleased] link reference" in entry for entry in applied)


def test_autofix_does_not_rewrite_existing_released_links():
    reader = ChangelogReader(versioning_scheme="semver")
    fixed, _applied = reader.autofix(_read(FIXTURE))

    # Hand-curated released links must be byte-for-byte unchanged.
    assert (
        fixed["0.2.0"]["metadata"]["url"]
        == "https://github.com/acme/proj/compare/v0.1.0...v0.2.0"
    )
    assert (
        fixed["0.1.0"]["metadata"]["url"]
        == "https://github.com/acme/proj/releases/tag/v0.1.0"
    )


def test_serialized_fix_emits_single_unreleased_line():
    reader = ChangelogReader(versioning_scheme="semver")
    fixed, _applied = reader.autofix(_read(FIXTURE))
    rendered = keepachangelog.from_dict(fixed)

    assert f"[Unreleased]: {EXPECTED_UNRELEASED}" in rendered
    # Exactly one [Unreleased]: line, and released links preserved.
    assert rendered.count("[Unreleased]: ") == 1
    assert "[0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0" in rendered


def test_no_backfill_when_no_released_links():
    text = """\
# Changelog

## [Unreleased]
### Added
- A new thing
"""
    reader = ChangelogReader(versioning_scheme="semver")
    fixed, applied = reader.autofix(_read(text))
    assert "url" not in fixed["unreleased"]["metadata"]
    assert not any("[Unreleased] link reference" in entry for entry in applied)


def test_no_backfill_when_unreleased_already_linked():
    text = FIXTURE.replace(
        "[0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0",
        "[Unreleased]: https://github.com/acme/proj/compare/v0.2.0...HEAD\n"
        "[0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0",
    )
    reader = ChangelogReader(versioning_scheme="semver")
    _fixed, applied = reader.autofix(_read(text))
    assert not any("[Unreleased] link reference" in entry for entry in applied)


def test_no_backfill_for_empty_unreleased():
    text = """\
# Changelog

## [Unreleased]

## [0.2.0] - 2026-01-02
### Added
- Second release

[0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0
"""
    reader = ChangelogReader(versioning_scheme="semver")
    fixed, applied = reader.autofix(_read(text))
    assert "url" not in fixed["unreleased"]["metadata"]
    assert not any("[Unreleased] link reference" in entry for entry in applied)


# Strict-mode fixture: canonical preamble + linked releases, missing [Unreleased] link.
STRICT_FIXTURE = """\
# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- A new thing

## [0.2.0] - 2026-01-02
### Added
- Second release

[0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0
"""


def _run(args: list[str]) -> int:
    from changelogmanager.cli import main

    return main(args)


def test_strict_flags_missing_unreleased_link_as_error(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(STRICT_FIXTURE, encoding="utf-8")
    code = _run(["--input-file", str(changelog), "validate", "--strict"])
    assert code == 1


def test_strict_fix_roundtrips_clean(tmp_path: Path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(STRICT_FIXTURE, encoding="utf-8")

    fix_code = _run(
        ["--input-file", str(changelog), "validate", "--fix", "--strict", "--no-format"]
    )
    assert fix_code == 0
    assert "[Unreleased]: https://github.com/acme/proj/compare/v0.2.0...HEAD" in (
        changelog.read_text(encoding="utf-8")
    )
    # After the fix, strict validate must pass.
    assert _run(["--input-file", str(changelog), "validate", "--strict"]) == 0


def test_strict_errors_on_unfixable_released_link(tmp_path: Path):
    # 0.2.0 has no link ref and we will not fabricate one; strict stays non-zero.
    text = STRICT_FIXTURE.replace(
        "\n[0.2.0]: https://github.com/acme/proj/compare/v0.1.0...v0.2.0\n",
        "\n[Unreleased]: https://github.com/acme/proj/compare/v0.2.0...HEAD\n",
    )
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(text, encoding="utf-8")
    code = _run(
        ["--input-file", str(changelog), "validate", "--fix", "--strict", "--no-format"]
    )
    assert code == 1


def test_strict_passes_brandnew_unlinked_changelog(tmp_path: Path):
    text = """\
# Changelog
All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### Added
- A thing
"""
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(text, encoding="utf-8")
    assert _run(["--input-file", str(changelog), "validate", "--strict"]) == 0


def test_plain_validate_still_passes_but_warns(tmp_path: Path, monkeypatch):
    import io

    import changelogmanager.llvm_diagnostics.messages as messages

    buf = io.StringIO()
    monkeypatch.setattr(messages, "stderr", buf)

    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text(FIXTURE, encoding="utf-8")

    reader = ChangelogReader(file_path=str(changelog), versioning_scheme="semver")
    # read() runs validate_contents, which emits the advisory; it must not raise.
    reader.read()
    combined = buf.getvalue()
    assert "[Unreleased] link reference" in combined
    assert "validate --fix" in combined
