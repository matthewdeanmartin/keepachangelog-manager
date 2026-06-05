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


US = "\x1f"  # unit separator used by the single-pass decorated git log


def decorated_log(rows):
    """Builds %H\\x1f%D\\x1f%s output. Each row is (sha, [tags], subject)."""

    lines = []
    for sha, tags, subject in rows:
        decoration = ", ".join(f"tag: {tag}" for tag in tags)
        lines.append(f"{sha}{US}{decoration}{US}{subject}")
    return "\n".join(lines) + ("\n" if lines else "")


def commit_git_outputs(*, for_each_ref, rows, count=None):
    """Mock outputs for the single-pass commit discovery path.

    ``rows`` is the decorated newest-first commit list; ``count`` is the
    rev-list --count guard total (defaults to the number of rows).
    """

    return {
        "for-each-ref": for_each_ref,
        "rev-list --no-merges --count": str(len(rows) if count is None else count)
        + "\n",
        "log --no-merges --pretty=%H%x1f%D%x1f%s": decorated_log(rows),
    }


def test_discover_tag_releases_normalizes_orders_and_skips_non_semver(monkeypatch):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_tag_run(
            "v1.0.0\t2024-01-01\nrelease-candidate\t2024-01-15\nv1.2.0\t2024-02-01\n"
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
            commit_git_outputs(
                for_each_ref="v1.0.0\t2024-01-01\nv1.1.0\t2024-02-01\n",
                # newest-first: v1.1.0's commits, then v1.0.0's tagged commit
                rows=[
                    ("def456", [], ":bug: fix token cache"),
                    ("fed789", ["v1.1.0"], "Changed: update parser registry"),
                    ("abc123", ["v1.0.0"], "feat: first release"),
                ],
            )
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
            commit_git_outputs(
                for_each_ref="v1.0.0\t2024-01-01\nv1.1.0\t2024-02-01\n",
                rows=[
                    ("def456", ["v1.1.0"], "fix: repair cli"),
                    ("abc123", ["v1.0.0"], "feat: first release"),
                ],
            )
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


def test_command_backfill_rejects_replace_strategy():
    with pytest.raises(logging.Error, match="no stable identity"):
        cli.command_backfill(
            SimpleNamespace(
                source="tags",
                since=None,
                until=None,
                missing_only=True,
                dry_run=True,
                strategy="replace",
                include_unreleased=False,
            ),
            cli.CliContext(changelog=Changelog()),
        )


def commit_outputs():
    return commit_git_outputs(
        for_each_ref="v1.0.0\t2024-01-01\nv1.1.0\t2024-02-01\n",
        rows=[
            ("def456", [], "fix: repair cli"),
            ("abc999", ["v1.1.0"], "feat: add caching"),
            ("abc123", ["v1.0.0"], "feat: first release"),
        ],
    )


def test_plan_backfill_merge_appends_new_entries_to_existing_version(monkeypatch):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_git_run_by_command(commit_outputs()),
    )
    changelog = Changelog(
        changelog=OrderedDict(
            [
                (
                    "1.1.0",
                    {
                        "metadata": {
                            "version": "1.1.0",
                            "release_date": "2024-02-01",
                        },
                        "fixed": ["repair cli"],
                    },
                ),
                (
                    "1.0.0",
                    {
                        "metadata": {
                            "version": "1.0.0",
                            "release_date": "2024-01-01",
                        },
                        "added": ["first release"],
                    },
                ),
            ]
        )
    )

    plan = backfill.plan_backfill(
        changelog, source="commits", strategy="merge", missing_only=False, dry_run=True
    )

    assert plan.added_versions == []
    assert plan.merged_versions == ["1.1.0"]
    # The already-recorded "repair cli" entry is filtered; only the new one stays.
    merged = next(r for r in plan.releases if r.version == "1.1.0")
    assert [(e.change_type, e.text) for e in merged.entries] == [
        ("added", "add caching")
    ]
    assert plan.to_json()["merged_versions"] == ["1.1.0"]


def test_apply_backfill_merge_preserves_existing_entries(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_git_run_by_command(commit_outputs()),
    )
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog = Changelog(
        file_path=str(changelog_file),
        changelog=OrderedDict(
            [
                (
                    "1.1.0",
                    {
                        "metadata": {
                            "version": "1.1.0",
                            "release_date": "2024-02-01",
                        },
                        "fixed": ["repair cli"],
                    },
                )
            ]
        ),
    )

    plan = backfill.plan_backfill(
        changelog, source="commits", strategy="merge", missing_only=False
    )
    backfill.apply_backfill_plan(changelog, plan)
    changelog.write_to_file()

    content = changelog_file.read_text(encoding="UTF-8")
    assert "repair cli" in content
    assert "add caching" in content
    assert ChangelogReader(file_path=str(changelog_file)).validate_layout() == 0


