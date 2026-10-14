"""Recovery uses isolated real git repositories; network boundaries are mocked."""

import json
import subprocess
from pathlib import Path

import pytest

import changelogmanager.llvm_diagnostics as diagnostics
from changelogmanager import recovery
from changelogmanager.changelog import Changelog
from changelogmanager.changelog_reader import ChangelogReader
from changelogmanager.release_scope import ReleaseScope
from tests.test_release_bump_and_lint_message import run_cli


def git(*args):
    return subprocess.run(
        ["git", *args], check=True, capture_output=True, text=True
    ).stdout.strip()


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    git("init", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    Path("pyproject.toml").write_text(
        '[project]\nname = "demo"\nversion = "1.0.0"\ndescription = "old"\n'
    )
    notes = Changelog(
        changelog={
            "unreleased": {
                "metadata": {
                    "version": "unreleased",
                    "url": "https://github.com/o/r/compare/v1.0.0...HEAD",
                },
                "added": ["Feature"],
            },
            "1.0.0": {
                "metadata": {
                    "version": "1.0.0",
                    "release_date": "2025-01-01",
                    "url": "https://github.com/o/r/tree/v1.0.0",
                },
                "added": ["Initial"],
            },
        }
    )
    notes.write_to_file()
    git("add", ".")
    git("commit", "-m", "initial")
    base = git("rev-parse", "HEAD")
    notes.release("1.1.0")
    notes.write_to_file()
    Path("pyproject.toml").write_text(
        Path("pyproject.toml").read_text().replace('"1.0.0"', '"1.1.0"')
    )
    git("add", ".")
    git("commit", "-m", "bump")
    bump = git("rev-parse", "HEAD")
    git("tag", "v1.1.0")
    return tmp_path, base, bump


def plan(project, **overrides):
    root, _, bump = project
    args = {
        "tag": "v1.1.0",
        "scope": ReleaseScope(root=root),
        "changelog": "CHANGELOG.md",
        "scheme": "semver",
        "bump_commit": bump,
        "restore_unreleased": True,
        "restore_versions": True,
    }
    args.update(overrides)
    return recovery.plan_recovery(**args)


def execute(value, **overrides):
    args = {
        "repository": "o/r",
        "token": None,
        "remote": "origin",
        "delete_release": False,
        "delete_local_tag": True,
        "delete_remote_tag": False,
        "commit": False,
        "push": False,
        "dry_run": False,
    }
    args.update(overrides)
    return recovery.execute_recovery(value, **args)


def test_restore_preserves_later_fixes_and_new_notes(project):
    Path("pyproject.toml").write_text(
        Path("pyproject.toml").read_text().replace('"old"', '"new"')
    )
    data = ChangelogReader().read()
    data["unreleased"] = {
        "metadata": {"version": "unreleased"},
        "fixed": ["Later fix"],
        "added": ["Feature"],
    }
    Changelog(changelog=data).write_to_file()
    git("add", ".")
    git("commit", "-m", "later fix")
    result = execute(plan(project), commit=True)
    assert 'version = "1.0.0"' in Path("pyproject.toml").read_text()
    assert 'description = "new"' in Path("pyproject.toml").read_text()
    data = ChangelogReader().read()
    assert "1.1.0" not in data
    assert data["unreleased"]["added"] == ["Feature"]
    assert data["unreleased"]["fixed"] == ["Later fix"]
    assert data["unreleased"]["metadata"]["url"].endswith("v1.0.0...HEAD")
    assert result["actions"]["commit"] == "succeeded"
    assert git("status", "--porcelain") == ""
    assert execute(result, commit=True, receipt=Path(result["receipt"])) == result


@pytest.mark.parametrize("notes,versions", [(True, False), (False, True), (True, True)])
def test_selective_cli_offline_preview(project, monkeypatch, notes, versions):
    monkeypatch.setattr(
        recovery,
        "github_release",
        lambda *a, **k: pytest.fail("network during dry-run"),
    )
    original = {
        name: Path(name).read_bytes() for name in ("CHANGELOG.md", "pyproject.toml")
    }
    args = [
        "--json",
        "release-rollback",
        "--tag",
        "v1.1.0",
        "--repository",
        "o/r",
        "--bump-commit",
        project[2],
        "--dry-run",
    ]
    args += ["--restore-unreleased"] if notes else []
    args += ["--restore-versions"] if versions else []
    result = run_cli(args)
    assert result.exit_code == 0, result.output
    data = json.loads(result.stdout)
    assert data["actions"]["github"] == "planned"
    assert {item["path"] for item in data["files"]} == (
        {"CHANGELOG.md"} if notes else set()
    ) | ({"pyproject.toml"} if versions else set())
    assert all(Path(name).read_bytes() == value for name, value in original.items())
    assert not Path(".git/kaclm").exists()


def test_conflicting_version_prevents_external_mutation(project, monkeypatch):
    Path("pyproject.toml").write_text(
        Path("pyproject.toml").read_text().replace('"1.1.0"', '"2.0.0"')
    )
    git("commit", "-am", "unrelated version")
    monkeypatch.setattr(
        recovery,
        "github_release",
        lambda *a, **k: pytest.fail("must plan before network"),
    )
    with pytest.raises(diagnostics.Error, match="conflicts"):
        execute(plan(project), delete_release=True)
    assert git("tag", "--list") == "v1.1.0"


def test_manually_restored_heading(project):
    text = Path("CHANGELOG.md").read_text()
    import re

    text = re.sub(r"## \[1.1.0\] - [0-9-]+", "## [Unreleased]", text)
    Path("CHANGELOG.md").write_text(text)
    git("commit", "-am", "manual heading restoration")
    execute(plan(project))
    assert ChangelogReader().read()["unreleased"]["added"] == ["Feature"]


def test_failure_receipt_resumes_without_repeating_local_edits(project, monkeypatch):
    value = plan(project)
    calls = []

    def api(repository, tag, token, delete_id=None):
        calls.append(delete_id)
        if delete_id:
            raise diagnostics.Error(message="permission denied")
        return {"id": 42}

    monkeypatch.setattr(recovery, "github_release", api)
    with pytest.raises(diagnostics.Error, match="resume"):
        execute(value, delete_release=True)
    receipt = Path(value["receipt"])
    saved = json.loads(receipt.read_text())
    assert saved["actions"]["files"] == "succeeded"
    assert saved["actions"]["github"] == "failed"
    assert git("tag", "--list") == "v1.1.0"
    monkeypatch.setattr(recovery, "github_release", lambda *a, **k: None)
    execute(saved, delete_release=True, receipt=receipt)
    assert saved["actions"]["github"] == "already_absent"
    assert git("tag", "--list") == ""


def test_changed_release_identity_is_not_deleted(project, monkeypatch):
    values = iter([{"id": 42}, {"id": 43}])
    monkeypatch.setattr(recovery, "github_release", lambda *a, **k: next(values))
    with pytest.raises(diagnostics.Error, match="changed since planning"):
        execute(plan(project), delete_release=True)


def test_remote_tag_absence_and_failure_are_distinct(project):
    with pytest.raises(diagnostics.Error):
        recovery.tag_sha("v1.1.0", "nonexistent-remote")
    assert recovery.tag_sha("missing") == ""


def test_real_remote_cleanup_and_push(project, tmp_path):
    remote = tmp_path / "remote.git"
    git("init", "--bare", str(remote))
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "main", "--tags")
    value = execute(plan(project), delete_remote_tag=True, commit=True, push=True)
    assert value["actions"]["push"] == "succeeded"
    assert recovery.tag_sha("v1.1.0", "origin") == ""
    assert git("ls-remote", "origin", "refs/heads/main").split()[0] == git(
        "rev-parse", "HEAD"
    )


