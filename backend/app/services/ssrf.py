from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse

import httpx

BLOCKED_HOSTS = {"localhost", "metadata.google.internal", "metadata"}


class FetchError(ValueError):
    pass


def _is_blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return bool(
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_https(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise FetchError("Only public HTTPS product URLs are fetched.")
    host = parsed.hostname
    if not host or host in BLOCKED_HOSTS:
        raise FetchError("Host is not allowed.")
    try:
        infos = socket.getaddrinfo(host, 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise FetchError(f"Could not resolve host {host}.") from exc
    for info in infos:
        address = info[4][0]
        if _is_blocked_ip(address):
            raise FetchError("Resolved address is private or reserved. Fetch blocked.")
    return url


async def fetch_public_https(url: str, max_bytes: int = 2_000_000) -> tuple[bytes, str, str]:
    current = validate_public_https(url)
    async with httpx.AsyncClient(follow_redirects=False, timeout=15.0) as client:
        for _ in range(4):
            response = await client.get(current, headers={"User-Agent": "ClosestChemistry/1.0"})
            if response.is_redirect:
                location = response.headers.get("location")
                if not location:
                    raise FetchError("Redirect missing Location.")
                current = validate_public_https(
                    location if location.startswith("https://") else str(response.url.join(location))
                )
                continue
            response.raise_for_status()
            content = response.content
            if len(content) > max_bytes:
                raise FetchError("Remote document exceeds size limit.")
            return content, response.headers.get("content-type", ""), str(response.url)
        raise FetchError("Too many redirects.")
