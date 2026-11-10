"""The HTTP application: the MCP server at `/mcp`, streamable HTTP in stateless mode, and a
health check at `/health`."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from mcp.server.streamable_http_manager import StreamableHTTPASGIApp, StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings
from starlette.routing import Route

from mtg_goldfishing.adapters.mcp.server import mcp_server
from mtg_goldfishing.adapters.mcp.tools import ToolSurface
from mtg_goldfishing.application.service import Service

MCP_PATH = "/mcp"
LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _transport_security(host: str) -> TransportSecuritySettings:
    """Guard a service bound to the local machine against DNS rebinding.

    A service bound to another address is meant to be reached by other names, so the
    `Host` and `Origin` headers are not checked.
    """
    if host not in LOOPBACK:
        return TransportSecuritySettings(enable_dns_rebinding_protection=False)
    return TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=["127.0.0.1:*", "localhost:*", "[::1]:*"],
        allowed_origins=["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
    )


async def health() -> dict[str, str]:
    """A small success response for checking that the service is up."""
    return {"status": "ok"}


# @spec TOOL-001, TOOL-002
def create_app(service: Service, *, host: str = "127.0.0.1") -> FastAPI:
    """The FastAPI application serving the tools over `service`."""
    sessions = StreamableHTTPSessionManager(
        app=mcp_server(ToolSurface(service)),
        stateless=True,
        security_settings=_transport_security(host),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        async with sessions.run():
            yield

    app = FastAPI(title="MTG Goldfishing", lifespan=lifespan)
    app.add_api_route("/health", health, methods=["GET"])
    app.router.routes.append(Route(MCP_PATH, endpoint=StreamableHTTPASGIApp(sessions)))
    return app
