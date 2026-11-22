"""Normalize Seerr watch providers and match personal subscriptions."""

import re

ADMIN_STREAMING_ACCOUNT = ("aio", "", "")
_REGION = re.compile(r"[A-Z]{2}")
_LOGO = re.compile(r"/[a-zA-Z0-9_-]+\.(?:png|jpg|webp)")
_WATCH_LINK = re.compile(r"https://www\.themoviedb\.org/(?:movie|tv)/[a-zA-Z0-9_-]+/watch(?:\?locale=[A-Z]{2})?")


def streaming_regions(rows):
    if not isinstance(rows, list):
        return []
    return sorted({
        code for row in rows if isinstance(row, dict)
        and isinstance(code := row.get("iso_3166_1"), str) and _REGION.fullmatch(code)
    })


def streaming_providers(rows):
    providers = {}
    for row in rows if isinstance(rows, list) else ():
        if not isinstance(row, dict):
            continue
        provider_id, name, logo = row.get("id"), row.get("name"), row.get("logoPath")
        if type(provider_id) is not int or provider_id <= 0 or not isinstance(name, str) or not name.strip():
            continue
        logo_url = f"https://image.tmdb.org/t/p/w92{logo}" if isinstance(logo, str) and _LOGO.fullmatch(logo) else ""
        providers.setdefault(provider_id, {"id": provider_id, "name": name, "logo_url": logo_url})
    return list(providers.values())


def streaming_availability(rows, preference):
    country, provider_ids = preference
    result = {"configured": bool(country and provider_ids), "providers": [], "link": ""}
    if not result["configured"] or not isinstance(rows, list):
        return result
    for row in rows:
        if not isinstance(row, dict) or row.get("iso_3166_1") != country:
            continue
        selected = set(provider_ids)
        result["providers"] = [p for p in streaming_providers(row.get("flatrate")) if p["id"] in selected]
        link = row.get("link")
        if result["providers"] and isinstance(link, str) and _WATCH_LINK.fullmatch(link):
            result["link"] = link
        break
    return result
