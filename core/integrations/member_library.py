"""Recent media read with the signed-in viewer's own library permissions."""

import re
from concurrent.futures import ThreadPoolExecutor
from xml.etree import ElementTree as ET

import requests
from fastapi import HTTPException

from applications.catalog import ApplicationCatalog
from core.integrations.jellyfin import jellyfin_auth_headers


_RECENT_PAGE_SIZE = 20


def _get(base: str, path: str, headers: dict, **params) -> requests.Response:
    response = requests.get(f"{base}{path}", headers=headers, params=params, timeout=5, allow_redirects=False)
    if response.status_code in (401, 403):
        raise HTTPException(409, "Sign in again to access your media library.")
    if response.status_code != 200:
        raise ValueError("Unexpected media server response")
    return response


def _card(item_id, title, kind, overview) -> dict:
    item = {"id": str(item_id), "title": title, "mediaType": kind}
    if isinstance(overview, str) and overview.strip():
        item["overview"] = overview.strip()[:4000]
    return item


def _jellyfin_headers(base: str, server_id: str, token: str) -> dict:
    headers = jellyfin_auth_headers(token)
    if _get(base, "/System/Info/Public", headers).json().get("Id") != server_id:
        raise HTTPException(409, "The configured media server changed. Sign in again.")
    return headers


def _jellyfin_recent(base: str, server_id: str, account_id: str, token: str, offset: int) -> tuple[list[dict], bool]:
    headers = _jellyfin_headers(base, server_id, token)
    payload = _get(
        base, "/Items", headers, UserId=account_id, Recursive="true",
        IncludeItemTypes="Movie,Series", SortBy="DateCreated,SortName", SortOrder="Descending",
        StartIndex=offset, Limit=_RECENT_PAGE_SIZE, Fields="Overview",
    ).json()
    rows = payload["Items"]
    items = [
        _card(row["Id"], row["Name"], "movie" if row["Type"] == "Movie" else "tv", row.get("Overview"))
        for row in rows if row.get("Type") in ("Movie", "Series") and row.get("Id") and row.get("Name")
    ]
    total = payload.get("TotalRecordCount")
    return items, bool(rows) and (offset + len(rows) < total if type(total) is int else len(rows) == _RECENT_PAGE_SIZE)


def _plex_sections(base: str, server_id: str, token: str) -> tuple[dict, set[str]]:
    headers = {"Accept": "application/json", "X-Plex-Token": token}
    identity = _get(base, "/identity", {**headers, "Accept": "application/xml"})
    if ET.fromstring(identity.text).get("machineIdentifier") != server_id:
        raise HTTPException(409, "The configured media server changed. Sign in again.")
    directories = _get(base, "/library/sections", headers).json()["MediaContainer"].get("Directory", [])
    keys = {
        str(row.get("key")) for row in directories
        if row.get("type") in ("movie", "show") and str(row.get("key")).isascii() and str(row.get("key")).isdigit()
    }

    return headers, keys


def _plex_recent(base: str, server_id: str, token: str, offset: int) -> tuple[list[dict], bool]:
    headers, keys = _plex_sections(base, server_id, token)
    end = offset + _RECENT_PAGE_SIZE
    batch_size = 50

    def recent(section: str) -> list[tuple[int, dict]]:
        # Plex can return multiple episodes for one series. Keep reading each section
        # until it can supply the requested number of distinct titles plus one lookahead.
        cards = {}
        start = 0
        while len(cards) <= end:
            payload = _get(
                base, f"/library/sections/{section}/recentlyAdded", headers,
                **{"X-Plex-Container-Start": start, "X-Plex-Container-Size": batch_size},
            ).json()["MediaContainer"]
            rows = payload.get("Metadata", [])
            for row in rows:
                kind = row.get("type")
                if kind not in ("movie", "show", "season", "episode"):
                    continue
                parent = {"season": "parent", "episode": "grandparent"}.get(kind)
                item_id = row.get(f"{parent}RatingKey" if parent else "ratingKey")
                title = row.get(f"{parent}Title" if parent else "title")
                if item_id and title:
                    added = int(row.get("addedAt") or 0)
                    card = _card(item_id, title, "movie" if kind == "movie" else "tv", row.get("summary") if not parent else None)
                    key = str(item_id)
                    if key not in cards or added > cards[key][0]:
                        cards[key] = (added, card)
            start += len(rows)
            total = payload.get("totalSize")
            if not rows or (start >= total if type(total) is int else len(rows) < batch_size):
                break
        return sorted(cards.values(), key=lambda row: (-row[0], row[1]["id"]))[:end + 1]

    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = [row for section in pool.map(recent, sorted(keys)) for row in section]
    items = {}
    for _, item in sorted(rows, key=lambda row: (-row[0], row[1]["id"])):
        items.setdefault(item["id"], item)
    return list(items.values())[offset:end], len(items) > end


