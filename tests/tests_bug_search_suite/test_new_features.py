"""Coverage for the new edit/remove/from-commits/--fix/etc. features."""

from __future__ import annotations

import io
import json
import subprocess
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from changelogmanager.cli import classify_commit, main

VALID_CHANGELOG = """\
# Changelog
All notable changes follow Keep a Changelog and Semantic Versioning.

## [Unreleased]
### Added
- First feature
- Second feature

### Fixed
- A bug

## [1.0.0] - 2024-01-01
### Added
- Initial release
"""


def _write(path: Path, body: str = VALID_CHANGELOG) -> str:
    p = path / "CHANGELOG.md"
    p.write_text(body, encoding="utf-8")
    return str(p)


def _capture(argv: list[str]) -> tuple[int, str]:
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(argv)
    return rc, buf.getvalue()


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


class TestRemove:
    def test_remove_entry(self, tmp_path):
        p = _write(tmp_path)
        rc = main(["--input-file", p, "remove", "-t", "added", "-i", "0"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "First feature" not in text
        assert "Second feature" in text

    def test_remove_dry_run(self, tmp_path):
        p = _write(tmp_path)
        original = Path(p).read_text(encoding="utf-8")
        rc = main(["--input-file", p, "remove", "-t", "added", "-i", "0", "--dry-run"])
        assert rc == 0
        assert Path(p).read_text(encoding="utf-8") == original

    def test_remove_invalid_index(self, tmp_path):
        p = _write(tmp_path)
        rc = main(["--input-file", p, "remove", "-t", "added", "-i", "99"])
        assert rc == 1

    def test_remove_list(self, tmp_path):
        p = _write(tmp_path)
        rc, out = _capture(["--input-file", p, "remove", "--list"])
        assert rc == 0
        assert "First feature" in out
        assert "[added] 0" in out


# ---------------------------------------------------------------------------
# edit
# ---------------------------------------------------------------------------


class TestEdit:
    def test_edit_message(self, tmp_path):
        p = _write(tmp_path)
        rc = main(
            [
                "--input-file",
                p,
                "edit",
                "-t",
                "added",
                "-i",
                "0",
                "-m",
                "Renamed feature",
            ]
        )
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "Renamed feature" in text
        assert "First feature" not in text

    def test_edit_change_type(self, tmp_path):
        p = _write(tmp_path)
        rc = main(
            [
                "--input-file",
                p,
                "edit",
                "-t",
                "added",
                "-i",
                "0",
                "--new-change-type",
                "fixed",
            ]
        )
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        # Was under Added, should now appear under Fixed
        added_block = text.split("### Added")[1].split("##")[0]
        assert "First feature" not in added_block

    def test_edit_requires_change(self, tmp_path):
        p = _write(tmp_path)
        rc = main(["--input-file", p, "edit", "-t", "added", "-i", "0"])
        assert rc == 1


# ---------------------------------------------------------------------------
# release --yes
# ---------------------------------------------------------------------------


class TestReleaseYes:
    def test_release_with_yes(self, tmp_path):
        p = _write(tmp_path)
        rc = main(["--input-file", p, "release", "--yes"])
        assert rc == 0

    def test_release_without_yes_in_non_interactive_fails(self, tmp_path):
        p = _write(tmp_path)
        rc = main(["--input-file", p, "release"])
        assert rc == 1


# ---------------------------------------------------------------------------
# validate --fix
# ---------------------------------------------------------------------------

UNORDERED_CHANGELOG = """\
# Changelog

## [Unreleased]
### Added
- New feature
- New feature

## [1.0.0] - 2024-01-01
### Added
- Initial

## [2.0.0] - 2024-06-01
### Added
- Big change
"""


class TestValidateFix:
    def test_fix_reorders_versions(self, tmp_path):
        p = tmp_path / "CHANGELOG.md"
        p.write_text(UNORDERED_CHANGELOG, encoding="utf-8")
        rc = main(["--input-file", str(p), "validate", "--fix"])
        assert rc == 0
        text = p.read_text(encoding="utf-8")
        # 2.0.0 should appear before 1.0.0
        assert text.index("[2.0.0]") < text.index("[1.0.0]")
        # Duplicate should be removed
        assert text.count("New feature") == 1

    def test_fix_dry_run_does_not_write(self, tmp_path):
        p = tmp_path / "CHANGELOG.md"
        p.write_text(UNORDERED_CHANGELOG, encoding="utf-8")
        original = p.read_text(encoding="utf-8")
        rc = main(["--input-file", str(p), "validate", "--fix", "--dry-run"])
        assert rc == 0
        assert p.read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# --quiet / --json
# ---------------------------------------------------------------------------


class TestQuietJson:
    def test_quiet_suppresses_text_output(self, tmp_path):
        p = _write(tmp_path)
        rc, out = _capture(["--quiet", "--input-file", p, "version"])
        assert rc == 0
        assert out == ""

    def test_json_emits_structured_output(self, tmp_path):
        p = _write(tmp_path)
        rc, out = _capture(["--json", "--input-file", p, "version"])
        assert rc == 0
        payload = json.loads(out)
        assert payload["version"] == "1.0.0"
        assert payload["reference"] == "current"


# ---------------------------------------------------------------------------
# to-yaml / to-html
# ---------------------------------------------------------------------------


class TestExports:
    def test_to_yaml_writes_file(self, tmp_path):
        p = _write(tmp_path)
        out = tmp_path / "out.yaml"
        rc = main(["--input-file", p, "to-yaml", "--file-name", str(out)])
        assert rc == 0
        body = out.read_text(encoding="utf-8")
        assert "First feature" in body

    def test_to_html_writes_file(self, tmp_path):
        p = _write(tmp_path)
        out = tmp_path / "out.html"
        rc = main(["--input-file", p, "to-html", "--file-name", str(out)])
        assert rc == 0
        body = out.read_text(encoding="utf-8")
        assert "<h1>Changelog</h1>" in body
        assert "First feature" in body
        # html.escape ensures < and > don't leak from changelog content
        assert "<script>" not in body or "&lt;script&gt;" in body

    def test_to_html_escapes_content(self, tmp_path):
        body = """\
# Changelog

## [Unreleased]
### Added
- <script>alert(1)</script>
"""
        p = tmp_path / "CHANGELOG.md"
        p.write_text(body, encoding="utf-8")
        out = tmp_path / "out.html"
        rc = main(["--input-file", str(p), "to-html", "--file-name", str(out)])
        assert rc == 0
        rendered = out.read_text(encoding="utf-8")
        assert "<script>alert(1)</script>" not in rendered
        assert "&lt;script&gt;" in rendered


# ---------------------------------------------------------------------------
# github-release env-var fallback
# ---------------------------------------------------------------------------


class TestGitHubTokenFallback:
    def test_token_from_env(self, tmp_path, monkeypatch):
        p = _write(tmp_path)
        monkeypatch.setenv("GITHUB_TOKEN", "env-token")
        # Dry-run avoids real API calls.
        rc = main(
            ["--input-file", p, "github-release", "-r", "owner/repo", "--dry-run"]
        )
        assert rc == 0

    def test_missing_token_errors(self, tmp_path, monkeypatch):
        p = _write(tmp_path)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        rc = main(["--input-file", p, "github-release", "-r", "owner/repo"])
        assert rc == 1


# ---------------------------------------------------------------------------
# Conventional commit classifier
# ---------------------------------------------------------------------------


class TestClassifyCommit:
    def test_feat(self):
        assert classify_commit("feat: thing") == ("added", "thing")

    def test_fix(self):
        assert classify_commit("fix: bug") == ("fixed", "bug")

    def test_breaking(self):
        assert classify_commit("feat!: drop API") == ("removed", "drop API")

    def test_scope(self):
        assert classify_commit("fix(parser): nasty") == ("fixed", "nasty")

    def test_unknown_returns_none(self):
        assert classify_commit("just a sentence") is None


# ---------------------------------------------------------------------------
# from-commits
# ---------------------------------------------------------------------------


@pytest.fixture
def git_repo(tmp_path, monkeypatch):
    """A tiny git repo with a couple of commits."""

    monkeypatch.chdir(tmp_path)
    subprocess.run(["git", "init", "-q"], check=True, cwd=tmp_path)
    subprocess.run(["git", "config", "user.email", "t@t"], check=True, cwd=tmp_path)
    subprocess.run(["git", "config", "user.name", "t"], check=True, cwd=tmp_path)
    subprocess.run(
        ["git", "config", "commit.gpgsign", "false"], check=True, cwd=tmp_path
    )
    (tmp_path / "x").write_text("a", encoding="utf-8")
    subprocess.run(["git", "add", "x"], check=True, cwd=tmp_path)
    subprocess.run(
        ["git", "commit", "-q", "-m", "feat: hello"], check=True, cwd=tmp_path
    )
    (tmp_path / "x").write_text("b", encoding="utf-8")
    subprocess.run(
        ["git", "commit", "-q", "-am", "fix: oops"], check=True, cwd=tmp_path
    )
    return tmp_path


class TestFromCommits:
    def test_seeds_unreleased(self, git_repo):
        p = _write(git_repo)
        rc = main(["--input-file", p, "from-commits", "--all-history"])
        assert rc == 0
        text = Path(p).read_text(encoding="utf-8")
        assert "hello" in text
        assert "oops" in text

    def test_dry_run_does_not_write(self, git_repo):
        p = _write(git_repo)
        original = Path(p).read_text(encoding="utf-8")
        rc = main(["--input-file", p, "from-commits", "--all-history", "--dry-run"])
        assert rc == 0
        assert Path(p).read_text(encoding="utf-8") == original


# ---------------------------------------------------------------------------
# Auto-detect config + --all
# ---------------------------------------------------------------------------


class TestAutoDetectAndAll:
    def test_autodetect_yaml(self, tmp_path, monkeypatch):
        (tmp_path / ".changelogmanager.yml").write_text(
            "project:\n  components:\n    - name: api\n      changelog: API.md\n",
            encoding="utf-8",
        )
        (tmp_path / "API.md").write_text(
            "# Changelog\n\n## [1.0.0] - 2024-01-01\n### Added\n- Things\n",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        rc, out = _capture(["--component", "api", "version"])
        assert rc == 0
        assert "1.0.0" in out

    def test_validate_all(self, tmp_path, monkeypatch):
        (tmp_path / "config.yml").write_text(
            "project:\n"
            "  components:\n"
            "    - name: api\n"
            "      changelog: api/CHANGELOG.md\n"
            "    - name: web\n"
            "      changelog: web/CHANGELOG.md\n",
            encoding="utf-8",
        )
        for name in ("api", "web"):
            (tmp_path / name).mkdir()
            (tmp_path / name / "CHANGELOG.md").write_text(
                "# Changelog\n\n## [1.0.0] - 2024-01-01\n### Added\n- Stuff\n",
                encoding="utf-8",
            )
        monkeypatch.chdir(tmp_path)
        rc = main(["--config", "config.yml", "validate", "--all"])
        assert rc == 0

    def test_validate_all_requires_config(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        rc = main(["validate", "--all"])
        assert rc == 1
