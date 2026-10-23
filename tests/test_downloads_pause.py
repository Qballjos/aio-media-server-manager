"""Pause all / Resume all across the download clients."""

from types import SimpleNamespace

from core import downloads_pause


class FakeSab:
    def __init__(self):
        self.calls = []

    def _request(self, mode, extra=None):
        self.calls.append((mode, extra))
        return {"status": True}


class FakeQbit:
    base_url = "http://qbit/api/v2"

    def __init__(self, rows):
        self.posts = []
        self.session = SimpleNamespace(
            get=lambda url, timeout: SimpleNamespace(json=lambda: rows),
            post=self._post,
        )

    def _post(self, url, data, timeout):
        self.posts.append((url.rsplit("/", 1)[-1], data["hashes"]))
        return SimpleNamespace(status_code=200)


def test_pause_and_resume_leave_your_own_paused_torrents_alone(monkeypatch, tmp_path):
    sab = FakeSab()
    qbit = FakeQbit([{"hash": "a", "state": "downloading"}, {"hash": "b", "state": "stoppedDL"}, {"hash": "c", "state": "stalledUP"}])
    monkeypatch.setattr(downloads_pause, "_state_path", lambda: tmp_path / "pause.json")
    monkeypatch.setattr(downloads_pause, "_clients", lambda: {"sabnzbd": sab, "qbittorrent": qbit})

    state = downloads_pause.pause_all(30)
    assert state["paused"] is True and state["resume_at"]
    assert sab.calls == [("config", {"name": "set_pause", "value": 30})]  # SAB keeps its own timer
    assert qbit.posts == [("stop", "a|c")]  # b was already paused by you

    state = downloads_pause.resume_all()
    assert state == {"applied": {"sabnzbd": True, "qbittorrent": True}, "paused": False, "resume_at": None}
    assert sab.calls[-1] == ("resume", None)
    assert qbit.posts[-1] == ("start", "a|c")
    assert not (tmp_path / "pause.json").exists()


def test_pause_until_resumed_has_no_resume_time(monkeypatch, tmp_path):
    sab = FakeSab()
    monkeypatch.setattr(downloads_pause, "_state_path", lambda: tmp_path / "pause.json")
    monkeypatch.setattr(downloads_pause, "_clients", lambda: {"sabnzbd": sab})
    state = downloads_pause.pause_all(None)
    assert state == {"applied": {"sabnzbd": True}, "paused": True, "resume_at": None}
    assert sab.calls == [("pause", None)]
