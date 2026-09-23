from pathlib import Path
from unittest.mock import MagicMock, patch

from core.crypto import SecretStore
from core.integrations.local_auth import patch_bazarr_auth_yaml, set_servarr_forms_auth, sha256_hex
from core.shared_credentials import save_shared_admin_credentials, shared_admin_credentials


def test_save_and_read_shared_admin_credentials(tmp_path: Path, monkeypatch):
    store = SecretStore(key_path=tmp_path / "secret.key", storage_path=tmp_path / "secrets.enc")
    monkeypatch.setattr("core.shared_credentials.secret_store", store)
    assert shared_admin_credentials() is None
    save_shared_admin_credentials("amm", "SharedPass123!")
    assert shared_admin_credentials() == ("amm", "SharedPass123!")


@patch("core.integrations.local_auth.requests.put")
@patch("core.integrations.local_auth.requests.get")
def test_set_servarr_forms_auth(mock_get, mock_put):
    mock_get.return_value = MagicMock(status_code=200, json=lambda: {"port": 8989, "bindAddress": "*"})
    mock_put.return_value = MagicMock(status_code=202)
    assert set_servarr_forms_auth("http://127.0.0.1:8989/api/v3", "key", "amm", "SharedPass123!") is True
    payload = mock_put.call_args.kwargs["json"]
    assert payload["authenticationMethod"] == "forms"
    assert payload["username"] == "amm"
    assert payload["password"] == "SharedPass123!"
    assert payload["passwordConfirmation"] == "SharedPass123!"


def test_patch_bazarr_auth_yaml(tmp_path: Path):
    config = tmp_path / "config.yaml"
    assert patch_bazarr_auth_yaml(config, "amm", "SharedPass123!") is True
    text = config.read_text(encoding="utf-8")
    assert "type: form" in text
    assert "amm" in text
    assert sha256_hex("SharedPass123!") in text
