# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Tests for changelogmanager.credentials."""

import pytest

from changelogmanager.credentials import check_token, clear_token, get_token, set_token


def test_get_token_prefers_cli_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    result = get_token("github_token", cli_value="cli-token", env_var="GITHUB_TOKEN")
    assert result == "cli-token"


def test_get_token_falls_back_to_keyring(
    monkeypatch: pytest.MonkeyPatch, mocker: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    # patch keyring inside the module
    mocker.patch("builtins.__import__", wraps=__import__)
    keyring_mod = mocker.MagicMock()
    keyring_mod.get_password.return_value = "keyring-token"
    mocker.patch.dict("sys.modules", {"keyring": keyring_mod})

    result = get_token("github_token", cli_value=None, env_var="GITHUB_TOKEN")
    assert result == "keyring-token"
    keyring_mod.get_password.assert_called_once_with(
        "keepachangelog-manager", "github_token"
    )


def test_get_token_falls_back_to_env_when_keyring_empty(
    monkeypatch: pytest.MonkeyPatch, mocker: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "env-token")
    keyring_mod = mocker.MagicMock()
    keyring_mod.get_password.return_value = None
    mocker.patch.dict("sys.modules", {"keyring": keyring_mod})

    result = get_token("github_token", cli_value=None, env_var="GITHUB_TOKEN")
    assert result == "env-token"


def test_get_token_returns_none_when_nothing_configured(
    monkeypatch: pytest.MonkeyPatch, mocker: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    keyring_mod = mocker.MagicMock()
    keyring_mod.get_password.return_value = None
    mocker.patch.dict("sys.modules", {"keyring": keyring_mod})

    result = get_token("github_token", cli_value=None, env_var="GITHUB_TOKEN")
    assert result is None


def test_get_token_strips_whitespace_from_env(
    monkeypatch: pytest.MonkeyPatch, mocker: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "  ")
    keyring_mod = mocker.MagicMock()
    keyring_mod.get_password.return_value = None
    mocker.patch.dict("sys.modules", {"keyring": keyring_mod})

    result = get_token("github_token", cli_value=None, env_var="GITHUB_TOKEN")
    assert result is None


def test_set_token(mocker: pytest.MonkeyPatch) -> None:
    keyring_mod = mocker.MagicMock()
    mocker.patch.dict("sys.modules", {"keyring": keyring_mod})

    set_token("github_token", "my-secret")
    keyring_mod.set_password.assert_called_once_with(
        "keepachangelog-manager", "github_token", "my-secret"
    )


def test_clear_token_returns_true_when_existed(mocker: pytest.MonkeyPatch) -> None:
    keyring_mod = mocker.MagicMock()
    keyring_mod.get_password.return_value = "old-token"
    keyring_mod.errors = mocker.MagicMock()
    keyring_mod.errors.PasswordDeleteError = Exception
    mocker.patch.dict(
        "sys.modules", {"keyring": keyring_mod, "keyring.errors": keyring_mod.errors}
    )

    assert clear_token("github_token") is True
    keyring_mod.delete_password.assert_called_once_with(
        "keepachangelog-manager", "github_token"
    )


def test_clear_token_returns_false_when_not_present(mocker: pytest.MonkeyPatch) -> None:
    keyring_mod = mocker.MagicMock()
    keyring_mod.get_password.return_value = None
    keyring_mod.errors = mocker.MagicMock()
    keyring_mod.errors.PasswordDeleteError = Exception
    mocker.patch.dict(
        "sys.modules", {"keyring": keyring_mod, "keyring.errors": keyring_mod.errors}
    )

    assert clear_token("github_token") is False
    keyring_mod.delete_password.assert_not_called()


def test_check_token_true_when_present(mocker: pytest.MonkeyPatch) -> None:
    keyring_mod = mocker.MagicMock()
    keyring_mod.get_password.return_value = "some-token"
    mocker.patch.dict("sys.modules", {"keyring": keyring_mod})

    assert check_token("github_token") is True


def test_check_token_false_when_absent(mocker: pytest.MonkeyPatch) -> None:
    keyring_mod = mocker.MagicMock()
    keyring_mod.get_password.return_value = None
    mocker.patch.dict("sys.modules", {"keyring": keyring_mod})

    assert check_token("github_token") is False