def test_backfill_merge_is_idempotent(monkeypatch, tmp_path):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_git_run_by_command(commit_outputs()),
    )
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog = Changelog(
        file_path=str(changelog_file),
        changelog=OrderedDict(
            [
                (
                    "1.1.0",
                    {
                        "metadata": {
                            "version": "1.1.0",
                            "release_date": "2024-02-01",
                        },
                        "fixed": ["repair cli"],
                    },
                )
            ]
        ),
    )

    first = backfill.plan_backfill(
        changelog, source="commits", strategy="merge", missing_only=False
    )
    backfill.apply_backfill_plan(changelog, first)

    second = backfill.plan_backfill(
        changelog, source="commits", strategy="merge", missing_only=False
    )

    assert second.merged_versions == []
    assert second.added_versions == []
    assert set(second.skipped_versions) == {"1.0.0", "1.1.0"}
    assert second.releases == []


def test_command_backfill_merge_reports_and_writes(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_git_run_by_command(commit_outputs()),
    )
    changelog_file = tmp_path / "CHANGELOG.md"
    changelog = Changelog(
        file_path=str(changelog_file),
        changelog=OrderedDict(
            [
                (
                    "1.1.0",
                    {
                        "metadata": {
                            "version": "1.1.0",
                            "release_date": "2024-02-01",
                        },
                        "fixed": ["repair cli"],
                    },
                )
            ]
        ),
    )

    cli.command_backfill(
        SimpleNamespace(
            source="commits",
            since=None,
            until=None,
            missing_only=False,
            dry_run=False,
            strategy="merge",
            include_unreleased=False,
            commit_schema="auto",
        ),
        cli.CliContext(changelog=changelog),
    )

    output = capsys.readouterr().out
    assert "merge 1 new entry into 1.1.0" in output
    assert "add caching" in changelog_file.read_text(encoding="UTF-8")


def test_parse_decoration_tags_extracts_only_tags():
    decoration = "HEAD -> main, tag: v2.0.0, origin/main, tag: release-2"
    assert backfill.parse_decoration_tags(decoration) == ["v2.0.0", "release-2"]
    assert backfill.parse_decoration_tags("") == []


def test_partition_commits_by_tag_assigns_intervals():
    # Newest-first walk across three releases; untagged commits flow to the
    # nearest newer tag's release.
    rows = [
        ("h1", [], "feat: post-2.0 work"),
        ("h2", ["v2.0.0"], "feat: tag two"),
        ("h3", [], "fix: between"),
        ("h4", ["v1.0.0"], "feat: tag one"),
    ]
    buckets = backfill.partition_commits_by_tag(
        rows, ascending_tags=["v1.0.0", "v2.0.0"]
    )
    assert [c.sha for c in buckets["v2.0.0"]] == ["h1", "h2", "h3"]
    assert [c.sha for c in buckets["v1.0.0"]] == ["h4"]


def test_discover_commit_releases_refuses_monster_history(monkeypatch):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_git_run_by_command(
            commit_git_outputs(
                for_each_ref="v1.0.0\t2024-01-01\n",
                rows=[("a", ["v1.0.0"], "feat: x")],
                count=10_001,
            )
        ),
    )
    with pytest.raises(logging.Error, match="exceeds the backfill limit"):
        backfill.discover_commit_releases(max_commits=10_000)


def test_discover_commit_releases_unlimited_when_max_commits_zero(monkeypatch):
    monkeypatch.setattr(
        backfill.subprocess,
        "run",
        fake_git_run_by_command(
            commit_git_outputs(
                for_each_ref="v1.0.0\t2024-01-01\n",
                rows=[("a", ["v1.0.0"], "feat: x")],
                count=10_000_000,
            )
        ),
    )
    releases, _ = backfill.discover_commit_releases(max_commits=0)
    assert [r.version for r in releases] == ["1.0.0"]


def test_cap_release_entries_truncates_with_summary():
    entries = [
        backfill.BackfillEntry(change_type="changed", text=f"c{i}", source="commits")
        for i in range(backfill.MAX_ENTRIES_PER_RELEASE + 50)
    ]
    capped = backfill.cap_release_entries(entries, commit_count=len(entries))
    assert len(capped) == backfill.MAX_ENTRIES_PER_RELEASE + 1
    assert "50 more commit(s)" in capped[-1].text


def test_backfill_parser_max_commits_option():
    parser = cli.build_parser()
    args = parser.parse_args(["backfill", "--max-commits", "0"])
    assert args.max_commits == 0
    default = parser.parse_args(["backfill"])
    assert default.max_commits is None


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
