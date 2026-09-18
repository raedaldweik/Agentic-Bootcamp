"""bootcamp-mcp: a scoped SAS Viya MCP server for the EHS x SAS Agentic AI Bootcamp.

Built on ``sas_mcp_server`` (the SAS Viya MCP server): the same authentication
proxy, the same Viya HTTP client and compute-session pool, the same FedSQL
engine. What differs is the surface: eight tools instead of 92, and every one
of them refuses to touch anything outside ``ALLOWED_TABLES`` / ``ALLOWED_MODELS``.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("bootcamp-mcp")
except PackageNotFoundError:  # running from a source checkout
    __version__ = "0.0.0+dev"

__all__ = ["__version__"]
