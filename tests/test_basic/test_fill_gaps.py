"""Tests for the capability-gap fills: config-init new-path fix, interactive
flows for index/token commands, and the --include-unreleased backfill branch."""

import argparse
from types import SimpleNamespace

import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager import backfill, cli, services


def make_args(**kwargs):
    return argparse.Namespace(**kwargs)


class DummyChangelog:
    def __init__(self, *, unreleased_entries=None, has_unreleased=True):
        # unreleased_entries: list of (change_type, index, message)
        self.entries = list(unreleased_entries or [])
        self.has_unreleased_value = has_unreleased
        self.calls = []
        self.file_path = "CHANGELOG.md"
        self.added = []

    def get_file_path(self):
        return self.file_path

    def has_unreleased(self):
        return self.has_unreleased_value

    def list_unreleased(self):
        return list(self.entries)

    def remove(self, change_type, index):
        self.calls.append(("remove", change_type, index))
        return f"{change_type}[{index}]"

    def edit(self, change_type, index, new_message=None, new_change_type=None):
        self.calls.append(("edit", change_type, index, new_message, new_change_type))

    def add(self, change_type, message):
        self.added.append((change_type, message))

    def write_to_file(self):
        self.calls.append(("write_to_file",))

    def get(self, version=None):
        return {}

    def suggest_future_version(self):
        return "1.2.3"

    def get_versioning_scheme(self):
        return "semver"


# ---------------------------------------------------------------------------
# config init --config <new-path> fix
# ---------------------------------------------------------------------------


def test_config_init_with_missing_explicit_config_does_not_crash(monkeypatch, tmp_path):
    """main() must not load a not-yet-created config before the init handler runs."""

    target = tmp_path / "new-config.yml"

    def fake_versioning(config):
        # main() must only resolve the scheme from an existing file (or None),
        # never from the not-yet-created target path.
        assert config != str(target)
        return "semver"

    monkeypatch.setattr(cli.entry, "get_versioning_scheme", fake_versioning)
    monkeypatch.setattr(
        cli.prompts,
        "prompt_for_config_init",
        lambda config, *, default_format, prompt_for_format: {
            "config_format": "yaml",
            "commit_style": "conventional",
            "versioning_scheme": "semver",
            "enforce_preamble": False,
            "component_name": "default",
            "changelog_path": "CHANGELOG.md",
            "prompted_components": True,
        },
    )

    assert cli.main(["--config", str(target), "config", "init"]) == 0
    assert target.is_file()


def test_main_config_command_with_missing_explicit_config_errors_cleanly():
    """`config` (display) on a missing explicit path exits 1 cleanly (no traceback).

    Before the fix, main() eagerly loaded the versioning scheme from the explicit
    config path and raised an uncaught FileNotFoundError. Now a missing explicit
    config surfaces as a handled logging.Error (return code 1).
    """

    rc = cli.main(["--config", "definitely-not-here.yml", "config"])
    assert rc == 1


# ---------------------------------------------------------------------------
# Interactive entry picker for remove / edit
# ---------------------------------------------------------------------------


def test_resolve_entry_selection_returns_explicit_args_without_prompt(monkeypatch):
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)
    monkeypatch.setattr(
        cli.inquirer, "prompt", lambda prompts: pytest.fail("unexpected prompt")
    )
    args = make_args(change_type="fixed", index=0)
    assert cli.resolve_entry_selection(args, DummyChangelog(), action="removed") == (
        "fixed",
        0,
    )


def test_resolve_entry_selection_prompts_when_missing(monkeypatch):
    changelog = DummyChangelog(
        unreleased_entries=[("added", 0, "A feature"), ("fixed", 0, "A bug")]
    )
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)

    captured = {}

    def fake_prompt(prompts):
        captured["choices"] = list(prompts[0].choices)
        # choose the second entry
        return {"entry": captured["choices"][1]}

    monkeypatch.setattr(cli.inquirer, "prompt", fake_prompt)

    args = make_args(change_type=None, index=None)
    assert cli.resolve_entry_selection(args, changelog, action="edited") == ("fixed", 0)
    assert captured["choices"] == ["[added] 0: A feature", "[fixed] 0: A bug"]


