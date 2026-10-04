"""Bootcamp environment links and branding, read from the environment so the deployed app can be
pointed at the day's SAS Viya and SAS RAM environments (and the materials repo) from the Railway
Variables tab without a rebuild.

  VIYA_URL        the SAS Viya environment participants log into
  RAM_URL         the SAS Retrieval Agent Manager UI
  MATERIALS_URL   the bootcamp materials (defaults to this repository on GitHub)
  EHS_LOGO_URL    optional: an absolute URL to a hosted EHS logo, used instead of /ehs-logo.png
  SAS_LOGO_URL    optional: an absolute URL to a hosted SAS logo, used instead of /sas-logo.png
"""
from __future__ import annotations

import os

from fastapi import APIRouter, Request

from services import teams

router = APIRouter()

MATERIALS_DEFAULT = "https://github.com/raedaldweik/Agentic-Bootcamp"


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
            {"id": "ram", "label": "RAM", "sub": "Where you build and test your agent",
             "url": _env("RAM_URL"), "icon": "ram"},
            {"id": "viya", "label": "Viya", "sub": "Data, models and dashboards",
             "url": _env("VIYA_URL"), "icon": "viya"},
            {"id": "materials", "label": "Hackathon materials", "sub": "Decks, labs, data and this application",
             "url": _env("MATERIALS_URL", MATERIALS_DEFAULT), "icon": "materials"},
        ],
        "branding": {
            "ehs_logo_url": _env("EHS_LOGO_URL") or None,
            "sas_logo_url": _env("SAS_LOGO_URL") or None,
        },
    }
