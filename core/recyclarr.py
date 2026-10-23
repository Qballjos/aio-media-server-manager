"""TRaSH Guides Recyclarr v8 config and one-shot sync."""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from applications.catalog import ApplicationCatalog
from core.integrations.credentials import get_application_api_key
from core.settings import settings

logger = logging.getLogger(__name__)

PREFS_NAME = "amm-prefs.json"
YAML_NAME = "recyclarr.yml"
LAST_SYNC_NAME = "last-sync.json"
MANAGED_MARK = "AMM Recyclarr managed"
SETTINGS_NAME = "settings.yml"
_GIT_PATH_RE = re.compile(r"^git_path:\s*.*$", re.MULTILINE)
_ERROR_LINE_RE = re.compile(r"\[(?:[\d:]+ )?(?:ERR|FTL)\]\s*(.+)")
_GIT_MISSING = (
    "Recyclarr needs git to clone TRaSH Guides. "
    "Install git on the host (native) or recreate the container from an image that includes git."
)

# Official Recyclarr config-templates / TRaSH guide-backed profile IDs.
_SONARR_WEB_1080P = "72dae194fc92bf828f32cde7744e51a1"
_SONARR_WEB_2160P = "d1498e7d189fbe6c7110ceaabb7473e6"
_SONARR_ANIME_REMUX_1080P = "20e0fc959f1f1704bed501f23bdae76f"
_RADARR_HD_BLURAY_WEB = "d1d67249d3890e49bc12e275d989a7e9"
_RADARR_UHD_BLURAY_WEB = "64fb5f9858489bdac2af690e27c8f42f"

def _sonarr_all_sources_block(resolution: str) -> str:
    """WEB, Bluray and HDTV in one group: all are accepted and none replaces another just for its
    source; TRaSH scores still pick the best release. The guide's cutoff names its "WEB …" group,
    which empties out here, so the cutoff points at the new group."""
    return "\n".join(
        [
            "        upgrade:",
            "          allowed: true",
            f"          until_quality: {resolution}",
            "          until_score: 10000",
            "        qualities:",
            f"          - name: {resolution}",
            "            qualities:",
            *(f"              - {source}-{resolution}" for source in ("WEBDL", "WEBRip", "Bluray", "HDTV")),
        ]
    )


SONARR_OLDER_TV = "older tv shows"
# Older series often only exist as Bluray, HDTV or 720p: 1080p first, 720p when that is all there is.
_SONARR_OLDER_TV_PROFILE = f"""\
      - name: {SONARR_OLDER_TV}
        reset_unmatched_scores:
          enabled: true
        min_format_score: 0
        upgrade:
          allowed: true
          until_quality: 1080p
          until_score: 10000
        qualities:
          - name: 1080p
            qualities:
              - WEBDL-1080p
              - WEBRip-1080p
              - Bluray-1080p
              - HDTV-1080p
          - name: 720p
            qualities:
              - WEBDL-720p
              - WEBRip-720p
              - Bluray-720p
              - HDTV-720p"""
# A profile without a trash_id gets no guide scores, so it gets the ones WEB-1080p uses: the WEB
# tiers and the TRaSH groups that keep out unwanted formats (LQ, BR-DISK, x265 HD, …). Naming a
# default group here replaces the guide's auto-sync of it, so its guide profiles are listed too.
_SONARR_SCORE_GROUPS = (
    ("59c3af66780d08332fdc64e68297098f", "[Unwanted] Unwanted Formats", (_SONARR_WEB_1080P, _SONARR_WEB_2160P)),
    ("22256473b656e195eabc2798e326fbb7", "[Required] Repack/Proper", ()),
    ("158188097a58d7687dee647e04af0da3", "[Optional] Golden Rule HD", (_SONARR_WEB_1080P,)),
    ("74aff4168620ed49dcc67e92b2c2a5b4", "[Optional] Language Profiles", (_SONARR_WEB_1080P, _SONARR_WEB_2160P)),
    (
        "abe720fab2d27682adc2a735136cec02",
        "[Streaming Services] General",
        (_SONARR_WEB_1080P, _SONARR_WEB_2160P, _SONARR_ANIME_REMUX_1080P),
    ),
    ("85fae4a2294965b75710ef2989c850eb", "[Streaming Services] HD/UHD boost", (_SONARR_WEB_1080P, _SONARR_WEB_2160P)),
)


