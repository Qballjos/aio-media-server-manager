"""The GPU probe must not fail on a host whose kernel module files cannot be read."""

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
