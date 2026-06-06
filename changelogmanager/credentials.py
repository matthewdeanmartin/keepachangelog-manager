# SPDX-License-Identifier: Apache-2.0; see LICENSE.md.

"""Credential resolution for online backfill sources."""

import os
from typing import Optional

KEYRING_SERVICE = "keepachangelog-manager"


def get_token(
    service_key: str, cli_value: Optional[str], env_var: str
) -> Optional[str]:
    """Returns the first non-empty token from: CLI flag → keyring → env var."""
    if cli_value:
        return cli_value
    import keyring

    val = keyring.get_password(KEYRING_SERVICE, service_key)
    if val:
        return val
    return os.environ.get(env_var, "").strip() or None


def set_token(service_key: str, token: str) -> None:
    """Stores token in the OS keyring."""
    import keyring

    keyring.set_password(KEYRING_SERVICE, service_key, token)


def clear_token(service_key: str) -> bool:
    """Removes token from the OS keyring. Returns True if it existed."""
    import keyring
    import keyring.errors

    existing = keyring.get_password(KEYRING_SERVICE, service_key)
    if existing is None:
        return False
    try:
        keyring.delete_password(KEYRING_SERVICE, service_key)
    except keyring.errors.PasswordDeleteError:
        return False
    return True


def check_token(service_key: str) -> bool:
    """Returns True if a token is stored in the OS keyring for service_key."""
    import keyring

    return keyring.get_password(KEYRING_SERVICE, service_key) is not None
