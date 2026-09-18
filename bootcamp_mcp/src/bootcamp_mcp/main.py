"""``bootcamp-mcp``: run the HTTP server (what the container starts)."""

import uvicorn

from .config import HOST_PORT


def main() -> None:
    uvicorn.run("bootcamp_mcp.server:app", host="0.0.0.0", port=HOST_PORT)


if __name__ == "__main__":
    main()
