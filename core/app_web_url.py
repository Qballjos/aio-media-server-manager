"""Public Open UI URLs for catalog apps (LAN :port vs Cloudflare subdomains)."""

from __future__ import annotations

import re

from fastapi import Request

from core.public_hostnames import subdomain_for
from core.settings import settings

_LAN_SUFFIXES = (".local", ".lan")
_IPV4 = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}$")

# Common multi-part public suffixes so media.example.co.uk → example.co.uk
# (not media.example.co.uk). Not a full Public Suffix List — set Public app
# domain explicitly for unusual zones.
_MULTI_PART_SUFFIXES = frozenset(
    {
        "co.uk",
        "org.uk",
        "me.uk",
        "ac.uk",
        "gov.uk",
        "com.au",
        "net.au",
        "org.au",
        "co.nz",
        "org.nz",
        "co.jp",
        "or.jp",
        "ne.jp",
        "com.br",
        "com.mx",
        "co.za",
        "org.za",
        "com.cn",
        "com.hk",
        "com.sg",
        "co.in",
        "com.tw",
        "com.tr",
        "co.kr",
        "com.ar",
        "com.pl",
    }
)


def is_lan_hostname(host: str) -> bool:
    h = (host or "").strip().lower()
    if not h or h == "localhost" or h.endswith(_LAN_SUFFIXES):
        return True
    if _IPV4.match(h) or ":" in h:
        return True
    return False


def _public_suffix_labels(parts: list[str]) -> list[str]:
    if len(parts) >= 2:
        two = ".".join(parts[-2:])
        if two in _MULTI_PART_SUFFIXES:
            return parts[-2:]
    if len(parts) >= 3:
        three = ".".join(parts[-3:])
        if three in _MULTI_PART_SUFFIXES:
            return parts[-3:]
    return parts[-1:] if parts else []


def derive_public_app_base_domain(hostname: str) -> str:
    """Registrable DNS zone for Open UI links (handles multi-part TLDs)."""
    parts = [p for p in (hostname or "").strip().lower().split(".") if p]
    if len(parts) < 2:
        return ""
    suffix = _public_suffix_labels(parts)
    need = len(suffix) + 1  # one label under the public suffix
    if len(parts) < need:
        return ".".join(parts)
    return ".".join(parts[-need:])


def app_web_ui_url(
    *,
    app_name: str,
    port: int,
    hostname: str,
    scheme: str = "http",
    base_domain: str | None = None,
    subdomain: str | None = None,
) -> str:
    host = (hostname or "127.0.0.1").strip().lower()
    proto = (scheme or "http").split(":")[0].lower()
    configured = (base_domain if base_domain is not None else settings.public_app_base_domain) or ""
    configured = configured.strip().strip(".").lower()

    # LAN http://ip access must keep :port links even when Public app domain is set.
    # Subdomain links are for HTTPS / public hostnames only.
    on_lan = proto != "https" and is_lan_hostname(host)
    if on_lan:
        return f"http://{host}:{int(port)}"

    base = configured or derive_public_app_base_domain(host)
    custom = (subdomain if subdomain is not None else subdomain_for(app_name)) or ""
    custom = re.sub(r"[^a-z0-9-]", "", custom.strip().lower())
    name = custom or re.sub(r"[^a-z0-9-]", "", (app_name or "").strip().lower())
    if base and name:
        return f"https://{name}.{base}"
    return f"{proto}://{host}:{int(port)}"


def app_web_ui_url_for_request(request: Request, *, app_name: str, port: int) -> str:
    host = request.url.hostname or "127.0.0.1"
    scheme = request.url.scheme or "http"
    return app_web_ui_url(app_name=app_name, port=port, hostname=host, scheme=scheme)
