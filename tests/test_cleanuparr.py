"""Cleanuparr launch isolation and upstream API contracts (v2.11.0)."""
from copy import deepcopy
import json

import pytest
import requests

from applications.catalog import ApplicationCatalog
from core.crypto import SecretStore
from core.settings import Settings


@pytest.fixture
def cfg(tmp_path):
    return Settings(config_dir=tmp_path / "config", install_dir=tmp_path / "apps",
                    download_dir=tmp_path / "downloads", media_dir=tmp_path / "media")


def test_cleanuparr_launch_uses_isolated_config_and_selected_port(cfg, monkeypatch):
    monkeypatch.setenv("DOTNET_RUNNING_IN_CONTAINER", "true")
    plugin = ApplicationCatalog(app_settings=cfg).get("cleanuparr")
    plugin.pre_install()
    exe = plugin.install_dir / "Cleanuparr"
    exe.write_text("synthetic binary")
    (plugin.install_dir / "wwwroot").mkdir()
    plugin.post_install()
    plugin.apply_listen_port(12011)
    env = plugin.extra_env()
    assert env["DOTNET_RUNNING_IN_CONTAINER"] == "false"
    assert env["CLEANUPARR_CONFIG_PATH"] == str(cfg.config_dir / "cleanuparr")
    assert plugin.start_command() == [str(exe)]
    assert plugin.working_directory() == exe.parent
    assert plugin.health_check_url() == "http://127.0.0.1:12011/health/ready"
    assert json.loads((plugin.config_dir / "cleanuparr.json").read_text())["PORT"] == 12011


class Upstream:
    """Stateful HTTP boundary; exercise real setup, merge and read-back code."""
    def __init__(self):
        self.headers = {}
        self.account = None
        self.complete = False
        self.general = {"dryRun": False, "httpTimeout": 100, "ignoredDownloads": ["keep-me"],
                        "auth": {"disableAuthForLocalAddresses": False}}
        self.arrs = {name: {"instances": []} for name in ("sonarr", "radarr", "lidarr")}
        self.configs = {
            "queue_cleaner": {"enabled": False, "cronExpression": "0 0/5 * * * ?", "failedImport": {},
                              "errored": {}, "ignoredDownloads": [], "stallRules": [], "slowRules": []},
            "malware_blocker": {"enabled": False, "sonarr": {}, "radarr": {}, "lidarr": {}},
            "download_cleaner": {"enabled": False},
            "seeker": {"searchEnabled": True, "proactiveSearchEnabled": False, "searchInterval": 10},
        }
        self.stall_rules = []
        self.clients = []
        self.calls = []
        self.reject = None

    def request(self, method, url, **kwargs):
        path = url.split("/api/", 1)[1]
        data = deepcopy(kwargs.get("json"))
        self.calls.append((method, path, data))
        status, body = 200, {}
        if path == self.reject:
            status = 500
            body = {"detail": "upstream-secret-must-not-leak"}
        elif path == "auth/status":
            body = {"setupCompleted": self.complete}
        elif path == "auth/setup/account":
            if self.account:
                status = 409
            else:
                self.account = data
                status = 201
        elif path == "auth/setup/complete":
            self.complete = True
        elif path == "auth/login":
            if data != self.account or not self.complete:
                status = 401
            else:
                body = {"requiresTwoFactor": False, "tokens": {"accessToken": "jwt", "refreshToken": "refresh"}}
        elif path == "account/api-key":
            body = {"apiKey": "cleanuparr-key"}
        elif path == "account":
            body = {"username": self.account["username"], "twoFactorEnabled": False}
        elif path == "account/password":
            assert data["currentPassword"] == self.account["password"]
            self.account["password"] = data["newPassword"]
        elif path == "account/username":
            assert data["currentPassword"] == self.account["password"]
            self.account["username"] = data["newUsername"]
        elif path == "configuration/general":
            if method == "PUT":
                self.general = data
            body = self.general
        elif path.startswith("configuration/") and path.split("/")[-1] in self.configs:
            name = path.split("/")[-1]
            if method == "PUT":
                self.configs[name] = data
            body = deepcopy(self.configs[name])
        elif path == "queue-rules/stall":
            if method == "POST":
                self.stall_rules.append({"id": "stall-1", **data})
                status = 201
            body = deepcopy(self.stall_rules)
        elif path == "configuration/download_client":
            if method == "POST":
                self.clients.append({"id": str(len(self.clients) + 1), **data})
                status = 201
            body = {"clients": deepcopy(self.clients)}
        elif path.startswith("configuration/download_client/"):
            ident = path.rsplit("/", 1)[1]
            row = next(r for r in self.clients if r["id"] == ident)
            row.update(data)
        elif path.split("/")[-1] in self.arrs:
            body = deepcopy(self.arrs[path.split("/")[-1]])
        elif "/instances" in path:
            name = path.split("/")[1]
            if method == "POST":
                self.arrs[name]["instances"].append({"id": str(len(self.arrs[name]["instances"]) + 1), **data})
                status = 201
            else:
                ident = path.rsplit("/", 1)[1]
                next(r for r in self.arrs[name]["instances"] if r["id"] == ident).update(data)
        else:
            raise AssertionError((method, path, data))
        result = requests.Response()
        result.status_code = status
        result._content = json.dumps(body).encode()
        return result