def test_resolve_entry_selection_errors_when_non_interactive(monkeypatch):
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: False)
    args = make_args(change_type=None, index=None)
    with pytest.raises(logging.Error, match="--change-type and --index are required"):
        cli.resolve_entry_selection(args, DummyChangelog(), action="removed")


def test_command_remove_uses_interactive_picker(monkeypatch):
    changelog = DummyChangelog(unreleased_entries=[("fixed", 0, "A bug")])
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)
    monkeypatch.setattr(
        cli.prompts, "prompt_for_unreleased_entry", lambda cl, *, action: ("fixed", 0)
    )

    cli.command_remove(
        make_args(list=False, change_type=None, index=None, dry_run=False),
        cli.CliContext(changelog=changelog),
    )
    assert ("remove", "fixed", 0) in changelog.calls
    assert ("write_to_file",) in changelog.calls


def test_command_edit_prompts_for_entry_and_message(monkeypatch):
    changelog = DummyChangelog(unreleased_entries=[("added", 0, "Old text")])
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)
    monkeypatch.setattr(
        cli.prompts, "prompt_for_unreleased_entry", lambda cl, *, action: ("added", 0)
    )
    monkeypatch.setattr(
        cli.prompts, "prompt_text", lambda message, default=None: "New text"
    )

    cli.command_edit(
        make_args(
            change_type=None,
            index=None,
            message=None,
            new_change_type=None,
            dry_run=False,
        ),
        cli.CliContext(changelog=changelog),
    )
    assert ("edit", "added", 0, "New text", None) in changelog.calls


def test_command_edit_non_interactive_still_requires_change(monkeypatch):
    changelog = DummyChangelog(unreleased_entries=[("added", 0, "Old text")])
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: False)
    with pytest.raises(logging.Error, match="--change-type and --index are required"):
        cli.command_edit(
            make_args(
                change_type=None,
                index=None,
                message=None,
                new_change_type=None,
                dry_run=False,
            ),
            cli.CliContext(changelog=changelog),
        )


# ---------------------------------------------------------------------------
# Interactive token / repository prompts
# ---------------------------------------------------------------------------


def test_resolve_required_value_prefers_explicit(monkeypatch):
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)
    monkeypatch.setattr(
        cli.inquirer, "prompt", lambda prompts: pytest.fail("unexpected prompt")
    )
    assert (
        cli.resolve_required_value("owner/repo", env_var=None, message="Repo")
        == "owner/repo"
    )


def test_resolve_required_value_uses_env(monkeypatch):
    monkeypatch.setenv("MY_TOKEN", "from-env")
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)
    monkeypatch.setattr(
        cli.inquirer, "prompt", lambda prompts: pytest.fail("unexpected prompt")
    )
    assert (
        cli.resolve_required_value(None, env_var="MY_TOKEN", message="Token")
        == "from-env"
    )


def test_resolve_required_value_prompts_interactively(monkeypatch):
    monkeypatch.delenv("MY_TOKEN", raising=False)
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)
    monkeypatch.setattr(
        cli.prompts, "prompt_text", lambda message, default=None: "typed"
    )
    assert (
        cli.resolve_required_value(None, env_var="MY_TOKEN", message="Token") == "typed"
    )


def test_resolve_required_value_non_interactive_returns_none(monkeypatch):
    monkeypatch.delenv("MY_TOKEN", raising=False)
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: False)
    assert cli.resolve_required_value(None, env_var="MY_TOKEN", message="Token") is None


def test_command_github_release_prompts_for_repository(monkeypatch):
    changelog = DummyChangelog(has_unreleased=True)
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)

    prompts = iter(["owner/repo", "secret-token"])
    monkeypatch.setattr(
        cli.prompts, "prompt_text", lambda message, default=None: next(prompts)
    )

    args = make_args(
        repository=None,
        github_token=None,
        draft=True,
        dry_run=True,
    )
    ctx = cli.CliContext(changelog=changelog)
    cli.command_github_release(args, ctx)

    assert args.repository == "owner/repo"
    assert ctx.json_payload["version"] == "1.2.3"


