import base64
import ipaddress
import socket
from collections.abc import Mapping, Sequence
from typing import TypedDict
from urllib.parse import urlparse

import tornado.httpclient
import tornado.web

from compresso import config
from compresso.libs import narrowing
from compresso.libs.installation_link import Links
from compresso.webserver.request_auth import API_AUTH_HEADER_NAME, authorize_request
from compresso.webserver.security_headers import SecurityHeadersMixin

_HTTP_SCHEME = "http://"

PROXY_REQUEST_HEADER_ALLOWLIST = (
    "Accept",
    "Accept-Encoding",
    "Accept-Language",
    "Content-Type",
    "Content-Encoding",
    "Cache-Control",
    "If-Match",
    "If-None-Match",
    "If-Modified-Since",
    "If-Unmodified-Since",
    "If-Range",
    "Range",
    "X-Transfer-Offset",
    "X-Chunk-Checksum",
)
PROXY_RESPONSE_HEADER_ALLOWLIST = (
    "Content-Type",
    "Content-Disposition",
    "Content-Encoding",
    "Cache-Control",
    "ETag",
    "Last-Modified",
    "Accept-Ranges",
    "Content-Range",
    "Expires",
    "Retry-After",
    "X-Transfer-Offset",
    "X-Chunk-Checksum",
)
TARGET_CREDENTIAL_HEADERS = ("Authorization", API_AUTH_HEADER_NAME)
BLOCKED_REDIRECT_STATUSES = frozenset((301, 302, 303, 307, 308))


class ProxyTarget(TypedDict):
    url_base: str
    headers: dict[str, str]
    config: dict[str, object]


def _allowed_headers(headers: Mapping[str, str], allowlist: Sequence[str]) -> dict[str, str]:
    return {name: value for name in allowlist if (value := headers.get(name)) is not None}


def build_proxy_request_headers(inbound_headers: Mapping[str, str], target_credentials: Mapping[str, str]) -> dict[str, str]:
    """Copy only protocol metadata, then apply credentials for the selected worker."""
    headers = _allowed_headers(inbound_headers, PROXY_REQUEST_HEADER_ALLOWLIST)
    headers.update(_allowed_headers(target_credentials, TARGET_CREDENTIAL_HEADERS))
    return headers


def build_proxy_response_headers(upstream_headers: Mapping[str, str]) -> dict[str, str]:
    """Return only response metadata safe to expose through the master."""
    return _allowed_headers(upstream_headers, PROXY_RESPONSE_HEADER_ALLOWLIST)


def is_blocked_proxy_redirect(status_code: int) -> bool:
    """Return whether an upstream response would redirect the proxy client."""
    return status_code in BLOCKED_REDIRECT_STATUSES


_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / cloud metadata
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def _is_blocked_address(hostname: str) -> bool:
    """
    Check if a hostname resolves to a loopback, link-local, or cloud metadata IP.
    LAN addresses (10.x, 172.16-31.x, 192.168.x) are allowed since remote
    installations are typically other machines on the local network.
    Returns True if the address should be blocked (fail-closed on DNS errors).
    """
    try:
        addr_infos = socket.getaddrinfo(hostname, None)
    except (socket.gaierror, OSError):
        # Fail closed: if we can't resolve, don't allow the request
        return True
    for _family, _type, _proto, _canonname, sockaddr in addr_infos:
        ip_str = sockaddr[0]
        if not isinstance(ip_str, str):
            return True
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return True
        if addr.is_private and not config.Config().get_allow_lan_proxy_targets():
            return True
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                return True
    return False


