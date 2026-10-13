"""Component history and sidecar isolation against real, temporary Git repositories."""

import io
import json
import re
import subprocess
from contextlib import redirect_stderr, redirect_stdout

import pytest

from changelogmanager import backfill, services
from changelogmanager.cli import main
from changelogmanager.commit_routing import component_history
from changelogmanager.config import clear_configuration_cache
from changelogmanager.github import GitHub
from changelogmanager.release_scope import release_scope


def cli(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        code = main(list(args))
    return code, stdout.getvalue(), stderr.getvalue()


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "repo"
    root.mkdir()
    for name in ("core", "plugin"):
        folder = root / name
        folder.mkdir()
        (folder / "CHANGELOG.md").write_text(
            "# Changelog\n\n## [Unreleased]\n", encoding="utf-8"
        )
        (folder / "__about__.py").write_text(
            '__version__ = "0.0.1"\n', encoding="utf-8"
        )
    config = root / "changelogmanager.toml"
    config.write_text(
        """[versioning]
scheme = "semver"
[fragments]
directory = "shared-fragments"
[[components]]
name = "core"
changelog = "core/CHANGELOG.md"
tasks_file = "core/TASKS.md"
fragment_directory = "core/changelog.d"
version_files = ["core/__about__.py"]
match = ["core/**", "shared/**"]
[[components]]
name = "plugin"
changelog = "plugin/CHANGELOG.md"
fragment_directory = "plugin/changelog.d"
version_files = ["plugin/__about__.py"]
match = ["plugin/**", "shared/**"]
""",
        encoding="utf-8",
    )
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Test")
    git(root, "config", "user.email", "test@example.invalid")
    git(root, "add", ".")
    git(root, "commit", "-m", "feat: initial packages")
    git(root, "tag", "core-v0.0.1")
    git(root, "tag", "plugin-v0.0.1")

    def commit(path, subject):
        target = root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(subject + "\n", encoding="utf-8")
        git(root, "add", path)
        git(root, "commit", "-m", subject)

    commit("core/early.py", "feat: core earlier")
    commit("plugin/early.py", "fix: plugin earlier")
    git(root, "tag", "plugin-v0.0.2")
    commit("core/recent.py", "fix: core recent")
    commit("plugin/recent.py", "feat: plugin later")
    commit("shared/util.py", "feat: shared behavior")
    monkeypatch.chdir(root)
    return root, config


def messages(payload):
    return {entry["message"] for entry in payload["added"]}


def test_single_import_routes_files_and_uses_own_tag_from_another_cwd(
    workspace, tmp_path, monkeypatch
):
    root, config = workspace
    monkeypatch.chdir(tmp_path)
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "--json",
        "from-commits",
        "--dry-run",
    )
    assert code == 0, error
    payload = json.loads(output)
    assert payload["since"] == "core-v0.0.1"
    assert messages(payload) == {"core earlier", "core recent", "shared behavior"}
    assert "earlier" not in (root / "core/CHANGELOG.md").read_text()


def test_batch_import_uses_a_different_cutoff_for_each_component(workspace):
    root, config = workspace
    plugin_before = (root / "plugin/CHANGELOG.md").read_bytes()
    code, output, error = cli(
        "--config", str(config), "--json", "from-commits", "--all", "--dry-run"
    )
    assert code == 0, error
    components = {item["component"]: item for item in json.loads(output)["components"]}
    assert components["core"]["since"] == "core-v0.0.1"
    assert components["plugin"]["since"] == "plugin-v0.0.2"
    assert messages(components["core"]) == {
        "core earlier",
        "core recent",
        "shared behavior",
    }
    assert messages(components["plugin"]) == {"plugin later", "shared behavior"}
    assert (root / "plugin/CHANGELOG.md").read_bytes() == plugin_before


def test_batch_strict_skip_count_counts_a_shared_commit_once(workspace):
    root, config = workspace
    (root / "shared/unclassified.py").write_text("# unclassified change\n")
    git(root, "add", "shared/unclassified.py")
    git(root, "commit", "-m", "Unclassified subject")
    code, output, error = cli(
        "--config",
        str(config),
        "--json",
        "from-commits",
        "--all",
        "--strict",
        "--dry-run",
    )
    assert code == 0, error
    assert json.loads(output)["skipped"] == 1