def test_command_gitlab_release_prompts_for_project(monkeypatch):
    changelog = DummyChangelog(has_unreleased=True)
    monkeypatch.setattr(cli.prompts, "interactive_enabled", lambda: True)

    prompts = iter(["group/project", "glpat-token"])
    monkeypatch.setattr(
        cli.prompts, "prompt_text", lambda message, default=None: next(prompts)
    )
    monkeypatch.delenv("GITLAB_TOKEN", raising=False)
    monkeypatch.delenv("CI_JOB_TOKEN", raising=False)

    args = make_args(
        project=None,
        gitlab_token=None,
        gitlab_url="https://gitlab.com",
        ref="HEAD",
        dry_run=True,
    )
    ctx = cli.CliContext(changelog=changelog)
    cli.command_gitlab_release(args, ctx)

    assert args.project == "group/project"
    assert ctx.json_payload["project"] == "group/project"


# ---------------------------------------------------------------------------
# backfill --include-unreleased
# ---------------------------------------------------------------------------


def test_plan_unreleased_backfill_filters_existing(monkeypatch):
    class CL:
        def get_versioning_scheme(self):
            return "semver"

        def get(self):
            return {
                backfill.UNRELEASED_ENTRY: {
                    "metadata": {"version": backfill.UNRELEASED_ENTRY},
                    "added": ["Already there"],
                }
            }

    monkeypatch.setattr(backfill, "latest_release_tag", lambda **kwargs: "v1.0.0")
    monkeypatch.setattr(
        backfill,
        "git_log_between",
        lambda prev, cur, cwd=None: [
            backfill.GitCommit(sha="a", subject="feat: brand new"),
            backfill.GitCommit(sha="b", subject="added: Already there"),
        ],
    )

    entries = backfill.plan_unreleased_backfill(CL(), commit_schema="auto")
    texts = [(e.change_type, e.text) for e in entries]
    assert ("added", "brand new") in texts
    # "Already there" is filtered because it already exists in [Unreleased]
    assert all(text != "Already there" for _, text in texts)


def test_command_backfill_include_unreleased_adds_entries(monkeypatch):
    changelog = DummyChangelog()
    monkeypatch.setattr(
        services,
        "plan_unreleased_backfill",
        lambda cl, *, since, commit_schema: [
            backfill.BackfillEntry(
                change_type="added", text="new thing", source="commits"
            )
        ],
    )

    args = make_args(
        source="all",
        strategy="conservative",
        missing_only=True,
        include_unreleased=True,
        since=None,
        commit_schema="auto",
        dry_run=False,
    )
    ctx = cli.CliContext(changelog=changelog)
    cli.command_backfill(args, ctx)

    assert ("added", "new thing") in changelog.added
    assert ("write_to_file",) in changelog.calls
    assert ctx.json_payload["unreleased_added"] == [
        {"change_type": "added", "message": "new thing"}
    ]


def test_command_backfill_include_unreleased_dry_run(monkeypatch, capsys):
    changelog = DummyChangelog()
    monkeypatch.setattr(
        services,
        "plan_unreleased_backfill",
        lambda cl, *, since, commit_schema: [
            backfill.BackfillEntry(change_type="fixed", text="a fix", source="commits")
        ],
    )

    args = make_args(
        source="all",
        strategy="conservative",
        missing_only=True,
        include_unreleased=True,
        since=None,
        commit_schema="auto",
        dry_run=True,
    )
    ctx = cli.CliContext(changelog=changelog)
    cli.command_backfill(args, ctx)

    out = capsys.readouterr().out
    assert "would add: [fixed] a fix" in out
    assert changelog.added == []
    assert ("write_to_file",) not in changelog.calls
