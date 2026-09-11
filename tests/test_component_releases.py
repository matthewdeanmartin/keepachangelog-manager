"""Independent component releases share a Git repository, not version ownership."""

import io
import json
import subprocess
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

import pytest

from changelogmanager.cli import main
from changelogmanager.cli.loaders import load_changelog
from changelogmanager.config import clear_configuration_cache
from changelogmanager.github import GitHub
from changelogmanager.gitlab import GitLab
from changelogmanager.release_scope import release_scope

CHANGELOG = "# Changelog\n\n## [Unreleased]\n### Fixed\n- Repair parsing.\n\n## [0.0.1] - 2026-01-01\n### Added\n- Initial version.\n"


def cli(*args):
    stdout, stderr = io.StringIO(), io.StringIO()
    with redirect_stdout(stdout), redirect_stderr(stderr):
        try:
            code = main(list(args)) or 0
        except SystemExit as error:
            code = error.code
    return code, stdout.getvalue(), stderr.getvalue()


def project(root):
    for component in ("core", "plugin"):
        folder = root / component
        folder.mkdir(parents=True)
        (folder / "pyproject.toml").write_text(
            '[project]\nname = "' + component + '"\nversion = "0.0.1"\n',
            encoding="utf-8",
        )
        (folder / "__about__.py").write_text(
            '__version__ = "0.0.1"\n', encoding="utf-8"
        )
        (folder / "CHANGELOG.md").write_text(CHANGELOG, encoding="utf-8")
    config = root / "changelogmanager.toml"
    config.write_text(
        """[versioning]
scheme = "semver"
[[components]]
name = "core"
changelog = "core/CHANGELOG.md"
version_files = ["core/pyproject.toml", "core/__about__.py"]
tag_template = "v{version}"
[[components]]
name = "plugin"
changelog = "plugin/CHANGELOG.md"
version_files = ["plugin/pyproject.toml", "plugin/__about__.py"]
tag_template = "plugin-v{version}"
""",
        encoding="utf-8",
    )
    return config


@pytest.mark.parametrize(
    "component,tag", [("core", "v0.1.0"), ("plugin", "plugin-v0.1.0")]
)
def test_release_changes_only_selected_files(tmp_path, component, tag):
    config = project(tmp_path)
    sibling = "plugin" if component == "core" else "core"
    before = {path: path.read_bytes() for path in (tmp_path / sibling).iterdir()}
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        component,
        "--json",
        "release",
        "--bump-versions",
        "--override-version",
        tag,
        "--yes",
    )
    assert code == 0, error
    assert 'version = "0.1.0"' in (tmp_path / component / "pyproject.toml").read_text()
    assert (
        '__version__ = "0.1.0"' in (tmp_path / component / "__about__.py").read_text()
    )
    assert "## [0.1.0]" in (tmp_path / component / "CHANGELOG.md").read_text()
    assert all(path.read_bytes() == content for path, content in before.items())


def test_preview_namespaces_and_targets_match_actual_release(tmp_path):
    config = project(tmp_path)
    before = {path: path.read_bytes() for path in tmp_path.rglob("*") if path.is_file()}
    outputs = []
    for component, tag in [("core", "v0.1.0"), ("plugin", "plugin-v0.1.0")]:
        code, output, error = cli(
            "--config",
            str(config),
            "--component",
            component,
            "--json",
            "release-bump",
            "--version",
            tag,
            "--dry-run",
        )
        assert code == 0, error
        data = json.loads(output)
        assert data["tag_name"] == tag
        assert {Path(path).parent.name for path in data["bump_candidates"]} == {
            component
        }
        outputs.append(data["branch"])
    assert len(set(outputs)) == 2
    assert all(path.read_bytes() == content for path, content in before.items())


def test_github_refresh_preserves_other_drafts(tmp_path, monkeypatch):
    config = project(tmp_path)
    calls = []
    monkeypatch.setattr(
        GitHub,
        "get_releases",
        lambda self: [
            {"id": 1, "draft": True, "tag_name": "v0.0.2"},
            {
                "id": 2,
                "draft": True,
                "tag_name": "plugin-v0.0.2",
                "body": "Human notes",
            },
            {"id": 3, "draft": False, "tag_name": "plugin-v0.0.1"},
        ],
    )

    def request(self, method, api, data=None):
        calls.append((api, data))
        return {"id": 2, "tag_name": "plugin-v0.0.2", "draft": True} if data else None

    monkeypatch.setattr(GitHub, "github_request", request)
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "plugin",
        "--json",
        "github-release",
        "--repository",
        "test/repo",
        "--github-token",
        "fake",
    )
    assert code == 0, error
    assert calls[0][0] == "releases/2"
    assert calls[0][1]["body"].startswith("Human notes")
    assert all(data is not None for api, data in calls)
    assert not any(api in ("releases/1", "releases/3") for api, data in calls)
    assert json.loads(output)["tag_name"] == "plugin-v0.0.2"


def test_gitlab_uses_component_tag(tmp_path, monkeypatch):
    config = project(tmp_path)
    calls = []
    monkeypatch.setattr(GitLab, "get_release", lambda self, tag: None)

    def request(self, method, api, data=None):
        calls.append(data)
        return {"tag_name": data["tag_name"]}

    monkeypatch.setattr(GitLab, "gitlab_request", request)
    from changelogmanager.services import gitlab_release

    gitlab_release(
        load_changelog(str(config), "plugin", None),
        project="test/repo",
        token="fake",
        gitlab_url="https://gitlab.example",
        ref="main",
        scope=release_scope(str(config), "plugin"),
    )
    assert calls[0]["tag_name"] == "plugin-v0.0.2"


