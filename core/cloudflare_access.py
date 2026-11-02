"""Create Cloudflare Access applications for exposed *Arr, download, Seerr, and NeutArr hostnames.

The operator adds the login method in Zero Trust. AIO only reads it and attaches
an Allow policy to the hostnames that should sit behind Access. Jellyfin, Plex,
and the manager dashboard are never given an Access application.
"""

from __future__ import annotations

import json
import re
from typing import Any

from core.cloudflare_api import (
    CloudflareApiError,
    _cf_request,
    api_token_configured,
    decode_tunnel_token,
    planned_routes,
)
from core.public_hostnames import ACCESS_GATE_APPS
from core.settings import settings

_POLICY_NAME = "AIO Access"
_STATE_NAME = "cloudflare_access.json"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SESSION = {"seerr": "24h"}
_DEFAULT_SESSION = "8h"
_PERMISSION_HINT = (
    " The API token also needs Access: Apps and Policies Write and "
    "Access: Organizations, Identity Providers, and Groups Read."
)


def _state_path():
    return settings.config_dir / _STATE_NAME


def load_access_state() -> dict[str, Any]:
    path = _state_path()
    if not path.is_file():
        return {"emails": [], "policy_id": "", "apps": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"emails": [], "policy_id": "", "apps": {}}
    if not isinstance(raw, dict):
        return {"emails": [], "policy_id": "", "apps": {}}
    emails = raw.get("emails") if isinstance(raw.get("emails"), list) else []
    apps = raw.get("apps") if isinstance(raw.get("apps"), dict) else {}
    return {
        "emails": [str(item).strip().lower() for item in emails if str(item).strip()],
        "policy_id": str(raw.get("policy_id") or "").strip(),
        "apps": apps,
    }


def save_access_state(state: dict[str, Any]) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")


def parse_emails(raw: str | list[str] | None) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, list):
        parts = [str(item) for item in raw]
    else:
        parts = re.split(r"[\s,;]+", str(raw))
    found: list[str] = []
    for part in parts:
        addr = part.strip().lower()
        if not addr:
            continue
        if not _EMAIL.match(addr):
            raise CloudflareApiError(f"Not an email address: {addr}")
        if addr not in found:
            found.append(addr)
    return found


def policy_include(identity_providers: list[dict[str, Any]], emails: list[str]) -> list[dict[str, Any]]:
    """Who may pass Access.

    Emails are an OR list. Without emails, only a Cloudflare login method that
    is restricted to account members is safe. Google and One-time PIN would
    otherwise let any account through.
    """
    if emails:
        return [{"email": {"email": addr}} for addr in emails]
    locked = [
        row
        for row in identity_providers
        if row.get("type") == "cloudflare" and row.get("restrict_to_account_members") and row.get("id")
    ]
    if locked and len(locked) == len(identity_providers):
        return [{"login_method": {"id": str(row["id"])}} for row in locked]
    raise CloudflareApiError(
        "Add the email addresses that may sign in. Google and One-time PIN let anyone through "
        "unless the policy names those addresses. A Cloudflare login method with "
        "Restrict to account members does not need the list."
    )


def _permission_hint(exc: CloudflareApiError) -> CloudflareApiError:
    text = str(exc)
    low = text.lower()
    if "permission" in low or "not authorized" in low or "insufficient" in low:
        if _PERMISSION_HINT.strip() not in text:
            return CloudflareApiError(text + _PERMISSION_HINT)
    return exc


async def _cf(method: str, path: str, **kwargs: Any) -> Any:
    try:
        return await _cf_request(method, path, **kwargs)
    except CloudflareApiError as exc:
        raise _permission_hint(exc) from exc


