"""The GPU probe must not fail on a host whose kernel module files cannot be read."""

from pathlib import Path

from core import transcoding


def test_loaded_module_is_detected_without_reading_its_files(tmp_path, monkeypatch):
    module = tmp_path / "i915"
    module.mkdir()
    uevent = module / "uevent"
    uevent.write_text("")
    uevent.chmod(0o200)  # write-only, like sysfs: reading it raised PermissionError on Synology
    monkeypatch.setattr(transcoding, "_SYS_MODULE", tmp_path)
    result = transcoding.probe_transcoding()
    assert result["intel_quicksync"] is True
    assert result["available"] is True
    assert "jellyfin_ffmpeg" in result


def test_probe_reports_jellyfin_ffmpeg_when_present(tmp_path, monkeypatch):
    ffmpeg = tmp_path / "ffmpeg"
    ffmpeg.write_text("x", encoding="utf-8")
    real_is_file = Path.is_file

    def fake_is_file(self: Path) -> bool:
        if str(self) == "/usr/lib/jellyfin-ffmpeg/ffmpeg":
            return True
        return real_is_file(self)

    monkeypatch.setattr(Path, "is_file", fake_is_file)
    result = transcoding.probe_transcoding()
    assert result["jellyfin_ffmpeg"] == "/usr/lib/jellyfin-ffmpeg/ffmpeg"
