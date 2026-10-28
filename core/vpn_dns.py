"""Caching DNS forwarder for the VPN apps.

Prowlarr, qBittorrent, and FlareSolverr resolve through this instead of asking
a public resolver directly. Their lookups had no cache and no retry, so one
lost UDP packet on the tunnel failed the lookup and Prowlarr disabled the
indexer. Upstream queries leave on the tunnel interface (SO_BINDTODEVICE), go to
several resolvers at once, retry over TCP, and fall back to the last good answer
while the upstream is unreachable.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
import time
from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from typing import Callable

logger = logging.getLogger(__name__)

LISTEN_HOST = "127.0.0.153"
LISTEN_PORT = 53
UPSTREAMS = ("1.1.1.1", "9.9.9.9", "8.8.8.8", "1.0.0.1")
_FIRST_WAVE = 2
_SECOND_WAVE_DELAY = 0.8
_UDP_TIMEOUT = 1.5
_TCP_TIMEOUT = 2.5
# glibc waits 5s per nameserver (see the resolv.conf options), so answer or give up before that.
_DEADLINE = 4.5
_MIN_TTL = 30
_MAX_TTL = 600
_STALE_SECONDS = 6 * 3600
_CACHE_SIZE = 4096
_RCODE_SERVFAIL = 2
_RCODE_NXDOMAIN = 3


def _skip_name(msg: bytes, offset: int) -> int:
    while True:
        if offset >= len(msg):
            raise ValueError("name runs past message")
        length = msg[offset]
        if length == 0:
            return offset + 1
        if length & 0xC0 == 0xC0:
            return offset + 2
        offset += 1 + length


def question_key(msg: bytes) -> tuple[bytes, int] | None:
    """Lower-cased question section and its end offset, or None for anything but one question."""
    if len(msg) < 12:
        return None
    qdcount = struct.unpack("!H", msg[4:6])[0]
    if qdcount != 1:
        return None
    try:
        end = _skip_name(msg, 12) + 4
    except ValueError:
        return None
    if end > len(msg):
        return None
    return msg[12:end].lower(), end


def answer_ttl(msg: bytes) -> int:
    """Smallest TTL in the answer and authority sections, clamped for caching."""
    try:
        qdcount, ancount, nscount = struct.unpack("!HHH", msg[4:10])
        offset = 12
        for _ in range(qdcount):
            offset = _skip_name(msg, offset) + 4
        ttls: list[int] = []
        for _ in range(ancount + nscount):
            offset = _skip_name(msg, offset)
            _rtype, _rclass, ttl, rdlength = struct.unpack("!HHIH", msg[offset : offset + 10])
            ttls.append(ttl)
            offset += 10 + rdlength
    except (ValueError, struct.error):
        return _MIN_TTL
    if not ttls:
        return _MIN_TTL
    return max(_MIN_TTL, min(_MAX_TTL, min(ttls)))


def _rcode(msg: bytes) -> int:
    return msg[3] & 0x0F if len(msg) >= 4 else _RCODE_SERVFAIL


def _truncated(msg: bytes) -> bool:
    return len(msg) >= 3 and bool(msg[2] & 0x02)


def _with_id(msg: bytes, query: bytes) -> bytes:
    return query[:2] + msg[2:]


def servfail(query: bytes) -> bytes:
    """Minimal SERVFAIL reply so glibc moves on to the next nameserver."""
    key = question_key(query)
    question = query[12 : key[1]] if key else b""
    flags = 0x8180 | _RCODE_SERVFAIL | (struct.unpack("!H", query[2:4])[0] & 0x0100 if len(query) >= 4 else 0)
    return query[:2] + struct.pack("!HHHHH", flags, 1 if question else 0, 0, 0, 0) + question


class VpnDnsForwarder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cache_lock = threading.Lock()
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        self._sockets: list[socket.socket] = []
        self._pool: ThreadPoolExecutor | None = None
        self._ask_pool = ThreadPoolExecutor(max_workers=64, thread_name_prefix="amm-vpn-dns-up")
        self._iface: Callable[[], str | None] = lambda: None
        self._cache: OrderedDict[bytes, tuple[float, bytes]] = OrderedDict()
        self._stats = {
            "queries": 0,
            "cache_hits": 0,
            "stale_answers": 0,
            "upstream_failures": 0,
            "servfail": 0,
        }
        self._upstream_errors: dict[str, int] = {server: 0 for server in UPSTREAMS}
        self._last_error = ""

    # ---- lifecycle -------------------------------------------------------

    def running(self) -> bool:
        with self._lock:
            return bool(self._threads) and all(thread.is_alive() for thread in self._threads)

    def ensure(self, iface: Callable[[], str | None]) -> bool:
        """Start listening on 127.0.0.153:53. False (and logged) when the port is taken."""
        with self._lock:
            self._iface = iface
            if self._threads and all(thread.is_alive() for thread in self._threads):
                return True
            self._stop_unlocked()
            self._stop.clear()
            udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                udp.bind((LISTEN_HOST, LISTEN_PORT))
                tcp.bind((LISTEN_HOST, LISTEN_PORT))
                tcp.listen(64)
                udp.settimeout(1.0)
                tcp.settimeout(1.0)
            except OSError as exc:
                for sock in (udp, tcp):
                    try:
                        sock.close()
                    except OSError:
                        pass
                self._last_error = f"could not bind {LISTEN_HOST}:{LISTEN_PORT}: {exc}"
                logger.warning(
                    "VPN DNS cache unavailable (%s). VPN apps query public resolvers directly.",
                    self._last_error,
                )
                return False
            self._pool = ThreadPoolExecutor(max_workers=32, thread_name_prefix="amm-vpn-dns")
            self._sockets = [udp, tcp]
            self._threads = [
                threading.Thread(target=self._serve_udp, args=(udp,), name="amm-vpn-dns-udp", daemon=True),
                threading.Thread(target=self._serve_tcp, args=(tcp,), name="amm-vpn-dns-tcp", daemon=True),
            ]
            for thread in self._threads:
                thread.start()
            self._last_error = ""
            logger.info("VPN DNS cache listening on %s:%s via the tunnel", LISTEN_HOST, LISTEN_PORT)
            return True

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        self._stop.set()
        for sock in self._sockets:
            try:
                sock.close()
            except OSError:
                pass
        for thread in self._threads:
            if thread.is_alive() and thread is not threading.current_thread():
                thread.join(timeout=2.0)
        if self._pool is not None:
            self._pool.shutdown(wait=False, cancel_futures=True)
        self._pool = None
        self._sockets = []
        self._threads = []

    def status(self) -> dict:
        with self._cache_lock:
            cached = len(self._cache)
        return {
            "listening": self.running(),
            "address": f"{LISTEN_HOST}:{LISTEN_PORT}",
            "upstreams": list(UPSTREAMS),
            "cached_names": cached,
            "upstream_errors": dict(self._upstream_errors),
            "last_error": self._last_error,
            **self._stats,
        }

    # ---- listeners -------------------------------------------------------

    def _serve_udp(self, sock: socket.socket) -> None:
        while not self._stop.is_set():
            try:
                query, client = sock.recvfrom(4096)
            except socket.timeout:
                continue
            except OSError:
                break
            pool = self._pool
            if pool is None:
                break
            pool.submit(self._answer_udp, sock, query, client)

    def _answer_udp(self, sock: socket.socket, query: bytes, client) -> None:
        reply = self.resolve(query, tcp=False)
        try:
            sock.sendto(reply, client)
        except OSError:
            pass

    def _serve_tcp(self, server: socket.socket) -> None:
        while not self._stop.is_set():
            try:
                conn, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            pool = self._pool
            if pool is None:
                conn.close()
                break
            pool.submit(self._answer_tcp, conn)

    def _answer_tcp(self, conn: socket.socket) -> None:
        try:
            conn.settimeout(_TCP_TIMEOUT)
            while True:
                header = _recv_exact(conn, 2)
                if not header:
                    return
                query = _recv_exact(conn, struct.unpack("!H", header)[0])
                if not query:
                    return
                reply = self.resolve(query, tcp=True)
                conn.sendall(struct.pack("!H", len(reply)) + reply)
        except OSError:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass

    # ---- resolution ------------------------------------------------------

    def resolve(self, query: bytes, *, tcp: bool) -> bytes:
        self._stats["queries"] += 1
        key = question_key(query)
        now = time.monotonic()
        cached = self._cache_get(key[0]) if key else None
        if cached and cached[0] > now:
            self._stats["cache_hits"] += 1
            return _with_id(cached[1], query)
        reply = self._upstream(query, tcp=tcp)
        if reply is not None and key and not _truncated(reply):
            self._cache_put(key[0], now + answer_ttl(reply), reply)
            return reply
        if reply is not None:
            return reply
        if cached and cached[0] + _STALE_SECONDS > now:
            self._stats["stale_answers"] += 1
            return _with_id(cached[1], query)
        self._stats["servfail"] += 1
        return servfail(query)

    def _upstream(self, query: bytes, *, tcp: bool) -> bytes | None:
        iface = self._iface()
        if not iface:
            self._last_error = "tunnel interface is not up"
            return None
        pool = self._ask_pool
        start = time.monotonic()
        deadline = start + _DEADLINE
        pending = {pool.submit(self._ask, server, query, iface, tcp) for server in UPSTREAMS[:_FIRST_WAVE]}
        later = list(UPSTREAMS[_FIRST_WAVE:])
        while pending or later:
            now = time.monotonic()
            if later and (not pending or now - start >= _SECOND_WAVE_DELAY):
                pending |= {pool.submit(self._ask, server, query, iface, tcp) for server in later}
                later = []
            until = start + _SECOND_WAVE_DELAY if later else deadline
            if now >= deadline:
                break
            done, pending = wait(pending, timeout=max(0.05, until - now), return_when=FIRST_COMPLETED)
            for future in done:
                reply = future.result()
                if reply is not None:
                    return reply
        self._stats["upstream_failures"] += 1
        return None

    def _ask(self, server: str, query: bytes, iface: str, tcp: bool) -> bytes | None:
        try:
            reply = None if tcp else _udp_exchange(server, query, iface)
            if reply is None or _truncated(reply):
                reply = _tcp_exchange(server, query, iface)
        except OSError as exc:
            self._upstream_errors[server] = self._upstream_errors.get(server, 0) + 1
            self._last_error = f"{server}: {exc}"
            return None
        if reply is None or len(reply) < 12 or reply[:2] != query[:2]:
            self._upstream_errors[server] = self._upstream_errors.get(server, 0) + 1
            return None
        if _rcode(reply) not in (0, _RCODE_NXDOMAIN):
            self._upstream_errors[server] = self._upstream_errors.get(server, 0) + 1
            return None
        return reply

    def _cache_get(self, key: bytes) -> tuple[float, bytes] | None:
        with self._cache_lock:
            item = self._cache.get(key)
            if item is not None:
                self._cache.move_to_end(key)
            return item

    def _cache_put(self, key: bytes, expires: float, reply: bytes) -> None:
        with self._cache_lock:
            self._cache[key] = (expires, reply)
            self._cache.move_to_end(key)
            while len(self._cache) > _CACHE_SIZE:
                self._cache.popitem(last=False)


def _bound_socket(kind: int, iface: str) -> socket.socket:
    sock = socket.socket(socket.AF_INET, kind)
    try:
        sock.setsockopt(socket.SOL_SOCKET, getattr(socket, "SO_BINDTODEVICE", 25), iface.encode() + b"\0")
    except OSError:
        sock.close()
        raise
    return sock


def _udp_exchange(server: str, query: bytes, iface: str) -> bytes | None:
    sock = _bound_socket(socket.SOCK_DGRAM, iface)
    try:
        sock.settimeout(_UDP_TIMEOUT)
        sock.connect((server, 53))
        sock.send(query)
        deadline = time.monotonic() + _UDP_TIMEOUT
        while time.monotonic() < deadline:
            reply = sock.recv(4096)
            if reply[:2] == query[:2]:
                return reply
        return None
    except socket.timeout:
        return None
    finally:
        sock.close()


def _tcp_exchange(server: str, query: bytes, iface: str) -> bytes | None:
    sock = _bound_socket(socket.SOCK_STREAM, iface)
    try:
        sock.settimeout(_TCP_TIMEOUT)
        sock.connect((server, 53))
        sock.sendall(struct.pack("!H", len(query)) + query)
        header = _recv_exact(sock, 2)
        if not header:
            return None
        return _recv_exact(sock, struct.unpack("!H", header)[0])
    except socket.timeout:
        return None
    finally:
        sock.close()


def _recv_exact(sock: socket.socket, size: int) -> bytes | None:
    data = b""
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data += chunk
    return data


vpn_dns_forwarder = VpnDnsForwarder()
