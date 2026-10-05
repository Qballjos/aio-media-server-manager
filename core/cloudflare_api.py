"""Cloudflare API helpers for publishing tunnel hostnames from the appliance UI."""

from __future__ import annotations

import base64
import json
import logging
from typing import Any

import httpx

from core.cloudflare_tunnel import cloudflare_tunnel
from core.crypto import secret_store
from core.public_hostnames import (
    catalog_public_apps,
    load_hostnames,
    mark_published,
    normalize_subdomain,
)
from core.settings import settings

logger = logging.getLogger(__name__)

API_TOKEN_SECRET = "cloudflare_api_token"
CF_API = "https://api.cloudflare.com/client/v4"


class CloudflareApiError(RuntimeError):
    """Cloudflare API or credential problem."""


def get_api_token() -> str:
    return (secret_store.get_secret(API_TOKEN_SECRET) or "").strip()


def set_api_token(token: str | None) -> None:
    value = (token or "").strip()
    if value:
        secret_store.save_secret(API_TOKEN_SECRET, value)
    else:
        secret_store.delete_secret(API_TOKEN_SECRET)


def api_token_configured() -> bool:
    return bool(get_api_token())


def _b64_json_decode(blob: str) -> dict[str, Any]:
    """Decode base64 (URL-safe or standard) JSON from cloudflared connector tokens."""
    text = (blob or "").strip()
    pad = "=" * (-len(text) % 4)
    last_error: Exception | None = None
    for decoder in (base64.urlsafe_b64decode, base64.b64decode):
        try:
            raw = decoder((text + pad).encode("ascii"))
            parsed = json.loads(raw.decode("utf-8"))
            if isinstance(parsed, dict):
                return parsed
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            last_error = exc
            continue
    raise CloudflareApiError("Could not decode tunnel connector token.") from last_error


def _normalize_connector_token(raw: str) -> str:
    text = (raw or "").strip().strip('"').strip("'")
    for needle in ("--token ", " tunnel run "):
        if needle in text:
            text = text.rsplit(needle, 1)[-1].strip().strip('"').strip("'")
    return text


def _decode_connector_token_raw(raw: str) -> dict[str, str]:
    raw = _normalize_connector_token(raw)
    if not raw:
        raise CloudflareApiError("Tunnel connector token is missing. Save it under Cloudflare Tunnel first.")

    parts = raw.split(".")
    if len(parts) >= 3:
        try:
            return _tunnel_ids_from_payload(_b64_json_decode(parts[1]))
        except CloudflareApiError:
            pass

    if raw.startswith("{") and raw.endswith("}"):
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return _tunnel_ids_from_payload(parsed)
        except json.JSONDecodeError:
            pass

    return _tunnel_ids_from_payload(_b64_json_decode(raw))


def _tunnel_ids_from_payload(payload: dict[str, Any]) -> dict[str, str]:
    account_id = str(
        payload.get("a") or payload.get("AccountTag") or payload.get("account_id") or ""
    ).strip()
    tunnel_id = str(
        payload.get("t") or payload.get("TunnelID") or payload.get("tunnel_id") or ""
    ).strip()
    if not account_id or not tunnel_id:
        raise CloudflareApiError("Tunnel token is missing account or tunnel id.")
    return {"account_id": account_id, "tunnel_id": tunnel_id}


def decode_tunnel_token(token: str | None = None) -> dict[str, str]:
    """Decode cloudflared connector token → account_id + tunnel_id.

    Remotely managed tunnel tokens from the dashboard are **not** JWTs. They are
    base64-encoded JSON (often starting with ``eyJ…`` because the JSON begins with
    ``{"a":…}``). Legacy/alternate forms may use a three-part JWT; both are accepted.
    """
    if token is not None:
        return _decode_connector_token_raw(token)

    candidates: list[str] = []
    for value in (
        cloudflare_tunnel.read_connector_token(),
        cloudflare_tunnel.read_token(),
    ):
        norm = _normalize_connector_token(value)
        if norm and norm not in candidates:
            candidates.append(norm)
    if not candidates:
        raise CloudflareApiError("Tunnel connector token is missing. Save it under Cloudflare Tunnel first.")

    last_error: CloudflareApiError | None = None
    for raw in candidates:
        try:
            return _decode_connector_token_raw(raw)
        except CloudflareApiError as exc:
            last_error = exc
    raise last_error or CloudflareApiError("Could not decode tunnel connector token.")