async def _cf_list(path: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for page in range(1, 21):
        result = await _cf("GET", path, params={"page": page, "per_page": 50})
        batch = [row for row in result if isinstance(row, dict)] if isinstance(result, list) else []
        rows.extend(batch)
        if len(batch) < 50:
            break
    return rows


def _idp_summary(row: dict[str, Any]) -> dict[str, Any]:
    config = row.get("config") if isinstance(row.get("config"), dict) else {}
    return {
        "id": str(row.get("id") or ""),
        "name": str(row.get("name") or row.get("type") or "Login method"),
        "type": str(row.get("type") or ""),
        "restrict_to_account_members": bool(config.get("restrict_to_account_members")),
    }


async def list_identity_providers(account_id: str) -> list[dict[str, Any]]:
    rows = await _cf_list(f"/accounts/{account_id}/access/identity_providers")
    return [_idp_summary(row) for row in rows if row.get("id")]


def _session_for(name: str) -> str:
    return _SESSION.get(name, _DEFAULT_SESSION)


def _app_body(
    *,
    display_name: str,
    hostname: str,
    session: str,
    policy_id: str,
    idp_ids: list[str],
) -> dict[str, Any]:
    return {
        "name": f"AIO {display_name}",
        "domain": hostname,
        "type": "self_hosted",
        "session_duration": session,
        "allowed_idps": idp_ids,
        "auto_redirect_to_identity": len(idp_ids) == 1,
        "policies": [{"id": policy_id, "precedence": 1}],
    }


async def _upsert_policy(account_id: str, policy_id: str, include: list[dict[str, Any]]) -> str:
    body = {"name": _POLICY_NAME, "decision": "allow", "include": include}
    base = f"/accounts/{account_id}/access/policies"
    if policy_id:
        try:
            existing = await _cf("GET", f"{base}/{policy_id}")
        except CloudflareApiError:
            existing = None
        if isinstance(existing, dict) and existing.get("id"):
            merged = dict(existing)
            merged.update(body)
            for key in ("created_at", "updated_at", "uid"):
                merged.pop(key, None)
            saved = await _cf("PUT", f"{base}/{policy_id}", json_body=merged)
            return str((saved or {}).get("id") or policy_id)
    listed = await _cf_list(base)
    for row in listed:
        if str(row.get("name") or "") == _POLICY_NAME and row.get("id"):
            found = str(row["id"])
            merged = dict(row)
            merged.update(body)
            for key in ("created_at", "updated_at", "uid"):
                merged.pop(key, None)
            saved = await _cf("PUT", f"{base}/{found}", json_body=merged)
            return str((saved or {}).get("id") or found)
    created = await _cf("POST", base, json_body=body)
    new_id = str((created or {}).get("id") or "").strip()
    if not new_id:
        raise CloudflareApiError("Cloudflare did not return an id for the Access policy.")
    return new_id


async def _upsert_app(
    account_id: str,
    *,
    existing_id: str,
    hostname: str,
    payload: dict[str, Any],
    known_by_domain: dict[str, dict[str, Any]],
) -> tuple[str, bool]:
    """Return (app id, created by this call)."""
    base = f"/accounts/{account_id}/access/apps"
    target_id = existing_id
    created = False
    if not target_id:
        match = known_by_domain.get(hostname)
        if match and match.get("id"):
            target_id = str(match["id"])
    if target_id:
        try:
            current = await _cf("GET", f"{base}/{target_id}")
        except CloudflareApiError:
            current = None
        if isinstance(current, dict) and current.get("id"):
            merged = dict(current)
            merged.update(payload)
            for key in ("created_at", "updated_at", "uid"):
                merged.pop(key, None)
            saved = await _cf("PUT", f"{base}/{target_id}", json_body=merged)
            return str((saved or {}).get("id") or target_id), False
        target_id = ""
    saved = await _cf("POST", base, json_body=payload)
    new_id = str((saved or {}).get("id") or "").strip()
    if not new_id:
        raise CloudflareApiError(f"Cloudflare did not return an id for {hostname}.")
    created = True
    return new_id, created


async def access_status() -> dict[str, Any]:
    state = load_access_state()
    providers: list[dict[str, Any]] = []
    idp_error = ""
    if api_token_configured():
        try:
            account_id = decode_tunnel_token().get("account_id", "")
            if account_id:
                providers = await list_identity_providers(account_id)
        except CloudflareApiError as exc:
            idp_error = str(exc)
    return {
        "emails": state["emails"],
        "policy_id": state["policy_id"],
        "apps": state["apps"],
        "protected_apps": sorted(ACCESS_GATE_APPS),
        "identity_providers": providers,
        "idp_error": idp_error,
    }


async def apply_access(
    *,
    emails: str | list[str] | None = None,
    hostnames: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    parsed = parse_emails(emails) if emails is not None else load_access_state()["emails"]
    account_id = decode_tunnel_token().get("account_id", "")
    if not account_id:
        raise CloudflareApiError("Tunnel connector token is missing. Save it under Cloudflare Tunnel first.")

    providers = await list_identity_providers(account_id)
    if not providers:
        raise CloudflareApiError(
            "No login method found in Cloudflare Zero Trust. Add Cloudflare, Google, or One-time PIN "
            "under Zero Trust → Integrations → Identity providers, then try again."
        )
    include = policy_include(providers, parsed)
    state = load_access_state()
    policy_id = await _upsert_policy(account_id, str(state.get("policy_id") or ""), include)

    routes = planned_routes(hostnames=hostnames)
    wanted = [row for row in routes if row.get("access_gate") and row.get("enabled")]
    missing_host = [row["display_name"] for row in wanted if not row.get("hostname")]
    if missing_host:
        raise CloudflareApiError(
            "Set Public app domain before adding Access. Missing a hostname for: "
            + ", ".join(missing_host)
        )

    listed = await _cf_list(f"/accounts/{account_id}/access/apps")
    by_domain = {str(row.get("domain") or "").lower(): row for row in listed if row.get("domain")}
    idp_ids = [str(row["id"]) for row in providers if row.get("id")]
    stored_apps = dict(state.get("apps") or {})
    applied: list[dict[str, str]] = []
    removed: list[str] = []

    for row in routes:
        name = str(row["name"])
        if name not in ACCESS_GATE_APPS:
            continue
        previous = stored_apps.get(name) if isinstance(stored_apps.get(name), dict) else {}
        previous_id = str((previous or {}).get("id") or "")
        if not row.get("enabled"):
            if previous_id and previous.get("created"):
                await _cf("DELETE", f"/accounts/{account_id}/access/apps/{previous_id}")
                removed.append(name)
            stored_apps.pop(name, None)
            continue
        hostname = str(row["hostname"]).lower()
        payload = _app_body(
            display_name=str(row["display_name"]),
            hostname=hostname,
            session=_session_for(name),
            policy_id=policy_id,
            idp_ids=idp_ids,
        )
        app_id, created = await _upsert_app(
            account_id,
            existing_id=previous_id,
            hostname=hostname,
            payload=payload,
            known_by_domain=by_domain,
        )
        stored_apps[name] = {"id": app_id, "hostname": hostname, "created": bool(previous.get("created") or created)}
        applied.append({"name": name, "hostname": hostname, "id": app_id})

    save_access_state({"emails": parsed, "policy_id": policy_id, "apps": stored_apps})
    return {
        "ok": True,
        "policy_id": policy_id,
        "emails": parsed,
        "identity_providers": [{"name": row["name"], "type": row["type"]} for row in providers],
        "applied": applied,
        "removed": removed,
    }
