from core.integrations.member_calendar import _folder_grants, _target_is_shared


def test_future_location_must_match_only_shared_libraries(tmp_path):
    shared = tmp_path / "media" / "shared"
    nested_private = shared / "private"
    folders = _folder_grants([
        ("visible", [str(shared)]),
        ("private", [str(nested_private)]),
    ], {"visible"})
    assert _target_is_shared(str(shared / "Film"), folders)
    assert not _target_is_shared(str(nested_private / "Anime"), folders)
    assert not _target_is_shared(str(shared.with_name("shared-private") / "Film"), folders)
    assert not _target_is_shared(str(shared / ".." / "private" / "Film"), folders)
    assert not _target_is_shared("", folders)


def test_calendar_shows_verified_existing_and_shared_future_titles(monkeypatch):
    from datetime import date, timedelta

    from core.integrations import member_calendar as module

    today = date.today()
    planned = today + timedelta(days=1)
    releases = [
        ({"title": "Future shared", "when": str(planned), "kind": "movie", "detail": "", "has_file": False}, "/media/shared/A", planned),
        ({"title": "Future private", "when": str(planned), "kind": "movie", "detail": "", "has_file": False}, "/media/private/B", planned),
        ({"title": "Current private", "when": str(today), "kind": "movie", "detail": "", "has_file": True}, "/media/shared/C", today),
        ({"title": "Current shared", "when": str(today), "kind": "movie", "detail": "", "has_file": True}, "/media/private/D", today),
        ({"title": "Shared series", "when": str(planned), "kind": "episode", "detail": "S02E08",
          "has_file": False, "milestones": ["season-finale"], "_tvdb": 123}, "/media/shared/E", planned),
    ]
    monkeypatch.setattr(module, "_jellyfin_headers", lambda *_: {})
    monkeypatch.setattr(module, "_jellyfin_folders", lambda *_: _folder_grants(
        [("shared", ["/media/shared"]), ("private", ["/media/private"])], {"shared"},
    ))
    monkeypatch.setattr(module, "_calendar_rows", lambda *_: releases)
    monkeypatch.setattr(module, "_visible_item", lambda *args: args[-1]["title"] == "Current shared")
    events = module.member_calendar("jellyfin", "server", "viewer", "viewer-token", today, planned)
    assert [(event["title"], event["available"]) for event in events] == [
        ("Current shared", True), ("Future shared", False), ("Shared series", False),
    ]
    assert all(set(event) == {"title", "when", "kind", "detail", "available"} for event in events[:2])
    assert events[2]["milestones"] == ["season-finale"]
    assert "_tvdb" not in events[2]


def test_plex_future_folders_require_explicitly_unrestricted_share(monkeypatch):
    from types import SimpleNamespace

    from core.integrations import member_calendar as module

    plugin = SimpleNamespace(port=32400, config_dir=None)
    monkeypatch.setattr(module, "PlexClient", lambda **_: SimpleNamespace(token="owner-token"))
    monkeypatch.setattr(module, "_get", lambda *_: SimpleNamespace(json=lambda: {
        "MediaContainer": {"Directory": [
            {"key": "1", "Location": [{"path": "/media/shared"}]},
            {"key": "2", "Location": [{"path": "/media/private"}]},
        ]},
    }))
    filter_movies = ""

    def get(*args, **kwargs):
        assert kwargs["headers"]["X-Plex-Token"] == "owner-token"
        assert kwargs["allow_redirects"] is False
        return SimpleNamespace(status_code=200, text=(
            f'<MediaContainer><User id="42" restricted="0" filterAll="" filterMovies="{filter_movies}" filterTelevision="">'
            '<Server machineIdentifier="server-a" /></User></MediaContainer>'
        ))

    monkeypatch.setattr(module.requests, "get", get)
    grants = module._plex_folders("http://127.0.0.1:32400", plugin, "42", "server-a", {"1"})
    assert _target_is_shared("/media/shared/Film", grants)
    assert not _target_is_shared("/media/private/Anime", grants)
    filter_movies = "label=Kids"
    assert module._plex_folders("http://127.0.0.1:32400", plugin, "42", "server-a", {"1"}) == []


def test_jellyfin_future_folders_use_viewer_policy_and_current_views(monkeypatch):
    from types import SimpleNamespace

    from core.integrations import member_calendar as module

    policy = {"EnableMediaPlayback": True, "IsDisabled": False, "BlockedMediaFolders": ["blocked"]}
    monkeypatch.setattr(module, "get_application_api_key", lambda *_: "mapping-key")

    def get(_base, path, headers, **params):
        if path == "/Users/Me":
            assert headers == {"Authorization": "viewer-token"}
            payload = {"Id": "viewer", "Policy": policy}
        elif path == "/UserViews":
            assert headers == {"Authorization": "viewer-token"}
            assert params["UserId"] == "viewer"
            payload = {"Items": [{"Id": "shared"}, {"Id": "blocked"}]}
        else:
            assert path == "/Library/VirtualFolders"
            assert 'Token="mapping-key"' in headers["Authorization"]
            payload = [
                {"ItemId": "shared", "Locations": ["/media/shared"]},
                {"ItemId": "blocked", "Locations": ["/media/blocked"]},
                {"ItemId": "private", "Locations": ["/media/private"]},
            ]
        return SimpleNamespace(json=lambda: payload)

    monkeypatch.setattr(module, "_get", get)
    plugin = SimpleNamespace(config_dir=None)
    args = ("http://127.0.0.1:8096", plugin, {"Authorization": "viewer-token"}, "viewer")
    grants = module._jellyfin_folders(*args)
    assert _target_is_shared("/media/shared/Film", grants)
    assert not _target_is_shared("/media/blocked/Film", grants)
    assert not _target_is_shared("/media/private/Anime", grants)
    policy["BlockedTags"] = ["personal"]
    assert module._jellyfin_folders(*args) == []