def _sonarr_older_tv_scores(guide_profiles: set[str]) -> str:
    lines = [
        "    custom_formats:",
        "      - trash_ids:",
        "          - e6258996055b9fbab7e9cb2f75819294  # WEB Tier 01",
        "          - 58790d4e2fdcd9733aa7ae68ba2bb503  # WEB Tier 02",
        "          - d84935abd3f8556dcd51d4f27e22d0a6  # WEB Tier 03",
        "          - d0c516558625b04b363fa6c5c2c7cfd4  # WEB Scene",
        "        assign_scores_to:",
        f"          - name: {SONARR_OLDER_TV}",
        "    custom_format_groups:",
        "      add:",
    ]
    for trash_id, label, guide in _SONARR_SCORE_GROUPS:
        lines += [f"        - trash_id: {trash_id}  # {label}", "          assign_scores_to:", f"            - name: {SONARR_OLDER_TV}"]
        lines += [f"            - trash_id: {profile}" for profile in guide if profile in guide_profiles]
    return "\n".join(lines)


PROFILE_OPTIONS = (
    {
        "id": "sonarr_web_1080p",
        "label": "Sonarr WEB-1080p",
        "guide": "https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles/#web-1080p",
        "default": True,
    },
    {
        "id": "sonarr_all_sources",
        "label": "Sonarr WEB profiles: also accept Bluray and HDTV",
        "guide": "https://recyclarr.dev/wiki/yaml/config-reference/quality-profiles/",
        "default": True,
    },
    {
        "id": "sonarr_older_tv",
        "label": "Sonarr older tv shows (720p–1080p, any source)",
        "guide": "https://recyclarr.dev/wiki/yaml/config-reference/quality-profiles/",
        "default": True,
    },
    {
        "id": "sonarr_web_2160p",
        "label": "Sonarr WEB-2160p",
        "guide": "https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles/#web-2160p",
        "default": False,
    },
    {
        "id": "sonarr_anime",
        "label": "Sonarr Anime Remux-1080p",
        "guide": "https://trash-guides.info/Sonarr/sonarr-setup-quality-profiles-anime/",
        "default": True,
    },
    {
        "id": "radarr_hd",
        "label": "Radarr HD Bluray + WEB",
        "guide": "https://trash-guides.info/Radarr/radarr-setup-quality-profiles/#hd-bluray-web",
        "default": True,
    },
    {
        "id": "radarr_uhd",
        "label": "Radarr UHD Bluray + WEB",
        "guide": "https://trash-guides.info/Radarr/radarr-setup-quality-profiles/#uhd-bluray-web",
        "default": False,
    },
)


def default_prefs() -> dict[str, Any]:
    flags = {item["id"]: item["default"] for item in PROFILE_OPTIONS}
    flags["naming"] = "plex"
    flags["user_edited"] = False
    return flags


def prefs_path(config_dir: Path) -> Path:
    return Path(config_dir) / PREFS_NAME


def yaml_path(config_dir: Path) -> Path:
    return Path(config_dir) / YAML_NAME


def settings_path(config_dir: Path) -> Path:
    return Path(config_dir) / SETTINGS_NAME


def git_executable() -> str | None:
    found = shutil.which("git")
    if found:
        return found
    for candidate in ("/usr/bin/git", "/usr/local/bin/git", "/bin/git"):
        path = Path(candidate)
        if path.is_file() and os.access(path, os.X_OK):
            return str(path)
    return None


def ensure_git_path_setting(config_dir: Path, git_exe: str) -> None:
    """Point Recyclarr at an absolute git binary (settings.yml git_path)."""
    path = settings_path(config_dir)
    quoted = json.dumps(git_exe)
    line = f"git_path: {quoted}"
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.is_file():
        path.write_text(
            "# yaml-language-server: $schema=https://schemas.recyclarr.dev/latest/settings-schema.json\n"
            f"# {MANAGED_MARK}\n"
            f"{line}\n",
            encoding="utf-8",
        )
        return
    text = path.read_text(encoding="utf-8")
    if re.search(rf"^git_path:\s*{re.escape(quoted)}\s*$", text, re.MULTILINE):
        return
    if _GIT_PATH_RE.search(text):
        path.write_text(_GIT_PATH_RE.sub(line, text, count=1), encoding="utf-8")
        return
    path.write_text(text.rstrip() + "\n" + line + "\n", encoding="utf-8")