@pytest.fixture
def client(cfg, monkeypatch):
    from core.integrations import cleanuparr
    monkeypatch.setattr(cleanuparr, "secret_store", SecretStore(cfg=cfg))
    upstream = Upstream()
    return cleanuparr.CleanuparrClient(http=upstream), upstream


def test_bootstrap_enables_dry_run_before_connections_and_keeps_it_after_retry(client):
    api, upstream = client
    api.ensure_admin("admin", "Password123!")
    assert upstream.complete
    assert upstream.general["dryRun"] is True
    assert upstream.general["ignoredDownloads"] == ["keep-me"]
    assert api.api_key == "cleanuparr-key"
    assert not upstream.general["auth"]["disableAuthForLocalAddresses"]
    upstream.general["dryRun"] = False
    api.ensure_admin("admin", "Password123!")
    assert upstream.general["dryRun"] is False
    assert sum(path == "auth/setup/account" for _, path, _ in upstream.calls) == 1


def test_bootstrap_does_not_complete_someone_elses_partial_setup(client):
    from core.integrations.cleanuparr import CleanuparrError
    api, upstream = client
    upstream.account = {"username": "other", "password": "OtherPassword!"}
    with pytest.raises(CleanuparrError):
        api.ensure_admin("admin", "Password123!")
    assert upstream.complete is False


def test_bootstrap_retries_after_general_settings_failure_before_wiring(client):
    from core.integrations.cleanuparr import CleanuparrError
    api, upstream = client
    upstream.reject = "configuration/general"
    with pytest.raises(CleanuparrError, match="Cleanuparr") as error:
        api.ensure_admin("admin", "Password123!")
    assert "upstream-secret" not in str(error.value)
    upstream.reject = None
    api.ensure_admin("admin", "Password123!")
    assert upstream.general["dryRun"] is True


def test_shared_admin_changes_use_the_previous_password(client):
    api, upstream = client
    api.ensure_admin("admin", "Password123!")
    api.ensure_admin("newadmin", "NewPassword123!")
    assert upstream.account == {"username": "newadmin", "password": "NewPassword123!"}


def test_wiring_updates_managed_endpoints_without_duplicates_or_changing_rules(client):
    api, upstream = client
    api.ensure_admin("admin", "Password123!")
    configured = deepcopy(upstream.configs)
    upstream.arrs["sonarr"]["instances"].append(
        {"id": "external", "name": "My remote Sonarr", "url": "https://remote.example", "enabled": True})
    api.ensure_arr("sonarr", url="http://127.0.0.1:8989", api_key="sonarr-key", version=4)
    upstream.arrs["sonarr"]["instances"][1]["enabled"] = False
    api.ensure_arr("sonarr", url="http://127.0.0.1:18989", api_key="rotated-key", version=4)
    rows = upstream.arrs["sonarr"]["instances"]
    assert len(rows) == 2
    assert rows[0]["url"] == "https://remote.example"
    assert rows[1]["url"] == "http://127.0.0.1:18989"
    assert rows[1]["apiKey"] == "rotated-key"
    assert rows[1]["enabled"] is False
    api.ensure_download_client("qbittorrent", host="http://127.0.0.1:8081", username="admin", password="pw")
    upstream.clients[0]["downloadDirectoryTarget"] = "/custom"
    upstream.clients[0]["enabled"] = False
    api.ensure_download_client("qbittorrent", host="http://127.0.0.1:18081", username="admin", password="new")
    assert len(upstream.clients) == 1
    assert upstream.clients[0]["host"] == "http://127.0.0.1:18081"
    assert upstream.clients[0]["downloadDirectoryTarget"] == "/custom"
    assert upstream.clients[0]["enabled"] is False
    assert upstream.configs == configured