def resolve_proxy_target(target_id: str | None) -> ProxyTarget | None:
    """
    Finds the remote installation config based on target_id (name, address, or uuid).
    Returns a dict with 'url', 'auth_header' (dict), or None.
    """
    links = Links()
    remotes = links.settings.get_remote_installations()
    target_config: dict[str, object] | None = None

    # Helper to search remotes
    def search_remotes(search_list: Sequence[dict[str, object]]) -> dict[str, object] | None:
        if not target_id:
            return None
        t_id = str(target_id).strip().lower()
        # Priority 1: Address (normalized)
        for r in search_list:
            addr = str(r.get("address", "")).strip().lower().rstrip("/")
            addr_bare = addr.replace(_HTTP_SCHEME, "").replace("https://", "")
            t_id_bare = t_id.replace(_HTTP_SCHEME, "").replace("https://", "")
            if addr == t_id or addr == t_id.rstrip("/") or addr_bare == t_id_bare:
                return r
        # Priority 2: UUID
        for r in search_list:
            if str(r.get("uuid", "")).strip().lower() == t_id:
                return r
        # Priority 3: Name
        for r in search_list:
            if str(r.get("name", "")).strip().lower() == t_id:
                return r
        return None

    target_config = search_remotes(remotes)

    if not target_config:
        # Try reloading settings in case another process updated them
        links.settings.reload()
        remotes = links.settings.get_remote_installations()
        target_config = search_remotes(remotes)

    if not target_config:
        return None

    # Construct URL base
    url_base = narrowing.strict_str(target_config.get("address")).rstrip("/")
    if not url_base.startswith("http"):
        url_base = _HTTP_SCHEME + url_base

    # Validate target is not a private/internal address (SSRF protection)
    parsed = urlparse(url_base)
    hostname = parsed.hostname
    if not hostname or _is_blocked_address(hostname):
        return None

    # Auth
    auth_headers: dict[str, str] = {}
    auth_type = narrowing.strict_str(target_config.get("auth"))
    if auth_type.lower() == "basic":
        username = narrowing.strict_str(target_config.get("username"))
        password = narrowing.strict_str(target_config.get("password"))
        auth_str = f"{username}:{password}"
        auth_bytes = auth_str.encode("ascii")
        base64_bytes = base64.b64encode(auth_bytes)
        auth_headers["Authorization"] = f"Basic {base64_bytes.decode('ascii')}"
    api_token = str(target_config.get("api_token") or "")
    if api_token:
        auth_headers[API_AUTH_HEADER_NAME] = api_token

    return {"url_base": url_base, "headers": auth_headers, "config": target_config}


class ProxyHandler(SecurityHeadersMixin, tornado.web.RequestHandler):
    SUPPORTED_METHODS = ("GET", "HEAD", "POST", "DELETE", "PATCH", "PUT", "OPTIONS")

    def set_default_headers(self) -> None:
        self.set_security_headers()

    async def prepare(self) -> None:
        if not authorize_request(self):
            return

    async def _handle_request(self, method: str) -> None:
        target_id = self.request.headers.get("X-Compresso-Target-Installation")
        target_info = resolve_proxy_target(target_id)

        if not target_info:
            self.set_status(400)
            self.write({"error": "Unknown remote installation"})
            return

        # Construct URL
        path = self.request.path
        if self.request.query:
            path += "?" + self.request.query

        url = f"{target_info['url_base']}{path}"

        # Prepare headers
        headers = build_proxy_request_headers(self.request.headers, target_info["headers"])

        # Override Host to target? optional, but some servers require it matching
        # headers['Host'] = ...

        body = self.request.body if self.request.body else None

        client = tornado.httpclient.AsyncHTTPClient()
        try:
            response = await client.fetch(
                url, method=method, headers=headers, body=body, follow_redirects=False, raise_error=False
            )

            if is_blocked_proxy_redirect(response.code):
                self.set_status(502)
                self.write({"error": "Worker redirect blocked"})
                return

            self.set_status(response.code)
            for key, value in build_proxy_response_headers(response.headers).items():
                self.set_header(key, value)

            if response.body:
                self.write(response.body)

        except Exception:
            self.set_status(502)
            self.write({"error": "Proxy Error"})

    async def get(self) -> None:
        await self._handle_request("GET")

    async def head(self) -> None:
        await self._handle_request("HEAD")

    async def post(self) -> None:
        await self._handle_request("POST")

    async def delete(self) -> None:
        await self._handle_request("DELETE")

    async def patch(self) -> None:
        await self._handle_request("PATCH")

    async def put(self) -> None:
        await self._handle_request("PUT")

    async def options(self) -> None:
        await self._handle_request("OPTIONS")
