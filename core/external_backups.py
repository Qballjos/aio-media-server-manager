"""Streaming authenticated encryption and HTTPS/WebDAV configuration backups."""
from __future__ import annotations

import hashlib
from contextlib import nullcontext
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import time
from urllib.parse import quote, urlsplit
import uuid

import requests
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from core.backup_manager import BackupManager
from core.crypto import SecretStore
from core.settings import settings

_MAGIC = b"AIOBACKUP1"
_CHUNK = 1024 * 1024
_LIMIT = 20 * 1024**3
_NAME = re.compile(r"^amm-[A-Za-z0-9_-]+\.tar\.gz\.aioenc$")


def _key(password, salt):
    return PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=600000).derive(password.encode())


def encrypt_archive(source: Path, target: Path, password: str):
    salt, iv = os.urandom(16), os.urandom(12)
    header = _MAGIC + salt + iv
    cipher = Cipher(algorithms.AES(_key(password, salt)), modes.GCM(iv)).encryptor()
    cipher.authenticate_additional_data(header)
    with source.open("rb") as src, target.open("wb") as dst:
        os.chmod(target, 0o600)
        dst.write(header)
        for chunk in iter(lambda: src.read(_CHUNK), b""):
            dst.write(cipher.update(chunk))
        dst.write(cipher.finalize())
        dst.write(cipher.tag)


def decrypt_archive(source: Path, target: Path, password: str):
    length = source.stat().st_size
    header_size = len(_MAGIC) + 28
    if length < header_size + 16 or length > _LIMIT:
        raise ValueError("Encrypted backup size is invalid")
    try:
        with source.open("rb") as src, target.open("wb") as dst:
            os.chmod(target, 0o600)
            header = src.read(header_size)
            if not header.startswith(_MAGIC):
                raise ValueError("Unknown encrypted backup format")
            salt, iv = header[len(_MAGIC):len(_MAGIC)+16], header[-12:]
            src.seek(-16, 2)
            tag = src.read(16)
            src.seek(header_size)
            cipher = Cipher(algorithms.AES(_key(password, salt)), modes.GCM(iv, tag)).decryptor()
            cipher.authenticate_additional_data(header)
            remaining = length - header_size - 16
            while remaining:
                chunk = src.read(min(_CHUNK, remaining))
                if not chunk:
                    raise ValueError("Incomplete encrypted backup")
                dst.write(cipher.update(chunk))
                remaining -= len(chunk)
            dst.write(cipher.finalize())
    except Exception:
        target.unlink(missing_ok=True)
        raise ValueError("Backup could not be decrypted; check its integrity and encryption password") from None


