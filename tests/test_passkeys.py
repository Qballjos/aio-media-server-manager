from __future__ import annotations

import pytest
from webauthn.helpers import bytes_to_base64url

from core import passkeys


@pytest.mark.parametrize(("origin", "host", "rp_id"), [
    ("https://manager.example", "manager.example", "manager.example"),
    ("https://manager.example", "manager.example:443", "manager.example"),
    ("https://manager.example:8443", "manager.example:8443", "manager.example"),
    ("http://localhost:8765", "localhost:8765", "localhost"),
    ("https://manager.example:8443", "manager.example", None),
    ("https://another.example", "manager.example", None),
    ("http://manager.example", "manager.example", None),
    ("https://192.0.2.1", "192.0.2.1", None),
    ("https://manager.example/path", "manager.example", None),
])
def test_passkey_origin(origin, host, rp_id):
    assert passkeys.relying_party(origin, host) == rp_id


def test_passkey_challenge_is_bound_to_origin_purpose_and_account_and_single_use():
    challenges = passkeys.PasskeyChallenges()
    origin = "https://manager.example"
    challenge = b"fixture challenge"
    key = bytes_to_base64url(challenge)
    challenges.add(challenge, "register", origin, "account version")

    assert challenges.take(key, "login", origin, "account version") is None
    assert challenges.take(key, "register", "https://other.example", "account version") is None
    assert challenges.take(key, "register", origin, "new account version") is None
    assert challenges.take(key, "register", origin, "account version") == challenge
    assert challenges.take(key, "register", origin, "account version") is None


def test_passkey_challenge_expires(monkeypatch):
    challenges = passkeys.PasskeyChallenges()
    origin = "https://manager.example"
    challenge = b"fixture challenge"
    now = 1000
    monkeypatch.setattr(passkeys.time, "monotonic", lambda: now)
    challenges.add(challenge, "login", origin, "account version")
    now += passkeys.CHALLENGE_TTL
    assert challenges.take(bytes_to_base64url(challenge), "login", origin, "account version") is None
