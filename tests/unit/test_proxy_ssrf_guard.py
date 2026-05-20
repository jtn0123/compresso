#!/usr/bin/env python3

"""
tests.unit.test_proxy_ssrf_guard.py

Unit tests for compresso.webserver.proxy._is_blocked_address:
- Loopback/link-local/IPv6 link-local block-list behavior
- AWS metadata service blocking (169.254.169.254)
- DNS failure fail-closed behavior
- Resolvable hostname that returns a blocked IP
- Empty/None hostname handling
- Public IPs are allowed (8.8.8.8)
- RFC1918 private/LAN addresses are explicitly allowed per the module's
  docstring (remote installations are typically on the local network)
"""

import socket
from unittest.mock import patch

import pytest

from compresso.webserver.proxy import _is_blocked_address


def _addrinfo(ip):
    """Build a getaddrinfo-shaped result for a single IP."""
    if ":" in ip:
        return [(socket.AF_INET6, socket.SOCK_STREAM, 0, "", (ip, 0, 0, 0))]
    return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", (ip, 0))]


@pytest.mark.unittest
class TestIsBlockedAddress:
    """Tests for the SSRF guard used before proxying remote installation requests."""

    def test_loopback_ipv4_127_0_0_1_is_blocked(self):
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            assert _is_blocked_address("127.0.0.1") is True

    def test_loopback_ipv4_127_5_5_5_is_blocked(self):
        # Anything inside 127.0.0.0/8 is loopback
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo("127.5.5.5")):
            assert _is_blocked_address("127.5.5.5") is True

    def test_loopback_ipv6_is_blocked(self):
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo("::1")):
            assert _is_blocked_address("ip6-localhost") is True

    def test_aws_metadata_link_local_is_blocked(self):
        # 169.254.169.254 — the cloud metadata service — must always be blocked.
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo("169.254.169.254")):
            assert _is_blocked_address("metadata.local") is True

    def test_link_local_ipv6_is_blocked(self):
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo("fe80::1")):
            assert _is_blocked_address("ll.example") is True

    def test_public_ipv4_is_not_blocked(self):
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo("8.8.8.8")):
            assert _is_blocked_address("dns.google") is False

    def test_rfc1918_lan_addresses_are_allowed_by_design(self):
        # The module docstring states LAN addresses (10.x, 172.16-31.x, 192.168.x)
        # are intentionally permitted because remote installations are usually on the
        # local network. Lock in that behavior so we notice if it ever changes.
        for ip in ("10.0.0.5", "192.168.1.1", "172.16.0.1"):
            with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo(ip)):
                assert _is_blocked_address("lan.example") is False, f"Expected {ip} to be allowed (LAN)"

    def test_hostname_resolving_to_loopback_is_blocked(self):
        # Even a benign-looking hostname is blocked if DNS points it at a loopback IP
        # (this is the classic DNS rebinding scenario).
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo("127.0.0.1")):
            assert _is_blocked_address("evil.example.com") is True

    def test_hostname_resolving_to_metadata_ip_is_blocked(self):
        # Hostname that points to the AWS metadata IP must be blocked.
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=_addrinfo("169.254.169.254")):
            assert _is_blocked_address("metadata-rebinder.example") is True

    def test_dns_failure_fails_closed(self):
        with patch("compresso.webserver.proxy.socket.getaddrinfo", side_effect=socket.gaierror("name or service not known")):
            assert _is_blocked_address("does-not-resolve.invalid") is True

    def test_oserror_fails_closed(self):
        # OSError is also caught and should fail closed.
        with patch("compresso.webserver.proxy.socket.getaddrinfo", side_effect=OSError("network unreachable")):
            assert _is_blocked_address("anywhere.example") is True

    def test_empty_hostname_fails_closed(self):
        # getaddrinfo("", None) typically raises gaierror, but be defensive and
        # use a side_effect to guarantee the fail-closed behavior is exercised
        # without depending on the host resolver's quirks.
        with patch("compresso.webserver.proxy.socket.getaddrinfo", side_effect=socket.gaierror("empty")):
            assert _is_blocked_address("") is True

    def test_none_hostname_fails_closed(self):
        # socket.getaddrinfo(None, ...) returns a loopback in some environments,
        # so we simulate the more common failure mode of raising gaierror.
        with patch("compresso.webserver.proxy.socket.getaddrinfo", side_effect=socket.gaierror("none")):
            assert _is_blocked_address(None) is True

    def test_multiple_addresses_blocks_if_any_is_blocked(self):
        # If a hostname returns both a public and a private/loopback address,
        # the function must still block (defense in depth).
        addrs = [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("8.8.8.8", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 0, "", ("127.0.0.1", 0)),
        ]
        with patch("compresso.webserver.proxy.socket.getaddrinfo", return_value=addrs):
            assert _is_blocked_address("mixed.example") is True


if __name__ == "__main__":
    pytest.main(["-s", "--log-cli-level=INFO", __file__])
