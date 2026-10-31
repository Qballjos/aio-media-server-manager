from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from api.routers import homepage as routes
from core import homepage


@pytest.fixture
def jellyfin(monkeypatch, tmp_path):
    plugin = SimpleNamespace(name="jellyfin", port=8096, config_dir=tmp_path)
    monkeypatch.setattr(homepage, "ApplicationCatalog", lambda: SimpleNamespace(has=lambda name: name == "jellyfin", get=lambda name: plugin))
    monkeypatch.setattr(homepage, "_running_names", lambda: {"jellyfin"})
    monkeypatch.setattr(homepage, "get_application_api_key", lambda *args: "fixture-only")


@pytest.mark.parametrize("image,width,height", [("Primary", 240, 360), ("Primary", 780, 1170), ("Backdrop", 1280, 720)])
def test_art_respects_shape_and_resolution(jellyfin, monkeypatch, image, width, height):
    calls = []

    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return b"full-resolution-image", "image/jpeg", None

    monkeypatch.setattr(homepage, "_fetch_bytes", fetch)
    assert homepage.homepage_art("jellyfin", "item", image, width, height) == (b"full-resolution-image", "image/jpeg")
    assert calls[0][0].endswith("/Items/item/Images/" + image)
    assert calls[0][1]["params"] == {"fillWidth": str(width), "fillHeight": str(height), "quality": "90"}


def test_missing_backdrop_falls_back_to_full_poster(jellyfin, monkeypatch):
    calls = []

    def fetch(url, **kwargs):
        calls.append((url, kwargs))
        return (None, "", "HTTP 404") if url.endswith("Backdrop") else (b"poster", "image/jpeg", None)

    monkeypatch.setattr(homepage, "_fetch_bytes", fetch)
    assert homepage.homepage_art("jellyfin", "item", "Backdrop", 1280, 720)[0] == b"poster"
    assert calls[1][0].endswith("/Images/Primary")
    assert calls[1][1]["params"]["maxWidth"] == "1280"


def test_auth_failure_is_not_retried_as_other_art(jellyfin, monkeypatch):
    calls = []

    def fetch(url, **kwargs):
        calls.append(url)
        return None, "", "HTTP 401"

    monkeypatch.setattr(homepage, "_fetch_bytes", fetch)
    assert homepage.homepage_art("jellyfin", "item", "Backdrop")[0] is None
    assert len(calls) == 1


def test_art_route_forwards_valid_sizes_and_rejects_unbounded_inputs(monkeypatch):
    monkeypatch.setattr(routes, "_ensure_authenticated", lambda request: None)
    calls = []

    def art(*args):
        calls.append(args)
        return b"image", "image/jpeg"

    monkeypatch.setattr(routes, "homepage_art", art)
    app = FastAPI()
    app.include_router(routes.router)
    with TestClient(app) as client:
        path = "/api/homepage/art?source=jellyfin&item_id=item"
        assert client.get(path + "&image=Backdrop&fillWidth=1280&fillHeight=720").status_code == 200
        assert calls[-1] == ("jellyfin", "item", "Backdrop", 1280, 720)
        for query in ["image=../Other", "fillWidth=0", "fillWidth=3841", "fillHeight=2161"]:
            assert client.get(path + "&" + query).status_code == 422


@pytest.mark.parametrize("kind,types", [("movie", "Movie"), ("tv", "Series"), ("", "Series,Movie")])
def test_library_pages_filter_media_type(jellyfin, monkeypatch, kind, types):
    monkeypatch.setattr(homepage, "_source_ready", lambda *args, **kwargs: True)
    calls = []

    def fetch(url, **kwargs):
        calls.append(kwargs["params"])
        return {"Items": []}, None

    monkeypatch.setattr(homepage, "_fetch_json", fetch)
    homepage.homepage_recent("media.example.invalid", 3, "https", kind)
    assert calls[0]["IncludeItemTypes"] == types
    assert calls[0]["StartIndex"] == "40"
    assert calls[0]["Limit"] == "20"
