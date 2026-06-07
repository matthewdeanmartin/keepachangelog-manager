
import subprocess

import pytest

from changelogmanager.backfill import git_executable
from changelogmanager.message_lint import _git, resolve_unpushed_range


def test_git_helper_calls_subprocess_correctly(mocker):
    # Mock subprocess.run to avoid actual git calls and to check parameters
    mock_run = mocker.patch("subprocess.run")
    mock_run.return_value = subprocess.CompletedProcess(args=[], returncode=0, stdout="true", stderr="")

    args = ["rev-parse", "--is-inside-work-tree"]
    cwd = "/some/path"

    result = _git(args, cwd=cwd)

    mock_run.assert_called_once_with(
        [git_executable(), *args],
        capture_output=True,
        text=True,
        cwd=cwd,
        check=False
    )
    assert result.returncode == 0
    assert result.stdout == "true"

def test_resolve_unpushed_range_handles_no_upstream(mocker):
    # Mock _git to simulate no upstream configured
    def mock_git_impl(args, cwd=None):
        if "--is-inside-work-tree" in args:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="true")
        if "@{push}" in args or "@{upstream}" in args:
            return subprocess.CompletedProcess(args=args, returncode=128, stdout="", stderr="error")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")

    mocker.patch("changelogmanager.message_lint._git", side_effect=mock_git_impl)

    unpushed = resolve_unpushed_range()
    assert unpushed.revision == "HEAD"
    assert unpushed.has_upstream is False
    assert unpushed.upstream is None

def test_resolve_unpushed_range_handles_upstream(mocker):
    # Mock _git to simulate upstream exists
    def mock_git_impl(args, cwd=None):
        if "--is-inside-work-tree" in args:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="true")
        if "@{push}" in args:
            return subprocess.CompletedProcess(args=args, returncode=0, stdout="resolved_push\n")
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="")

    mocker.patch("changelogmanager.message_lint._git", side_effect=mock_git_impl)

    unpushed = resolve_unpushed_range()
    assert unpushed.revision == "@{push}..HEAD"
    assert unpushed.has_upstream is True
    assert unpushed.upstream == "@{push}"
