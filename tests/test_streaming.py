from core.integrations.streaming import streaming_availability
from core.media_users import MediaUsers


def test_streaming_matches_only_selected_regional_subscriptions():
    netflix = {"id": 8, "name": "Netflix", "logoPath": "/netflix.jpg"}
    rows = [
        {"iso_3166_1": "US", "flatrate": [netflix]},
        {"iso_3166_1": "NL", "flatrate": [netflix, netflix, None, {"id": 9, "name": "Prime Video"}],
         "buy": [{"id": 10, "name": "Rental"}], "link": "https://example.com/"},
    ]
    assert streaming_availability(rows, ("NL", [8, 10])) == {
        "configured": True,
        "providers": [{"id": 8, "name": "Netflix", "logo_url": "https://image.tmdb.org/t/p/w92/netflix.jpg"}],
        "link": "",
    }
    assert streaming_availability(rows, ("BE", [8]))["providers"] == []
    assert streaming_availability(None, ("", []))["configured"] is False


def test_streaming_preferences_are_account_scoped(tmp_path):
    store = MediaUsers(tmp_path)
    member = ("plex", "server", "member")
    other = ("plex", "server", "other")
    store.set_streaming(member, "NL", [8, 9])
    assert store.streaming(member) == ("NL", [8, 9])
    assert store.streaming(other) == ("", [])
    store.set_streaming(member, "BE", [])
    assert store.streaming(member) == ("BE", [])
