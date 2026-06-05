import argparse
from types import SimpleNamespace

import pytest

import changelogmanager.cli.entry as cli_main_module
import changelogmanager.llvm_diagnostics as logging
from changelogmanager import cli
from changelogmanager.change_types import UNRELEASED_ENTRY


class DummyChangelog:
    def __init__(self, exists=False, has_unreleased=True):
        self.exists_value = exists
        self.has_unreleased_value = has_unreleased
        self.calls = []
        self.file_path = "CHANGELOG.md"

    def exists(self):
        return self.exists_value

    def get_file_path(self):
        return self.file_path

    def has_unreleased(self):
        return self.has_unreleased_value

    def write_to_file(self):
        self.calls.append(("write_to_file",))

    def release(self, version):
        self.calls.append(("release", version))

    def to_json(self, schema_version="current"):
        self.calls.append(("to_json", schema_version))
        return "[]"

    def write_to_json(self, file, schema_version="current"):
        self.calls.append(("write_to_json", file, schema_version))

    def add(self, change_type, message):
        self.calls.append(("add", change_type, message))

    def add_many(self, entries):
        for change_type, message in entries:
            self.calls.append(("add", change_type, message))

    def get(self, version=None):
        self.calls.append(("get", version))
        return {"metadata": {"version": version or UNRELEASED_ENTRY}}

    def suggest_future_version(self):
        self.calls.append(("suggest_future_version",))
        return "1.2.3"


def make_args(**kwargs):
    return argparse.Namespace(**kwargs)


def test_configure_logging_selects_requested_formatter():
    cli.configure_logging("github")
    assert isinstance(logging.formatters.get_config(), logging.formatters.GitHub)

    cli.configure_logging("llvm")
    assert isinstance(logging.formatters.get_config(), logging.formatters.Llvm)


def test_load_changelog_uses_component_config_when_present(monkeypatch):
    seen = {}

    class FakeReader:
        def __init__(
            self,
            file_path,
            enforce_preamble=False,
            preamble_keywords=None,
            versioning_scheme="semver",
        ):
            seen["file_path"] = file_path
            seen["enforce_preamble"] = enforce_preamble
            seen["preamble_keywords"] = preamble_keywords
            seen["versioning_scheme"] = versioning_scheme

        def read(self):
            return {"1.0.0": {"metadata": {"version": "1.0.0"}}}

    monkeypatch.setattr(
        cli.loaders,
        "get_component_from_config",
        lambda config, component: {"changelog": "docs/COMPONENT_CHANGELOG.md"},
    )
    monkeypatch.setattr(
        cli.loaders,
        "get_preamble_keywords",
        lambda config: ("keep a changelog", "semantic versioning"),
    )
    monkeypatch.setattr(cli.loaders, "get_versioning_scheme", lambda config: "semver")
    monkeypatch.setattr(cli.loaders, "ChangelogReader", FakeReader)

    # No explicit --input-file (None): the config/component changelog is used.
    changelog = cli.load_changelog(
        config="components.yml",
        component="api",
        input_file=None,
    )

    assert seen["file_path"] == "docs/COMPONENT_CHANGELOG.md"
    assert changelog.get_file_path() == "docs/COMPONENT_CHANGELOG.md"
    assert changelog.get()["1.0.0"]["metadata"]["version"] == "1.0.0"
    assert seen["preamble_keywords"] == ("keep a changelog", "semantic versioning")
    assert seen["versioning_scheme"] == "semver"


def test_explicit_input_file_overrides_component_config(monkeypatch):
    """An explicit --input-file must win over a config/component changelog path.

    This guards against ambient config (e.g. a ``[tool.changelogmanager]`` table in
    the cwd's ``pyproject.toml``) silently redirecting an explicit ``--input-file`` to
    the wrong file — which previously let tests/scripts clobber the repo's own
    CHANGELOG.md.
    """

    seen = {}

    class FakeReader:
        def __init__(self, file_path, **_kwargs):
            seen["file_path"] = file_path

        def read(self):
            return {}

    monkeypatch.setattr(
        cli.loaders,
        "get_component_from_config",
        lambda config, component: {"changelog": "docs/COMPONENT_CHANGELOG.md"},
    )
    monkeypatch.setattr(cli.loaders, "get_preamble_keywords", lambda config: ())
    monkeypatch.setattr(cli.loaders, "get_versioning_scheme", lambda config: "semver")
    monkeypatch.setattr(cli.loaders, "ChangelogReader", FakeReader)

    changelog = cli.load_changelog(
        config="components.yml",
        component="api",
        input_file="EXPLICIT.md",
    )

    assert seen["file_path"] == "EXPLICIT.md"
    assert changelog.get_file_path() == "EXPLICIT.md"


