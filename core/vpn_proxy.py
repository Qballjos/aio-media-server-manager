"""TCP proxies that publish VPN-netns WebUIs on the container's main network.

Docker publishes host ports into this container's main netns. qBittorrent /
Prowlarr / Flaresolverr listen inside ``amm-torrent``, so Synology/Docker
userland proxies get connection resets unless something in the main netns
accepts those ports and forwards into the veth peer.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Iterable, Mapping

logger = logging.getLogger(__name__)


class VpnWebUiProxy:
    """Listen on 0.0.0.0:<port> and bridge to dest_host:<dest_port>."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._servers: dict[int, socket.socket] = {}
        self._threads: dict[int, threading.Thread] = {}
        self._targets: dict[int, tuple[str, int]] = {}
        self._dest_host = "10.200.200.2"

    def ensure(
        self,
        ports: Iterable[int] | Mapping[int, int],
        *,
        dest_host: str = "10.200.200.2",
    ) -> list[int]:
        if isinstance(ports, Mapping):
            mapping = {int(listen): int(dest) for listen, dest in ports.items() if int(listen) > 0}
        else:
            mapping = {int(p): int(p) for p in ports if int(p) > 0}
        with self._lock:
            self._dest_host = dest_host
            self._stop.clear()
            for port in list(self._servers):
                if port not in mapping:
                    self._stop_one(port)
            ready: list[int] = []
            for listen_port, dest_port in sorted(mapping.items()):
                self._targets[listen_port] = (dest_host, dest_port)
                if listen_port in self._threads and self._threads[listen_port].is_alive():
                    ready.append(listen_port)
                    continue
                if self._start_one(listen_port):
                    ready.append(listen_port)
            return ready

    def stop_all(self) -> None:
        with self._lock:
            self._stop.set()
            for port in list(self._servers):
                self._stop_one(port)

    def listening_ports(self) -> list[int]:
        with self._lock:
            return sorted(
                port
                for port, thread in self._threads.items()
                if thread.is_alive() and port in self._servers
            )

    def _start_one(self, port: int) -> bool:
        target = self._targets.get(port, (self._dest_host, port))
        sock = self._servers.pop(port, None)
        thread = self._threads.pop(port, None)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("0.0.0.0", port))
            sock.listen(128)
            sock.settimeout(1.0)
        except OSError as exc:
            logger.warning("VPN WebUI proxy could not bind 0.0.0.0:%s: %s", port, exc)
            try:
                sock.close()
            except OSError:
                pass
            return False

        thread = threading.Thread(
            target=self._serve,
            args=(port, sock, target),
            name=f"amm-vpn-proxy-{port}",
            daemon=True,
        )
        self._servers[port] = sock
        self._threads[port] = thread
        self._targets[port] = target
        thread.start()
        logger.info("VPN WebUI proxy listening on 0.0.0.0:%s → %s:%s", port, target[0], target[1])
        return True

    def _stop_one(self, port: int) -> None:
        sock = self._servers.pop(port, None)
        thread = self._threads.pop(port, None)
        self._targets.pop(port, None)
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)

    def _serve(self, port: int, server: socket.socket, target: tuple[str, int]) -> None:
        while not self._stop.is_set():
            try:
                client, _addr = server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            worker = threading.Thread(
                target=self._bridge,
                args=(client, target),
                name=f"amm-vpn-bridge-{port}",
                daemon=True,
            )
            worker.start()
        try:
            server.close()
        except OSError:
            pass

    def _bridge(self, client: socket.socket, target: tuple[str, int]) -> None:
        upstream: socket.socket | None = None
        try:
            upstream = socket.create_connection(target, timeout=5.0)
            client.settimeout(120.0)
            upstream.settimeout(120.0)
            done = threading.Event()

            def copy(src: socket.socket, dst: socket.socket) -> None:
                try:
                    while not done.is_set():
                        try:
                            data = src.recv(65536)
                        except OSError:
                            break
                        if not data:
                            break
                        try:
                            dst.sendall(data)
                        except OSError:
                            break
                finally:
                    done.set()
                    try:
                        dst.shutdown(socket.SHUT_WR)
                    except OSError:
                        pass

            t1 = threading.Thread(target=copy, args=(client, upstream), daemon=True)
            t2 = threading.Thread(target=copy, args=(upstream, client), daemon=True)
            t1.start()
            t2.start()
            t1.join(timeout=130.0)
            t2.join(timeout=5.0)
        except OSError as exc:
            logger.debug("VPN WebUI proxy bridge to %s failed: %s", target, exc)
        finally:
            for sock in (client, upstream):
                if sock is None:
                    continue
                try:
                    sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                try:
                    sock.close()
                except OSError:
                    pass


vpn_webui_proxy = VpnWebUiProxy()
