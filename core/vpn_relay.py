"""UDP relay so WireGuard inside amm-torrent can reach its endpoint without NAT.

Synology/Docker often cannot MASQUERADE from the torrent netns. The relay binds on
the host veth IP; wg-quick inside the netns peers with that address, and this
process forwards datagrams to the real VPN endpoint using the main netns (normal
Docker outbound NAT).
"""

from __future__ import annotations

import logging
import select
import socket
import threading

logger = logging.getLogger(__name__)


class WgEndpointRelay:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._sock: socket.socket | None = None
        self._listen: tuple[str, int] | None = None
        self._dest: tuple[str, int] | None = None

    def ensure(self, *, listen_host: str, listen_port: int, dest_host: str, dest_port: int) -> bool:
        listen = (listen_host, int(listen_port))
        dest = (dest_host, int(dest_port))
        with self._lock:
            if (
                self._thread is not None
                and self._thread.is_alive()
                and self._listen == listen
                and self._dest == dest
            ):
                return True
            self._stop_unlocked()
            self._stop.clear()
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                sock.bind(listen)
                sock.settimeout(1.0)
            except OSError as exc:
                logger.warning("VPN endpoint relay could not bind %s:%s: %s", listen[0], listen[1], exc)
                try:
                    sock.close()
                except OSError:
                    pass
                return False
            self._sock = sock
            self._listen = listen
            self._dest = dest
            self._thread = threading.Thread(
                target=self._serve,
                args=(sock, dest),
                name=f"amm-wg-relay-{listen[1]}",
                daemon=True,
            )
            self._thread.start()
            logger.info(
                "VPN endpoint relay %s:%s → %s:%s",
                listen[0],
                listen[1],
                dest[0],
                dest[1],
            )
            return True

    def stop(self) -> None:
        with self._lock:
            self._stop_unlocked()

    def _stop_unlocked(self) -> None:
        self._stop.set()
        sock = self._sock
        self._sock = None
        thread = self._thread
        self._thread = None
        self._listen = None
        self._dest = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _serve(self, sock: socket.socket, dest: tuple[str, int]) -> None:
        client: tuple[str, int] | None = None
        upstream = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            upstream.settimeout(1.0)
            while not self._stop.is_set():
                try:
                    readable, _, _ = select.select([sock, upstream], [], [], 1.0)
                except (OSError, ValueError):
                    break
                if sock in readable:
                    try:
                        data, addr = sock.recvfrom(65535)
                    except OSError:
                        break
                    if not data:
                        continue
                    client = addr
                    try:
                        upstream.sendto(data, dest)
                    except OSError as exc:
                        logger.debug("VPN relay send to %s failed: %s", dest, exc)
                if upstream in readable:
                    try:
                        data, _from = upstream.recvfrom(65535)
                    except OSError:
                        continue
                    if not data or client is None:
                        continue
                    try:
                        sock.sendto(data, client)
                    except OSError as exc:
                        logger.debug("VPN relay reply to %s failed: %s", client, exc)
        finally:
            try:
                upstream.close()
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass


vpn_endpoint_relay = WgEndpointRelay()