class ExternalBackups:
    def __init__(self, cfg=None):
        self.cfg = cfg or settings
        self.secrets = SecretStore(cfg=self.cfg)
        self.manager = BackupManager(self.cfg)
        self.path = self.cfg.config_dir / "external_backup.json"

    def config(self):
        try:
            data = json.loads(self.path.read_text())
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def public(self):
        data = self.config()
        return {"enabled": bool(data.get("enabled")), "url": data.get("url", ""),
                "username": data.get("username", ""),
                "password_saved": bool(self.secrets.get_secret("webdav_password")),
                "encryption_password_saved": bool(self.secrets.get_secret("backup_encryption_password")),
                "last_transfer": data.get("last_transfer"), "last_drill": data.get("last_drill")}

    def save(self, *, enabled=False, url="", username="", password=None, encryption_password=None):
        parsed = urlsplit(url.strip())
        if url and (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Use an HTTPS/WebDAV folder URL without credentials, query or fragment")
        if encryption_password is not None and len(encryption_password) < 16:
            raise ValueError("Use an encryption password of at least 16 characters and keep an offline copy")
        existing_key = self.secrets.get_secret("backup_encryption_password")
        if enabled and (not url or not (encryption_password or existing_key)):
            raise ValueError("Configure a WebDAV folder and encryption password before enabling external backups")
        data = {**self.config(), "enabled": bool(enabled), "url": url.strip().rstrip("/"), "username": username}
        if password is not None:
            self.secrets.save_secret("webdav_password", password)
        if encryption_password is not None:
            self.secrets.save_secret("backup_encryption_password", encryption_password)
        self._save(data)
        return self.public()

    def _save(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data))
        temporary.replace(self.path)

    def _record(self, key, result):
        self._save({**self.config(), key: {"at": time.time(), **result}})

    def _session(self):
        session = requests.Session()
        session.trust_env = False
        config = self.config()
        session.auth = (config.get("username", ""), self.secrets.get_secret("webdav_password") or "")
        return session

    def _url(self, name):
        if not _NAME.fullmatch(name):
            raise ValueError("Use the encrypted filename returned by an external backup export")
        base = self.config().get("url", "")
        parsed = urlsplit(base)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("Configure an HTTPS/WebDAV destination first")
        return base.rstrip("/") + "/" + quote(name, safe="")

    def _download(self, session, name, target=None):
        digest, total = hashlib.sha256(), 0
        with session.get(self._url(name), stream=True, timeout=(5, 60), allow_redirects=False) as response:
            if response.status_code != 200:
                raise ValueError(f"WebDAV download failed (HTTP {response.status_code}); redirects are not followed")
            with (target.open("wb") if target else nullcontext(None)) as output:
                if target:
                    os.chmod(target, 0o600)
                for chunk in response.iter_content(_CHUNK):
                    total += len(chunk)
                    if total > _LIMIT:
                        raise ValueError("External backup exceeds the 20 GiB download limit")
                    digest.update(chunk)
                    if output is not None:
                        output.write(chunk)
        return digest.hexdigest()

    def export(self, name):
        if not self.config().get("enabled"):
            return {"status": "disabled"}
        try:
            if not self.manager.verify_backup(name).get("ok"):
                raise ValueError("Local backup failed verification")
            source = self.manager.resolve_archive(name)
            if source.stat().st_size > _LIMIT - 128:
                raise ValueError("Backup exceeds the 20 GiB external transfer limit")
            password = self.secrets.get_secret("backup_encryption_password")
            if not password:
                raise ValueError("Encryption password is unavailable")
            self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryDirectory(dir=self.cfg.cache_dir) as directory, self._session() as session:
                encrypted = Path(directory) / "backup.aioenc"
                encrypt_archive(source, encrypted, password)
                remote = name + ".aioenc"
                with encrypted.open("rb") as stream:
                    response = session.put(self._url(remote), data=stream, headers={"Content-Type": "application/octet-stream"}, timeout=(5, 60), allow_redirects=False)
                if response.status_code not in {200, 201, 204}:
                    raise ValueError(f"WebDAV upload failed (HTTP {response.status_code})")
                with encrypted.open("rb") as stream:
                    expected = hashlib.file_digest(stream, "sha256").hexdigest()
                if self._download(session, remote) != expected:
                    raise ValueError("Remote backup checksum differs after upload")
            result = {"status": "verified", "name": remote}
            self._record("last_transfer", result)
            return result
        except Exception:
            self._record("last_transfer", {"status": "failed", "error": "External transfer failed; check destination and credentials"})
            raise

    def import_backup(self, name):
        self._url(name)
        password = self.secrets.get_secret("backup_encryption_password")
        if not password:
            raise ValueError("Configure the original encryption password before importing")
        self.cfg.backup_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.cfg.backup_dir) as directory, self._session() as session:
            encrypted = Path(directory) / "remote.aioenc"
            archive = Path(directory) / "amm-import.tar.gz"
            self._download(session, name, encrypted)
            decrypt_archive(encrypted, archive, password)
            # Verify before importing into the real backup directory.
            from core.settings import Settings
            isolated = BackupManager(Settings(config_dir=Path(directory) / "config", backup_dir=Path(directory)))
            isolated.ensure_sidecar(archive)
            if not isolated.verify_backup(archive.name).get("ok"):
                raise ValueError("Imported backup failed verification")
            destination = self.cfg.backup_dir / f"amm-imported-{uuid.uuid4().hex[:12]}.tar.gz"
            archive.replace(destination)
            self.manager.ensure_sidecar(destination)
        return {"status": "imported", "name": destination.name}

    def drill(self, name):
        try:
            return self._drill(name)
        except Exception:
            self._record("last_drill", {"status": "failed", "name": name})
            raise

    def _drill(self, name):
        """Extract into a disposable root, never the active configuration."""
        if not self.manager.verify_backup(name).get("ok"):
            raise ValueError("Backup failed verification")
        from core.settings import Settings
        self.cfg.cache_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=self.cfg.cache_dir) as directory:
            root = Path(directory)
            cfg = Settings(config_dir=root / "config", backup_dir=root / "backups")
            cfg.backup_dir.mkdir(parents=True)
            source = self.manager.resolve_archive(name)
            shutil.copyfile(source, cfg.backup_dir / name)
            sandbox = BackupManager(cfg)
            sandbox.ensure_sidecar(cfg.backup_dir / name)
            result = sandbox.restore_backup(name)
            if result["files"] == 0:
                raise ValueError("No files were restored in the test")
            manifest = sandbox.read_manifest(cfg.backup_dir / name)
            for rel, entry in (manifest.get("files") or {}).items():
                path = cfg.config_dir / rel
                if sandbox.is_excluded(rel):
                    continue
                if not path.resolve().is_relative_to(cfg.config_dir.resolve()):
                    raise ValueError("Unsafe restored path")
                with path.open("rb") as stream:
                    if hashlib.file_digest(stream, "sha256").hexdigest() != entry["sha256"]:
                        raise ValueError("Restored file differs from backup")
        result = {"status": "verified", "name": name, "files": result["files"]}
        self._record("last_drill", result)
        return result
