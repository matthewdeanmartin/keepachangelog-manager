"""Tests for the scoped-down `rewrite-messages` command (plan-only; apply stubbed).

The apply path is intentionally unimplemented: these tests pin the *safety
contract* — unpushed-only scope, mandatory consent, fail-fast apply — rather than
any history-rewriting behaviour.
"""

from __future__ import annotations

import subprocess

import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager import backfill, cli, message_lint
from changelogmanager.message_lint import LintOutcome


def _commits(subjects):
    return [
        backfill.GitCommit(sha=f"{index:040x}", subject=subject)
        for index, subject in enumerate(subjects)
    ]


class TestSuggestions:
    @pytest.mark.parametrize(
        ("subject", "expected_prefix"),
        [
            ("fix the parser", "Fixed:"),
            ("add dark mode", "Added:"),
            ("remove old api", "Removed:"),
            ("deprecate v1", "Deprecated:"),
            ("security patch for cve", "Security:"),
            ("do formatting again", "Changed:"),
            ("wip", "Changed:"),
        ],
    )
    def test_guess_category(self, subject, expected_prefix):
        assert message_lint.suggest_subject(subject).startswith(expected_prefix)

    def test_auto_prefix_overrides_guess(self):
        assert message_lint.suggest_subject(
            "fix the parser", auto_prefix="changed"
        ) == "Changed: fix the parser"

    def test_every_suggestion_relints_as_passing(self):
        for subject in ["wip", "junk", "do formatting again", "asdf", "update x"]:
            suggestion = message_lint.suggest_subject(subject)
            assert message_lint.classify_subject(suggestion).outcome is (
                LintOutcome.CHANGELOG
            )


class TestPlanRewrite:
    def test_plan_proposes_only_for_unclassified(self, monkeypatch):
        monkeypatch.setattr(
            message_lint,
            "resolve_unpushed_range",
            lambda **k: message_lint.UnpushedRange("origin/main..HEAD", True, "@{push}"),
        )
        subjects = ["Added: real", "chore: tidy", "do formatting again", "wip"]
        monkeypatch.setattr(
            backfill, "git_log_between", lambda *a, **k: _commits(subjects)
        )
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: 4)

        plan = message_lint.plan_rewrite()

        assert plan.unpushed_range == "origin/main..HEAD"
        assert [e.old_subject for e in plan.entries] == [
            "do formatting again",
            "wip",
        ]
        # Suggestions classify, so none remain unclassified.
        assert plan.still_unclassified == []
        assert all(e.outcome_after == "changelog" for e in plan.entries)

    def test_plan_json_and_tsv_shapes(self, monkeypatch):
        monkeypatch.setattr(
            message_lint,
            "resolve_unpushed_range",
            lambda **k: message_lint.UnpushedRange("HEAD", False, None),
        )
        monkeypatch.setattr(
            backfill, "git_log_between", lambda *a, **k: _commits(["wip"])
        )
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: 1)

        plan = message_lint.plan_rewrite()
        payload = plan.to_json()
        assert sorted(payload) == ["counts", "entries", "has_upstream", "unpushed_range"]
        assert payload["has_upstream"] is False

        tsv = plan.to_tsv()
        fields = tsv.split("\t")
        assert len(fields) == 4  # sha, old, suggested, outcome_after
        assert fields[2] == "Changed: wip"
        assert fields[3] == "changelog"

    def test_tsv_strips_embedded_tabs(self, monkeypatch):
        monkeypatch.setattr(
            message_lint,
            "resolve_unpushed_range",
            lambda **k: message_lint.UnpushedRange("HEAD", False, None),
        )
        monkeypatch.setattr(
            backfill, "git_log_between", lambda *a, **k: _commits(["a\tb wip"])
        )
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: 1)
        plan = message_lint.plan_rewrite()
        # One record stays on a single line with exactly 4 tab-separated fields.
        assert plan.to_tsv().count("\n") == 0
        assert plan.to_tsv().count("\t") == 3


