"""Refuse to fetch URLs that point into private networks (SSRF protection).

The API downloads whatever URL a client sends. Without this check, a client could make
the server fetch http://localhost:6379, http://10.0.0.5/admin, or the cloud metadata
service at http://169.254.169.254/ (which can hand out the server's own credentials).

The check resolves the hostname with the same system resolver the downloader will use,
so disguises like http://2130706433/ (127.0.0.1 as one number), http://0x7f.1/, or a
public-looking DNS name pointing at 10.0.0.5 are all caught.

Limits, by design of an application-level check: a server that *redirects* to a private
address, or DNS that changes its answer between this check and the download ("DNS
rebinding"), can still get through. The real boundary is the network: run the worker
where it can't reach private ranges (an egress firewall / container network policy).
"""

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address


class UnsafeURLError(ValueError):
    """The URL points somewhere the server must not fetch from."""


def _resolve(host: str, port: int) -> list[str]:
    """All IP addresses `host` resolves to. (Patched in tests: no real DNS there.)"""
    infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    return [str(info[4][0]) for info in infos]


def _is_public(ip: IPAddress) -> bool:
    # An IPv6 address can wrap an IPv4 one (::ffff:127.0.0.1); judge the IPv4 inside.
    # Current Python already rates these correctly on its own; older patch releases had
    # bugs here, so unwrap explicitly rather than depend on the exact Python version.
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    # is_global is False for loopback, private, link-local (incl. 169.254.169.254),
    # carrier-grade NAT (100.64/10), multicast, reserved and documentation ranges.
    return ip.is_global and not ip.is_multicast


def check_public_url(url: str) -> None:
    """Raise UnsafeURLError unless `url` is http(s) and every address it resolves to is
    public. Blocks on DNS: call it from a thread in async code."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeURLError("only http(s) URLs are allowed")
    host = parsed.hostname
    if not host:
        raise UnsafeURLError("URL has no host")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as e:  # e.g. a port above 65535
        raise UnsafeURLError(f"invalid port in URL: {e}") from e

    try:
        addresses = _resolve(host, port)
    except (socket.gaierror, UnicodeError) as e:
        raise UnsafeURLError(f"can't resolve host {host!r}") from e

    for address in addresses:
        ip = ipaddress.ip_address(address.split("%", 1)[0])  # drop IPv6 zone ids ("fe80::1%en0")
        if not _is_public(ip):
            # Log the address for operators; don't tell the client about internal hosts.
            logger.warning("blocked URL %s: %s resolves to non-public %s", url, host, ip)
            raise UnsafeURLError(f"{host} points to a private or reserved network address")
