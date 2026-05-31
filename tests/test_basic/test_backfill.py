from collections import OrderedDict
from types import SimpleNamespace

import pytest

import changelogmanager._llvm_diagnostics as logging
from changelogmanager import backfill, cli
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader


def fake_tag_run(stdout):
    def _run(*args, **kwargs):
        return SimpleNamespace(stdout=stdout)

    return _run


def test_discover_tag_releases_normalizes_orders_and_skips_non_semver(monkeypatch):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_tag_run(
            "v1.0.0\t2024-01-01\n"
            "release-candidate\t2024-01-15\n"
            "v1.2.0\t2024-02-01\n"
        ),
    )

    releases, skipped = backfill.discover_tag_releases()

    assert [release.version for release in releases] == ["1.2.0", "1.0.0"]
    assert [release.tag for release in releases] == ["v1.2.0", "v1.0.0"]
    assert skipped == ["release-candidate"]
    assert releases[0].entries[0].text == (
        "Release notes unavailable; backfilled from tag `v1.2.0`."
    )


def test_plan_tag_backfill_skips_existing_versions(monkeypatch):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_tag_run("v1.0.0\t2024-01-01\nv1.1.0\t2024-02-01\n"),
    )
    changelog = Changelog(
        changelog=OrderedDict(
            [
                (
                    "1.0.0",
                    {"metadata": {"version": "1.0.0", "release_date": "2024-01-01"}},
                )
            ]
        )
    )

    plan = backfill.plan_tag_backfill(changelog, dry_run=True)

    assert plan.added_versions == ["1.1.0"]
    assert plan.skipped_versions == ["1.0.0"]
    assert plan.to_json() == {
        "added_versions": ["1.1.0"],
        "skipped_versions": ["1.0.0"],
        "skipped_tags": [],
        "sources": ["tags"],
        "dry_run": True,
    }


def test_apply_backfill_plan_writes_valid_changelog(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_tag_run("v1.0.0\t2024-01-01\nv1.1.0\t2024-02-01\n"),
    )
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog = Changelog(file_path=str(changelog_file))
    plan = backfill.plan_tag_backfill(changelog)

    backfill.apply_backfill_plan(changelog, plan)
    changelog.write_to_file()

    content = changelog_file.read_text(encoding="UTF-8")
    assert content.index("## [1.1.0]") < content.index("## [1.0.0]")
    assert "### Changed" in content
    assert "backfilled from tag `v1.1.0`" in content
    assert ChangelogReader(file_path=str(changelog_file)).validate_layout() == 0


def test_command_backfill_dry_run_reports_without_writing(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_tag_run("v1.0.0\t2024-01-01\n"),
    )
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog = Changelog(file_path=str(changelog_file))

    cli.command_backfill(
        SimpleNamespace(
            source="tags",
            since=None,
            until=None,
            missing_only=True,
            dry_run=True,
            strategy="conservative",
            include_unreleased=False,
        ),
        cli.CliContext(changelog=changelog),
    )

    assert not changelog_file.exists()
    output = capsys.readouterr().out
    assert "Backfill plan for" in output
    assert "add 1.0.0 from tag v1.0.0" in output
    assert "Dry run: would update" in output


def test_command_backfill_rejects_existing_version_updates():
    with pytest.raises(logging.Error, match="existing versions"):
        cli.command_backfill(
            SimpleNamespace(
                source="tags",
                since=None,
                until=None,
                missing_only=False,
                dry_run=True,
                strategy="conservative",
                include_unreleased=False,
            ),
            cli.CliContext(changelog=Changelog()),
        )


def test_backfill_parser_options():
    parser = cli.build_parser()

    args = parser.parse_args(
        [
            "backfill",
            "--source",
            "tags",
            "--since",
            "v1.0.0",
            "--until",
            "v2.0.0",
            "--no-missing-only",
            "--dry-run",
        ]
    )

    assert args.handler is cli.command_backfill
    assert args.source == "tags"
    assert args.since == "v1.0.0"
    assert args.until == "v2.0.0"
    assert args.missing_only is False
    assert args.dry_run is True
