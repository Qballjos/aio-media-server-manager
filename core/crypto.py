"""
core/crypto.py — Encrypted Secret Storage

Provides symmetric encryption using Fernet (AES-128-CBC + HMAC-SHA256)
to safely store application credentials, API keys, and connection tokens.
Enforces strict 0600 POSIX file permissions on key files.
"""

from __future__ import annotations

import json
import logging
import os
import stat
from pathlib import Path
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from core.settings import Settings, settings

logger = logging.getLogger(__name__)


def mask_secret(value: str) -> str:
    """Return a masked representation of a secret string."""
    if not value:
        return ""
    if len(value) <= 6:
        return "******"
    return f"{value[:2]}{'*' * min(len(value) - 4, 12)}{value[-2:]}"


class SecretStore:
    """Manages encrypted key-value pairs stored on disk."""

    def __init__(self, key_path: Optional[Path] = None, storage_path: Optional[Path] = None, cfg: Optional[Settings] = None):
        self._settings = cfg or settings
        self._custom_key_path = key_path
        self._custom_storage_path = storage_path
        self._fernet: Optional[Fernet] = None
        self._memory_data: dict[str, str] = {}
        if key_path is not None:
            try:
                self._ensure_cipher()
            except Exception as e:
                logger.warning("Could not initialize custom key_path: %s", e)

    @property
    def key_path(self) -> Path:
        return self._custom_key_path or (self._settings.config_dir / "secret.key")

    @property
    def storage_path(self) -> Path:
        return self._custom_storage_path or (self._settings.config_dir / "secrets.enc")

    def _ensure_cipher(self) -> Fernet:
        """Load or generate the master encryption key with 0600 permissions."""
        if self._fernet is not None:
            return self._fernet

        kpath = self.key_path
        if kpath.exists():
            try:
                if hasattr(os, "chmod"):
                    try:
                        os.chmod(kpath, stat.S_IRUSR | stat.S_IWUSR)
                    except OSError:
                        pass
                key_data = kpath.read_bytes().strip()
                self._fernet = Fernet(key_data)
                return self._fernet
            except Exception as e:
                logger.warning("Failed to load existing encryption key from %s: %s. Generating new.", kpath, e)

        # Generate new key
        try:
            kpath.parent.mkdir(parents=True, exist_ok=True)
            new_key = Fernet.generate_key()
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            mode = stat.S_IRUSR | stat.S_IWUSR  # 0600
            fd = os.open(str(kpath), flags, mode)
            with open(fd, "wb") as f:
                f.write(new_key)
            self._fernet = Fernet(new_key)
            logger.info("Initialized new encryption key at %s with 0600 permissions", kpath)
            return self._fernet
        except OSError as exc:
            # If default /config is read-only (e.g. running outside container without AMM_CONFIG_DIR set),
            # generate an ephemeral key in memory or raise a clear error
            logger.warning("Could not write secret key to %s: %s. Using in-memory cipher fallback.", kpath, exc)
            self._fernet = Fernet(Fernet.generate_key())
            return self._fernet

    def encrypt(self, plaintext: str) -> str:
        """Encrypt plaintext string into base64 ciphertext."""
        cipher = self._ensure_cipher()
        return cipher.encrypt(plaintext.encode("utf-8")).decode("utf-8")

    def decrypt(self, ciphertext: str) -> str:
        """Decrypt ciphertext into plaintext string."""
        cipher = self._ensure_cipher()
        try:
            return cipher.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            logger.error("Failed to decrypt token: invalid token or wrong key")
            raise ValueError("Invalid secret or corrupted encryption key") from exc

    def _load_raw(self) -> dict[str, str]:
        """Load raw encrypted dictionary from disk or in-memory fallback."""
        data = dict(self._memory_data)
        path = self.storage_path
        if not path.exists():
            return data
        try:
            content = path.read_text(encoding="utf-8")
            disk_data = json.loads(content)
            if isinstance(disk_data, dict):
                data.update(disk_data)
        except Exception as e:
            logger.warning("Could not parse secret storage file: %s", e)
        return data

    def _save_raw(self, data: dict[str, str]) -> None:
        """Save raw encrypted dictionary to disk with 0600 permissions, keeping in-memory copy."""
        self._memory_data = dict(data)
        path = self.storage_path
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
            mode = stat.S_IRUSR | stat.S_IWUSR  # 0600
            fd = os.open(str(tmp), flags, mode)
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)
            tmp.replace(path)
        except OSError as e:
            logger.warning("Could not save secrets to %s: %s. Using in-memory fallback.", path, e)


    def reload(self) -> None:
        """Drop the cached key and in-memory copy so the next call reads disk (after a restore)."""
        self._fernet = None
        self._memory_data = {}

    def save_secret(self, name: str, value: str) -> None:
        """Encrypt and store a named secret."""
        encrypted_val = self.encrypt(value)
        data = self._load_raw()
        data[name] = encrypted_val
        self._save_raw(data)
        logger.debug("Saved encrypted secret '%s'", name)

    def get_secret(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """Retrieve and decrypt a named secret."""
        data = self._load_raw()
        if name not in data:
            return default
        try:
            return self.decrypt(data[name])
        except Exception:
            return default

    def delete_secret(self, name: str) -> bool:
        """Remove a named secret. Returns True if removed."""
        data = self._load_raw()
        if name in data:
            del data[name]
            self._save_raw(data)
            return True
        return False

    def list_secrets(self, mask: bool = True) -> dict[str, str]:
        """
        List all stored secrets. If mask is True, values are masked (e.g. ab****yz).
        If mask is False, decrypted plaintexts are returned.
        """
        data = self._load_raw()
        result: dict[str, str] = {}
        for k, encrypted_val in data.items():
            try:
                decrypted = self.decrypt(encrypted_val)
                result[k] = mask_secret(decrypted) if mask else decrypted
            except Exception:
                result[k] = "[DECRYPTION_ERROR]"
        return result


# Global singleton secret store
secret_store = SecretStore()
