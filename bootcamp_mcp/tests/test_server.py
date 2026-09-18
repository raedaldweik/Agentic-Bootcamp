"""The HTTP server module: auth wiring, routes and the registered surface."""

import httpx
import pytest
from fastmcp import Client

from bootcamp_mcp import server
from bootcamp_mcp.tools import ALL_TOOLS


def test_auth_is_the_upstream_proxy():
    from sas_mcp_server.auth import PermissiveOAuthProxy

    assert isinstance(server.viya_auth, PermissiveOAuthProxy)
    assert server.mcp.auth is server.viya_auth
    assert any(isinstance(m, server.AuthMiddleware) for m in server.mcp.middleware)


async def test_registered_surface():
    assert tuple(server.TOOLS) == ALL_TOOLS
    async with Client(server.mcp) as client:
        names = {t.name for t in await client.list_tools()}
    assert names == set(ALL_TOOLS)


async def test_health_and_facts_routes():
    transport = httpx.ASGITransport(app=server.app)
    async with (
        server.app.router.lifespan_context(server.app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        health = await client.get("/health")
        facts = await client.get("/")
    assert health.status_code == 200 and health.json()["status"] == "healthy"
    body = facts.json()
    assert body["allowed_tables"] == ["CASUSER.REGISTRY_TEAM3", "PUBLIC.EHS_FACILITIES"]
    assert body["allowed_models"] == ["deterioration_team3"]
    assert body["tools"] == list(ALL_TOOLS)
    assert body["auth"]["enabled"] is True


async def test_mcp_endpoint_requires_a_token():
    transport = httpx.ASGITransport(app=server.app)
    async with (
        server.app.router.lifespan_context(server.app),
        httpx.AsyncClient(transport=transport, base_url="http://test") as client,
    ):
        resp = await client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert resp.status_code == 401


def test_empty_scope_is_a_config_error(monkeypatch):
    from sas_mcp_server.exceptions import ConfigError

    monkeypatch.setattr(server, "ALLOWED_TABLES", "")
    monkeypatch.setattr(server, "ALLOWED_MODELS", "")
    with pytest.raises(ConfigError):
        server.build_scopes()