async def _cf_request(
    method: str,
    path: str,
    *,
    json_body: dict[str, Any] | None = None,
    params: dict[str, Any] | None = None,
) -> Any:
    token = get_api_token()
    if not token:
        raise CloudflareApiError(
            "Cloudflare API token is not configured. Paste one under Settings → Network → Public subdomains "
            "(My Profile → API Tokens → Create Token → Edit zone DNS, then add Account → Cloudflare Tunnel → Edit). "
            "This is not the eyJ… tunnel connector token. "
            "See https://developers.cloudflare.com/fundamentals/api/get-started/create-token/"
        )
    url = path if path.startswith("http") else f"{CF_API}{path}"
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=json_body,
            params=params,
        )
    try:
        data = resp.json()
    except Exception as exc:
        raise CloudflareApiError(f"Cloudflare API returned non-JSON ({resp.status_code}).") from exc
    if resp.status_code >= 400 or not data.get("success", False):
        errors = data.get("errors") or []
        msg = "; ".join(
            str(e.get("message") or e) for e in errors if e
        ) or f"HTTP {resp.status_code}"
        raise CloudflareApiError(msg)
    return data.get("result")


async def resolve_zone_id(zone_name: str) -> str:
    name = (zone_name or "").strip().lower().strip(".")
    if not name:
        raise CloudflareApiError("Set Public app domain (e.g. example.com) before publishing.")
    result = await _cf_request("GET", "/zones", params={"name": name, "status": "active"})
    rows = result if isinstance(result, list) else []
    if not rows:
        raise CloudflareApiError(f"No active Cloudflare zone found for {name!r}.")
    zone_id = str(rows[0].get("id") or "").strip()
    if not zone_id:
        raise CloudflareApiError(f"Zone lookup for {name!r} returned no id.")
    return zone_id


def _service_url(port: int) -> str:
    return f"http://127.0.0.1:{int(port)}"


def _hostname(subdomain: str, base_domain: str) -> str:
    return f"{subdomain}.{base_domain}".lower()


