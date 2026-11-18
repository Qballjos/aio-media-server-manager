"""RFC 6238 authenticator codes and one-time recovery code helpers."""

import base64
import hashlib
import hmac
import re
import secrets
import time


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii")


def totp_code(secret: str, counter: int) -> str:
    key = base64.b32decode(secret)
    digest = hmac.digest(key, counter.to_bytes(8, "big"), "sha1")
    offset = digest[-1] & 15
    value = int.from_bytes(digest[offset:offset + 4], "big") & 0x7fffffff
    return f"{value % 1_000_000:06d}"


def current_counter() -> int:
    return int(time.time()) // 30


def match_counter(secret: str, code: str, last_counter: int = -1) -> int | None:
    if not re.fullmatch(r"[0-9]{6}", code):
        return None
    counter = current_counter()
    for step in range(counter + 1, max(counter - 2, -1), -1):
        if step > last_counter and hmac.compare_digest(totp_code(secret, step), code):
            return step
    return None


def recovery_codes() -> list[str]:
    return [secrets.token_hex(16) for _ in range(10)]


def recovery_digest(code: str) -> str:
    return hashlib.sha256(code.lower().encode("utf-8")).hexdigest()
