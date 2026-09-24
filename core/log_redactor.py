"""
core/log_redactor.py — Secret and credential redaction for logs.

Ensures that API keys, passwords, bearer tokens, and values stored in the
encrypted SecretStore are never exposed in log buffers, live streams, or exports.
"""

from __future__ import annotations

import re
from typing import Optional

from core.crypto import secret_store

# Generic patterns for sensitive values in logs, URLs, headers, and configs
_SENSITIVE_PATTERNS = [
    # api_key / apikey parameter
    (re.compile(r"(?i)(api[_-]?key[:=\s'\"]+)([a-zA-Z0-9_\-]{8,})"), r"\1[REDACTED_API_KEY]"),
    # token / auth_token parameter
    (re.compile(r"(?i)(token[:=\s'\"]+)([a-zA-Z0-9_\-\.]{8,})"), r"\1[REDACTED_TOKEN]"),
    # password / pass / secret parameter
    (re.compile(r"(?i)(password|passwd|secret)[:=\s'\"]+([^&\s,'\"\n]{4,})"), r"\1=[REDACTED_SECRET]"),
    # Authorization header (Bearer / Basic)
    (re.compile(r"(?i)(authorization[:\s]+(?:Bearer|Basic)\s+)([a-zA-Z0-9_\-\.\+/=]+)"), r"\1[REDACTED_AUTH]"),
    # 32 or 40 hex char strings that look like API hashes (e.g. Sonarr/Radarr/Prowlarr API keys)
    (re.compile(r"\b[a-f0-9]{32}\b"), "[REDACTED_KEY]"),
]

# Do not treat hostnames, usernames, or catalog names as credentials.
_STORED_SECRET_KEY = re.compile(r"(password|passwd|secret|token|api_key|apikey|_key$|claim)", re.IGNORECASE)
_MIN_STORED_SECRET_LEN = 8


def redact_log_line(line: str, custom_secrets: Optional[list[str]] = None) -> str:
    """
    Scrub credentials, tokens, and encrypted secret values from a single log line.
    """
    if not line:
        return ""

    result = line

    # 1. Redact credential values currently in SecretStore if available
    try:
        stored_secrets = secret_store.list_secrets(mask=False)
        for secret_name, secret_val in stored_secrets.items():
            if not secret_val or len(secret_val) < _MIN_STORED_SECRET_LEN:
                continue
            if not _STORED_SECRET_KEY.search(secret_name):
                continue
            if secret_val in result:
                result = result.replace(secret_val, "[REDACTED_SECRET]")
    except Exception:
        pass

    # 2. Redact custom passed secrets (e.g. during testing or wiring)
    if custom_secrets:
        for s in custom_secrets:
            if s and len(s) >= 4 and s in result:
                result = result.replace(s, "[REDACTED_SECRET]")

    # 3. Apply regex pattern redactions
    for pattern, replacement in _SENSITIVE_PATTERNS:
        result = pattern.sub(replacement, result)

    return result
