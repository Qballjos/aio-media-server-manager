"""Removing stuck downloads from Home."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from core import download_cleanup


def test_tracked_downloads_go_through_sonarr_and_the_rest_through_the_client():
    queue = {"records": [{"id": 7, "downloadId": "ABCDEF"}, {"id": 8, "downloadId": "OTHER"}]}
    get = MagicMock(return_value=SimpleNamespace(json=lambda: queue))
    delete = MagicMock(return_value=SimpleNamespace(raise_for_status=lambda: None))
    plugin = SimpleNamespace(port=8989, config_dir="/c", is_installed=lambda: True)
    catalog = SimpleNamespace(has=lambda name: name == "sonarr", get=lambda name: plugin)
    sab = MagicMock()
    sab._request.return_value = {"status": True}
    with (
        patch("applications.catalog.ApplicationCatalog", return_value=catalog),
        patch("core.integrations.credentials.get_application_api_key", return_value="k"),
        patch.object(download_cleanup.requests, "get", get),
        patch.object(download_cleanup.requests, "delete", delete),
        patch("core.downloads_pause._clients", return_value={"sabnzbd": sab}),
    ):
        result = download_cleanup.remove_downloads(
            [
                {"source": "qbittorrent", "download_id": "abcdef"},  # Sonarr writes the hash in upper case
                {"source": "sabnzbd", "download_id": "SABnzbd_nzo_X1y"},  # not in any queue
            ]
        )
    assert result == {"requested": 2, "searched_again": 1, "removed_from_client": 1}
    assert delete.call_args.kwargs["json"] == {"ids": [7]}
    assert delete.call_args.kwargs["params"]["blocklist"] == "true"
    assert delete.call_args.kwargs["params"]["skipRedownload"] == "false"
    sab._request.assert_called_once_with("queue", {"name": "delete", "value": "SABnzbd_nzo_X1y", "del_files": 1})