def _path_with_git(env: dict[str, str], git_exe: str) -> str:
    git_dir = str(Path(git_exe).parent)
    current = env.get("PATH") or os.environ.get("PATH") or ""
    parts = [item for item in current.split(os.pathsep) if item and item != git_dir]
    return os.pathsep.join([git_dir, *parts]) if parts else git_dir


def _recyclarr_log_files(config_dir: Path) -> str:
    roots = (Path(config_dir) / "logs", Path(config_dir) / "logs" / "cli")
    paths: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        paths.extend(root.glob("*.log"))
        paths.extend(root.glob("*.debug.log"))
    if not paths:
        return ""
    newest = max(paths, key=lambda path: path.stat().st_mtime)
    try:
        text = newest.read_text(encoding="utf-8", errors="replace")[-4000:]
    except OSError:
        return ""
    if not text.strip():
        return ""
    return f"--- {newest.name} ---\n{text.strip()}"


def load_prefs(config_dir: Path) -> dict[str, Any]:
    path = prefs_path(config_dir)
    data = default_prefs()
    if path.is_file():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                data.update(loaded)
        except json.JSONDecodeError:
            pass
    return data


def save_prefs(config_dir: Path, prefs: dict[str, Any]) -> dict[str, Any]:
    merged = default_prefs()
    merged.update(prefs)
    Path(config_dir).mkdir(parents=True, exist_ok=True)
    prefs_path(config_dir).write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged


def write_recyclarr_config(
    config_dir: Path,
    *,
    sonarr_url: str,
    sonarr_key: str,
    radarr_url: str,
    radarr_key: str,
    prefs: dict[str, Any] | None = None,
    force: bool = False,
) -> Path:
    root = Path(config_dir)
    root.mkdir(parents=True, exist_ok=True)
    path = yaml_path(root)
    stored = load_prefs(root) if prefs is None else {**default_prefs(), **prefs}
    if path.is_file() and not force and (stored.get("user_edited") or _is_foreign(path)):
        _refresh_endpoints(path, sonarr_url, sonarr_key, radarr_url, radarr_key)
        return path
    naming = str(stored.get("naming") or "plex")
    body = _render_yaml(
        stored,
        sonarr_url=sonarr_url,
        sonarr_key=sonarr_key,
        radarr_url=radarr_url,
        radarr_key=radarr_key,
        naming=naming,
    )
    path.write_text(body, encoding="utf-8")
    save_prefs(root, {**stored, "user_edited": False})
    logger.info("Wrote TRaSH Recyclarr config at %s", path)
    return path


