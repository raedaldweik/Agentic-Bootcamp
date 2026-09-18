"""HTTP-mode server: the transport SAS Retrieval Agent Manager connects to.

Authentication is the upstream server's, unchanged: ``viya_auth`` is the same
``PermissiveOAuthProxy`` built by ``sas_mcp_server.config`` (browser OAuth
with PKCE against SASLogon, and, with ``ALLOW_RAW_BEARER=true``, a Viya JWT
presented directly by a client such as RAM), and the middleware below is the
upstream ``AuthMiddleware``: it swaps the bearer on the request for the Viya
access token and stores it in the request context for the tools.

Copyright notice: the middleware and token getter are reproduced from
sassoftware/sas-mcp-server (Apache-2.0) so the two servers cannot drift.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from dotenv import load_dotenv
from fastmcp import Context, FastMCP
from fastmcp.server.dependencies import get_http_request
from fastmcp.server.middleware import Middleware, MiddlewareContext
from sas_mcp_server.exceptions import AuthenticationError, ConfigError
from sas_mcp_server.viya_client import logger
from sas_mcp_server.viya_utils import shutdown_session_cache
from starlette.requests import Request
from starlette.responses import JSONResponse

from . import __version__
from .config import (
    ALLOW_RAW_BEARER,
    ALLOWED_MODELS,
    ALLOWED_TABLES,
    AUTH_ENABLED,
    CAS_SERVER,
    CONTEXT_NAME,
    MAX_ROWS,
    MAX_SCORE_ROWS,
    SCORE_STEP,
    SERVER_NAME,
    VIYA_ENDPOINT,
    viya_auth,
)
from .scope import ModelScope, TableScope
from .tools import register

load_dotenv()


class AuthMiddleware(Middleware):
    """Swap the client's bearer token for the upstream Viya access token."""

    async def on_call_tool(self, ctx: MiddlewareContext, call_next: Any) -> Any:
        request = get_http_request()
        bearer_token = request.headers.get("Authorization")
        if not bearer_token:
            logger.error("No auth header found. Cannot proceed")
            raise AuthenticationError("No auth header found. Cannot proceed")

        parts = bearer_token.split()
        jwt = parts[1] if len(parts) > 1 and parts[0].lower() == "bearer" else bearer_token
        logger.info("Client auth header found, Swapping for upstream token")
        viya_access_info = await viya_auth.load_access_token(jwt)
        if viya_access_info:
            logger.info("Viya access info retrieved successfully!")
            fastmcp_ctx = ctx.fastmcp_context
            if fastmcp_ctx is not None:
                await fastmcp_ctx.set_state("access_token", viya_access_info.token)
        else:
            logger.error("Could not retrieve upstream access token!")
        return await call_next(ctx)


async def _http_get_token(ctx: Context) -> str:
    if not AUTH_ENABLED:
        return ""
    token = await ctx.get_state("access_token")
    if not token:
        raise AuthenticationError("No auth header found. Cannot authenticate to Viya")
    return token


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    """Tear down warm compute sessions when the server stops."""
    try:
        yield {}
    finally:
        await shutdown_session_cache()


def build_scopes() -> tuple[TableScope, ModelScope]:
    tables = TableScope.from_env(ALLOWED_TABLES)
    models = ModelScope.from_env(ALLOWED_MODELS)
    if not tables and not models:
        raise ConfigError(
            "Nothing is in scope: set ALLOWED_TABLES (caslib.table, comma-separated) and/or "
            "ALLOWED_MODELS (MAS module ids) so the server has something to expose."
        )
    return tables, models


TABLES, MODELS = build_scopes()

logger.info(
    "bootcamp-mcp %s (http) - connecting to SAS Viya at %s; tables=%s models=%s",
    __version__,
    VIYA_ENDPOINT,
    TABLES.display,
    MODELS.display,
)

_mcp_kwargs: dict[str, Any] = {"lifespan": _lifespan, "version": __version__}
if AUTH_ENABLED:
    _mcp_kwargs["auth"] = viya_auth
else:
    logger.warning(
        "VIYA_AUTH=false: SASLogon authentication is disabled; Viya API calls are sent without Authorization headers"
    )
mcp = FastMCP(SERVER_NAME, **_mcp_kwargs)
if AUTH_ENABLED:
    mcp.add_middleware(AuthMiddleware())

TOOLS = register(
    mcp,
    _http_get_token,
    tables=TABLES,
    models=MODELS,
    cas_server=CAS_SERVER,
    context_name=CONTEXT_NAME,
    max_rows=MAX_ROWS,
    max_score_rows=MAX_SCORE_ROWS,
    score_step=SCORE_STEP,
)


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request: Request) -> JSONResponse:
    return JSONResponse({"status": "healthy", "service": "bootcamp-mcp", "version": __version__})


@mcp.custom_route("/", methods=["GET"])
async def facts(request: Request) -> JSONResponse:
    """Deployment shape for the facilitator: which scope this container carries.

    Unauthenticated by design and limited to configuration (no data, no
    tokens), the same posture as the upstream landing page.
    """
    return JSONResponse(
        {
            "name": SERVER_NAME,
            "version": __version__,
            "viya": VIYA_ENDPOINT,
            "auth": {"enabled": AUTH_ENABLED, "allow_raw_bearer": ALLOW_RAW_BEARER},
            "tools": TOOLS,
            "allowed_tables": TABLES.display,
            "allowed_models": MODELS.display,
            "cas_server": CAS_SERVER,
            "max_rows": MAX_ROWS,
        }
    )


app = mcp.http_app()
