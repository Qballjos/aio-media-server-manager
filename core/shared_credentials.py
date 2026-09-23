"""Encrypted copy of the manager admin login for apps that support local users."""

from __future__ import annotations

from typing import Optional

from core.crypto import secret_store

SHARED_USERNAME_KEY = "shared_admin_username"
SHARED_PASSWORD_KEY = "shared_admin_password"


def save_shared_admin_credentials(username: str, password: str) -> None:
    user = (username or "").strip() or "admin"
    if not password:
        return
    secret_store.save_secret(SHARED_USERNAME_KEY, user)
    secret_store.save_secret(SHARED_PASSWORD_KEY, password)


def shared_admin_credentials() -> Optional[tuple[str, str]]:
    username = secret_store.get_secret(SHARED_USERNAME_KEY)
    password = secret_store.get_secret(SHARED_PASSWORD_KEY)
    if not username or not password:
        return None
    return username, password
