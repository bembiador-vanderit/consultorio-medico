"""No official DB, credentials or pairing. Private ingress + public HTTP boundary."""
import pytest
from fastapi import FastAPI, Depends, Request, HTTPException
from fastapi.testclient import TestClient
from uvicorn import Config

from app.api.routes.local_agents import secure_transport
from app.core.trusted_proxy import TrustedProxyIngress

HOST = "atlas.example.test"
PEER = "192.0.2.11"
HEADERS = {"host": HOST, "x-forwarded-host": HOST, "x-forwarded-proto": "https"}


def application():
    app = FastAPI()

    @app.get("/scope")
    def scope(request: Request):
        return {"scheme": request.url.scheme, "host": request.url.hostname,
                "client": request.client.host,
                "headers": dict(request.headers)}

    @app.get("/device", dependencies=[Depends(secure_transport)])
    def device():
        raise HTTPException(401, "Credencial de estación requerida")

    return app


def ingress():
    return TrustedProxyIngress(application(), peer=PEER, hostname=HOST)


def client_at(app, peer):
    # Installed Starlette predates TestClient(client=...). Set only the synthetic
    # ASGI connection peer, outside the middleware under test.
    async def with_peer(scope, receive, send):
        if scope["type"] in {"http", "websocket"}:
            scope = {**scope, "client": (peer, 1234)}
        await app(scope, receive, send)
    return TestClient(with_peer)


def test_private_exact_peer_https_and_host():
    with client_at(ingress(), PEER) as client:
        response = client.get("/scope", headers=HEADERS)
        assert response.status_code == 200
        data = response.json()
        assert (data["scheme"], data["host"], data["client"]) == ("https", HOST, PEER)
        assert not any(key.startswith("x-forwarded-") for key in data["headers"])
        assert client.get("/device", headers=HEADERS).status_code == 401


@pytest.mark.parametrize("peer", ["192.0.2.10", "192.0.2.12", "127.0.0.1", "testclient"])
def test_untrusted_peer_cannot_spoof_host_proto_or_for(peer):
    with client_at(ingress(), peer) as client:
        assert client.get("/scope", headers={**HEADERS, "x-forwarded-for": PEER}).status_code == 400


@pytest.mark.parametrize("changes", [
    {"host": "other.example.test"}, {"host": HOST + ":8001"},
    {"x-forwarded-host": "other.example.test"},
    {"x-forwarded-proto": "http"}, {"x-forwarded-proto": "https,http"},
    {"forwarded": "proto=https;host=atlas.example.test"},
    {"tailscale-funnel-request": "?1"},
])
def test_private_bad_or_ambiguous_forwarding_denied(changes):
    with client_at(ingress(), PEER) as client:
        assert client.get("/scope", headers={**HEADERS, **changes}).status_code == 400


@pytest.mark.parametrize("name", ["host", "x-forwarded-proto", "x-forwarded-host"])
def test_missing_or_duplicate_critical_header_denied(name):
    headers = [(key, value) for key, value in HEADERS.items() if key != name]
    with client_at(ingress(), PEER) as client:
        assert client.get("/scope", headers=headers).status_code == 400
        headers += [(name, HEADERS[name]), (name, HEADERS[name])]
        assert client.get("/scope", headers=headers).status_code == 400


def test_forwarded_client_identity_never_trusted_or_exposed():
    with client_at(ingress(), PEER) as client:
        result = client.get("/scope", headers={**HEADERS, "x-forwarded-for": "127.0.0.1",
            "x-forwarded-port": "1234", "x-real-ip": "127.0.0.1", "tailscale-user-login": "forged@example.test"})
        assert result.status_code == 200
        data = result.json()
        assert data["client"] == PEER
        assert not any(key.startswith(("x-forwarded-", "tailscale-")) or key == "x-real-ip" for key in data["headers"])


@pytest.mark.parametrize("headers", [HEADERS,
    {**HEADERS, "x-forwarded-for": "127.0.0.1"},
    {**HEADERS, "forwarded": "proto=https"},
])
def test_direct_http_stays_http_and_registry_denies(headers):
    # This matches --no-proxy-headers on the public Uvicorn listener.
    config = Config(application(), proxy_headers=False)
    config.load()
    with client_at(config.loaded_app, PEER) as client:
        data = client.get("/scope", headers=headers).json()
        assert data["scheme"] == "http"
        assert data["client"] == PEER
        assert client.get("/device", headers=headers).status_code == 400


@pytest.mark.parametrize("peer", ["*", "192.0.2.0/24", "0.0.0.0", "", "gateway"])
def test_configuration_rejects_broad_trust(peer):
    with pytest.raises(ValueError):
        TrustedProxyIngress(application(), peer=peer, hostname=HOST)


@pytest.mark.parametrize("hostname", ["*", "", "https://atlas.example.test", "localhost", "atlas..example.test"])
def test_configuration_requires_canonical_hostname(hostname):
    with pytest.raises(ValueError):
        TrustedProxyIngress(application(), peer=PEER, hostname=hostname)
