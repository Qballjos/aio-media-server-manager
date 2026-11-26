"""Plex-hosted PIN approval and account verification."""

from urllib.parse import urlencode

import requests
from fastapi import HTTPException

_PRODUCT = "AIO Media Server Manager"


def _request(method: str, host: str, path: str, client_id: str, *, token: str = "", **kwargs):
    headers = {
        "Accept": "application/json",
        "X-Plex-Client-Identifier": client_id,
        "X-Plex-Product": _PRODUCT,
    }
    if token:
        headers["X-Plex-Token"] = token
    try:
        response = requests.request(
            method, f"https://{host}/api/v2{path}", headers=headers,
            allow_redirects=False, timeout=8, **kwargs,
        )
        if response.status_code == 404 and path.startswith("/pins/"):
            raise HTTPException(404, "Plex sign-in attempt expired.")
        if response.status_code in (401, 403):
            raise HTTPException(403, "Plex did not authorize the sign-in.")
        if response.status_code not in (200, 201):
            raise ValueError("Unexpected Plex response status")
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        raise HTTPException(502, "Plex sign-in is unavailable.") from exc


def begin_plex_sign_in(client_id: str) -> tuple[str, str]:
    pin = _request("POST", "plex.tv", "/pins", client_id, params={"strong": "true"})
    pin_id = pin.get("id") if isinstance(pin, dict) else None
    code = pin.get("code") if isinstance(pin, dict) else None
    if type(pin_id) is not int or pin_id <= 0 or not isinstance(code, str) or not code:
        raise HTTPException(502, "Plex returned an invalid sign-in PIN.")
    query = urlencode({"clientID": client_id, "code": code, "context[device][product]": _PRODUCT})
    return f"https://app.plex.tv/auth#?{query}", str(pin_id)


def finish_plex_sign_in(client_id: str, pin_id: str, server_id: str) -> tuple[str, str] | None:
    pin = _request("GET", "plex.tv", f"/pins/{pin_id}", client_id)
    if not isinstance(pin, dict) or "authToken" not in pin:
        raise HTTPException(502, "Plex returned an invalid sign-in state.")
    token = pin["authToken"]
    if token is None:
        return None
    if not isinstance(token, str) or not token:
        raise HTTPException(502, "Plex returned an invalid sign-in token.")

    account = _request("GET", "plex.tv", "/user", client_id, token=token)
    account_id = account.get("id") if isinstance(account, dict) else None
    if type(account_id) is not int or account_id <= 0:
        raise HTTPException(502, "Plex did not identify the account.")

    resources = _request("GET", "clients.plex.tv", "/resources", client_id, token=token)
    if not isinstance(resources, list):
        raise HTTPException(502, "Plex returned an invalid server list.")
    for resource in resources:
        if (
            isinstance(resource, dict)
            and resource.get("clientIdentifier") == server_id
            and "server" in str(resource.get("provides", "")).split(",")
        ):
            server_token = resource.get("accessToken")
            if isinstance(server_token, str) and server_token:
                return str(account_id), server_token
    raise HTTPException(403, "The Plex account does not have access to this server.")
