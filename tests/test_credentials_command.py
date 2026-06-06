# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tests for the ``credentials`` CLI subcommand."""

import argparse
import types

import pytest

import changelogmanager.llvm_diagnostics as logging
from changelogmanager.cli.commands import command_credentials
from changelogmanager.cli.context import CliContext


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_ctx() -> CliContext:
    return CliContext(
        changelog=None,  # type: ignore[arg-type]
        json_output=False,
        quiet=False,
    )


def _make_keyring_mod(mocker: pytest.MonkeyPatch) -> types.ModuleType:
    """Returns a fake keyring module with a simple in-memory store."""
    store: dict[tuple[str, str], str] = {}

    mod = types.ModuleType("keyring")

    def get_password(service: str, key: str) -> str | None:
        return store.get((service, key))

    def set_password(service: str, key: str, value: str) -> None:
        store[(service, key)] = value

    def delete_password(service: str, key: str) -> None:
        store.pop((service, key), None)

    errors_mod = types.ModuleType("keyring.errors")

    class PasswordDeleteError(Exception):
        pass

    errors_mod.PasswordDeleteError = PasswordDeleteError  # type: ignore[attr-defined]

    mod.get_password = get_password  # type: ignore[attr-defined]
    mod.set_password = set_password  # type: ignore[attr-defined]
    mod.delete_password = delete_password  # type: ignore[attr-defined]
    mod.errors = errors_mod  # type: ignore[attr-defined]

    mocker.patch.dict("sys.modules", {"keyring": mod, "keyring.errors": errors_mod})
    return mod


# ---------------------------------------------------------------------------
# credentials check
# ---------------------------------------------------------------------------


def test_credentials_check_no_tokens(mocker: pytest.MonkeyPatch, capsys: pytest.CaptureFixture) -> None:
    _make_keyring_mod(mocker)
    args = argparse.Namespace(credentials_command="check")
    ctx = _make_ctx()
    command_credentials(args, ctx)
    out = capsys.readouterr().out
    assert "not set" in out
    payload = ctx.json_payload.get("tokens", [])
    assert any(t["service"] == "github" and t["status"] == "not set" for t in payload)
    assert any(t["service"] == "gitlab" and t["status"] == "not set" for t in payload)


def test_credentials_check_github_configured(
    mocker: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    kr = _make_keyring_mod(mocker)
    kr.set_password("keepachangelog-manager", "github_token", "ghp_abc")
    args = argparse.Namespace(credentials_command="check")
    ctx = _make_ctx()
    command_credentials(args, ctx)
    out = capsys.readouterr().out
    assert "GitHub token: configured" in out
    assert "GitLab token: not set" in out


# ---------------------------------------------------------------------------
# credentials set
# ---------------------------------------------------------------------------


def test_credentials_set_github_stores_token(
    mocker: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    kr = _make_keyring_mod(mocker)
    mocker.patch("getpass.getpass", return_value="my-secret-token")
    args = argparse.Namespace(credentials_command="set", service="github")
    ctx = _make_ctx()
    command_credentials(args, ctx)
    assert kr.get_password("keepachangelog-manager", "github_token") == "my-secret-token"
    out = capsys.readouterr().out
    assert "stored" in out.lower()


def test_credentials_set_gitlab_stores_token(
    mocker: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    kr = _make_keyring_mod(mocker)
    mocker.patch("getpass.getpass", return_value="glpat-xyz")
    args = argparse.Namespace(credentials_command="set", service="gitlab")
    ctx = _make_ctx()
    command_credentials(args, ctx)
    assert kr.get_password("keepachangelog-manager", "gitlab_token") == "glpat-xyz"


def test_credentials_set_strips_whitespace(
    mocker: pytest.MonkeyPatch,
) -> None:
    kr = _make_keyring_mod(mocker)
    mocker.patch("getpass.getpass", return_value="  token-with-spaces  ")
    args = argparse.Namespace(credentials_command="set", service="github")
    ctx = _make_ctx()
    command_credentials(args, ctx)
    assert kr.get_password("keepachangelog-manager", "github_token") == "token-with-spaces"


def test_credentials_set_rejects_empty_token(mocker: pytest.MonkeyPatch) -> None:
    _make_keyring_mod(mocker)
    mocker.patch("getpass.getpass", return_value="   ")
    args = argparse.Namespace(credentials_command="set", service="github")
    ctx = _make_ctx()
    with pytest.raises(logging.Error, match="empty"):
        command_credentials(args, ctx)


# ---------------------------------------------------------------------------
# credentials clear
# ---------------------------------------------------------------------------


def test_credentials_clear_existing_token(
    mocker: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    kr = _make_keyring_mod(mocker)
    kr.set_password("keepachangelog-manager", "github_token", "ghp_abc")
    args = argparse.Namespace(credentials_command="clear", service="github")
    ctx = _make_ctx()
    command_credentials(args, ctx)
    assert kr.get_password("keepachangelog-manager", "github_token") is None
    out = capsys.readouterr().out
    assert "removed" in out.lower()


def test_credentials_clear_nonexistent_token(
    mocker: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _make_keyring_mod(mocker)
    args = argparse.Namespace(credentials_command="clear", service="github")
    ctx = _make_ctx()
    command_credentials(args, ctx)
    out = capsys.readouterr().out
    assert "not set" in out.lower()


def test_credentials_clear_gitlab(
    mocker: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    kr = _make_keyring_mod(mocker)
    kr.set_password("keepachangelog-manager", "gitlab_token", "glpat-tok")
    args = argparse.Namespace(credentials_command="clear", service="gitlab")
    ctx = _make_ctx()
    command_credentials(args, ctx)
    assert kr.get_password("keepachangelog-manager", "gitlab_token") is None
    out = capsys.readouterr().out
    assert "removed" in out.lower()


# ---------------------------------------------------------------------------
# parser integration — subparser wiring
# ---------------------------------------------------------------------------


def test_parser_credentials_set_parses() -> None:
    from changelogmanager.cli.parser import build_parser

    parser = build_parser()
    args = parser.parse_args(["credentials", "set", "github"])
    assert args.credentials_command == "set"
    assert args.service == "github"


def test_parser_credentials_clear_parses() -> None:
    from changelogmanager.cli.parser import build_parser

    parser = build_parser()
    args = parser.parse_args(["credentials", "clear", "gitlab"])
    assert args.credentials_command == "clear"
    assert args.service == "gitlab"


def test_parser_credentials_check_parses() -> None:
    from changelogmanager.cli.parser import build_parser

    parser = build_parser()
    args = parser.parse_args(["credentials", "check"])
    assert args.credentials_command == "check"
    assert not hasattr(args, "service")