@pytest.mark.parametrize(
    "replacement,message",
    [
        ('version_files = ["../outside.py"]', "escapes"),
        ('version_files = ["core/__about__.py"]', "owned"),
        ("version_files = []", "nonempty"),
    ],
)
def test_invalid_ownership_is_rejected(tmp_path, replacement, message):
    config = project(tmp_path)
    config.write_text(
        config.read_text().replace(
            'version_files = ["plugin/pyproject.toml", "plugin/__about__.py"]',
            replacement,
        )
    )
    with pytest.raises(Exception, match=message):
        release_scope(str(config), "plugin")


def test_colliding_templates_and_wrong_component_tag_rejected(tmp_path):
    config = project(tmp_path)
    with pytest.raises(Exception, match="does not match"):
        release_scope(str(config), "core").version("plugin-v0.1.0")
    config.write_text(config.read_text().replace('"plugin-v{version}"', '"v{version}"'))
    clear_configuration_cache()
    with pytest.raises(Exception, match="colliding"):
        release_scope(str(config), "plugin")


def test_missing_version_file_fails_before_changelog_write(tmp_path):
    config = project(tmp_path)
    (tmp_path / "plugin/__about__.py").unlink()
    before = (tmp_path / "plugin/CHANGELOG.md").read_bytes()
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "plugin",
        "release",
        "--bump-versions",
        "--yes",
    )
    assert code != 0
    assert (tmp_path / "plugin/CHANGELOG.md").read_bytes() == before


def test_real_release_branch_stages_only_selected_component(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = project(repo)

    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=repo, check=True, capture_output=True, text=True
        ).stdout

    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    git("add", ".")
    git("commit", "-m", "initial")
    remote = tmp_path / "remote.git"
    git("init", "--bare", str(remote))
    git("remote", "add", "origin", str(remote))
    monkeypatch.chdir(repo)
    # Shell redirection can create an untracked output file before the command starts.
    (repo / "release-result.json").write_text("")
    outputs = repo / "actions-output"
    outputs.write_text("")
    monkeypatch.setenv("GITHUB_OUTPUT", str(outputs))
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "plugin",
        "--json",
        "release-bump",
        "--version",
        "plugin-v0.1.0",
        "--yes",
        "--github-output",
    )
    assert code == 0, error
    assert set(git("diff", "--name-only", "main", "HEAD").splitlines()) == {
        "plugin/CHANGELOG.md",
        "plugin/pyproject.toml",
        "plugin/__about__.py",
    }
    result = json.loads(output)
    assert result["commit_sha"] == git("rev-parse", "HEAD").strip()
    assert {
        Path(value).relative_to(repo).as_posix() for value in result["changed_files"]
    } == {
        "plugin/CHANGELOG.md",
        "plugin/pyproject.toml",
        "plugin/__about__.py",
    }
    assert git("ls-remote", "--heads", "origin", "release/plugin/bump-0.1.0")

    assert f"commit_sha={result['commit_sha']}" in outputs.read_text()
    assert "branch=release/plugin/bump-0.1.0" in outputs.read_text()


def test_default_tags_separate_components_at_same_version(tmp_path):
    config = project(tmp_path)
    config.write_text(
        "\n".join(
            line
            for line in config.read_text().splitlines()
            if not line.startswith("tag_template")
        )
    )
    assert release_scope(str(config), "core").tag("0.1.0") == "core-v0.1.0"
    assert release_scope(str(config), "plugin").tag("0.1.0") == "plugin-v0.1.0"


def test_monorepo_without_explicit_files_refuses_recursive_bump(tmp_path):
    config = project(tmp_path)
    config.write_text(
        "\n".join(
            line
            for line in config.read_text().splitlines()
            if not line.startswith("version_files")
        )
    )
    before = (tmp_path / "plugin/CHANGELOG.md").read_bytes()
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "plugin",
        "release",
        "--bump-versions",
        "--yes",
    )
    assert code != 0
    assert (tmp_path / "plugin/CHANGELOG.md").read_bytes() == before


def test_dirty_tracked_file_prevents_release_commit(tmp_path, monkeypatch):
    config = project(tmp_path)
    monkeypatch.chdir(tmp_path)

    def git(*args):
        return subprocess.run(
            ["git", *args], check=True, capture_output=True, text=True
        )

    git("init", "-b", "main")
    git("config", "user.name", "Test")
    git("config", "user.email", "test@example.invalid")
    git("add", ".")
    git("commit", "-m", "initial")
    (tmp_path / "core/__about__.py").write_text("# unrelated edit\n")
    before = (tmp_path / "plugin/CHANGELOG.md").read_bytes()
    code, output, error = cli(
        "--config",
        str(config),
        "--component",
        "plugin",
        "release-bump",
        "--version",
        "0.1.0",
        "--yes",
    )
    assert code != 0
    assert (tmp_path / "plugin/CHANGELOG.md").read_bytes() == before
    assert not git("diff", "--cached", "--name-only").stdout.strip()