def test_resolve_changelog_file_precedence():
    """flag > config component changelog > built-in default."""

    from changelogmanager.cli.loaders import (
        DEFAULT_CHANGELOG_FILE,
        resolve_changelog_file,
    )

    # No config, no explicit flag -> built-in default.
    assert (
        resolve_changelog_file(config=None, component="default", input_file=None)
        == DEFAULT_CHANGELOG_FILE
    )
    # Explicit flag, no config -> the flag.
    assert (
        resolve_changelog_file(config=None, component="default", input_file="a.md")
        == "a.md"
    )


def test_prompt_for_missing_add_arguments_uses_existing_values_without_prompt(
    monkeypatch,
):
    monkeypatch.setattr(
        cli.inquirer, "prompt", lambda prompts: pytest.fail("unexpected prompt")
    )

    entry = cli.prompt_for_missing_add_arguments("fixed", "Patched bug")

    assert entry == {
        "change_type": "fixed",
        "message": "Patched bug",
        "confirm": "Yes",
    }


def test_prompt_for_missing_add_arguments_prompts_for_missing_values(monkeypatch):
    captured = {}

    def fake_prompt(prompts):
        captured["names"] = [prompt.name for prompt in prompts]
        return {"change_type": "added", "message": "Feature", "confirm": "No"}

    monkeypatch.setattr(cli.inquirer, "prompt", fake_prompt)

    entry = cli.prompt_for_missing_add_arguments(None, None)

    assert captured["names"] == ["change_type", "message", "confirm"]
    assert entry == {"change_type": "added", "message": "Feature", "confirm": "No"}


def test_command_create_handles_existing_files_and_dry_run(capsys):
    with pytest.raises(logging.Info, match="File already exists"):
        cli.command_create(
            make_args(dry_run=False),
            cli.CliContext(changelog=DummyChangelog(exists=True)),
        )

    changelog = DummyChangelog()
    cli.command_create(make_args(dry_run=True), cli.CliContext(changelog=changelog))

    assert changelog.calls == []
    assert "Dry run: would create CHANGELOG.md" in capsys.readouterr().out


def test_command_release_add_and_to_json_respect_dry_run_and_confirmation(
    monkeypatch, capsys
):
    changelog = DummyChangelog()

    cli.command_release(
        make_args(dry_run=True, override_version="1.2.0"),
        cli.CliContext(changelog=changelog),
    )
    assert ("release", "1.2.0") in changelog.calls
    assert ("write_to_file",) not in changelog.calls
    assert "Dry run: would release CHANGELOG.md" in capsys.readouterr().out

    monkeypatch.setattr(
        cli.prompts,
        "prompt_for_missing_add_arguments",
        lambda change_type, message: {
            "change_type": "fixed",
            "message": "Patched",
            "confirm": "No",
        },
    )
    cli.command_add(
        make_args(change_type=None, message=None, dry_run=False),
        cli.CliContext(changelog=changelog),
    )
    assert ("add", "fixed", "Patched") in changelog.calls
    assert changelog.calls.count(("write_to_file",)) == 0

    cli.command_to_json(
        make_args(dry_run=True, file_name="out.json"),
        cli.CliContext(changelog=changelog),
    )
    assert ("to_json", "current") in changelog.calls
    assert "Dry run: would write JSON output to out.json" in capsys.readouterr().out


def test_command_github_release_supports_dry_run_and_real_execution(
    monkeypatch, capsys
):
    changelog = DummyChangelog()
    calls = []

    class FakeGitHub:
        def __init__(self, repository, token):
            calls.append(("init", repository, token))

        def delete_draft_releases(self):
            calls.append(("delete_draft_releases",))

        def create_release(self, changelog, draft):
            calls.append(("create_release", changelog, draft))
            return {
                "id": 99,
                "tag_name": "v1.2.3",
                "html_url": "https://github.com/owner/repo/releases/tag/v1.2.3",
                "draft": draft,
            }

    cli.command_github_release(
        make_args(
            dry_run=True,
            draft=False,
            repository="owner/repo",
            github_token="token",
        ),
        cli.CliContext(changelog=changelog),
    )
    dry_run_output = capsys.readouterr().out
    assert ("suggest_future_version",) in changelog.calls
    assert "published GitHub release v1.2.3 in owner/repo" in dry_run_output

    monkeypatch.setattr(cli.commands, "GitHub", FakeGitHub)
    cli.command_github_release(
        make_args(
            dry_run=False,
            draft=True,
            repository="owner/repo",
            github_token="token",
        ),
        cli.CliContext(changelog=changelog),
    )
    create_output = capsys.readouterr().out

    assert calls == [
        ("init", "owner/repo", "token"),
        ("delete_draft_releases",),
        ("create_release", changelog, True),
    ]
    assert (
        "Created draft GitHub release v1.2.3 in owner/repo: "
        "https://github.com/owner/repo/releases/tag/v1.2.3" in create_output
    )


