"""
tests/test_catalog_and_ports.py — Unit tests for ApplicationCatalog and PortManager.
"""

from __future__ import annotations

import pytest

from applications.catalog import ApplicationCatalog
from applications.manifest import AppCategory, AppTier
from core.port_manager import PortManager
from core.settings import Settings


@pytest.fixture
def catalog(tmp_path) -> ApplicationCatalog:
    test_settings = Settings(
        config_dir=tmp_path / "config",
        install_dir=tmp_path / "apps",
    )
    return ApplicationCatalog(app_settings=test_settings)


def test_catalog_discovery():
    """Catalog discovers the 7 MVP core applications."""
    catalog = ApplicationCatalog()
    apps = catalog.all_plugins()

    app_names = {app.manifest.name for app in apps}
    expected_mvp = {
        "prowlarr",
        "sonarr",
        "radarr",
        "sabnzbd",
        "qbittorrent",
        "jellyfin",
        "seerr",
    }
    assert expected_mvp.issubset(app_names), f"Missing apps: {expected_mvp - app_names}"


def test_catalog_manifest_metadata():
    """Each application has valid manifest metadata matching requirements."""
    catalog = ApplicationCatalog()

    expected_ports = {
        "prowlarr": 9696,
        "sonarr": 8989,
        "radarr": 7878,
        "sabnzbd": 8085,
        "qbittorrent": 8081,
        "jellyfin": 8096,
        "seerr": 5055,
    }

    for name, expected_port in expected_ports.items():
        app = catalog.get(name)
        assert app is not None, f"App {name} not found in catalog"
        manifest = app.manifest
        assert manifest.name == name
        assert manifest.display_name
        assert manifest.default_port == expected_port
        assert "arm64" in manifest.supported_architectures
        assert manifest.tier in (AppTier.CORE, AppTier.RECOMMENDED)


def test_topological_sort_order():
    """Topological sort returns applications in dependency order."""
    catalog = ApplicationCatalog()
    ordered_names = catalog.resolve_install_order(catalog.names())

    # Indexer (prowlarr) must come before sonarr and radarr
    assert ordered_names.index("prowlarr") < ordered_names.index("sonarr")
    assert ordered_names.index("prowlarr") < ordered_names.index("radarr")


def test_catalog_entries_include_popularity():
    catalog = ApplicationCatalog()
    sonarr = catalog.get("sonarr").catalog_entry()
    mylar = catalog.get("mylar3").catalog_entry()
    assert sonarr["popularity"] > mylar["popularity"]
    assert sonarr["category"] == AppCategory.AUTOMATION.value
    assert sonarr["help_url"] == "https://wiki.servarr.com/sonarr"


def test_source_based_install_methods():
    catalog = ApplicationCatalog()
    from applications.manifest import InstallMethod

    assert catalog.get("bazarr").manifest.install_method == InstallMethod.GITHUB_RELEASE
    assert catalog.get("sabnzbd").manifest.preferred_patterns == (r"-src\.tar\.gz$",)
    assert catalog.get("seerr").manifest.install_method == InstallMethod.NODE_BUNDLE
    assert catalog.get("seerr").install.__func__ is not catalog.get("sonarr").install.__func__


def test_catalog_help_urls_and_icons():
    catalog = ApplicationCatalog()
    from pathlib import Path
    from applications.manifest import HELP_URLS

    icons = Path(__file__).resolve().parents[1] / "frontend" / "public" / "app-icons"
    mapping = {
        "flaresolverr": "flaresolverr.png",
        "grimmory": "grimmory.svg",
        "shelfmark": "shelfmark.png",
        "autobrr": "autobrr.svg",
        "bazarr": "bazarr.svg",
        "cleanuparr": "cleanuparr.png",
        "jellyfin": "jellyfin.svg",
        "kometa": "kometa.svg",
        "lidarr": "lidarr.svg",
        "maintainerr": "maintainerr.svg",
        "mylar3": "mylar.png",
        "neutarr": "neutarr.svg",
        "nzbget": "nzbget.svg",
        "plex": "plex.svg",
        "profilarr": "profilarr.svg",
        "prowlarr": "prowlarr.svg",
        "qbittorrent": "qbittorrent.svg",
        "radarr": "radarr.svg",
        "recyclarr": "recyclarr.svg",
        "sabnzbd": "sabnzbd.svg",
        "seerr": "seerr.svg",
        "sonarr": "sonarr.svg",
        "tautulli": "tautulli.svg",
        "unpackerr": "unpackerr.png",
    }
    for plugin in catalog.all_plugins():
        name = plugin.name
        entry = plugin.catalog_entry()
        assert name in HELP_URLS
        assert entry["help_url"] == HELP_URLS[name]
        assert (icons / mapping[name]).is_file(), f"missing icon for {name}"
    extra = sorted(
        path.name
        for path in icons.iterdir()
        if path.suffix.lower() in {".svg", ".png"} and path.name not in mapping.values()
    )
    assert extra == [], f"Unused app icons: {extra}"


def test_port_manager_registry_and_availability():
    """PortManager reports allocated ports and finds free alternatives."""
    pm = PortManager()

    # Default port allocation
    alloc = pm.allocate("prowlarr", 9696)
    assert alloc.app_name == "prowlarr"
    assert alloc.port == 9696
    assert pm.get_port("prowlarr", 9696) == 9696

    # Register custom port
    pm.register("custom_app", 9999)
    assert pm.get_port("custom_app", 9999) == 9999
    assert pm.list_registry().get("custom_app") == 9999

    # Conflict suggestion: if 9999 is taken by custom_app, suggest alternative for another app
    suggested = pm.suggest_alternative("other_app", 9999)
    assert suggested is not None
    assert suggested != 9999

    pm.unregister("custom_app")
    assert "custom_app" not in pm.list_registry()