def recent_for_member(provider: str, server_id: str, account_id: str, token: str, page: int) -> tuple[list[dict], bool]:
    port = ApplicationCatalog().get(provider).port
    base = f"http://127.0.0.1:{port}"
    offset = (page - 1) * _RECENT_PAGE_SIZE
    try:
        if provider == "jellyfin":
            return _jellyfin_recent(base, server_id, account_id, token, offset)
        if provider == "plex":
            return _plex_recent(base, server_id, token, offset)
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as exc:
        raise HTTPException(502, "Recently added media is temporarily unavailable.") from exc
    raise HTTPException(409, "This media server is not supported.")


def resume_for_member(provider: str, server_id: str, account_id: str, token: str) -> list[dict]:
    base = f"http://127.0.0.1:{ApplicationCatalog().get(provider).port}"
    try:
        if provider == "jellyfin":
            headers = _jellyfin_headers(base, server_id, token)
            rows = _get(
                base, "/UserItems/Resume", headers, UserId=account_id, Limit=_RECENT_PAGE_SIZE,
                IncludeItemTypes="Movie,Episode", MediaTypes="Video",
            ).json()["Items"]
            return [
                _card(row["Id"], row.get("SeriesName") or row["Name"], "tv" if row["Type"] == "Episode" else "movie", None)
                | {"posterId": str(row.get("SeriesId") or row["Id"]), "detail": row["Name"] if row["Type"] == "Episode" else ""}
                for row in rows[:_RECENT_PAGE_SIZE]
                if row.get("Type") in ("Movie", "Episode") and row.get("Id") and row.get("Name")
            ]
        if provider == "plex":
            headers, sections = _plex_sections(base, server_id, token)
            payload = _get(base, "/hubs/home/continueWatching", headers, count=_RECENT_PAGE_SIZE).json()["MediaContainer"]
            rows = payload.get("Metadata")
            if rows is None:
                rows = [row for hub in payload.get("Hub", []) for row in hub.get("Metadata", [])]
            return [
                _card(row["ratingKey"], row.get("grandparentTitle") or row["title"], "tv" if row["type"] == "episode" else "movie", None)
                | {"posterId": str(row.get("grandparentRatingKey") or row["ratingKey"]), "detail": row["title"] if row["type"] == "episode" else ""}
                for row in rows[:_RECENT_PAGE_SIZE]
                if row.get("type") in ("movie", "episode") and row.get("ratingKey") and row.get("title")
                and str(row.get("librarySectionID")) in sections
            ]
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as exc:
        raise HTTPException(502, "Could not load Continue watching.") from exc
    raise HTTPException(409, "This media server is not supported.")


def poster_for_member(provider: str, server_id: str, account_id: str, token: str, item_id: str) -> tuple[bytes, str]:
    port = ApplicationCatalog().get(provider).port
    base = f"http://127.0.0.1:{port}"
    missing = HTTPException(404, "Artwork not found.")
    try:
        if provider == "jellyfin" and re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F-]{36}", item_id):
            headers = _jellyfin_headers(base, server_id, token)
            rows = _get(base, "/Items", headers, UserId=account_id, Ids=item_id, Recursive="true").json()["Items"]
            if not any(str(row.get("Id", "")).replace("-", "").lower() == item_id.replace("-", "").lower() for row in rows):
                raise missing
            path = f"/Items/{item_id}/Images/Primary"
            params = {"MaxWidth": 360, "MaxHeight": 540, "Format": "jpg"}
        elif provider == "plex" and re.fullmatch(r"[0-9]{1,20}", item_id):
            headers, sections = _plex_sections(base, server_id, token)
            metadata = _get(base, f"/library/metadata/{item_id}", headers).json()["MediaContainer"]
            row = next((
                row for row in metadata.get("Metadata", [])
                if str(row.get("ratingKey")) == item_id
                and str(row.get("librarySectionID") or metadata.get("librarySectionID")) in sections
            ), None)
            if row is None:
                raise missing
            path = f"/library/metadata/{item_id}/thumb"
            thumb = row.get("thumb")
            if isinstance(thumb, str) and re.fullmatch(rf"{path}(?:/[0-9]+)?", thumb):
                path = thumb
            params = {}
        else:
            raise missing
        image = requests.get(
            f"{base}{path}", headers={**headers, "Accept": "image/*"}, params=params,
            timeout=5, stream=True, allow_redirects=False,
        )
        try:
            mime = image.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if image.status_code != 200 or mime not in ("image/jpeg", "image/png", "image/webp", "image/avif"):
                raise missing
            body = bytearray()
            for chunk in image.iter_content(chunk_size=65536):
                body.extend(chunk)
                if len(body) > 2 * 1024 * 1024:
                    raise missing
            return bytes(body), mime
        finally:
            image.close()
    except (requests.RequestException, ValueError, KeyError, TypeError, AttributeError, ET.ParseError) as exc:
        raise missing from exc


