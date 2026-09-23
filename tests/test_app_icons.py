from pathlib import Path

from applications.catalog import ApplicationCatalog

ICON_DIR = Path(__file__).resolve().parent.parent / "frontend" / "public" / "app-icons"
ICON_ALIASES: dict[str, str] = {}


def test_every_catalog_app_has_a_bundled_icon():
    missing = []
    for plugin in ApplicationCatalog().all_plugins():
        stem = ICON_ALIASES.get(plugin.name, plugin.name)
        if not any((ICON_DIR / f"{stem}{ext}").is_file() for ext in (".svg", ".png")):
            missing.append(plugin.name)
    assert missing == [], f"Missing app icons for: {missing}"


def test_no_unused_app_icons():
    catalog_stems = {
        ICON_ALIASES.get(plugin.name, plugin.name)
        for plugin in ApplicationCatalog().all_plugins()
    }
    extra = [
        path.name
        for path in sorted(ICON_DIR.iterdir())
        if path.suffix.lower() in {".svg", ".png"} and path.stem not in catalog_stems
    ]
    assert extra == [], f"Unused app icons: {extra}"
