import socket

import pytest

from clippers import netguard
from clippers.netguard import UnsafeURLError, check_public_url

# Captured when this module is imported, before conftest's per-test fake replaces it.
REAL_RESOLVE = netguard._resolve  # pyright: ignore[reportPrivateUsage]


def resolves_to(monkeypatch: pytest.MonkeyPatch, *addresses: str) -> None:
    monkeypatch.setattr(netguard, "_resolve", lambda host, port: list(addresses))


@pytest.mark.parametrize(
    "address",
    [
        "127.0.0.1",  # loopback
        "10.0.0.5",  # private
        "172.16.3.4",
        "192.168.1.1",
        "169.254.169.254",  # cloud metadata service (link-local)
        "100.64.0.1",  # carrier-grade NAT
        "0.0.0.0",
        "224.0.0.1",  # multicast
        "::1",
        "fe80::1%en0",  # link-local with a zone id
        "fc00::1",  # IPv6 private
        "::ffff:127.0.0.1",  # IPv4 loopback wrapped in IPv6
    ],
)
def test_non_public_addresses_are_blocked(monkeypatch: pytest.MonkeyPatch, address: str) -> None:
    resolves_to(monkeypatch, address)

    with pytest.raises(UnsafeURLError, match="private or reserved"):
        check_public_url("https://innocent-looking.example/video.mp4")


def test_public_address_is_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    resolves_to(monkeypatch, "142.250.200.14", "2a00:1450:4009:81a::200e")

    check_public_url("https://www.youtube.com/watch?v=abc")  # no exception


def test_one_private_answer_among_public_ones_is_enough_to_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # DNS can return several addresses; the downloader may connect to any of them.
    resolves_to(monkeypatch, "8.8.8.8", "10.1.2.3")

    with pytest.raises(UnsafeURLError):
        check_public_url("https://mixed.example/")


def test_client_message_does_not_reveal_the_internal_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolves_to(monkeypatch, "10.20.30.40")

    with pytest.raises(UnsafeURLError) as exc_info:
        check_public_url("https://intranet.example/")

    assert "10.20.30.40" not in str(exc_info.value)


@pytest.mark.parametrize(
    ("url", "message"),
    [
        ("ftp://example.com/x.mp4", "only http"),
        ("file:///etc/passwd", "only http"),
        ("https:///no-host", "no host"),
        ("https://example.com:99999/", "invalid port"),
    ],
)
def test_malformed_urls(url: str, message: str) -> None:
    with pytest.raises(UnsafeURLError, match=message):
        check_public_url(url)


def test_unresolvable_host(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(host: str, port: int) -> list[str]:
        raise socket.gaierror("nodename nor servname provided")

    monkeypatch.setattr(netguard, "_resolve", fail)

    with pytest.raises(UnsafeURLError, match="can't resolve"):
        check_public_url("https://no-such-host.invalid/")


@pytest.mark.parametrize("url", ["http://2130706433/", "http://0x7f.1/", "http://127.1/"])
def test_real_resolver_sees_through_numeric_disguises(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    # The real system resolver (conftest swaps in a fake for every test; undo that here).
    # No network needed: numeric hosts are decoded locally, all to 127.0.0.1.
    monkeypatch.setattr(netguard, "_resolve", REAL_RESOLVE)

    with pytest.raises(UnsafeURLError):
        check_public_url(url)
