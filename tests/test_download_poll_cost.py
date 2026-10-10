"""Home's download list: finished torrents stay out and a poll does no needless work."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from applications.sabnzbd import SabnzbdApp
from core import homepage
from core.integrations import credentials


def test_finished_torrents_are_hidden_and_states_read_well():
    rows = [
        {"name": "Done", "state": "stoppedUP", "progress": 1.0},
        {"name": "Old done", "state": "pausedUP", "progress": 1.0},
        {"name": "Busy", "state": "downloading", "progress": 0.42, "dlspeed": 1000, "eta": 60},
        {"name": "Stuck", "state": "stalledDL", "progress": 0.1},
        {"name": "Odd", "state": "newState", "progress": 0.5},
    ]
    client = SimpleNamespace(
        base_url="http://qbit/api/v2",
        app_accessible=lambda: True,
        session=SimpleNamespace(get=lambda url, timeout: SimpleNamespace(status_code=200, json=lambda: rows)),
    )
    plugin = SimpleNamespace(port=8080, is_installed=lambda: True)
    catalog = SimpleNamespace(has=lambda name: True, get=lambda name: plugin)
    with patch("core.homepage.QBittorrentClient", return_value=client):
        items = homepage._collect_qbittorrent_queue(catalog, {"qbittorrent"}, [])
    assert [(i["title"], i["status"]) for i in items] == [
        ("Busy", "Downloading"), ("Stuck", "Stalled"), ("Odd", "newState"),
    ]


def test_sabnzbd_import_check_runs_once_per_venv(tmp_path):
    from applications import sabnzbd as sab_module

    python = tmp_path / "venv" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("")
    sab_module._IMPORTS_OK.clear()
    run = MagicMock(return_value=SimpleNamespace(returncode=0))
    app = SabnzbdApp.__new__(SabnzbdApp)
    with patch("applications.sabnzbd.subprocess.run", run):
        assert app._runtime_imports_ok(python) is True
        assert app._runtime_imports_ok(python) is True
    assert run.call_count == 1


def test_api_key_lookup_only_writes_when_it_changed(tmp_path):
    (tmp_path / "config.xml").write_text("<Config><ApiKey>" + "a" * 32 + "</ApiKey></Config>")
    store = MagicMock()
    store.get_secret.return_value = "a" * 32
    with patch.object(credentials, "secret_store", store):
        assert credentials.get_application_api_key("sonarr", tmp_path) == "a" * 32
        store.save_secret.assert_not_called()
        store.get_secret.return_value = "old"
        credentials.get_application_api_key("sonarr", tmp_path)
    store.save_secret.assert_called_once_with("sonarr_api_key", "a" * 32)
