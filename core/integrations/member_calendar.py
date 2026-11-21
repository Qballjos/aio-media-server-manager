"""A release calendar filtered by the viewer's current library permissions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
import re
from xml.etree import ElementTree as ET

import requests
from fastapi import HTTPException

from applications.catalog import ApplicationCatalog
from core.homepage import _arr_headers, _parse_radarr_calendar, _parse_sonarr_calendar
from core.integrations.credentials import get_application_api_key
from core.integrations.jellyfin import jellyfin_auth_headers
from core.integrations.member_library import _get, _jellyfin_headers, _plex_sections
from core.integrations.plex import PlexClient

_FAILURES = (HTTPException, requests.RequestException, OSError, ValueError, KeyError, TypeError, AttributeError, ET.ParseError)


def _path(value: str) -> Path | None:
    if not isinstance(value, str) or not value.startswith("/") or ".." in Path(value).parts:
        return None
    try:
        return Path(value).resolve()
    except (OSError, RuntimeError):
        return None


def _folder_grants(libraries, visible: set[str]) -> list[tuple[Path, bool]]:
    return [
        (path, str(library_id) in visible)
        for library_id, locations in libraries
        for location in locations
        if (path := _path(location)) is not None
    ]


def _target_is_shared(target: str, folders: list[tuple[Path, bool]]) -> bool:
    path = _path(target)
    if path is None:
        return False
    # Overlapping roots are ambiguous if any matching library is private.
    matches = [shared for root, shared in folders if path.is_relative_to(root)]
    return bool(matches) and all(matches) and not any(not shared and root.is_relative_to(path) for root, shared in folders)


def _jellyfin_folders(base, plugin, headers, account_id):
    try:
        viewer = _get(base, "/Users/Me", headers).json()
        if str(viewer.get("Id", "")).replace("-", "").lower() != account_id.replace("-", "").lower():
            return []
        policy = viewer.get("Policy")
        if (
            not isinstance(policy, dict)
            or policy.get("EnableMediaPlayback") is not True
            or policy.get("IsDisabled") is not False
            or policy.get("MaxParentalRating") is not None
            or policy.get("MaxParentalSubRating") not in (None, 0)
            or any(policy.get(key) for key in ("BlockedTags", "AllowedTags", "BlockUnratedItems", "AccessSchedules"))
        ):
            return []
        key = get_application_api_key("jellyfin", plugin.config_dir)
        if not key:
            return []
        def normalize(value):
            return str(value or "").replace("-", "").lower()

        views = _get(base, "/UserViews", headers, UserId=account_id, IncludeExternalContent="false").json()["Items"]
        visible = {normalize(row.get("Id")) for row in views if row.get("Id")}
        blocked = {normalize(value) for value in (policy.get("BlockedMediaFolders") or [])}
        libraries = _get(base, "/Library/VirtualFolders", jellyfin_auth_headers(key)).json()
        return _folder_grants(
            ((normalize(row.get("ItemId")), row.get("Locations") or []) for row in libraries),
            visible - blocked,
        )
    except _FAILURES:
        return []


def _plex_folders(base, plugin, account_id, server_id, sections):
    try:
        owner = PlexClient(port=plugin.port, config_dir=plugin.config_dir)
        if not owner.token:
            return []
        reply = requests.get(
            "https://plex.tv/api/users/", headers={"X-Plex-Token": owner.token, "Accept": "application/xml"},
            timeout=5, allow_redirects=False,
        )
        if reply.status_code != 200:
            return []
        matches = [
            user for user in ET.fromstring(reply.text).findall("User")
            if user.get("id") == account_id and any(
                server.get("machineIdentifier") == server_id for server in user.findall("Server")
            )
        ]
        if len(matches) != 1 or matches[0].get("restricted") != "0" or any(
            matches[0].get(key) != "" for key in ("filterAll", "filterMovies", "filterTelevision")
        ):
            return []
        headers = {"Accept": "application/json", "X-Plex-Token": owner.token}
        directories = _get(base, "/library/sections", headers).json()["MediaContainer"]["Directory"]
        return _folder_grants(
            ((row.get("key"), [location.get("path") for location in row.get("Location", [])]) for row in directories),
            sections,
        )
    except _FAILURES:
        return []


def _calendar_rows(catalog, start, end):
    for app, parser in (("sonarr", _parse_sonarr_calendar), ("radarr", _parse_radarr_calendar)):
        plugin = catalog.get(app)
        headers = _arr_headers(app, plugin.config_dir)
        if not headers.get("X-Api-Key"):
            continue
        try:
            rows = _get(
                f"http://127.0.0.1:{plugin.port}", "/api/v3/calendar", headers,
                start=start.isoformat(), end=end.isoformat(), unmonitored="false",
                **({"includeSeries": "true"} if app == "sonarr" else {}),
            ).json()
        except _FAILURES:
            continue
        for row in rows if isinstance(rows, list) else []:
            if not isinstance(row, dict):
                continue
            try:
                event = parser([row])[0]
                target = (row.get("series") or {}).get("path") if app == "sonarr" else row.get("path")
                day = date.fromisoformat(event["when"][:10])
            except (ValueError, TypeError, KeyError, AttributeError, IndexError):
                continue
            if start <= day <= end:
                yield event, target, day


def _visible_item(base, headers, account_id, sections, event):
    movie = event["kind"] == "movie"
    provider_key = "Tmdb" if movie else "Tvdb"
    external_id = event.get("_tmdb" if movie else "_tvdb")
    if not external_id:
        return False
    title = event["title"]
    if sections is None:
        kind = "Movie" if movie else "Series"
        matches = _get(
            base, "/Items", headers, UserId=account_id, SearchTerm=title, Recursive="true",
            IncludeItemTypes=kind, Fields="ProviderIds", Limit=50,
        ).json()["Items"]
        for item in matches:
            if item.get("Type") != kind or str((item.get("ProviderIds") or {}).get(provider_key)) != str(external_id):
                continue
            if movie:
                return True
            item_id = str(item.get("Id") or "")
            if not re.fullmatch(r"[a-fA-F0-9]{32}|[a-fA-F0-9-]{36}", item_id):
                continue
            episodes = _get(
                base, "/Items", headers, UserId=account_id, ParentId=item_id, IncludeItemTypes="Episode",
                Recursive="true", IsMissing="false", ParentIndexNumber=event["_season"], IndexNumber=event["_episode"],
            ).json()["Items"]
            if any(
                episode.get("Type") == "Episode" and episode.get("LocationType") != "Virtual"
                and episode.get("ParentIndexNumber") == event["_season"] and episode.get("IndexNumber") == event["_episode"]
                for episode in episodes
            ):
                return True
        return False

    for section in sections:
        matches = _get(
            base, f"/library/sections/{section}/all", headers, type=1 if movie else 2, title=title, includeGuids=1,
            **{"X-Plex-Container-Start": 0, "X-Plex-Container-Size": 50},
        ).json()["MediaContainer"].get("Metadata", [])
        for item in matches:
            if item.get("type") != ("movie" if movie else "show") or not any(
                guid.get("id") == f"{provider_key.lower()}://{external_id}" for guid in item.get("Guid", [])
            ):
                continue
            if movie:
                return True
            item_id = str(item.get("ratingKey") or "")
            if not re.fullmatch(r"[0-9]{1,20}", item_id):
                continue
            episodes = _get(
                base, f"/library/metadata/{item_id}/allLeaves", headers,
                **{"X-Plex-Container-Start": 0, "X-Plex-Container-Size": 2000},
            ).json()["MediaContainer"].get("Metadata", [])
            if any(
                episode.get("type") == "episode" and str(episode.get("grandparentRatingKey")) == item_id
                and episode.get("parentIndex") == event["_season"] and episode.get("index") == event["_episode"]
                for episode in episodes
            ):
                return True
    return False


def member_calendar(provider: str, server_id: str, account_id: str, token: str, start: date, end: date):
    catalog = ApplicationCatalog()
    plugin = catalog.get(provider)
    base = f"http://127.0.0.1:{plugin.port}"
    if provider == "jellyfin":
        headers = _jellyfin_headers(base, server_id, token)
        sections = None
        folders = _jellyfin_folders(base, plugin, headers, account_id)
    elif provider == "plex":
        headers, sections = _plex_sections(base, server_id, token)
        folders = _plex_folders(base, plugin, account_id, server_id, sections)
    else:
        return []

    def visible(row):
        event, target, day = row
        if not event["has_file"] and day >= date.today() and _target_is_shared(target, folders):
            available = False
        else:
            try:
                available = _visible_item(base, headers, account_id, sections, event)
            except _FAILURES:
                return None
            if not available:
                return None
        result = {key: event[key] for key in ("kind", "title", "detail", "when")} | {"available": available}
        if event.get("milestones"):
            result["milestones"] = event["milestones"]
        return result

    with ThreadPoolExecutor(max_workers=6) as pool:
        events = [event for event in pool.map(visible, _calendar_rows(catalog, start, end)) if event]
    return sorted(events, key=lambda event: event["when"])