def test_new_setup_gets_conservative_defaults_before_connections(client):
    api, upstream = client
    api.ensure_admin("admin", "Password123!")
    assert upstream.general["dryRun"] is True
    assert upstream.general["connectivityCheckEnabled"] is True
    assert upstream.general["httpCertificateValidation"] == "Enabled"
    assert upstream.general["connectivityCheckUrls"] == ["https://github.com", "https://www.cloudflare.com"]
    queue = upstream.configs["queue_cleaner"]
    assert queue["enabled"] is True and queue["cronExpression"] == "0 0/5 * * * ?"
    assert queue["failedImport"]["maxStrikes"] == 6
    assert queue["failedImport"]["patternMode"] == "Include"
    assert queue["failedImport"]["ignorePrivate"] is True
    assert queue["failedImport"]["skipIfNotFoundInClient"] is True
    assert queue["failedImport"]["forceImport"] is False
    assert queue["errored"]["maxStrikes"] == 0
    assert queue["downloadingMetadataMaxStrikes"] == 0
    assert queue["slowRules"] == []
    assert len(upstream.stall_rules) == 1
    stall = upstream.stall_rules[0]
    assert stall["maxStrikes"] == 12 and stall["privacyType"] == "Public"
    assert stall["resetStrikesOnProgress"] is True
    assert stall["deletePrivateTorrentsFromClient"] is False
    malware = upstream.configs["malware_blocker"]
    assert malware["enabled"] is True and malware["cronExpression"] == "0 * * * * ?"
    assert malware["ignorePrivate"] is True and malware["deletePrivate"] is False
    assert malware["deleteIfAnyFileBlocked"] is False
    assert malware["sonarr"]["blocklistPath"] == "https://cleanuparr.pages.dev/static/blacklist_permissive"
    assert malware["radarr"]["blocklistType"] == "Blacklist"
    assert malware["lidarr"].get("enabled", False) is False
    assert upstream.configs["download_cleaner"]["enabled"] is False
    assert upstream.configs["seeker"]["searchEnabled"] is True
    assert upstream.configs["seeker"]["proactiveSearchEnabled"] is False
    assert upstream.configs["seeker"]["searchInterval"] == 10
    assert upstream.clients == []


def test_default_profile_retries_without_duplicate_rules_and_preserves_later_choices(client):
    from core.integrations.cleanuparr import CleanuparrError
    api, upstream = client
    upstream.reject = "configuration/malware_blocker"
    with pytest.raises(CleanuparrError):
        api.ensure_admin("admin", "Password123!")
    upstream.reject = None
    api.ensure_admin("admin", "Password123!")
    assert len(upstream.stall_rules) == 1
    upstream.general["dryRun"] = False
    upstream.configs["queue_cleaner"]["enabled"] = False
    upstream.stall_rules[0]["maxStrikes"] = 24
    upstream.configs["malware_blocker"]["sonarr"]["blocklistPath"] = "/my-list.txt"
    before = deepcopy(upstream.configs), deepcopy(upstream.stall_rules)
    api.ensure_admin("admin", "Password123!")
    assert upstream.general["dryRun"] is False
    assert before == (upstream.configs, upstream.stall_rules)


def test_existing_account_with_supplied_key_does_not_get_new_defaults(client):
    api, upstream = client
    upstream.account = {"username": "custom", "password": "CustomPassword!"}
    upstream.complete = True
    api.api_key = "operator-supplied-key"
    before = deepcopy(upstream.configs), deepcopy(upstream.general)
    api.ensure_admin("admin", "Password123!")
    assert before == (upstream.configs, upstream.general)
    assert all(method == "GET" for method, _, _ in upstream.calls)