def test_manifest_bump_and_recovery_without_explicit_sha(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    git("init", "-b", "main")
    git("config", "user.email", "test@example.invalid")
    git("config", "user.name", "Test")
    Path("pyproject.toml").write_text('[project]\nname = "demo"\nversion = "1.0.0"\n')
    Changelog(
        changelog={
            "unreleased": {"metadata": {"version": "unreleased"}, "added": ["Feature"]}
        }
    ).write_to_file()
    git("add", ".")
    git("commit", "-m", "initial")
    remote = tmp_path / "remote.git"
    git("init", "--bare", str(remote))
    git("remote", "add", "origin", str(remote))
    result = run_cli(["--json", "release-bump", "--version", "1.1.0", "--yes"])
    assert result.exit_code == 0, result.output
    manifest = json.loads(Path(recovery.manifest_name("v1.1.0")).read_text())
    assert manifest["version_files"] == ["pyproject.toml"]
    result = run_cli(
        [
            "--json",
            "release-rollback",
            "--tag",
            "v1.1.0",
            "--restore-unreleased",
            "--restore-versions",
            "--no-github",
            "--no-remote-tag",
            "--yes",
        ]
    )
    assert result.exit_code == 0, result.output
    assert 'version = "1.0.0"' in Path("pyproject.toml").read_text()


def test_only_version_changes_can_be_inverted():
    with pytest.raises(diagnostics.Error, match="Ambiguous"):
        recovery.inverse_versions(
            'version = "1"\nx = 1\n',
            'version = "2"\nx = 2\n',
            'version = "2"\nx = 2\n',
            "file",
        )


def test_preview_rejects_dirty_files(project):
    Path("pyproject.toml").write_text("local edit")
    with pytest.raises(diagnostics.Error, match="clean working tree"):
        plan(project)


def test_resume_cli_uses_receipt_tag_after_deletion(project):
    value = execute(plan(project))
    result = run_cli(
        [
            "--json",
            "release-rollback",
            "--resume",
            value["receipt"],
            "--repository",
            "o/r",
            "--no-github",
            "--no-remote-tag",
            "--yes",
        ]
    )
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["tag"] == "v1.1.0"


def test_publication_check_warns_without_blocking_cleanup(project, monkeypatch):
    monkeypatch.setattr(recovery, "pypi_published", lambda package, version: True)
    value = execute(plan(project), check_pypi="demo")
    assert "NEW version" in value["publication_check"]
    assert value["actions"]["local_tag"] == "succeeded"


def test_publication_failure_does_not_write_files(project, monkeypatch):
    original = Path("pyproject.toml").read_bytes()

    def unavailable(*args):
        raise diagnostics.Error(message="index unavailable")

    monkeypatch.setattr(recovery, "pypi_published", unavailable)
    with pytest.raises(diagnostics.Error, match="index unavailable"):
        execute(plan(project), check_pypi="demo")
    assert Path("pyproject.toml").read_bytes() == original
    assert git("tag", "--list") == "v1.1.0"


def test_custom_component_prefix_and_version_ownership(project):
    root, _, _ = project
    Path("other.py").write_text('__version__ = "9.0.0"\n')
    git("add", ".")
    git("commit", "-m", "another component")
    scope = ReleaseScope(
        component="lib",
        root=root,
        version_files=(root / "pyproject.toml",),
        tag_template="lib-{version}",
        monorepo=True,
    )
    value = plan(project, tag="lib-1.1.0", scope=scope)
    execute(value, delete_local_tag=False)
    assert Path("other.py").read_text() == '__version__ = "9.0.0"\n'


def test_changed_remote_tag_is_not_deleted(project, monkeypatch):
    real = recovery.tag_sha
    values = iter(["a" * 40, "b" * 40])
    monkeypatch.setattr(
        recovery,
        "tag_sha",
        lambda tag, remote=None: next(values) if remote else real(tag),
    )
    with pytest.raises(diagnostics.Error, match="remote_tag changed"):
        execute(plan(project), delete_remote_tag=True)
    assert git("tag", "--list") == "v1.1.0"


def test_resume_refuses_edited_recovered_file(project):
    value = execute(plan(project))
    Path("pyproject.toml").write_text(value["files"][1]["before"])
    with pytest.raises(diagnostics.Error, match="file changed"):
        execute(value, receipt=Path(value["receipt"]))


@pytest.mark.parametrize("name", ["Cargo.toml", "Cargo.lock", "uv.lock", "version.py"])
def test_version_only_inverse_keeps_neighbor_changes(name):
    key = "__version__" if name.endswith(".py") else "version"
    before = f'{key} = "1.0.0"\nother = "old"\n'
    after = before.replace("1.0.0", "1.1.0-rc.1")
    current = after.replace('"old"', '"new"')
    assert recovery.inverse_versions(before, after, current, name) == before.replace(
        '"old"', '"new"'
    )


def test_ambiguous_lock_versions_are_not_guessed():
    before = 'version = "1.0.0"\n\nversion = "1.1.0"\n'
    after = before.replace('"1.0.0"', '"1.1.0"')
    with pytest.raises(diagnostics.Error, match="conflicts"):
        recovery.inverse_versions(before, after, after, "uv.lock")


def test_git_ref_prefix_is_not_an_exact_tag(project):
    git("tag", "nested/child")
    assert recovery.tag_sha("nested") == ""


def test_manifest_can_record_another_attempt(project):
    root, base, bump = project
    args = {
        "tag": "v1.1.0",
        "version": "1.1.0",
        "base_sha": base,
        "changelog": "CHANGELOG.md",
        "files": ["pyproject.toml"],
        "scope": ReleaseScope(root=root),
        "repository": "o/r",
    }
    path = recovery.record_manifest(**args)
    args["base_sha"] = bump
    recovery.record_manifest(**args)
    assert json.loads(path.read_text())["base_sha"] == bump