def test_github_pr_file_routing_paginates_and_includes_rename_source(monkeypatch):
    import changelogmanager.github as github_module

    monkeypatch.setattr(github_module, "RELEASES_CHUNK_SIZE", 1)
    pages = {
        1: [{"filename": "plugin/new.py", "previous_filename": "core/old.py"}],
        2: [{"filename": "core/other.py"}],
        3: [],
    }
    seen = []

    def get_page(self, api, data):
        seen.append((api, data["page"]))
        return pages[data["page"]]

    monkeypatch.setattr(GitHub, "_get_with_rate_check", get_page)
    assert GitHub(repository="owner/repo", token="").get_pr_files(42) == [
        "plugin/new.py",
        "core/old.py",
        "core/other.py",
    ]
    assert seen == [("pulls/42/files", 1), ("pulls/42/files", 2), ("pulls/42/files", 3)]


@pytest.mark.parametrize(
    "content,valid",
    [
        ("[[broken", False),
        ('[project]\nname = "dynamic"\ndynamic = ["version"]', False),
        ("[project]\nversion = 1", False),
        ('[project]\nversion = "1.0.0"', True),
    ],
)
def test_version_readiness_inspection_does_not_change_pyproject(
    tmp_path, content, valid
):
    from changelogmanager.version_bumper import version_file_issue

    path = tmp_path / "pyproject.toml"
    path.write_text(content, encoding="utf-8")
    before = path.read_bytes()
    assert (version_file_issue(path) is None) is valid
    assert path.read_bytes() == before


def test_explicit_common_cutoff_and_all_history_are_preserved(workspace):
    _root, config = workspace
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "--json",
        "from-commits",
        "--since",
        "plugin-v0.0.2",
        "--dry-run",
    )
    assert code == 0, error
    assert messages(json.loads(output)) == {"core recent", "shared behavior"}
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "--json",
        "from-commits",
        "--all-history",
        "--dry-run",
    )
    assert code == 0, error
    assert json.loads(output)["since"] is None
    assert "initial packages" in messages(json.loads(output))


def test_unreleased_backfill_uses_own_cutoff_and_files(workspace):
    _root, config = workspace
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "--json",
        "backfill",
        "--include-unreleased",
        "--dry-run",
    )
    assert code == 0, error
    payload = json.loads(output)
    assert payload["since"] == "core-v0.0.1"
    assert {item["message"] for item in payload["unreleased_added"]} == {
        "core earlier",
        "core recent",
        "shared behavior",
    }


@pytest.mark.parametrize("source", ["tags", "commits", "local"])
def test_historical_backfill_uses_own_namespace_and_commit_files(workspace, source):
    root, config = workspace
    git(root, "tag", "core-v0.0.2")
    before = (root / "plugin/CHANGELOG.md").read_bytes()
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "--json",
        "backfill",
        "--source",
        source,
        "--dry-run",
    )
    assert code == 0, error
    assert set(json.loads(output)["added_versions"]) == {"0.0.1", "0.0.2"}
    releases, skipped = backfill.discover_tag_releases(
        history=component_history(str(config), "core")
    )
    assert {release.tag for release in releases} == {"core-v0.0.1", "core-v0.0.2"}
    assert skipped == []
    code, _output, error = cli(
        "--config", str(config), "--component", "core", "backfill", "--source", source
    )
    assert code == 0, error
    if source != "tags":
        content = (root / "core/CHANGELOG.md").read_text()
        assert all(
            message in content
            for message in ("core earlier", "core recent", "shared behavior")
        )
        assert "plugin earlier" not in content
        assert "plugin later" not in content
    assert (root / "plugin/CHANGELOG.md").read_bytes() == before


def test_scoped_backfill_accepts_bare_version_bounds(workspace):
    root, config = workspace
    git(root, "tag", "core-v0.0.2")
    history = component_history(str(config), "core")
    releases, skipped = backfill.discover_tag_releases(
        since="0.0.2", until="core-v0.0.2", history=history
    )
    assert [release.tag for release in releases] == ["core-v0.0.2"]
    assert skipped == []


def test_backfill_lower_bound_does_not_import_older_release_commits(workspace):
    root, config = workspace
    git(root, "tag", "core-v0.0.2")
    releases, _skipped = backfill.discover_commit_releases(
        since="0.0.2", history=component_history(str(config), "core")
    )
    assert [release.version for release in releases] == ["0.0.2"]
    assert {entry.text for entry in releases[0].entries} == {
        "core earlier",
        "core recent",
        "shared behavior",
    }


@pytest.mark.parametrize(
    "first,second",
    [("v{version}", "v{version}-plugin"), ("v{version}-core", "v1{version}")],
)
def test_namespace_overlap_fails_during_config_inspection(workspace, first, second):
    _root, config = workspace
    config.write_text(
        config.read_text()
        .replace('name = "core"', f'name = "core"\ntag_template = "{first}"')
        .replace('name = "plugin"', f'name = "plugin"\ntag_template = "{second}"')
    )
    clear_configuration_cache()
    code, _output, error = cli("--config", str(config), "components", "list")
    assert code == 1
    assert "colliding tag templates" in error


