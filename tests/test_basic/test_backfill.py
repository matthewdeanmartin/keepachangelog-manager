from collections import OrderedDict
from types import SimpleNamespace

import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager import backfill, cli
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader


def fake_tag_run(stdout):
    def run(*args, **kwargs):
        return SimpleNamespace(stdout=stdout)

    return run


def fake_git_run_by_command(outputs):
    def run(cmd, *args, **kwargs):
        text = " ".join(cmd)
        for needle, stdout in outputs.items():
            if needle in text:
                return SimpleNamespace(stdout=stdout)
        return SimpleNamespace(stdout="")

    return run


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


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("feat(api): add token refresh", ("added", "add token refresh")),
        (":bug: handle empty response", ("fixed", "handle empty response")),
        ("✨ add OAuth device flow", ("added", "add OAuth device flow")),
        ("Fixed: restore changelog ordering", ("fixed", "restore changelog ordering")),
        ("[Security] reject weak tokens", ("security", "reject weak tokens")),
    ],
)
def test_commit_schema_registry_classifies_common_styles(subject, expected):
    assert backfill.classify_commit_subject(subject) == expected


def test_discover_commit_releases_uses_commits_before_tag_placeholders(monkeypatch):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_git_run_by_command(
            {
                "for-each-ref": "v1.0.0\t2024-01-01\nv1.1.0\t2024-02-01\n",
                "log --no-merges --pretty=%H%x09%s v1.0.0..v1.1.0": (
                    "def456\t:bug: fix token cache\n"
                    "fed789\tChanged: update parser registry\n"
                ),
                "log --no-merges --pretty=%H%x09%s v1.0.0": (
                    "abc123\tfeat: first release\n"
                ),
            }
        ),
    )

    releases, skipped = backfill.discover_commit_releases()

    assert skipped == []
    assert [release.version for release in releases] == ["1.1.0", "1.0.0"]
    assert [(entry.change_type, entry.text) for entry in releases[0].entries] == [
        ("fixed", "fix token cache"),
        ("changed", "update parser registry"),
    ]
    assert releases[0].sources[0].name == "commits"


def test_plan_backfill_commits_skips_existing_versions(monkeypatch):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_git_run_by_command(
            {
                "for-each-ref": "v1.0.0\t2024-01-01\nv1.1.0\t2024-02-01\n",
                "log --no-merges --pretty=%H%x09%s v1.0.0..v1.1.0": (
                    "def456\tfix: repair cli\n"
                ),
                "log --no-merges --pretty=%H%x09%s v1.0.0": (
                    "abc123\tfeat: first release\n"
                ),
            }
        ),
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

    plan = backfill.plan_backfill(changelog, source="commits", dry_run=True)

    assert plan.added_versions == ["1.1.0"]
    assert plan.skipped_versions == ["1.0.0"]
    assert plan.sources == ["commits"]
    assert plan.releases[0].entries[0].text == "repair cli"


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
    assert content.index("v1.1.0") < content.index("v1.0.0")
    assert "### Changed" in content
    assert "backfilled from tag `v1.1.0`" in content
    assert ChangelogReader(file_path=str(changelog_file)).validate_layout() == 0


def test_command_backfill_dry_run_reports_without_writing(
    monkeypatch, tmp_path, capsys
):
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
            "--commit-schema",
            "gitmoji",
        ]
    )

    assert args.handler is cli.command_backfill
    assert args.source == "tags"
    assert args.since == "v1.0.0"
    assert args.until == "v2.0.0"
    assert args.missing_only is False
    assert args.dry_run is True
    assert args.commit_schema == "gitmoji"
