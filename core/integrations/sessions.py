"""Sign the shared manager admin in to a catalog app and hand back its browser cookies.

Browsers do not isolate cookies by port, so a cookie the manager sets for its own
host is also sent to http://<same host>:<app port>. That lets the dashboard open an
app already signed in without the app knowing anything about the manager.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import requests

from core.shared_credentials import shared_admin_credentials

logger = logging.getLogger(__name__)

SERVARR_APPS = ("sonarr", "radarr", "lidarr", "prowlarr")
# Jellyfin uses a separate Quick Connect handoff for localStorage tokens;
# NZBGet uses HTTP basic auth and Plex uses a Plex account.
SIGN_IN_APPS = frozenset({"seerr", "qbittorrent", "bazarr", "sabnzbd", *SERVARR_APPS})


def app_session_cookies(
    name: str,
    port: int,
    *,
    plex_config_dir: Path | None = None,
    http: Optional[requests.Session] = None,
) -> requests.cookies.RequestsCookieJar | None:
    """Return the app's session cookies for the shared admin, or None when there are none."""
    name = (name or "").strip().lower()
    if name not in SIGN_IN_APPS:
        return None
    if name == "seerr":
        from core.integrations.plex import PlexClient
        from core.integrations.seerr import seerr_admin_login

        token = PlexClient(config_dir=plex_config_dir).token if plex_config_dir else None
        client = seerr_admin_login(port, plex_token=token)
        return client.http.cookies if client else None

    creds = shared_admin_credentials()
    if not creds:
        return None
    username, password = creds
    http = http or requests.Session()
    base = f"http://127.0.0.1:{int(port)}"
    try:
        if name in SERVARR_APPS:
            # Forms auth: success is a 302 carrying <App>Auth; failure redirects to /login.
            http.post(
                f"{base}/login",
                data={"username": username, "password": password, "rememberMe": "on"},
                allow_redirects=False,
                timeout=8.0,
            )
        elif name == "qbittorrent":
            http.post(
                f"{base}/api/v2/auth/login",
                data={"username": username, "password": password},
                timeout=8.0,
            )
        elif name == "bazarr":
            http.post(
                f"{base}/api/system/account",
                params={"action": "login"},
                data={"username": username, "password": password},
                timeout=8.0,
            )
        elif name == "sabnzbd":
            http.post(
                f"{base}/sabnzbd/login",
                data={"username": username, "password": password, "remember_me": "1"},
                allow_redirects=False,
                timeout=8.0,
            )
    except Exception as exc:
        logger.debug("%s sign-in for the shared admin failed: %s", name, exc)
        return None
    return http.cookies if len(http.cookies) else None