def test_rollback_detects_own_tag_and_refuses_sibling_tag_before_any_deletion(
    workspace, monkeypatch
):
    _root, config = workspace
    calls = []
    monkeypatch.setattr(
        services,
        "release_rollback",
        lambda **kwargs: calls.append(kwargs)
        or services.ReleaseRollbackResult(tag=kwargs["tag"], dry_run=True),
    )
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "--json",
        "release-rollback",
        "--dry-run",
    )
    assert code == 0, error
    assert json.loads(output)["tag"] == "core-v0.0.1"
    assert calls[0]["tag"] == "core-v0.0.1"
    calls.clear()
    code, _output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "release-rollback",
        "--tag",
        "plugin-v0.0.2",
        "--dry-run",
    )
    assert code == 1
    assert "does not match component" in error
    assert calls == []


def test_missing_component_tag_does_not_fall_back_to_sibling(workspace):
    root, config = workspace
    git(root, "tag", "-d", "core-v0.0.1")
    assert services.last_release_tag(release_scope(str(config), "core")) is None
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "--json",
        "from-commits",
        "--dry-run",
    )
    assert code == 0, error
    assert json.loads(output)["since"] is None
    assert "initial packages" in messages(json.loads(output))


@pytest.mark.parametrize("add_command", ["fragments", "add"])
def test_fragments_are_isolated_and_resolved_from_config(
    workspace, tmp_path, monkeypatch, add_command
):
    root, config = workspace
    monkeypatch.chdir(tmp_path)
    prefix = ("--config", str(config), "--component", "core")
    add_args = (
        ("fragments", "add", "added", "Core feature")
        if add_command == "fragments"
        else (
            "add",
            "--fragment",
            "--change-type",
            "added",
            "--message",
            "Core feature",
        )
    )
    code, _output, error = cli(*prefix, *add_args)
    assert code == 0, error
    assert (root / "core/changelog.d/core-feature.added.md").is_file()
    assert not (tmp_path / "changelog.d").exists()
    cli(
        "--config",
        str(config),
        "--component",
        "plugin",
        "fragments",
        "add",
        "fixed",
        "Plugin fix",
    )
    code, _output, error = cli(*prefix, "fragments", "collect")
    assert code == 0, error
    assert "Core feature" in (root / "core/CHANGELOG.md").read_text()
    assert "Plugin fix" not in (root / "core/CHANGELOG.md").read_text()
    assert (root / "plugin/changelog.d/plugin-fix.fixed.md").is_file()


def test_fragment_cli_override_and_global_fallback(workspace, tmp_path, monkeypatch):
    root, config = workspace
    config.write_text(
        config.read_text().replace('fragment_directory = "core/changelog.d"\n', "")
    )
    clear_configuration_cache()
    monkeypatch.chdir(tmp_path)
    prefix = ("--config", str(config), "--component", "core")
    assert cli(*prefix, "fragments", "add", "added", "Global feature")[0] == 0
    assert (root / "shared-fragments/global-feature.added.md").is_file()
    assert (
        cli(
            *prefix,
            "fragments",
            "add",
            "added",
            "Override feature",
            "--fragment-dir",
            "override",
        )[0]
        == 0
    )
    assert (tmp_path / "override/override-feature.added.md").is_file()


def test_github_release_backfill_filters_and_normalizes_component_tags(
    workspace, monkeypatch
):
    _root, config = workspace
    monkeypatch.setattr(
        GitHub,
        "get_releases_for_backfill",
        lambda self: [
            {"version": "core-v0.0.2", "body": "Core notes"},
            {"version": "plugin-v0.0.2", "body": "Plugin notes"},
        ],
    )
    releases, skipped = backfill.discover_github_releases(
        "owner/repo", None, history=component_history(str(config), "core")
    )
    assert [release.version for release in releases] == ["0.0.2"]
    assert releases[0].entries[0].text == "Core notes"
    assert skipped == []


def test_github_pr_backfill_routes_files_and_uses_component_timeline(
    workspace, monkeypatch
):
    root, config = workspace
    git(root, "tag", "core-v0.0.2")
    date = git(root, "log", "-1", "--format=%cs")
    monkeypatch.setattr(
        GitHub,
        "get_merged_prs",
        lambda self, **kwargs: [
            {"number": 1, "title": "Core PR", "merged_at": date},
            {"number": 2, "title": "Plugin PR", "merged_at": date},
        ],
    )
    monkeypatch.setattr(
        GitHub,
        "get_pr_files",
        lambda self, number: (
            ["core/feature.py"] if number == 1 else ["plugin/feature.py"]
        ),
    )
    releases, _skipped = backfill.discover_github_prs(
        "owner/repo", None, history=component_history(str(config), "core")
    )
    assert {entry.text for release in releases for entry in release.entries} == {
        "Core PR"
    }


