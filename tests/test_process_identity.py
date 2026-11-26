import os
import sys
from pathlib import Path

import pytest

from core.settings import Settings


@pytest.fixture
def identity_context(tmp_path, monkeypatch):
    from core import process_identity

    config = Settings(
        AMM_CONFIG_DIR=tmp_path / "config",
        PUID=99,
        PGID=100,
    )
    monkeypatch.setattr(process_identity, "settings", config)
    monkeypatch.setattr(process_identity.sys, "platform", "linux")
    monkeypatch.setattr(process_identity.os, "geteuid", lambda: 0)
    # Host unit tests cannot chown as root. Real UID/file ownership is checked
    # separately by running a supervised child in the Linux appliance.
    monkeypatch.setattr(process_identity.os, "chown", lambda *args, **kwargs: None)
    return process_identity, config


def test_catalog_children_drop_root_and_use_writable_home(identity_context):
    module, config = identity_context
    env = {"HOME": "/root", "USER": "root", "LOGNAME": "root"}
    options = module.prepare_process_identity("sonarr", env)
    assert options["user"] == 99
    assert options["group"] == 100
    assert 0 not in options["extra_groups"]
    assert options["umask"] == 0o002
    assert env["HOME"] == str(config.config_dir / "sonarr")
    assert env["USER"] != "root"
    assert Path(env["HOME"]).is_dir()


def test_internal_services_keep_manager_privileges(identity_context):
    module, _ = identity_context
    env = {"HOME": "/root"}
    assert module.prepare_process_identity("jellyfin-cf-origin", env) == {}
    assert env == {"HOME": "/root"}


def test_unprivileged_manager_can_launch_with_its_configured_identity(identity_context, monkeypatch):
    module, _ = identity_context
    monkeypatch.setattr(module.os, "geteuid", lambda: 99)
    monkeypatch.setattr(module.os, "getegid", lambda: 100)
    assert module.prepare_process_identity("sonarr", {}) == {"umask": 0o002}


@pytest.mark.parametrize("uid,gid", [(1001, 100), (99, 1001)])
def test_unprivileged_manager_rejects_mismatched_identity(identity_context, monkeypatch, uid, gid):
    module, _ = identity_context
    monkeypatch.setattr(module.os, "geteuid", lambda: uid)
    monkeypatch.setattr(module.os, "getegid", lambda: gid)
    with pytest.raises(RuntimeError, match="PUID=99/PGID=100"):
        module.prepare_process_identity("sonarr", {})


def test_wireguard_wrapper_retains_privilege_to_enter_its_mount_namespace(identity_context, monkeypatch):
    from core.vpn import vpn_manager

    module, _ = identity_context
    monkeypatch.setattr(vpn_manager, "uses_uid_isolation", lambda: True)
    env = {"HOME": "/root"}
    assert module.prepare_process_identity("qbittorrent", env) == {"umask": 0o002}


def test_ownership_migration_does_not_follow_symlinks(tmp_path):
    from core.process_identity import _own_tree

    root = tmp_path / "app"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "file").write_text("keep")
    (root / "link").symlink_to(outside, target_is_directory=True)
    # A dangling link must not cause a failed startup either.
    (root / "missing").symlink_to(tmp_path / "missing")
    _own_tree(root, os.getuid(), os.getgid())
    assert (outside / "file").read_text() == "keep"


@pytest.mark.asyncio
async def test_identity_preparation_failure_marks_process_failed(monkeypatch):
    from core import process_identity
    from core.supervisor import ProcessSupervisor, ProcessState

    def fail(name, env):
        raise RuntimeError("Cannot use configured identity")

    monkeypatch.setattr(process_identity, "prepare_process_identity", fail)
    supervisor = ProcessSupervisor.get()
    with pytest.raises(RuntimeError, match="configured identity"):
        await supervisor.start("identity-failure", [sys.executable, "-c", "pass"])
    assert supervisor.status("identity-failure") == ProcessState.FAILED


@pytest.mark.skipif(sys.platform != "linux" or os.geteuid() != 0, reason="Linux root appliance check")
@pytest.mark.asyncio
async def test_supervised_child_creates_files_as_configured_uid(tmp_path, monkeypatch):
    from core import process_identity
    from core.supervisor import ProcessSupervisor, RestartPolicy

    config = Settings(AMM_CONFIG_DIR=tmp_path / "config", PUID=99, PGID=100)
    monkeypatch.setattr(process_identity, "settings", config)
    # pytest temp parents are private; allow the child to traverse this fixture.
    for parent in (tmp_path, *tmp_path.parents):
        if str(parent) == "/tmp":
            break
        parent.chmod(parent.stat().st_mode | 0o111)
    supervisor = ProcessSupervisor.get()
    await supervisor.start(
        "sonarr",
        [sys.executable, "-c", "import os,pathlib; p=pathlib.Path(os.environ['HOME']); (p/'new').mkdir(); (p/'new'/'file').write_text('test')"],
        restart_policy=RestartPolicy.NEVER,
    )
    proc = supervisor._entries["sonarr"].process
    await proc.wait()
    assert proc.returncode == 0
    path = config.config_dir / "sonarr" / "new"
    assert (path.stat().st_uid, path.stat().st_gid) == (99, 100)
    assert path.stat().st_mode & 0o777 == 0o775
    assert (path / "file").stat().st_mode & 0o777 == 0o664