def planned_routes(
    *,
    base_domain: str | None = None,
    hostnames: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    base = (base_domain if base_domain is not None else settings.public_app_base_domain or "").strip().lower().strip(".")
    stored = hostnames if hostnames is not None else load_hostnames()
    routes: list[dict[str, Any]] = []
    for app in catalog_public_apps():
        name = app["name"]
        entry = stored.get(name) or {}
        enabled = bool(entry.get("enabled", False)) if entry else False
        # Default: manager off until chosen; apps off until toggled.
        # If entry missing, treat as not published but show default subdomain in UI.
        sub = normalize_subdomain(str(entry.get("subdomain") or app["default_subdomain"]))
        host = _hostname(sub, base) if base and sub else ""
        routes.append(
            {
                "name": name,
                "display_name": app["display_name"],
                "port": app["port"],
                "installed": app["installed"],
                "enabled": enabled,
                "subdomain": sub,
                "hostname": host,
                "url": f"https://{host}" if host else "",
                "service": _service_url(app["port"]),
                "default_subdomain": app["default_subdomain"],
            }
        )
    return routes


async def get_tunnel_config(account_id: str, tunnel_id: str) -> dict[str, Any]:
    result = await _cf_request(
        "GET",
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
    )
    if not isinstance(result, dict):
        return {"config": {"ingress": []}}
    return result


async def put_tunnel_ingress(
    account_id: str,
    tunnel_id: str,
    ingress: list[dict[str, Any]],
    *,
    existing_config: dict[str, Any] | None = None,
) -> None:
    config = dict((existing_config or {}).get("config") or {})
    # Preserve unrelated config keys (warp-routing, etc.) when present.
    config["ingress"] = list(ingress)
    await _cf_request(
        "PUT",
        f"/accounts/{account_id}/cfd_tunnel/{tunnel_id}/configurations",
        json_body={"config": config},
    )


async def delete_dns_records_for_hostname(*, zone_id: str, hostname: str) -> int:
    name = hostname.strip().lower()
    existing = await _cf_request(
        "GET",
        f"/zones/{zone_id}/dns_records",
        params={"name": name},
    )
    rows = existing if isinstance(existing, list) else []
    removed = 0
    for row in rows:
        record_id = str(row.get("id") or "").strip()
        if not record_id:
            continue
        await _cf_request("DELETE", f"/zones/{zone_id}/dns_records/{record_id}")
        removed += 1
    return removed


async def upsert_dns_cname(*, zone_id: str, hostname: str, tunnel_id: str) -> str:
    name = hostname.strip().lower()
    target = f"{tunnel_id}.cfargotunnel.com"
    existing = await _cf_request(
        "GET",
        f"/zones/{zone_id}/dns_records",
        params={"name": name},
    )
    rows = existing if isinstance(existing, list) else []
    body = {
        "type": "CNAME",
        "name": name,
        "content": target,
        "proxied": True,
        "ttl": 1,
    }
    cnames = [r for r in rows if str(r.get("type") or "").upper() == "CNAME"]
    if cnames:
        record_id = str(cnames[0].get("id") or "")
        await _cf_request("PUT", f"/zones/{zone_id}/dns_records/{record_id}", json_body=body)
        return "updated"
    others = [r for r in rows if str(r.get("type") or "").upper() != "CNAME"]
    if others:
        kind = str(others[0].get("type") or "record")
        raise CloudflareApiError(
            f"DNS name {name} already exists as {kind}. Delete or rename that record in Cloudflare, then publish again."
        )
    await _cf_request("POST", f"/zones/{zone_id}/dns_records", json_body=body)
    return "created"


def managed_hostnames_for_publish(
    routes: list[dict[str, Any]],
    *,
    stored: dict[str, dict[str, Any]] | None = None,
) -> set[str]:
    """Only touch enabled hostnames plus previously published ones (rename/disable).

    Never strip unrelated dashboard routes such as a manually added media.example.com
    when that app was never published from AIO.
    """
    managed: set[str] = set()
    by_name = {str(r.get("name") or ""): r for r in routes}
    for row in routes:
        if row.get("enabled") and row.get("hostname"):
            managed.add(str(row["hostname"]).lower())
    for name, entry in (stored or {}).items():
        prev = str(entry.get("last_published") or "").strip().lower()
        if not prev:
            continue
        current = by_name.get(name) or {}
        if current.get("enabled"):
            host = str(current.get("hostname") or "").lower()
            if host and prev != host:
                managed.add(prev)  # renamed: drop old ingress hostname
        else:
            managed.add(prev)  # disabled: remove from tunnel
    return managed


def _merge_ingress(
    existing_ingress: list[dict[str, Any]],
    desired: list[dict[str, Any]],
    *,
    managed_hostnames: set[str],
) -> list[dict[str, Any]]:
    """Replace managed hostnames; keep other hostnames; ensure catch-all last."""
    kept: list[dict[str, Any]] = []
    for rule in existing_ingress:
        if not isinstance(rule, dict):
            continue
        host = str(rule.get("hostname") or "").strip().lower()
        service = str(rule.get("service") or "")
        if not host and service.startswith("http_status:"):
            continue  # drop old catch-all; re-add at end
        if host and host in managed_hostnames:
            continue
        kept.append(rule)

    merged = kept + desired
    merged.append({"service": "http_status:404"})
    return merged


async def sync_published_app_port(app_name: str, port: int) -> dict[str, Any]:
    """Rewrite published-application ingress when an exposed app's listen port changes.

    DNS CNAMEs target ``<tunnel-id>.cfargotunnel.com`` only — they do not embed the
    origin port — so we update the tunnel ingress service URL and leave DNS alone.
    """
    name = (app_name or "").strip().lower()
    new_port = int(port)
    if not name:
        raise CloudflareApiError("App name required.")
    if not api_token_configured():
        return {
            "ok": False,
            "skipped": True,
            "detail": "Cloudflare API token not configured; publish again from Settings → Network.",
        }

    stored = load_hostnames()
    entry = stored.get(name) or {}
    hostname = str(entry.get("last_published") or "").strip().lower()
    if not hostname:
        return {"ok": True, "skipped": True, "detail": "App is not published on the tunnel."}

    prev_port = entry.get("last_published_port")
    try:
        prev_port_i = int(prev_port) if prev_port is not None else None
    except (TypeError, ValueError):
        prev_port_i = None
    if prev_port_i == new_port:
        return {
            "ok": True,
            "skipped": True,
            "hostname": hostname,
            "port": new_port,
            "detail": "Tunnel already points at this port.",
        }

    ids = decode_tunnel_token()
    account_id = ids["account_id"]
    tunnel_id = ids["tunnel_id"]

    current = await get_tunnel_config(account_id, tunnel_id)
    config = current.get("config") if isinstance(current.get("config"), dict) else {}
    existing_ingress = list(config.get("ingress") or []) if isinstance(config, dict) else []
    service = _service_url(new_port)

    desired = [
        {
            "hostname": hostname,
            "service": service,
            "originRequest": {},
        }
    ]
    new_ingress = _merge_ingress(
        existing_ingress,
        desired,
        managed_hostnames={hostname},
    )
    await put_tunnel_ingress(account_id, tunnel_id, new_ingress, existing_config=current)

    mark_published({name: hostname}, ports={name: new_port})
    logger.info(
        "Synced Cloudflare published application for %s → %s (port %s)",
        name,
        hostname,
        new_port,
    )
    return {
        "ok": True,
        "skipped": False,
        "name": name,
        "hostname": hostname,
        "port": new_port,
        "previous_port": prev_port_i,
        "service": service,
        "detail": f"Published application service updated to {service}.",
    }


async def publish_hostnames(
    *,
    base_domain: str | None = None,
    hostnames: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    ids = decode_tunnel_token()
    account_id = ids["account_id"]
    tunnel_id = ids["tunnel_id"]
    base = (base_domain if base_domain is not None else settings.public_app_base_domain or "").strip().lower().strip(".")
    if not base:
        raise CloudflareApiError("Set Public app domain (e.g. example.com) before publishing.")

    stored = hostnames if hostnames is not None else load_hostnames()
    routes = planned_routes(base_domain=base, hostnames=stored)
    enabled = [r for r in routes if r["enabled"] and r["hostname"]]
    if not enabled and not any(str((stored.get(n) or {}).get("last_published") or "") for n in stored):
        raise CloudflareApiError("Enable at least one subdomain before publishing.")

    # Duplicate hostname guard
    seen: dict[str, str] = {}
    for row in enabled:
        other = seen.get(row["hostname"])
        if other:
            raise CloudflareApiError(f"Hostname {row['hostname']} is used by both {other} and {row['name']}.")
        seen[row["hostname"]] = row["name"]

    zone_id = await resolve_zone_id(base)
    current = await get_tunnel_config(account_id, tunnel_id)
    config = current.get("config") if isinstance(current.get("config"), dict) else {}
    existing_ingress = list(config.get("ingress") or []) if isinstance(config, dict) else []

    desired_ingress = [
        {
            "hostname": row["hostname"],
            "service": row["service"],
            "originRequest": {},
        }
        for row in enabled
    ]
    managed = managed_hostnames_for_publish(routes, stored=stored)

    new_ingress = _merge_ingress(existing_ingress, desired_ingress, managed_hostnames=managed)
    await put_tunnel_ingress(account_id, tunnel_id, new_ingress, existing_config=current)

    dns_results: list[dict[str, str]] = []
    for row in enabled:
        action = await upsert_dns_cname(zone_id=zone_id, hostname=row["hostname"], tunnel_id=tunnel_id)
        dns_results.append({"hostname": row["hostname"], "dns": action, "name": row["name"]})

    published_map = {r["name"]: r["hostname"] for r in enabled}
    published_ports = {r["name"]: int(r["port"]) for r in enabled}
    enabled_names = {r["name"] for r in enabled}
    cleared = [
        name
        for name, entry in stored.items()
        if entry.get("last_published") and name not in enabled_names
    ]
    mark_published(published_map, cleared=cleared, ports=published_ports)

    return {
        "ok": True,
        "account_id": account_id,
        "tunnel_id": tunnel_id,
        "zone": base,
        "published": [
            {"name": r["name"], "hostname": r["hostname"], "service": r["service"]} for r in enabled
        ],
        "removed": cleared,
        "dns": dns_results,
        "ingress_count": max(0, len(new_ingress) - 1),
        "warning": (
            "Published hostnames are reachable from the internet unless you add Cloudflare Access. "
            "DNS CNAMEs for disabled apps are left in place (published-application ingress hostname removed)."
            if enabled or cleared
            else ""
        ),
    }


async def verify_api_access() -> dict[str, Any]:
    """Lightweight check: token works and zone + tunnel ids resolve."""
    ids = decode_tunnel_token()
    base = (settings.public_app_base_domain or "").strip().lower().strip(".")
    zone_id = await resolve_zone_id(base) if base else ""
    # Confirm tunnel exists
    await _cf_request("GET", f"/accounts/{ids['account_id']}/cfd_tunnel/{ids['tunnel_id']}")
    return {
        "ok": True,
        "api_token_configured": True,
        "account_id": ids["account_id"],
        "tunnel_id": ids["tunnel_id"],
        "zone": base,
        "zone_id": zone_id,
    }
