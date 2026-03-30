import base64
import ipaddress
import socket
from urllib.parse import urlparse

import tornado.httpclient
import tornado.web

from compresso.libs.installation_link import Links

_HTTP_SCHEME = "http://"

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),  # Loopback
    ipaddress.ip_network("::1/128"),  # IPv6 loopback
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local / cloud metadata
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
]


def _is_blocked_address(hostname):
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
        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if addr.is_loopback or addr.is_link_local or addr.is_reserved:
            return True
        for net in _BLOCKED_NETWORKS:
            if addr in net:
                return True
    return False


def resolve_proxy_target(target_id):
    """
    Finds the remote installation config based on target_id (name, address, or uuid).
    Returns a dict with 'url', 'auth_header' (dict), or None.
    """
    links = Links()
    remotes = links.settings.get_remote_installations()
    target_config = None

    # Helper to search remotes
    def search_remotes(search_list):
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
    url_base = target_config.get("address", "").rstrip("/")
    if not url_base.startswith("http"):
        url_base = _HTTP_SCHEME + url_base

    # Validate target is not a private/internal address (SSRF protection)
    parsed = urlparse(url_base)
    hostname = parsed.hostname
    if not hostname or _is_blocked_address(hostname):
        return None

    # Auth
    auth_headers = {}
    if target_config.get("auth") and target_config.get("auth").lower() == "basic":
        username = target_config.get("username", "")
        password = target_config.get("password", "")
        auth_str = f"{username}:{password}"
        auth_bytes = auth_str.encode("ascii")
        base64_bytes = base64.b64encode(auth_bytes)
        auth_headers["Authorization"] = f"Basic {base64_bytes.decode('ascii')}"

    return {"url_base": url_base, "headers": auth_headers, "config": target_config}


class ProxyHandler(tornado.web.RequestHandler):
    SUPPORTED_METHODS = ("GET", "HEAD", "POST", "DELETE", "PATCH", "PUT", "OPTIONS")

    async def prepare(self):
        """No-op — base handler prepare is sufficient."""

    async def _handle_request(self, method):
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
        headers = self.request.headers.copy()
        for h in ["Host", "Content-Length", "Transfer-Encoding", "Connection", "X-Compresso-Target-Installation"]:
            if h in headers:
                del headers[h]

        # Add Auth
        headers.update(target_info["headers"])

        # Override Host to target? optional, but some servers require it matching
        # headers['Host'] = ...

        body = self.request.body if self.request.body else None

        client = tornado.httpclient.AsyncHTTPClient()
        try:
            response = await client.fetch(
                url, method=method, headers=headers, body=body, follow_redirects=False, raise_error=False
            )

            self.set_status(response.code)
            for k, v in response.headers.get_all():
                if k.lower() not in ["content-length", "transfer-encoding", "connection", "server"]:
                    self.set_header(k, v)

            if response.body:
                self.write(response.body)

        except Exception:
            self.set_status(502)
            self.write({"error": "Proxy Error"})

    async def get(self):
        await self._handle_request("GET")

    async def head(self):
        await self._handle_request("HEAD")

    async def post(self):
        await self._handle_request("POST")

    async def delete(self):
        await self._handle_request("DELETE")

    async def patch(self):
        await self._handle_request("PATCH")

    async def put(self):
        await self._handle_request("PUT")

    async def options(self):
        await self._handle_request("OPTIONS")
