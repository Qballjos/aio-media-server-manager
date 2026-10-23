"""Seerr links to Radarr/Sonarr/Jellyfin follow the address the browser uses."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core.integrations import seerr


def _resp(payload=None):
    return SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None)


def test_lan_access_points_seerr_links_at_the_nas_once():
    seerr._external_links_host = None
    servers = {
        "radarr": [{"id": 0, "hostname": "127.0.0.1", "port": 7878, "externalUrl": None}],
        "sonarr": [{"id": 0, "hostname": "127.0.0.1", "port": 8989, "externalUrl": None}],
    }
    jellyfin = {"ip": "127.0.0.1", "port": 8096, "useSsl": False, "urlBase": "", "externalHostname": "", "apiKey": "k"}
    get = MagicMock(side_effect=lambda url, **kw: _resp(jellyfin if url.endswith("/jellyfin") else servers[url.rsplit("/", 1)[-1]]))
    put, post = MagicMock(return_value=_resp()), MagicMock(return_value=_resp())
    plugin = SimpleNamespace(port=5055, config_dir="/config/seerr", is_installed=lambda: True)
    catalog = SimpleNamespace(has=lambda name: True, get=lambda name: plugin)
    with (
        patch("applications.catalog.ApplicationCatalog", return_value=catalog),
        patch("core.integrations.credentials.get_application_api_key", return_value="key"),
        patch.object(seerr.requests, "get", get),
        patch.object(seerr.requests, "put", put),
        patch.object(seerr.requests, "post", post),
    ):
        seerr.sync_seerr_external_links("aio.example.com")  # public access: we do not know the LAN address
        get.assert_not_called()
        seerr.sync_seerr_external_links("192.168.0.247")
        seerr.sync_seerr_external_links("192.168.0.247")  # same host again: nothing to do
    assert [c.kwargs["json"]["externalUrl"] for c in put.call_args_list] == ["http://192.168.0.247:7878", "http://192.168.0.247:8989"]
    assert "id" not in put.call_args_list[0].kwargs["json"]  # Seerr rejects the read-only id
    assert post.call_count == 1 and post.call_args.kwargs["json"]["externalHostname"] == "http://192.168.0.247:8096"
    assert "apiKey" not in post.call_args.kwargs["json"]


def test_a_public_link_someone_set_is_left_alone():
    seerr._external_links_host = None
    servers = {
        "radarr": [{"id": 0, "port": 7878, "externalUrl": "https://radarr.example.com"}],
        "sonarr": [{"id": 0, "port": 8989, "externalUrl": "http://192.168.0.10:8989"}],  # an old LAN address: ours
    }
    jellyfin = {"ip": "127.0.0.1", "port": 8096, "externalHostname": "https://jellyfin.example.com"}
    get = MagicMock(side_effect=lambda url, **kw: _resp(jellyfin if url.endswith("/jellyfin") else servers[url.rsplit("/", 1)[-1]]))
    put, post = MagicMock(return_value=_resp()), MagicMock(return_value=_resp())
    plugin = SimpleNamespace(port=5055, config_dir="/config/seerr", is_installed=lambda: True)
    catalog = SimpleNamespace(has=lambda name: True, get=lambda name: plugin)
    with (
        patch("applications.catalog.ApplicationCatalog", return_value=catalog),
        patch("core.integrations.credentials.get_application_api_key", return_value="key"),
        patch.object(seerr.requests, "get", get),
        patch.object(seerr.requests, "put", put),
        patch.object(seerr.requests, "post", post),
    ):
        seerr.sync_seerr_external_links("192.168.0.247")
    assert [c.kwargs["json"]["externalUrl"] for c in put.call_args_list] == ["http://192.168.0.247:8989"]
    post.assert_not_called()
