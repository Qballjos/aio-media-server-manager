"""Starter indexers in Prowlarr, with FlareSolverr attached where Cloudflare blocks them."""

from unittest.mock import MagicMock, patch

import pytest

from core.integrations.engine import IntegrationEngine
from core.integrations.prowlarr import ProwlarrClient
from core.settings import Settings


def _resp(status, payload=None, text=""):
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = payload if payload is not None else {}
    resp.text = text
    return resp


def _definition(name, privacy="public", urls=("https://example.org/",)):
    return {
        "name": name,
        "definitionName": name,
        "implementation": "Cardigann",
        "configContract": "CardigannSettings",
        "privacy": privacy,
        "protocol": "torrent",
        "enable": True,
        "appProfileId": 0,
        "priority": 25,
        "tags": [],
        "indexerUrls": list(urls),
        "fields": [{"name": "baseUrl", "value": None, "type": "select"}, {"name": "definitionFile", "value": name}],
    }


def _get_router(indexers, schema):
    def get(url, **kwargs):
        if url.endswith("/indexer/schema"):
            return _resp(200, schema)
        if url.endswith("/indexer"):
            return _resp(200, indexers)
        return _resp(404, [])

    return get


@patch("requests.post")
@patch("requests.get")
def test_add_starter_indexers_adds_only_known_public_definitions(mock_get, mock_post):
    mock_get.side_effect = _get_router([], [_definition("1337x"), _definition("Secret", privacy="private"), _definition("YTS")])
    mock_post.return_value = _resp(201, {"id": 1})
    client = ProwlarrClient(api_key="k")
    result = client.add_starter_indexers(wanted=("1337x", "YTS", "Secret", "Nope"))
    assert result == {"added": ["1337x", "YTS"], "disabled": [], "missing": ["Secret", "Nope"]}
    bodies = [call.kwargs["json"] for call in mock_post.call_args_list]
    assert [body["name"] for body in bodies] == ["1337x", "YTS"]
    assert all(body["enable"] is True and body["appProfileId"] == 1 for body in bodies)
    base_url = next(field for field in bodies[0]["fields"] if field["name"] == "baseUrl")
    assert base_url["value"] == "https://example.org/"


@patch("requests.post")
@patch("requests.get")
def test_add_starter_indexers_skips_existing_and_already_tried(mock_get, mock_post):
    mock_get.side_effect = _get_router([{"name": "YTS"}], [_definition("1337x"), _definition("YTS"), _definition("EZTV")])
    mock_post.return_value = _resp(201, {"id": 1})
    client = ProwlarrClient(api_key="k")
    result = client.add_starter_indexers(wanted=("1337x", "YTS", "EZTV"), skip={"EZTV"})
    assert result["added"] == ["1337x"]
    assert mock_post.call_count == 1


@patch("requests.post")
@patch("requests.get")
def test_add_starter_indexers_saves_a_failing_indexer_disabled(mock_get, mock_post):
    mock_get.side_effect = _get_router([], [_definition("1337x")])
    mock_post.side_effect = [_resp(400, text="Unable to connect to indexer"), _resp(201, {"id": 3})]
    client = ProwlarrClient(api_key="k")
    result = client.add_starter_indexers(wanted=("1337x",))
    assert result == {"added": [], "disabled": ["1337x"], "missing": []}
    assert mock_post.call_args_list[1].kwargs["json"]["enable"] is False


@pytest.mark.parametrize("initially_disabled", [False, True])
@patch("core.integrations.prowlarr.set_wiring_progress")
@patch("requests.put")
@patch("requests.post")
@patch("requests.get")
def test_starter_indexers_tags_only_cloudflare_blocked_indexers(
    mock_get, mock_post, mock_put, mock_progress, tmp_path, initially_disabled
):
    indexers = [
        {"id": 1, "name": "1337x", "enable": not initially_disabled, "tags": []},
        {"id": 2, "name": "YTS", "enable": not initially_disabled, "tags": []},
    ]
    proxy = {"id": 5, "name": "Flaresolverr (AMM)", "implementation": "FlareSolverr", "tags": []}

    def get(url, **kwargs):
        if url.endswith("/tag"):
            return _resp(200, [])
        if url.endswith("/indexerProxy"):
            return _resp(200, [proxy])
        if url.endswith("/indexer"):
            return _resp(200, indexers)
        return _resp(404, [])

    def post(url, **kwargs):
        if url.endswith("/tag"):
            return _resp(201, {"id": 7, "label": "flaresolverr"})
        if url.endswith("/indexer/test"):
            name = kwargs["json"]["name"]
            mock_progress.assert_called_with(f"Checking whether {name} needs FlareSolverr")
            if kwargs["json"]["name"] == "1337x":
                return _resp(400, text='[{"errorMessage":"Unable to access 1337x.to, blocked by CloudFlare Protection."}]')
            return _resp(200, {})
        return _resp(404)

    mock_get.side_effect = get
    mock_post.side_effect = post
    mock_put.return_value = _resp(202, {})
    client = ProwlarrClient(api_key="k")
    engine = IntegrationEngine(Settings(config_dir=tmp_path / "config"))
    starter = {
        "added": [] if initially_disabled else ["1337x", "YTS"],
        "disabled": ["1337x", "YTS"] if initially_disabled else [],
        "missing": [],
    }
    with (
        patch.object(client, "add_starter_indexers", return_value=starter),
        patch.object(engine, "_installed", return_value=True),
    ):
        report = engine._starter_indexers_step(client)
    assert "flaresolverr=1337x" in report["detail"]
    put_calls = {call.args[0].split("?")[0].rsplit("/", 1)[-1]: call for call in mock_put.call_args_list}
    assert put_calls["5"].kwargs["json"]["tags"] == [7]  # the proxy now only serves tagged indexers
    assert "forceSave=true" in put_calls["5"].args[0]
    assert put_calls["1"].kwargs["json"]["tags"] == [7]
    assert put_calls["1"].kwargs["json"]["enable"] is True
    assert indexers[1]["tags"] == []
    assert indexers[1]["enable"] is not initially_disabled
    assert "forceSave=true" in put_calls["1"].args[0]
    assert [call.args[0] for call in mock_progress.call_args_list] == [
        "Preparing FlareSolverr indexer connections",
        "Checking whether 1337x needs FlareSolverr",
        "Connecting 1337x to FlareSolverr",
        "Checking whether YTS needs FlareSolverr",
    ]


