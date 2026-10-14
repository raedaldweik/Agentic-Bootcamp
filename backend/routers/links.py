"""Environment links and branding, read from the environment so the deployed app can be
pointed at the SAS Viya and SAS RAM environments from the Railway Variables tab without a rebuild.
ENV1_VIYA_URL / ENV1_RAM_URL stand in when the plain variables are not set (services.teams).

  VIYA_URL        the SAS Viya environment
  RAM_URL         the SAS Retrieval Agent Manager UI
  LOGO_URL    optional: an absolute URL to a hosted logo, used instead of the bundled SAS logo
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Request

from services import teams

router = APIRouter()

def _env(name: str, default: str = "") -> str:
    # The browser's team first (services.teams), then the process environment.
    return teams.setting(name, default)


@router.get("/api/links")
def links(request: Request):
    teams.set_current(request.cookies.get(teams.COOKIE))
    cur = teams.current()
    return {
        "team": teams.public(cur),
        "links": [
            {"id": "ram", "label": "SAS RAM", "sub": "Where the agent is built and run",
             "url": _env("RAM_URL"), "icon": "ram"},
            {"id": "viya", "label": "SAS Viya", "sub": "Data, models and dashboards",
             "url": _env("VIYA_URL"), "icon": "viya"},
        ],
        "branding": {
            # one logo now, the SAS wordmark top left; SAS_LOGO_URL is honoured as the older name
            "logo_url": _env("LOGO_URL") or _env("SAS_LOGO_URL") or None,
        },
    }
