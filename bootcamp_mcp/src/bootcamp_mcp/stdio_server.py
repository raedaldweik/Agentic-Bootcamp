"""stdio-mode server, for testing the scope from a desktop MCP client.

Token resolution is the upstream server's: the SAS Viya CLI cache
(``~/.sas/credentials.json``), then the ``sas-mcp-login`` cache
(``~/.sas-mcp-server/credentials.json``), then a device-code flow. Importing
``sas_mcp_server.stdio_server`` builds the upstream server object as a side
effect (it is never run); the cost is a moment at start-up.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastmcp import FastMCP
from sas_mcp_server.stdio_server import _stdio_get_token
from sas_mcp_server.viya_client import logger
from sas_mcp_server.viya_utils import shutdown_session_cache

from . import __version__
from .config import (
    AUTH_ENABLED,
    CAS_SERVER,
    CONTEXT_NAME,
    MAX_ROWS,
    MAX_SCORE_ROWS,
    SCORE_STEP,
    SERVER_NAME,
    VIYA_ENDPOINT,
)
from .server import build_scopes
from .tools import register

load_dotenv()


@asynccontextmanager
async def _lifespan(server: FastMCP) -> AsyncIterator[dict]:
    try:
        yield {}
    finally:
        await shutdown_session_cache()


TABLES, MODELS = build_scopes()
logger.info("bootcamp-mcp %s (stdio) - connecting to SAS Viya at %s", __version__, VIYA_ENDPOINT)
if not AUTH_ENABLED:
    logger.warning("VIYA_AUTH=false: SASLogon authentication is disabled")

mcp = FastMCP(SERVER_NAME, version=__version__, lifespan=_lifespan)
register(
    mcp,
    _stdio_get_token,
    tables=TABLES,
    models=MODELS,
    cas_server=CAS_SERVER,
    context_name=CONTEXT_NAME,
    max_rows=MAX_ROWS,
    max_score_rows=MAX_SCORE_ROWS,
    score_step=SCORE_STEP,
)


def main() -> None:
    mcp.run(transport="stdio", show_banner=False)


if __name__ == "__main__":
    main()