def save_yaml(config_dir: Path, text: str) -> Path:
    path = yaml_path(config_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    cleaned = text.replace("\r\n", "\n")
    if not cleaned.endswith("\n"):
        cleaned += "\n"
    path.write_text(cleaned, encoding="utf-8")
    save_prefs(config_dir, {**load_prefs(config_dir), "user_edited": True})
    return path


def config_payload() -> dict[str, Any]:
    catalog = ApplicationCatalog()
    plugin = catalog.get("recyclarr") if catalog.has("recyclarr") else None
    config_dir = plugin.config_dir if plugin else settings.config_dir / "recyclarr"
    prefs = load_prefs(config_dir)
    path = yaml_path(config_dir)
    yaml_text = path.read_text(encoding="utf-8") if path.is_file() else ""
    return {
        "config_dir": str(config_dir),
        "yaml_path": str(path),
        "yaml": yaml_text,
        "prefs": prefs,
        "profiles": PROFILE_OPTIONS,
        "naming_options": [
            {"id": "plex", "label": "Plex (TRaSH default; works with Jellyfin too)"},
            {"id": "jellyfin", "label": "Jellyfin"},
            {"id": "default", "label": "Sonarr/Radarr default"},
        ],
        "user_edited": bool(prefs.get("user_edited")),
        "installed": bool(plugin and plugin.is_installed()),
        "help_url": "https://recyclarr.dev/wiki/guide-configs/",
    }


def apply_prefs_and_render(prefs: dict[str, Any], *, force: bool = True) -> dict[str, Any]:
    catalog = ApplicationCatalog()
    plugin = catalog.get("recyclarr") if catalog.has("recyclarr") else None
    config_dir = plugin.config_dir if plugin else settings.config_dir / "recyclarr"
    sonarr_port = catalog.get("sonarr").port if catalog.has("sonarr") else 8989
    radarr_port = catalog.get("radarr").port if catalog.has("radarr") else 7878
    if prefs.get("naming") not in {"plex", "jellyfin", "default"}:
        prefs = {**prefs, "naming": "plex"}
    merged = save_prefs(config_dir, {**prefs, "user_edited": False})
    write_recyclarr_config(
        config_dir,
        sonarr_url=f"http://127.0.0.1:{sonarr_port}",
        sonarr_key=get_application_api_key("sonarr") or "",
        radarr_url=f"http://127.0.0.1:{radarr_port}",
        radarr_key=get_application_api_key("radarr") or "",
        prefs=merged,
        force=force,
    )
    return config_payload()


_sync_lock = threading.Lock()


def run_sync(timeout: float = 180.0) -> dict[str, Any]:
    """Run one Recyclarr sync; a second request while one runs returns at once."""
    if not _sync_lock.acquire(blocking=False):
        return {
            "ok": False,
            "detail": "A Recyclarr sync is already running. Wait for it to finish.",
            "log": "",
            "returncode": None,
        }
    try:
        return _run_sync_unlocked(timeout)
    finally:
        _sync_lock.release()


def _run_sync_unlocked(timeout: float = 180.0) -> dict[str, Any]:
    catalog = ApplicationCatalog()
    if not catalog.has("recyclarr"):
        return _fail_sync(None, "Recyclarr is not in the catalog.")
    plugin = catalog.get("recyclarr")
    if not plugin.is_installed():
        return _fail_sync(plugin.config_dir, "Install Recyclarr first.")
    git_exe = git_executable()
    if not git_exe:
        return _fail_sync(plugin.config_dir, _GIT_MISSING)
    ensure_git_path_setting(plugin.config_dir, git_exe)
    write_recyclarr_config(
        plugin.config_dir,
        sonarr_url=f"http://127.0.0.1:{catalog.get('sonarr').port if catalog.has('sonarr') else 8989}",
        sonarr_key=get_application_api_key("sonarr") or "",
        radarr_url=f"http://127.0.0.1:{catalog.get('radarr').port if catalog.has('radarr') else 7878}",
        radarr_key=get_application_api_key("radarr") or "",
        force=False,
    )
    yaml_file = yaml_path(plugin.config_dir)
    try:
        cmd = list(plugin.start_command())
    except FileNotFoundError:
        return _fail_sync(plugin.config_dir, "Recyclarr binary is missing.")
    if "--config" not in cmd and "-c" not in cmd:
        cmd.extend(["--config", str(yaml_file)])
    if "--log" not in cmd:
        cmd.extend(["--log", "info"])
    env = {**os.environ, **plugin.extra_env()}
    env.pop("RECYCLARR_APP_DATA", None)
    env["RECYCLARR_CONFIG_DIR"] = str(plugin.config_dir)
    env.setdefault("HOME", str(plugin.config_dir))
    env["PATH"] = _path_with_git(env, git_exe)
    try:
        completed = subprocess.run(
            cmd,
            cwd=str(plugin.working_directory() or plugin.install_dir),
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return _fail_sync(plugin.config_dir, "Recyclarr binary is missing.")
    except subprocess.TimeoutExpired:
        return _fail_sync(plugin.config_dir, "Recyclarr sync timed out.")
    log = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
    extra = _recyclarr_log_files(plugin.config_dir)
    if extra:
        log = f"{log}\n{extra}".strip()
    ok = completed.returncode == 0
    lowered = log.lower()
    processed = any(
        token in lowered
        for token in ("processing", "created", "updated", "completed", "no changes", "already up", "up to date")
    )
    if ok and not processed:
        ok = False
        if "split instances" in lowered:
            detail = (
                "Recyclarr skipped sync because multiple instance names share the same "
                "Sonarr/Radarr URL. Use one instance per server with multiple quality profiles."
            )
        else:
            detail = "Recyclarr loaded TRaSH providers but did not sync any Sonarr/Radarr instances."
    elif ok:
        detail = "Sync finished."
    else:
        detail = f"Recyclarr exited {completed.returncode}."
        error = _ERROR_LINE_RE.search(log)
        if error:
            # Recyclarr's own reason, e.g. a TRaSH Guides clone or Sonarr/Radarr connection error.
            detail = f"Recyclarr exited {completed.returncode}: {error.group(1).strip()[:300]}"
        if "start process 'git'" in lowered or "file path 'git'" in lowered:
            detail = _GIT_MISSING
    if not ok:
        logger.warning("Recyclarr sync failed: %s", detail)
    result = {
        "ok": ok,
        "detail": detail,
        "log": log[-8000:],
        "returncode": completed.returncode,
        "config": str(yaml_file),
    }
    _store_last_sync(plugin.config_dir, result)
    return result


def _fail_sync(config_dir: Path | None, detail: str) -> dict[str, Any]:
    result = {"ok": False, "detail": detail, "log": "", "returncode": None}
    if config_dir is not None:
        _store_last_sync(config_dir, result)
    return result


def last_sync_payload(config_dir: Path | None = None) -> dict[str, Any] | None:
    if config_dir is None:
        catalog = ApplicationCatalog()
        plugin = catalog.get("recyclarr") if catalog.has("recyclarr") else None
        config_dir = plugin.config_dir if plugin else settings.config_dir / "recyclarr"
    path = Path(config_dir) / LAST_SYNC_NAME
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _store_last_sync(config_dir: Path, result: dict[str, Any]) -> None:
    path = Path(config_dir) / LAST_SYNC_NAME
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "at": datetime.now(timezone.utc).isoformat(),
                    "ok": bool(result.get("ok")),
                    "detail": result.get("detail"),
                    "returncode": result.get("returncode"),
                    "log": result.get("log") or "",
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        logger.debug("Could not write Recyclarr last-sync file: %s", exc)


def _is_foreign(path: Path) -> bool:
    text = path.read_text(encoding="utf-8")
    if MANAGED_MARK in text or "Generated by AIO Media Server Manager" in text:
        return False
    return "trash_id" in text


def _refresh_endpoints(path: Path, sonarr_url: str, sonarr_key: str, radarr_url: str, radarr_key: str) -> None:
    text = path.read_text(encoding="utf-8")
    text = re.sub(r"(sonarr:[\s\S]*?)base_url:\s*.*", rf"\1base_url: {sonarr_url}", text, count=1)
    if sonarr_key:
        text = re.sub(r"(sonarr:[\s\S]*?)api_key:\s*.*", rf"\1api_key: {sonarr_key}", text, count=1)
    text = re.sub(r"(radarr:[\s\S]*?)base_url:\s*.*", rf"\1base_url: {radarr_url}", text, count=1)
    if radarr_key:
        text = re.sub(r"(radarr:[\s\S]*?)api_key:\s*.*", rf"\1api_key: {radarr_key}", text, count=1)
    path.write_text(text, encoding="utf-8")


def _naming_block(kind: str, style: str) -> str:
    if kind == "sonarr":
        series = {"plex": "plex-imdb", "jellyfin": "jellyfin-tvdb"}.get(style, "default")
        return (
            "    media_naming:\n"
            f"      series: {series}\n"
            "      season: default\n"
            "      episodes:\n"
            "        rename: true\n"
            "        standard: default\n"
            "        daily: default\n"
            "        anime: default\n"
        )
    folder = {"plex": "plex-tmdb", "jellyfin": "jellyfin-tmdb"}.get(style, "default")
    standard = "plex-tmdb" if style == "plex" else "default"
    return (
        "    media_naming:\n"
        f"      folder: {folder}\n"
        "      movie:\n"
        "        rename: true\n"
        f"        standard: {standard}\n"
    )


def _service_instance(
    *,
    name: str,
    url: str,
    key: str,
    qdef: str,
    profiles: list[tuple[str, str]],
    naming: str,
    overrides: dict[str, str] | None = None,
    extra_profiles: str = "",
    extra: str = "",
) -> str:
    profile_lines: list[str] = []
    for trash_id, comment in profiles:
        profile_lines.append(f"      - trash_id: {trash_id}  # {comment}")
        profile_lines.append("        reset_unmatched_scores:")
        profile_lines.append("          enabled: true")
        if overrides and trash_id in overrides:
            profile_lines.append(overrides[trash_id])
    if extra_profiles:
        profile_lines.append(extra_profiles)
    return (
        f"  {name}:\n"
        f"    base_url: {url}\n"
        f"    api_key: {key}\n"
        "    delete_old_custom_formats: true\n"
        "    quality_definition:\n"
        f"      type: {qdef}\n"
        "    quality_profiles:\n"
        + "\n".join(profile_lines)
        + "\n"
        + (extra + "\n" if extra else "")
        + naming
    )


def _render_yaml(
    prefs: dict[str, Any],
    *,
    sonarr_url: str,
    sonarr_key: str,
    radarr_url: str,
    radarr_key: str,
    naming: str,
) -> str:
    # Recyclarr 8 identifies a server by base_url. Extra instance names on the same URL are
    # split and then skipped (exit 0, no Processing). One instance per *Arr, many profiles.
    sonarr_profiles: list[tuple[str, str]] = []
    if prefs.get("sonarr_web_1080p"):
        sonarr_profiles.append((_SONARR_WEB_1080P, "WEB-1080p"))
    if prefs.get("sonarr_web_2160p"):
        sonarr_profiles.append((_SONARR_WEB_2160P, "WEB-2160p"))
    if prefs.get("sonarr_anime"):
        sonarr_profiles.append((_SONARR_ANIME_REMUX_1080P, "[Anime] Remux-1080p"))
    sonarr_qdef = (
        "series"
        if prefs.get("sonarr_web_1080p") or prefs.get("sonarr_web_2160p") or prefs.get("sonarr_older_tv")
        else "anime"
    )
    sonarr_overrides: dict[str, str] = {}
    if prefs.get("sonarr_all_sources"):
        sonarr_overrides[_SONARR_WEB_1080P] = _sonarr_all_sources_block("1080p")
        sonarr_overrides[_SONARR_WEB_2160P] = _sonarr_all_sources_block("2160p")
    older_tv = bool(prefs.get("sonarr_older_tv"))
    radarr_profiles: list[tuple[str, str]] = []
    if prefs.get("radarr_hd"):
        radarr_profiles.append((_RADARR_HD_BLURAY_WEB, "HD Bluray + WEB"))
    if prefs.get("radarr_uhd"):
        radarr_profiles.append((_RADARR_UHD_BLURAY_WEB, "UHD Bluray + WEB"))
    parts = [
        "# yaml-language-server: $schema=https://schemas.recyclarr.dev/v8/config-schema.json",
        f"# {MANAGED_MARK} — official Recyclarr v8 / TRaSH Guides templates.",
        "# One instance per Sonarr/Radarr URL. Extra names on the same URL are skipped by Recyclarr 8.",
        "# HD profiles are on by default. Enable 4K from Catalog → Recyclarr → Settings.",
        "# Guide-backed quality profiles pull custom formats from TRaSH Guides.",
        "# https://recyclarr.dev/wiki/guide-configs/",
        "",
    ]
    if sonarr_profiles or older_tv:
        parts.append("sonarr:")
        parts.append(
            _service_instance(
                name="tv",
                url=sonarr_url,
                key=sonarr_key,
                qdef=sonarr_qdef,
                profiles=sonarr_profiles,
                naming=_naming_block("sonarr", naming),
                overrides=sonarr_overrides,
                extra_profiles=_SONARR_OLDER_TV_PROFILE if older_tv else "",
                extra=_sonarr_older_tv_scores({trash_id for trash_id, _ in sonarr_profiles}) if older_tv else "",
            )
        )
    if radarr_profiles:
        parts.append("radarr:")
        parts.append(
            _service_instance(
                name="movies",
                url=radarr_url,
                key=radarr_key,
                qdef="movie",
                profiles=radarr_profiles,
                naming=_naming_block("radarr", naming),
            )
        )
    if not sonarr_profiles and not older_tv and not radarr_profiles:
        parts.append("# No TRaSH profiles selected.")
    return "\n".join(parts).rstrip() + "\n"