def test_build_parser_parses_commands_and_defaults():
    parser = cli.build_parser()

    config_args = parser.parse_args(["config"])
    assert config_args.handler is cli.command_config

    skill_args = parser.parse_args(["skill", "export", "--path", "skills"])
    assert skill_args.handler is cli.command_skill_export
    assert skill_args.path == "skills"

    version_args = parser.parse_args(["version"])
    assert version_args.reference == "current"
    assert version_args.dry_run is False
    assert version_args.info is False
    assert version_args.verbose is False
    assert version_args.handler is cli.command_version

    verbose_args = parser.parse_args(["--verbose", "config"])
    assert verbose_args.verbose is True
    assert verbose_args.info is False

    github_release_args = parser.parse_args(
        ["github-release", "-r", "owner/repo", "-t", "token", "--release"]
    )
    assert github_release_args.draft is False
    assert github_release_args.handler is cli.command_github_release


def test_main_config_command_skips_changelog_loading(monkeypatch):
    seen = {}

    def fake_handler(args, context):
        seen["context"] = context

    args = SimpleNamespace(
        command="config",
        config_command=None,
        error_format="llvm",
        config=None,
        component="default",
        input_file="CHANGELOG.md",
        quiet=False,
        json=False,
        handler=fake_handler,
    )

    class FakeParser:
        def parse_args(self, argv):
            return args

    monkeypatch.setattr(cli_main_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(cli_main_module, "configure_logging", lambda error_format: None)
    monkeypatch.setattr(cli_main_module, "resolve_config", lambda config: None)
    monkeypatch.setattr(
        cli_main_module,
        "load_changelog",
        lambda **kwargs: pytest.fail("config should not load a changelog"),
    )

    assert cli.main([]) == 0
    assert isinstance(seen["context"], cli.CliContext)


def test_main_skill_command_skips_changelog_loading(monkeypatch):
    seen = {}

    def fake_handler(args, context):
        seen["context"] = context

    args = SimpleNamespace(
        command="skill",
        skill_command="export",
        error_format="llvm",
        config=None,
        component="default",
        input_file="CHANGELOG.md",
        quiet=False,
        json=False,
        handler=fake_handler,
        path="skills",
    )

    class FakeParser:
        def parse_args(self, argv):
            return args

    monkeypatch.setattr(cli_main_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(cli_main_module, "configure_logging", lambda error_format: None)
    monkeypatch.setattr(cli_main_module, "resolve_config", lambda config: None)
    monkeypatch.setattr(
        cli_main_module,
        "load_changelog",
        lambda **kwargs: pytest.fail("skill should not load a changelog"),
    )

    assert cli.main([]) == 0
    assert isinstance(seen["context"], cli.CliContext)


@pytest.mark.parametrize(
    ("exception_factory", "expected"),
    [
        (lambda: logging.Info(message="done"), 0),
        (lambda: logging.Warning(message="warn"), 0),
        (lambda: logging.Error(message="boom"), 1),
        (lambda: SystemExit("bad"), 1),
    ],
)
def test_main_returns_expected_exit_codes_for_exceptions(
    monkeypatch, exception_factory, expected
):
    def fake_handler(args, context):
        raise exception_factory()

    args = SimpleNamespace(
        command="version",
        error_format="llvm",
        config=None,
        component="default",
        input_file="CHANGELOG.md",
        quiet=False,
        json=False,
        handler=fake_handler,
    )

    class FakeParser:
        def parse_args(self, argv):
            return args

    monkeypatch.setattr(cli_main_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(cli_main_module, "configure_logging", lambda error_format: None)
    monkeypatch.setattr(cli_main_module, "resolve_config", lambda config: None)
    monkeypatch.setattr(
        cli_main_module, "load_changelog", lambda **kwargs: DummyChangelog()
    )

    assert cli.main([]) == expected


def test_main_returns_zero_for_successful_execution(monkeypatch):
    seen = {}

    def fake_handler(args, context):
        seen["context"] = context

    args = SimpleNamespace(
        command="version",
        error_format="llvm",
        config=None,
        component="default",
        input_file="CHANGELOG.md",
        quiet=False,
        json=False,
        handler=fake_handler,
    )

    class FakeParser:
        def parse_args(self, argv):
            return args

    monkeypatch.setattr(cli_main_module, "build_parser", lambda: FakeParser())
    monkeypatch.setattr(cli_main_module, "configure_logging", lambda error_format: None)
    monkeypatch.setattr(cli_main_module, "resolve_config", lambda config: None)
    monkeypatch.setattr(
        cli_main_module, "load_changelog", lambda **kwargs: DummyChangelog()
    )

    assert cli.main([]) == 0
    assert isinstance(seen["context"], cli.CliContext)
