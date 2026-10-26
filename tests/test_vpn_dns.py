"""Caching DNS forwarder used by the VPN apps."""

from __future__ import annotations

import struct

import pytest

from core import vpn_dns
from core.vpn_dns import VpnDnsForwarder, answer_ttl, question_key


def _query(name: str, qid: int = 0x1234) -> bytes:
    labels = b"".join(bytes([len(part)]) + part.encode() for part in name.split(".")) + b"\0"
    return struct.pack("!HHHHHH", qid, 0x0100, 1, 0, 0, 0) + labels + struct.pack("!HH", 1, 1)


def _answer(query: bytes, ip: str = "203.0.113.7", ttl: int = 300, rcode: int = 0) -> bytes:
    key = question_key(query)
    assert key
    question = query[12 : key[1]]
    header = query[:2] + struct.pack("!HHHHH", 0x8180 | rcode, 1, 1, 0, 0)
    record = b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, ttl, 4) + bytes(int(p) for p in ip.split("."))
    return header + question + record


@pytest.fixture
def forwarder(monkeypatch):
    fwd = VpnDnsForwarder()
    fwd._iface = lambda: "wg0"
    monkeypatch.setattr(vpn_dns, "_SECOND_WAVE_DELAY", 0.05)
    return fwd


def test_question_key_ignores_case_and_ttl_is_clamped():
    assert question_key(_query("Nyaa.SI"))[0] == question_key(_query("nyaa.si"))[0]
    assert answer_ttl(_answer(_query("nyaa.si"), ttl=5)) == vpn_dns._MIN_TTL
    assert answer_ttl(_answer(_query("nyaa.si"), ttl=90_000)) == vpn_dns._MAX_TTL
    assert answer_ttl(_answer(_query("nyaa.si"), ttl=120)) == 120


def test_answers_are_cached_and_keep_the_client_id(forwarder, monkeypatch):
    calls = []

    def udp(server, query, iface):
        calls.append(server)
        return _answer(query)

    monkeypatch.setattr(vpn_dns, "_udp_exchange", udp)
    first = forwarder.resolve(_query("nyaa.si", qid=1), tcp=False)
    second = forwarder.resolve(_query("nyaa.si", qid=2), tcp=False)
    assert first[:2] == b"\x00\x01"
    assert second[:2] == b"\x00\x02"
    assert second[2:] == first[2:]
    assert forwarder.status()["cache_hits"] == 1
    assert len(calls) <= vpn_dns._FIRST_WAVE


def test_last_good_answer_is_used_when_upstream_fails(forwarder, monkeypatch):
    monkeypatch.setattr(vpn_dns, "_udp_exchange", lambda server, query, iface: _answer(query))
    good = forwarder.resolve(_query("www.usenet-crawler.com"), tcp=False)

    key = question_key(_query("www.usenet-crawler.com"))[0]
    expires, reply = forwarder._cache[key]
    forwarder._cache[key] = (expires - 10_000, reply)

    def down(server, query, iface):
        raise OSError("network unreachable")

    monkeypatch.setattr(vpn_dns, "_udp_exchange", down)
    monkeypatch.setattr(vpn_dns, "_tcp_exchange", down)
    stale = forwarder.resolve(_query("www.usenet-crawler.com"), tcp=False)
    assert stale[2:] == good[2:]
    assert forwarder.status()["stale_answers"] == 1


def test_other_resolvers_answer_when_the_first_ones_fail(forwarder, monkeypatch):
    first_wave = set(vpn_dns.UPSTREAMS[: vpn_dns._FIRST_WAVE])

    def udp(server, query, iface):
        if server in first_wave:
            raise OSError("timed out")
        return _answer(query)

    monkeypatch.setattr(vpn_dns, "_udp_exchange", udp)
    monkeypatch.setattr(vpn_dns, "_tcp_exchange", udp)
    reply = forwarder.resolve(_query("nyaa.si"), tcp=False)
    assert reply[3] & 0x0F == 0
    assert sum(forwarder.status()["upstream_errors"].values()) >= 2


def test_servfail_from_upstream_is_not_cached_and_returns_servfail(forwarder, monkeypatch):
    monkeypatch.setattr(vpn_dns, "_udp_exchange", lambda server, query, iface: _answer(query, rcode=2))
    monkeypatch.setattr(vpn_dns, "_tcp_exchange", lambda server, query, iface: _answer(query, rcode=2))
    reply = forwarder.resolve(_query("nyaa.si"), tcp=False)
    assert reply[3] & 0x0F == 2
    assert reply[:2] == _query("nyaa.si")[:2]
    assert not forwarder._cache


def test_nxdomain_is_a_real_answer(forwarder, monkeypatch):
    monkeypatch.setattr(vpn_dns, "_udp_exchange", lambda server, query, iface: _answer(query, rcode=3))
    reply = forwarder.resolve(_query("missing.example"), tcp=False)
    assert reply[3] & 0x0F == 3


def test_no_tunnel_means_no_upstream_query(forwarder, monkeypatch):
    forwarder._iface = lambda: None

    def never(*args):
        raise AssertionError("must not query without the tunnel")

    monkeypatch.setattr(vpn_dns, "_udp_exchange", never)
    monkeypatch.setattr(vpn_dns, "_tcp_exchange", never)
    reply = forwarder.resolve(_query("nyaa.si"), tcp=False)
    assert reply[3] & 0x0F == 2


def test_truncated_udp_retries_over_tcp(forwarder, monkeypatch):
    def udp(server, query, iface):
        reply = bytearray(_answer(query))
        reply[2] |= 0x02
        return bytes(reply)

    monkeypatch.setattr(vpn_dns, "_udp_exchange", udp)
    monkeypatch.setattr(vpn_dns, "_tcp_exchange", lambda server, query, iface: _answer(query, ip="198.51.100.1"))
    reply = forwarder.resolve(_query("nyaa.si"), tcp=False)
    assert reply.endswith(bytes([198, 51, 100, 1]))
