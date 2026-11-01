"""Revocable Homey credentials: dashboard reads only, separate from Homey and admin access."""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import tempfile
import threading
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, Request


class HomeyConnections:
    def __init__(self, config_dir: Path):
        self.path = config_dir / ".homey-connections.json"
        self.lock = (
            threading.Lock()
        )  # the appliance runs one API process; requests use its thread pool

    def _read(self) -> dict:
        try:
            data = json.loads(self.path.read_text())
        except FileNotFoundError:
            return {"invitation": {}, "devices": []}
        if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
            raise ValueError("Invalid Homey device store")
        return data

    def _save(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.path.parent, delete=False
            ) as out:
                name = out.name
                json.dump(data, out)
                out.flush()
                os.fsync(out.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name):
                os.unlink(name)

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    def invite(self) -> dict:
        code = secrets.token_urlsafe(32)
        with self.lock:
            data = self._read()
            if len(data["devices"]) >= 32:
                raise HTTPException(409, "Remove an old Homey before adding another.")
            data["invitation"] = {
                "hash": self._hash(code),
                "expires": time.time() + 300,
            }
            self._save(data)
        return {"pairingCode": code, "expiresIn": 300}

    def claim(self, code: str, name: str) -> dict:
        with self.lock:
            data = self._read()
            invite = data.get("invitation", {})
            if invite.get("expires", 0) <= time.time() or not secrets.compare_digest(
                invite.get("hash", ""), self._hash(code)
            ):
                raise HTTPException(
                    401, "The pairing link is invalid, expired or already used."
                )
            token = "homey_" + secrets.token_urlsafe(32)
            device_id = str(uuid.uuid4())
            data["devices"].append(
                {
                    "id": device_id,
                    "name": name,
                    "created": int(time.time()),
                    "hash": self._hash(token),
                }
            )
            data["invitation"] = {}
            self._save(data)
        return {
            "version": 1,
            "accessToken": token,
            "deviceId": device_id,
            "deviceName": name,
        }

    def devices(self) -> list[dict]:
        with self.lock:
            return [
                {k: row[k] for k in ("id", "name", "created")}
                for row in self._read()["devices"]
            ]

    def revoke(self, device_id: str) -> None:
        with self.lock:
            data = self._read()
            data["devices"] = [row for row in data["devices"] if row["id"] != device_id]
            self._save(data)

    def authenticate(self, request: Request, token: str) -> str:
        hashed = self._hash(token)
        with self.lock:
            row = next(
                (
                    row
                    for row in self._read()["devices"]
                    if secrets.compare_digest(row["hash"], hashed)
                ),
                None,
            )
        if not row:
            raise HTTPException(
                401, "The Homey connection was revoked. Pair again in AIO."
            )
        path, method = request.url.path, request.method.upper()
        allowed = (method == "GET" and path == "/api/homey/dashboard") or (
            method == "POST" and path == "/api/homey/disconnect"
        )
        if not allowed:
            raise HTTPException(
                403, "This Homey connection has dashboard read access only."
            )
        return "homey:" + row["id"]