class TestRewriteMessagesCli:
    @pytest.fixture(autouse=True)
    def _mock_git(self, monkeypatch):
        monkeypatch.setattr(
            message_lint,
            "resolve_unpushed_range",
            lambda **k: message_lint.UnpushedRange("origin/main..HEAD", True, "@{push}"),
        )
        monkeypatch.setattr(
            backfill,
            "git_log_between",
            lambda *a, **k: _commits(["do formatting again", "Added: ok"]),
        )
        monkeypatch.setattr(backfill, "enforce_commit_budget", lambda *a, **k: 2)

    def test_plan_mode_exits_zero(self):
        assert cli.main(["rewrite-messages"]) == 0

    def test_plan_out_writes_file(self, tmp_path):
        out = tmp_path / "plan.tsv"
        assert cli.main(["rewrite-messages", "--plan-out", str(out)]) == 0
        content = out.read_text(encoding="utf-8").strip()
        assert content.count("\n") == 0  # one unclassified commit
        assert "Changed: do formatting again" in content

    def test_json_plan_shape(self, capsys):
        assert cli.main(["--json", "rewrite-messages"]) == 0
        import json

        payload = json.loads(capsys.readouterr().out)
        assert payload["unpushed_range"] == "origin/main..HEAD"
        assert len(payload["entries"]) == 1

    def test_apply_with_yes_is_not_implemented(self):
        # Consent given, but apply is deliberately stubbed: exit 1.
        assert cli.main(["rewrite-messages", "--apply", "--yes"]) == 1

    def test_apply_without_consent_non_tty_is_usage_error(self, monkeypatch):
        import sys

        monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
        assert cli.main(["rewrite-messages", "--apply"]) == 2

    def test_apply_interactive_no_is_cancelled(self, monkeypatch):
        import sys

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a: "n")
        # Cancelled is a non-error (logging.Info) -> exit 0.
        assert cli.main(["rewrite-messages", "--apply"]) == 0

    def test_apply_interactive_yes_reaches_not_implemented(self, monkeypatch):
        import sys

        monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
        monkeypatch.setattr("builtins.input", lambda *a: "yes")
        assert cli.main(["rewrite-messages", "--apply"]) == 1


class TestUnpushedRangeRealRepo:
    """Prove the pushed/unpushed boundary against a real repo with a fake remote."""

    def _git(self, repo, *args):
        return subprocess.run(
            ["git", *args],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        )

    def test_pushed_commits_are_excluded(self, tmp_path):
        # A bare "remote" plus a clone; commit, push, then add local-only commits.
        remote = tmp_path / "remote.git"
        subprocess.run(
            ["git", "init", "--bare", "-q", str(remote)], check=True, capture_output=True
        )
        repo = tmp_path / "work"
        subprocess.run(
            ["git", "clone", "-q", str(remote), str(repo)],
            check=True,
            capture_output=True,
        )
        self._git(repo, "config", "user.email", "t@example.com")
        self._git(repo, "config", "user.name", "Test")

        # One pushed commit (classifiable).
        self._git(repo, "commit", "--allow-empty", "-q", "-m", "Added: pushed feature")
        self._git(repo, "push", "-q", "origin", "HEAD")
        # Two local-only commits, one unclassifiable.
        self._git(repo, "commit", "--allow-empty", "-q", "-m", "do formatting again")
        self._git(repo, "commit", "--allow-empty", "-q", "-m", "Fixed: a real fix")

        rng = message_lint.resolve_unpushed_range(cwd=str(repo))
        assert rng.has_upstream is True

        plan = message_lint.plan_rewrite(cwd=str(repo))
        # The pushed "Added: pushed feature" must NOT appear; only the unpushed,
        # unclassifiable "do formatting again" is planned.
        olds = [e.old_subject for e in plan.entries]
        assert olds == ["do formatting again"]

    def test_no_upstream_branch_is_local_only(self, tmp_path):
        repo = tmp_path / "solo"
        repo.mkdir()
        self._git(repo, "init", "-q")
        self._git(repo, "config", "user.email", "t@example.com")
        self._git(repo, "config", "user.name", "Test")
        self._git(repo, "commit", "--allow-empty", "-q", "-m", "wip junk")

        rng = message_lint.resolve_unpushed_range(cwd=str(repo))
        assert rng.has_upstream is False
        assert rng.revision == "HEAD"

    def test_outside_work_tree_errors(self, tmp_path):
        with pytest.raises(logging.Error):
            message_lint.resolve_unpushed_range(cwd=str(tmp_path))
