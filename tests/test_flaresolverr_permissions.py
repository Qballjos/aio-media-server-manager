import stat

from applications.community import FlaresolverrApp


def test_start_repairs_runtime_for_vpn_uid_without_following_links(tmp_path, monkeypatch):
    from core.vpn import vpn_manager

    app = FlaresolverrApp(base_config_dir=tmp_path, base_install_dir=tmp_path)
    runtime = app.install_dir
    dynload = runtime / "_internal" / "python3.11" / "lib-dynload"
    dynload.mkdir(parents=True)
    extension = dynload / "_struct.cpython-311-x86_64-linux-gnu.so"
    extension.write_bytes(b"extension")
    extension.chmod(0o600)
    executable = runtime / "flaresolverr"
    executable.write_bytes(b"binary")
    executable.chmod(0o751)
    outside = tmp_path / "private"
    outside.mkdir(mode=0o700)
    (runtime / "external").symlink_to(outside, target_is_directory=True)
    for directory in (runtime, runtime / "_internal", dynload.parent, dynload):
        directory.chmod(0o711)
    monkeypatch.setattr(vpn_manager, "wrap_isolated_command", lambda cmd: cmd)

    app.build_start_command(executable)

    for directory in (runtime, runtime / "_internal", dynload.parent, dynload):
        assert stat.S_IMODE(directory.stat().st_mode) == 0o755
    assert stat.S_IMODE(extension.stat().st_mode) == 0o644
    assert stat.S_IMODE(executable.stat().st_mode) == 0o755
    assert stat.S_IMODE(outside.stat().st_mode) == 0o700
    app.build_start_command(executable)
    assert stat.S_IMODE(extension.stat().st_mode) == 0o644
