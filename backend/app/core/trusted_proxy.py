"""Explicit, private ingress for a TLS-terminating proxy on the Docker host.

Never install on a publicly reachable listener. A gateway IP alone does not
distinguish the proxy from direct requests to a Docker-published public port.
The dedicated port must be published on host loopback only. Local host processes
are inside this trust boundary; this is not process authentication or mTLS.
"""
import ipaddress
import re

from starlette.responses import JSONResponse
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


def forwarding_header(name: bytes) -> bool:
    return (name == b"forwarded" or name.startswith(b"x-forwarded-")
            or name == b"x-real-ip" or name.startswith(b"tailscale-"))


class TrustedProxyIngress:
    def __init__(self, app, *, peer: str, hostname: str):
        # An exact address, never a network or wildcard.
        address = ipaddress.ip_address(peer)
        if address.is_unspecified or address.is_multicast:
            raise ValueError("Trusted proxy requires an exact unicast address")
        if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", hostname):
            raise ValueError("Trusted proxy requires an explicit DNS hostname")
        if ".." in hostname or "." not in hostname:
            raise ValueError("Trusted proxy requires an explicit DNS hostname")
        self.peer = str(address)
        self.hosts = {hostname.encode("ascii"), (hostname + ":443").encode("ascii")}
        self.app = app
        self.proxy = ProxyHeadersMiddleware(self._clean_application, trusted_hosts=[self.peer])

    async def _clean_application(self, scope, receive, send):
        # Do not let downstream consumers reinterpret forwarded/identity headers.
        scope = dict(scope)
        scope["headers"] = [(k, v) for k, v in scope["headers"] if not forwarding_header(k)]
        await self.app(scope, receive, send)

    async def __call__(self, scope, receive, send):
        if scope["type"] not in {"http", "websocket"}:
            await self.app(scope, receive, send)
            return
        headers = scope.get("headers", [])
        values = lambda name: [v for k, v in headers if k == name]
        client = scope.get("client")
        trusted = bool(client and client[0] == self.peer)
        valid = (trusted and values(b"host") in [[h] for h in self.hosts]
                 and values(b"x-forwarded-proto") == [b"https"]
                 and values(b"x-forwarded-host") in [[h] for h in self.hosts]
                 and not values(b"forwarded")
                 and not values(b"tailscale-funnel-request"))
        if not valid:
            if scope["type"] == "websocket":
                await send({"type": "websocket.close", "code": 1008})
            else:
                await JSONResponse({"detail": "Entrada de proxy no autorizada"}, status_code=400)(scope, receive, send)
            return
        scope = dict(scope)
        # Only Proto is needed. In particular, never use a supplied For/Host to
        # switch tenant or forge a client address, even on the trusted ingress.
        scope["headers"] = [(k, v) for k, v in headers if not forwarding_header(k)]
        scope["headers"].append((b"x-forwarded-proto", b"https"))
        await self.proxy(scope, receive, send)
