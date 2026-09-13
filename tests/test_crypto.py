"""
tests/test_crypto.py — Tests for encrypted secret storage and key management
"""

import os
import stat
from pathlib import Path
import pytest
from core.crypto import SecretStore, mask_secret


def test_mask_secret():
    assert mask_secret("") == ""
    assert mask_secret("short") == "******"
    assert mask_secret("123456") == "******"
    masked = mask_secret("supersecretapikey123")
    assert masked.startswith("su")
    assert masked.endswith("23")
    assert "*" in masked
    assert "secret" not in masked


def test_secret_store_lifecycle(tmp_path: Path):
    key_file = tmp_path / "test.key"
    enc_file = tmp_path / "secrets.enc"

    store = SecretStore(key_path=key_file, storage_path=enc_file)
    assert key_file.exists()

    # Verify POSIX file permission 0600 if on POSIX
    if hasattr(os, "chmod"):
        mode = stat.S_IMODE(os.stat(key_file).st_mode)
        assert mode == 0o600

    # Save and retrieve secret
    store.save_secret("radarr_api_key", "my-radarr-api-token-12345")
    assert store.get_secret("radarr_api_key") == "my-radarr-api-token-12345"

    # Verify raw file contains encrypted ciphertext and not plaintext
    raw_content = enc_file.read_text(encoding="utf-8")
    assert "my-radarr-api-token-12345" not in raw_content
    assert "radarr_api_key" in raw_content

    # List secrets (masked vs unmasked)
    masked_list = store.list_secrets(mask=True)
    assert "radarr_api_key" in masked_list
    assert "my-radarr-api-token-12345" not in masked_list["radarr_api_key"]
    assert masked_list["radarr_api_key"].startswith("my")

    unmasked_list = store.list_secrets(mask=False)
    assert unmasked_list["radarr_api_key"] == "my-radarr-api-token-12345"

    # Non-existent key
    assert store.get_secret("non_existent") is None
    assert store.get_secret("non_existent", default="fallback") == "fallback"

    # Delete secret
    assert store.delete_secret("radarr_api_key") is True
    assert store.get_secret("radarr_api_key") is None
    assert store.delete_secret("radarr_api_key") is False


def test_secret_store_reload(tmp_path: Path):
    key_file = tmp_path / "reused.key"
    enc_file = tmp_path / "reused.enc"

    store1 = SecretStore(key_path=key_file, storage_path=enc_file)
    store1.save_secret("db_pass", "super_secret_db_pass_999")

    # Load from a new instance using the same files
    store2 = SecretStore(key_path=key_file, storage_path=enc_file)
    assert store2.get_secret("db_pass") == "super_secret_db_pass_999"
