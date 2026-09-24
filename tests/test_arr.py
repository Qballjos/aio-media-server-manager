from pathlib import Path

from applications.sonarr import SonarrApp


def test_sonarr_start_uses_data_dir_and_exe_cwd(tmp_path: Path) -> None:
    install_root = tmp_path / "apps"
    nested = install_root / "sonarr" / "Sonarr"
    nested.mkdir(parents=True)
    exe = nested / "Sonarr"
    exe.write_text("#!/bin/sh\n", encoding="utf-8")
    exe.chmod(0o755)

    app = SonarrApp(base_config_dir=tmp_path / "config", base_install_dir=install_root)
    cmd = app.start_command()

    assert cmd[0] == str(exe)
    assert "-nobrowser" in cmd
    assert f"-port={app.port}" in cmd
    assert app.working_directory() == nested
    assert "linux-core" in app.preferred_patterns()
    assert app.extra_env()["DOTNET_SYSTEM_GLOBALIZATION_INVARIANT"] == "0"
    assert str(nested) in app.extra_env()["LD_LIBRARY_PATH"]
