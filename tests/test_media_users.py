import pytest

from core.media_users import MediaUsers


@pytest.mark.parametrize("provider", ["jellyfin", "plex"])
def test_grants_are_idempotent_and_revocation_rotates_version(tmp_path, provider):
    users = MediaUsers(tmp_path)
    first = users.grant(provider, "server-a", "42")
    assert users.grant(provider, "server-a", "42") == first
    assert users.version(provider, "server-b", "42") is None
    users.revoke(provider, "server-a", "42")
    assert users.version(provider, "server-a", "42") is None
    assert users.grant(provider, "server-a", "42") != first
