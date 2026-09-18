"""Settings for the bootcamp server.

Everything about *connecting* to Viya (endpoint, OAuth client, TLS, raw-bearer
policy, compute context, port) is read by ``sas_mcp_server.config`` exactly as
the upstream server reads it, so one ``.env`` drives both servers. This module
adds only the bootcamp's own switches: the scope, the CAS server and two caps.
"""

import os

from dotenv import load_dotenv

# Importing the upstream config validates VIYA_ENDPOINT and builds the OAuth
# proxy (``viya_auth``). Re-exported so the rest of this package has one place
# to import settings from.
from sas_mcp_server.config import (  # noqa: F401
    ALLOW_RAW_BEARER,
    AUTH_ENABLED,
    CONTEXT_NAME,
    HOST_PORT,
    SSL_VERIFY,
    VIYA_ENDPOINT,
    viya_auth,
)
from sas_mcp_server.exceptions import ConfigError

load_dotenv()

DEFAULT_SERVER_NAME = "Bootcamp MCP Server"
SERVER_NAME = os.getenv("MCP_SERVER_NAME", DEFAULT_SERVER_NAME)

# The scope. Comma-separated, case-insensitive, ``*`` wildcards. Parsed and
# enforced by :mod:`bootcamp_mcp.scope`.
ALLOWED_TABLES = os.getenv("ALLOWED_TABLES", "")
ALLOWED_MODELS = os.getenv("ALLOWED_MODELS", "")

CAS_SERVER = os.getenv("CAS_SERVER", "cas-shared-default").strip() or "cas-shared-default"

# Cap on rows any single query / preview / scoring batch may pull (1..10000,
# the upper bound being the FedSQL helper's own MAX_LIMIT).
_max_rows_raw = os.getenv("BOOTCAMP_MAX_ROWS", "500").strip()
try:
    MAX_ROWS = max(1, min(int(_max_rows_raw), 10_000))
except ValueError:
    raise ConfigError(f"BOOTCAMP_MAX_ROWS must be an integer (got {_max_rows_raw!r}).") from None

# Which MAS step scores: "auto" (prefer "score", else "execute") or a name.
SCORE_STEP = os.getenv("BOOTCAMP_SCORE_STEP", "auto").strip() or "auto"

# How many rows one score_table_rows call may score. MAS scoring is one HTTP
# round trip per row, so this is a latency cap as much as a load cap.
MAX_SCORE_ROWS = 50