def member_inventory(
    provider: str, server_id: str, account_id: str, token: str, titles: dict[tuple[str, int], str],
) -> dict[tuple[str, int], dict[int, set[int]]]:
    """Return movie matches and accessible episode numbers per series season."""
    if not titles:
        return {}
    base = f"http://127.0.0.1:{ApplicationCatalog().get(provider).port}"
    failures = (HTTPException, requests.RequestException, ValueError, KeyError, TypeError, AttributeError)
    try:
        if provider == "jellyfin":
            headers = _jellyfin_headers(base, server_id, token)
            sections = None
        elif provider == "plex":
            headers, sections = _plex_sections(base, server_id, token)
        else:
            return {}
    except (*failures, ET.ParseError):
        return {}

    def matches(kind: str, media_id: int, title: str):
        if sections is None:
            item_type = "Movie" if kind == "movie" else "Series"
            rows = _get(
                base, "/Items", headers, UserId=account_id, Recursive="true", IncludeItemTypes=item_type,
                SearchTerm=title, Fields="ProviderIds", Limit=50,
            ).json()["Items"]
            return [
                row for row in rows if row.get("Type") == item_type
                and str((row.get("ProviderIds") or {}).get("Tmdb")) == str(media_id)
            ]

        rows = []
        for section in sections:
            metadata = _get(
                base, f"/library/sections/{section}/all", headers, type=1 if kind == "movie" else 2,
                title=title, includeGuids=1, **{"X-Plex-Container-Start": 0, "X-Plex-Container-Size": 50},
            ).json()["MediaContainer"].get("Metadata", [])
            rows.extend(
                row for row in metadata if row.get("type") == ("movie" if kind == "movie" else "show")
                and any(guid.get("id") == f"tmdb://{media_id}" for guid in row.get("Guid", []))
            )
        return rows

    def episode_numbers(show: dict) -> dict[int, set[int]]:
        if sections is None:
            item_id = str(show.get("Id") or "")
            if not re.fullmatch(r"[0-9a-fA-F]{32}|[0-9a-fA-F-]{36}", item_id):
                return {}
            episodes = _get(
                base, "/Items", headers, UserId=account_id, ParentId=item_id, Recursive="true",
                IncludeItemTypes="Episode", IsMissing="false", Limit=2000,
            ).json()["Items"]
            numbers = (
                (row.get("ParentIndexNumber"), row.get("IndexNumber")) for row in episodes
                if row.get("Type") == "Episode" and row.get("LocationType") != "Virtual"
            )
        else:
            item_id = str(show.get("ratingKey") or "")
            if not re.fullmatch(r"[0-9]{1,20}", item_id):
                return {}
            episodes = _get(
                base, f"/library/metadata/{item_id}/allLeaves", headers,
                **{"X-Plex-Container-Start": 0, "X-Plex-Container-Size": 2000},
            ).json()["MediaContainer"].get("Metadata", [])
            numbers = (
                (row.get("parentIndex"), row.get("index")) for row in episodes
                if row.get("type") == "episode" and str(row.get("grandparentRatingKey")) == item_id
            )
        seasons: dict[int, set[int]] = {}
        for season, episode in numbers:
            if type(season) is int and season >= 0:
                visible = seasons.setdefault(season, set())
                if type(episode) is int and episode > 0:
                    visible.add(episode)
        return seasons

    def match(entry):
        key, title = entry
        kind, media_id = key
        try:
            rows = matches(kind, media_id, title)
            if kind == "movie":
                return key, {} if rows else None
            seasons: dict[int, set[int]] = {}
            for row in rows:
                for season, numbers in episode_numbers(row).items():
                    seasons.setdefault(season, set()).update(numbers)
            return key, seasons or None
        except failures:
            return key, None

    with ThreadPoolExecutor(max_workers=6) as pool:
        return {key: value for key, value in pool.map(match, titles.items()) if value is not None}
