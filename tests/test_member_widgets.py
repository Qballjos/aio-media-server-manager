from types import SimpleNamespace

import pytest

from core.integrations import member_library
from core.integrations.seerr import SeerrClient


@pytest.mark.parametrize("provider", ["jellyfin", "plex"])
def test_resume_uses_viewer_token_and_filters_library_rows(monkeypatch, provider):
    monkeypatch.setattr(member_library, "ApplicationCatalog", lambda: SimpleNamespace(
        get=lambda _: SimpleNamespace(port=8096),
    ))

    def get(base, path, headers, **params):
        assert base == "http://127.0.0.1:8096"
        if provider == "jellyfin":
            assert "viewer-token" in " ".join(headers.values())
            if path == "/System/Info/Public":
                return SimpleNamespace(json=lambda: {"Id": "server"})
            assert path == "/UserItems/Resume"
            assert params["UserId"] == "member"
            return SimpleNamespace(json=lambda: {"Items": [
                {"Id": "episode", "Type": "Episode", "Name": "Episode 2", "SeriesId": "series", "SeriesName": "Show"},
            ]})
        assert headers["X-Plex-Token"] == "viewer-token"
        if path == "/identity":
            return SimpleNamespace(text='<MediaContainer machineIdentifier="server" />')
        if path == "/library/sections":
            return SimpleNamespace(json=lambda: {"MediaContainer": {"Directory": [{"key": "1", "type": "show"}]}})
        assert path == "/hubs/home/continueWatching"
        return SimpleNamespace(json=lambda: {"MediaContainer": {"Metadata": [
            {"ratingKey": "episode", "type": "episode", "title": "Episode 2", "grandparentRatingKey": "series",
             "grandparentTitle": "Show", "librarySectionID": 1},
            {"ratingKey": "private", "type": "movie", "title": "Private", "librarySectionID": 2},
        ]}})

    monkeypatch.setattr(member_library, "_get", get)
    assert member_library.resume_for_member(provider, "server", "member", "viewer-token") == [
        {"id": "episode", "title": "Show", "mediaType": "tv", "posterId": "series", "detail": "Episode 2"},
    ]


def test_calendar_request_coverage_excludes_other_users_and_declined_seasons(monkeypatch):
    with SeerrClient() as client:
        rows = [
            {"requestedBy": {"id": 7}, "status": 2, "type": "tv", "media": {"tmdbId": 10},
             "seasons": [{"seasonNumber": 1, "status": 3}, {"seasonNumber": 2, "status": 2}]},
            {"requestedBy": {"id": 8}, "status": 2, "type": "movie", "media": {"tmdbId": 11}},
            {"requestedBy": {"id": 7}, "status": 1, "type": "movie", "media": {"tmdbId": 12}},
        ]

        def requests(user_id, take, skip):
            assert (user_id, take, skip) == (7, 100, 0)
            return {"results": rows, "pageInfo": {"results": len(rows)}}

        monkeypatch.setattr(client, "user_requests", requests)

        def details(path):
            assert path == "/tv/10"
            return {"externalIds": {"tvdbId": 19}}

        monkeypatch.setattr(client, "_media_users_api", details)
        assert client.calendar_request_coverage(7) == {("episode", 19): {2}, ("movie", 12): set()}