def test_http_failure_is_reported_without_upstream_secrets(client):
    from core.integrations.cleanuparr import CleanuparrError
    api, upstream = client
    upstream.reject = "configuration/sonarr"
    with pytest.raises(CleanuparrError) as error:
        api.ensure_arr("sonarr", url="http://127.0.0.1:8989", api_key="secret", version=4)
    assert "secret" not in str(error.value)


def test_readback_detects_disabled_or_stale_connections_without_writes(client, cfg):
    from core.integrations.cleanuparr import verify_cleanuparr
    api, upstream = client
    api.ensure_admin("admin", "Password123!")
    catalog = ApplicationCatalog(app_settings=cfg)
    app = catalog.get("sonarr")
    app.pre_install()
    (app.install_dir / app.executable_name).write_text("binary")
    api.ensure_arr("sonarr", url="http://127.0.0.1:8989", api_key="key", version=4)
    checks = verify_cleanuparr(catalog, api=api)
    assert checks == [("Connection: sonarr", True)]
    upstream.arrs["sonarr"]["instances"][0]["enabled"] = False
    before = len(upstream.calls)
    assert verify_cleanuparr(catalog, api=api) == [("Connection: sonarr", False)]
    assert all(method == "GET" for method, _, _ in upstream.calls[before:])


def test_full_wiring_uses_selected_ports_keys_and_supported_clients(client, cfg, monkeypatch):
    from core.integrations import cleanuparr, credentials, qbittorrent
    from core import shared_credentials
    api, upstream = client
    catalog = ApplicationCatalog(app_settings=cfg)
    for name in ("cleanuparr", "sonarr", "radarr", "lidarr", "qbittorrent", "sabnzbd", "nzbget"):
        app = catalog.get(name)
        app.pre_install()
        app.metadata_path().write_text('{"version":"1.0.0"}')
    catalog.get("sonarr").port = 18989
    # SABnzbd checks its Python environment, which is outside this HTTP wiring test.
    monkeypatch.setattr(catalog.get("sabnzbd"), "is_installed", lambda: True)
    monkeypatch.setattr(cleanuparr, "CleanuparrClient", lambda **kwargs: api)
    monkeypatch.setattr(shared_credentials, "shared_admin_credentials", lambda: ("admin", "Password123!"))
    monkeypatch.setattr(credentials, "get_application_api_key", lambda name, *args: f"{name}-key")
    monkeypatch.setattr(qbittorrent, "qbittorrent_credentials", lambda: ("qb", "qb-password"))
    result = cleanuparr.wire_cleanuparr(catalog)
    assert len(result) == 5 and all(row["status"] == "success" for row in result)
    assert upstream.arrs["sonarr"]["instances"][0]["url"] == "http://127.0.0.1:18989"
    assert upstream.arrs["lidarr"]["instances"][0]["version"] == 3
    assert {row["typeName"] for row in upstream.clients} == {"qBittorrent", "Sabnzbd"}
    assert "key" not in json.dumps(result) and "password" not in json.dumps(result)


def test_browser_helper_is_installed_next_to_the_upstream_ui(cfg):
    plugin = ApplicationCatalog(app_settings=cfg).get("cleanuparr")
    plugin.pre_install()
    (plugin.install_dir / "Cleanuparr").write_text("binary")
    webroot = plugin.install_dir / "wwwroot"
    webroot.mkdir()
    assert plugin.prepare_browser_login()
    assert (webroot / "aio-login.html").is_file()
    assert (webroot / "aio-login.js").is_file()


@pytest.mark.parametrize("arch,expected", [("x86_64", "amd64"), ("arm64", "arm64")])
def test_release_selection_uses_the_matching_linux_build(cfg, arch, expected):
    from core.installer.arch import PlatformArch, PlatformOS
    from core.installer.github import GitHubReleaseClient
    plugin = ApplicationCatalog(app_settings=cfg).get("cleanuparr")
    release = {"assets": [{"name": name} for name in (
        "Cleanuparr-2.11.0-osx-amd64.zip", "Cleanuparr-2.11.0-linux-amd64.zip",
        "Cleanuparr-2.11.0-linux-arm64.zip", "Cleanuparr-2.11.0-win-amd64.zip")]}
    asset = GitHubReleaseClient().select_asset(release, PlatformArch(arch), PlatformOS.LINUX,
                                              preferred_patterns=plugin.preferred_patterns())
    assert asset["name"] == f"Cleanuparr-2.11.0-linux-{expected}.zip"