@patch("core.integrations.prowlarr.time.sleep", lambda *_: None)
@patch("core.integrations.prowlarr.set_wiring_progress")
@patch("requests.post")
@patch("requests.get")
def test_indexer_definitions_waits_for_the_definition_update_command(mock_get, mock_post, mock_progress):
    schema_calls = []
    few = [_definition("Knaben")]
    many = [_definition(f"Public{i}") for i in range(25)]

    def get(url, **kwargs):
        if url.endswith("/indexer/schema"):
            mock_progress.assert_called_with(
                "Reading Prowlarr's updated indexer catalog" if schema_calls else "Reading Prowlarr's indexer catalog"
            )
            schema_calls.append(url)
            return _resp(200, few if len(schema_calls) == 1 else many)
        if url.endswith("/command/9"):
            mock_progress.assert_called_with("Updating Prowlarr's indexer catalog")
            return _resp(200, {"id": 9, "status": "completed"})
        return _resp(404, [])

    mock_get.side_effect = get
    mock_post.return_value = _resp(201, {"id": 9, "name": "IndexerDefinitionUpdate", "status": "started"})
    client = ProwlarrClient(api_key="k")
    defs = client.indexer_definitions(wait=30.0)
    assert len(defs) == 25
    assert mock_post.call_args.kwargs["json"] == {"name": "IndexerDefinitionUpdate"}
    assert len(schema_calls) == 2  # once before the nudge, once after the command finished


def test_starter_indexer_progress_precedes_each_request(monkeypatch):
    client = ProwlarrClient(api_key="k")
    messages = []
    monkeypatch.setattr("core.integrations.prowlarr.set_wiring_progress", messages.append)

    def get(path, **kwargs):
        if path == "/indexer":
            assert messages[-1] == "Checking configured Prowlarr indexers"
            return [{"name": "EZTV"}]
        assert path == "/indexer/schema"
        assert messages[-1] == "Reading Prowlarr's indexer catalog"
        return [_definition(name) for name in ("1337x", "YTS", "EZTV", "Knaben")]

    def post(path, body, **kwargs):
        assert path == "/indexer"
        expected = "Checking and adding indexer" if body["enable"] else "Saving unavailable indexer"
        assert messages[-1] == f"{expected}: {body['name']}"
        return _resp(400 if body["name"] == "1337x" and body["enable"] else 201)

    monkeypatch.setattr(client, "_get", get)
    monkeypatch.setattr(client, "_post", post)
    assert client.add_starter_indexers(wanted=("1337x", "YTS", "EZTV", "Knaben"), skip={"Knaben"}) == {
        "added": ["YTS"], "disabled": ["1337x"], "missing": []
    }
    assert messages == [
        "Checking configured Prowlarr indexers",
        "Reading Prowlarr's indexer catalog",
        "Checking and adding indexer: 1337x",
        "Saving unavailable indexer: 1337x",
        "Checking and adding indexer: YTS",
    ]


def test_starter_indexers_run_in_the_background_without_overlap(monkeypatch):
    import threading

    from core.integrations import engine as engine_mod
    from core.integrations.engine import IntegrationEngine

    started = threading.Event()
    release = threading.Event()
    seen: list[str] = []

    def fake_step(self, client, *, progress=None):
        seen.append(threading.current_thread().name)
        started.set()
        release.wait(5)
        return {"target": "prowlarr", "action": "starter_indexers", "status": "success", "detail": "added=YTS"}

    monkeypatch.setattr(IntegrationEngine, "_starter_indexers_step", fake_step)
    engine = IntegrationEngine()
    first = engine._schedule_starter_indexers(object())
    assert first["target"] == "prowlarr" and first["status"] == "success"
    assert "background" in first["detail"]
    assert started.wait(5)
    # A second wiring pass while the first run is still busy must not start another.
    second = engine._schedule_starter_indexers(object())
    assert "already" in second["detail"]
    release.set()
    for _ in range(50):
        if not engine_mod._starter_indexers_lock.locked():
            break
        threading.Event().wait(0.1)
    assert not engine_mod._starter_indexers_lock.locked()
    assert seen == ["prowlarr-starter-indexers"]
