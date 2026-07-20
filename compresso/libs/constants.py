"""Shared constants that must be importable from `libs` without touching `webserver`.

The intended dependency direction is `webserver -> libs`. Anything under
`libs/` (or `ops/`) that needs one of these values imports it from here rather
than reaching back into the web layer.
"""

API_AUTH_HEADER_NAME = "X-Compresso-Api-Token"
WEBSOCKET_AUTH_PROTOCOL_PREFIX = "compresso-auth."
