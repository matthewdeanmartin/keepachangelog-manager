from __future__ import annotations

from datetime import date

from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.vendor import keepachangelog


def test_pep440_release_validation_and_bump(tmp_path):
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text(
        "# Changelog\n"
        "All notable changes follow Keep a Changelog and PEP 440.\n\n"
        "## [Unreleased]\n\n"
        "### Fixed\n"
        "- fix it\n\n"
        "## [1.2rc1] - 2024-04-01\n\n"
        "### Added\n"
        "- earlier\n",
        encoding="UTF-8",
    )

    data = ChangelogReader(
        file_path=str(changelog_file), versioning_scheme="pep440"
    ).read()
    changelog = Changelog(
        file_path=str(changelog_file),
        changelog=data,
        versioning_scheme="pep440",
    )

    assert str(changelog.version()) == "1.2rc1"
    assert str(changelog.suggest_future_version()) == "1.2.1"

    changelog.release()
    released = next(iter(changelog.get().values()))
    assert released["metadata"]["version"] == "1.2.1"
    assert released["metadata"]["pep440_version"]["release"] == [1, 2, 1]


class FrozenDate(date):
    @classmethod
    def today(cls):
        return cls(2026, 5, 31)


def test_calver_release_validation_and_bump(tmp_path, monkeypatch):
    monkeypatch.setattr("changelogmanager.versioning.date", FrozenDate)
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text(
        "# Changelog\n"
        "All notable changes follow Keep a Changelog and Calendar Versioning.\n\n"
        "## [Unreleased]\n\n"
        "### Added\n"
        "- add it\n\n"
        "## [2026.05.0] - 2026-05-01\n\n"
        "### Added\n"
        "- earlier\n",
        encoding="UTF-8",
    )

    data = ChangelogReader(
        file_path=str(changelog_file), versioning_scheme="calver"
    ).read()
    changelog = Changelog(
        file_path=str(changelog_file),
        changelog=data,
        versioning_scheme="calver",
    )

    assert str(changelog.suggest_future_version()) == "2026.05.0.1"

    changelog.release()
    released = next(iter(changelog.get().values()))
    assert released["metadata"]["version"] == "2026.05.0.1"
    assert released["metadata"]["calendar_version"] == {
        "year": FrozenDate.today().year,
        "month": FrozenDate.today().month,
        "day": None,
        "micro": 1,
    }


def test_vendored_parser_adds_supported_version_metadata():
    parsed = keepachangelog.to_dict(
        [
            "# Changelog\n",
            "## [1.0rc1] - 2024-01-01\n",
            "### Added\n",
            "- pep\n",
            "## [2024.04.0] - 2024-04-01\n",
            "### Added\n",
            "- cal\n",
        ]
    )

    assert parsed["1.0rc1"]["metadata"]["pep440_version"]["pre"] == ["rc", 1]
    assert parsed["2024.04.0"]["metadata"]["calendar_version"]["year"] == 2024


def test_reader_detects_versioning_scheme_from_preamble(tmp_path):
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog_file.write_text(
        "# Changelog\n"
        "All notable changes follow Keep a Changelog and PEP 440.\n\n"
        "## [1.0rc1] - 2024-01-01\n\n"
        "### Added\n"
        "- prerelease\n",
        encoding="UTF-8",
    )

    assert ChangelogReader(file_path=str(changelog_file)).validate_layout() == 0
