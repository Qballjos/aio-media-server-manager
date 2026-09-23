from pathlib import Path

from applications.catalog import ApplicationCatalog

ICON_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "app-icons"
ICON_ALIASES = {"mylar3": "mylar"}


def test_every_catalog_app_has_a_bundled_icon():
    missing = []
    for plugin in ApplicationCatalog().all_plugins():
        stem = ICON_ALIASES.get(plugin.name, plugin.name)
        if not any((ICON_DIR / f"{stem}{ext}").is_file() for ext in (".svg", ".png")):
            missing.append(plugin.name)
    assert missing == [], f"Missing app icons for: {missing}"
