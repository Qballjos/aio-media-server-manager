"""Who may see host debug data (system dump, process logs, error ring).

Local loopback is always allowed so you can curl from the appliance.
Cloudflare Tunnel terminates on 127.0.0.1 — those requests are treated as remote.
"""

from __future__ import annotations

from fastapi import HTTPException, Request, status

from core.auth import auth_manager

_LOOPBACK = frozenset({"127.0.0.1", "::1", "localhost", "::ffff:127.0.0.1"})
_PROXY_HINTS = ("cf-connecting-ip", "cf-ray", "cf-ipcountry", "cdn-loop")


def _peer_host(request: Request) -> str:
    return (request.client.host if request.client else "") or ""


def _request_hostname(request: Request) -> str:
    host = (request.headers.get("host") or "").strip()
    if host.startswith("["):
        end = host.find("]")
        if end != -1:
            return host[1:end].lower()
    return host.split(":")[0].strip().lower()


def is_local_troubleshooting(request: Request) -> bool:
    """True only for a loopback client that is not arriving via Cloudflare/CDN."""
    if any(request.headers.get(name) for name in _PROXY_HINTS):
        return False
    if _peer_host(request) not in _LOOPBACK:
        return False
    host = _request_hostname(request)
    return not host or host in _LOOPBACK


def debug_switch_on() -> bool:
    from core.diagnostics import diagnostics

    return bool(diagnostics.share_status().get("active"))


def can_view_debug(request: Request) -> bool:
    """Local troubleshooting, or a session while Diagnostics support share is on."""
    if is_local_troubleshooting(request):
        return True
    if not debug_switch_on():
        return False
    if auth_manager.setup_required():
        return False
    try:
        auth_manager.authenticate_request(request)
        return True
    except HTTPException:
        return False


def require_local_or_session(request: Request) -> None:
    """Local curl, or a logged-in admin. Not public on the LAN/WAN."""
    if is_local_troubleshooting(request):
        return
    if auth_manager.setup_required():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    auth_manager.authenticate_request(request)


def require_local_or_debug_switch(request: Request) -> None:
    """Process logs and error dumps: localhost, or Diagnostics support share on."""
    if can_view_debug(request):
        return
    if not debug_switch_on():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Enable Diagnostics support share to view debug data.",
        )
    require_local_or_session(request)
