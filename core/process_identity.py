"""Apply the configured appliance identity to catalog processes, not host helpers."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from core.settings import settings


def _own_tree(path: Path, uid: int, gid: int) -> None:
    """Migrate app-owned state without following links into libraries or host paths."""
    if path.is_symlink():
        raise RuntimeError(f"Cannot prepare application ownership through symlink: {path}")
    path.mkdir(parents=True, exist_ok=True)
    for root, dirs, files in os.walk(path, followlinks=False):
        for target in (Path(root), *(Path(root) / name for name in dirs + files)):
            if target.is_symlink():
                continue
            try:
                info = target.lstat()
                if (info.st_uid, info.st_gid) != (uid, gid):
                    os.chown(target, uid, gid, follow_symlinks=False)
            except FileNotFoundError:
                # Apps can remove temporary state while another service starts.
                continue


def prepare_process_identity(name: str, env: dict[str, str]) -> dict:
    """Return POSIX spawn options; namespace launchers drop identity inside the namespace."""
    if sys.platform != "linux":
        return {}

    from applications.catalog import PLUGIN_CLASSES
    from core.vpn import VPN_TUNNELED_APPS, vpn_manager

    plugin_class = next((cls for cls in PLUGIN_CLASSES if cls.manifest.name == name), None)
    if plugin_class is None:
        return {}  # nginx and other privileged appliance helpers are not catalog apps.
    if name in VPN_TUNNELED_APPS and vpn_manager.uses_uid_isolation():
        # setpriv runs inside a private resolver mount namespace and selects UID 910.
        # Dropping privileges before that wrapper would break isolation.
        return {"umask": 0o002}

    uid, gid = settings.puid, settings.pgid
    if os.geteuid() != 0:
        if (os.geteuid(), os.getegid()) != (uid, gid):
            raise RuntimeError(f"Cannot launch {name} as PUID={uid}/PGID={gid} from this unprivileged manager")
        return {"umask": 0o002}

    plugin = plugin_class(
        base_config_dir=settings.config_dir,
        base_install_dir=settings.install_dir,
        puid=uid,
        pgid=gid,
    )
    for path in (
        settings.config_dir / name,
        plugin.install_dir,
        settings.cache_dir / name,
        settings.config_dir / "logs" / name,
    ):
        _own_tree(path, uid, gid)
    plugin.config_dir.mkdir(parents=True, exist_ok=True)
    os.chown(plugin.config_dir, uid, gid, follow_symlinks=False)
    env.update(HOME=str(plugin.config_dir), USER=str(uid), LOGNAME=str(uid))

    if name in VPN_TUNNELED_APPS and vpn_manager.uses_netns_isolation():
        return {"umask": 0o002}  # ip netns exec must precede setpriv.

    # Keep GPU access without inheriting the manager's root supplementary groups.
    device_groups = {
        device.stat().st_gid for device in Path("/dev/dri").glob("*")
        if device.is_char_device() and device.stat().st_gid != 0
    }
    return {"user": uid, "group": gid, "extra_groups": sorted(device_groups), "umask": 0o002}
