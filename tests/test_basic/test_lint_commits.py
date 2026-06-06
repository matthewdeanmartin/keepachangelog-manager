"""Tests for the read-only `lint-commits` audit command and its service."""

from __future__ import annotations

import subprocess

import pytest

from changelogmanager import backfill, cli, message_lint
from changelogmanager.message_lint import LintOutcome


def _commits(subjects):
    return [
        backfill.GitCommit(sha=f"{index:040x}", subject=subject)
        for index, subject in enumerate(subjects)
    ]


class TestAuditCommits:
    def test_classifies_each_outcome(self, monkeypatch):
        subjects = [
            "Added: dark mode",  # changelog
            "feat: new api",  # changelog
            "chore: reformat",  # skip
            "Merge branch 'x'",  # skip (exempt)
            "do formatting again",  # unclassified
            "wip",  # unclassified
        ]
        monkeypatch.setattr(
            backfill, "git_log_between", lambda *a, **k: _commits(subjects)
        )
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: len(subjects))

        report = message_lint.audit_commits(since="v1.0.0")

        assert report.counts == {"changelog": 2, "skip": 2, "unclassified": 2}
        assert [c.subject for c in report.unclassified] == [
            "do formatting again",
            "wip",
        ]
        assert report.revision == "v1.0.0..HEAD"

    def test_revision_without_since_is_head(self, monkeypatch):
        monkeypatch.setattr(backfill, "git_log_between", lambda *a, **k: [])
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: 0)
        report = message_lint.audit_commits()
        assert report.revision == "HEAD"

    def test_until_bounds_the_range(self, monkeypatch):
        seen = {}

        def fake_log(since, start, **kwargs):
            seen["since"] = since
            seen["start"] = start
            return []

        monkeypatch.setattr(backfill, "git_log_between", fake_log)
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: 0)
        message_lint.audit_commits(since="v1.0.0", until="v2.0.0")
        assert seen == {"since": "v1.0.0", "start": "v2.0.0"}

    def test_budget_guard_is_enforced(self, monkeypatch):
        import changelogmanager.llvm_diagnostics as logging

        def boom(*a, **k):
            raise logging.Error(message="too many commits")

        monkeypatch.setattr(backfill, "enforce_commit_budget", boom)
        monkeypatch.setattr(backfill, "git_log_between", lambda *a, **k: [])
        with pytest.raises(logging.Error):
            message_lint.audit_commits(since="root", max_commits=1)

    def test_to_json_shape(self, monkeypatch):
        monkeypatch.setattr(
            backfill, "git_log_between", lambda *a, **k: _commits(["wip"])
        )
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: 1)
        payload = message_lint.audit_commits(since="v1").to_json()
        assert sorted(payload) == ["commits", "counts", "revision"]
        commit = payload["commits"][0]
        assert sorted(commit) == [
            "change_type",
            "matched_schema",
            "outcome",
            "reason",
            "sha",
            "subject",
        ]
        assert commit["outcome"] == LintOutcome.UNCLASSIFIED.value


class TestLintCommitsCli:
    """Drives the CLI handler with a mocked git walk."""

    @pytest.fixture(autouse=True)
    def _mock_git(self, monkeypatch):
        subjects = [
            "Added: a thing",
            "chore: reformat",
            "do formatting again",
        ]
        monkeypatch.setattr(
            backfill, "git_log_between", lambda *a, **k: _commits(subjects)
        )
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: 3)
        # No tags: keep last_release_tag from shelling out.
        from changelogmanager import services

        monkeypatch.setattr(services, "last_release_tag", lambda: None)

    def test_default_run_exits_zero(self):
        assert cli.main(["lint-commits", "--all-history"]) == 0

    def test_strict_fails_on_unclassified(self):
        assert cli.main(["lint-commits", "--all-history", "--strict"]) == 1

    def test_json_output(self, capsys):
        code = cli.main(["--json", "lint-commits", "--all-history"])
        assert code == 0
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["counts"] == {
            "changelog": 1,
            "skip": 1,
            "unclassified": 1,
        }

    def test_json_strict_still_emits_payload_then_fails(self, capsys):
        code = cli.main(["--json", "lint-commits", "--all-history", "--strict"])
        assert code == 1
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["counts"]["unclassified"] == 1

    def test_schema_override_changes_classification(self):
        # Under keepachangelog, "Added:" still classifies but "feat:"-style would
        # not; here the chore stays skip and Added stays changelog, no unclassified
        # escalation beyond the prose line -> still 1 unclassified, exit 1 strict.
        assert (
            cli.main(
                ["lint-commits", "--all-history", "--commit-schema", "keepachangelog", "--strict"]
            )
            == 1
        )


class TestLintCommitsRealRepo:
    """One integration test over a throwaway git repo (read-only audit)."""

    def _git(self, repo, *args):
        subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def _make_repo(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@example.com")
        self._git(repo, "config", "user.name", "Test")
        self._git(repo, "commit", "--allow-empty", "-q", "-m", "Added: first feature")
        self._git(repo, "commit", "--allow-empty", "-q", "-m", "chore: tidy")
        self._git(repo, "commit", "--allow-empty", "-q", "-m", "random junk subject")
        return repo

    def test_audit_over_real_history(self, tmp_path):
        repo = self._make_repo(tmp_path)
        report = message_lint.audit_commits(cwd=str(repo))
        assert report.counts["changelog"] == 1
        assert report.counts["skip"] == 1
        assert report.counts["unclassified"] == 1
        assert report.unclassified[0].subject == "random junk subject"