def test_inspection_is_read_only_and_reports_resolved_paths(workspace):
    root, config = workspace
    before = {
        path: path.read_bytes()
        for path in root.rglob("*")
        if path.is_file() and ".git" not in path.parts
    }
    code, output, error = cli(
        "--config", str(config), "--json", "components", "show", "core"
    )
    assert code == 0, error
    item = json.loads(output)["components"][0]
    assert item["changelog"] == str(root / "core/CHANGELOG.md")
    assert item["tasks_file"] == str(root / "core/TASKS.md")
    assert item["fragment_directory"] == str(root / "core/changelog.d")
    assert item["tag_template"] == "{component}-v{version}"
    assert item["version_files"] == [str(root / "core/__about__.py")]
    assert item["inherited"]["versioning"]["scheme"] == "semver"
    assert item["issues"] == []
    assert cli("--config", str(config), "components", "validate")[0] == 0
    assert all(path.read_bytes() == content for path, content in before.items())


def test_inspection_reports_missing_or_uneditable_files_in_json(workspace):
    root, config = workspace
    (root / "core/__about__.py").write_text(
        "# automatically generated by setuptools-scm\n__version__ = '1.0.0'\n"
    )
    (root / "plugin/CHANGELOG.md").unlink()
    code, output, error = cli(
        "--config", str(config), "--json", "components", "validate"
    )
    assert code == 1, error
    payload = json.loads(output)
    assert payload["valid"] is False
    assert "no editable version" in payload["components"][0]["issues"][0]
    assert "does not exist" in payload["components"][1]["issues"][0]


@pytest.mark.parametrize(
    "replacement,message",
    [
        ('name = "core"', "Duplicate component name"),
        ('changelog = "core/CHANGELOG.md"', "Changelog.*owned"),
        ('version_files = ["core/__about__.py"]', "owned by both"),
        ('version_files = ["../outside.py"]', "escapes"),
        ("version_files = []", "nonempty"),
        ("match = [42]", "match must be"),
    ],
)
def test_bad_configuration_fails_before_writing(workspace, replacement, message):
    root, config = workspace
    key = replacement.split(" = ", 1)[0]
    original = {
        "name": 'name = "plugin"',
        "changelog": 'changelog = "plugin/CHANGELOG.md"',
        "version_files": 'version_files = ["plugin/__about__.py"]',
        "match": 'match = ["plugin/**", "shared/**"]',
    }[key]
    config.write_text(config.read_text().replace(original, replacement))
    clear_configuration_cache()
    before = (root / "core/CHANGELOG.md").read_bytes()
    code, _output, error = cli(
        "--config",
        str(config),
        "--component",
        "core",
        "add",
        "--change-type",
        "added",
        "--message",
        "Should not write",
    )
    assert code == 1
    assert re.search(message, error)
    assert (root / "core/CHANGELOG.md").read_bytes() == before


def test_inspection_reports_ambiguous_routing_without_blocking_manual_releases(
    workspace,
):
    _root, config = workspace
    config.write_text(
        config.read_text()
        .replace('match = ["core/**", "shared/**"]\n', "")
        .replace('match = ["plugin/**", "shared/**"]\n', "")
    )
    clear_configuration_cache()
    code, output, _error = cli(
        "--config", str(config), "--json", "components", "validate"
    )
    assert code == 1
    assert "multiple" in json.loads(output)["components"][0]["routing_issues"][0]
    assert release_scope(str(config), "core").tag("1.0.0") == "core-v1.0.0"


def test_changelog_only_components_do_not_require_version_bump_configuration(workspace):
    _root, config = workspace
    config.write_text(
        config.read_text()
        .replace('version_files = ["core/__about__.py"]\n', "")
        .replace('version_files = ["plugin/__about__.py"]\n', "")
    )
    clear_configuration_cache()
    code, output, error = cli(
        "--config", str(config), "--json", "components", "validate"
    )
    assert code == 0, error
    components = json.loads(output)["components"]
    assert components[0]["version_bump_ready"] is False
    assert "require explicit version_files" in components[0]["warnings"][0]
    code, _output, error = cli(
        "--config", str(config), "--component", "core", "release", "--dry-run", "--yes"
    )
    assert code == 0, error
    config.write_text("[defaults]\nbump_versions = true\n" + config.read_text())
    clear_configuration_cache()
    assert cli("--config", str(config), "components", "validate")[0] == 1
