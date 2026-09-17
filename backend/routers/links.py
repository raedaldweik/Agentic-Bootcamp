"""Bootcamp environment links and branding, read from the environment so the deployed app can be
pointed at the day's SAS Viya and SAS RAM environments (and the materials repo) from the Railway
Variables tab without a rebuild.

  VIYA_URL        the SAS Viya environment participants log into
  RAM_URL         the SAS Retrieval Agent Manager UI
  MATERIALS_URL   the bootcamp materials (defaults to this repository on GitHub)
  EHS_LOGO_URL    optional: an absolute URL to the official EHS logo, used instead of /ehs-logo.svg
"""
from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter()

MATERIALS_DEFAULT = "https://github.com/raedaldweik/Agentic-Bootcamp"


def _env(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


@router.get("/api/links")
def links():
    return {
        "links": [
            {"id": "viya", "label": "SAS Viya environment", "sub": "Data, models, decisions and Visual Analytics",
             "url": _env("VIYA_URL"), "icon": "viya"},
            {"id": "ram", "label": "SAS RAM environment", "sub": "Retrieval Agent Manager: agents, collections, tools",
             "url": _env("RAM_URL"), "icon": "ram"},
            {"id": "materials", "label": "Bootcamp materials", "sub": "Decks, labs, data and this application",
             "url": _env("MATERIALS_URL", MATERIALS_DEFAULT), "icon": "materials"},
        ],
        "branding": {"ehs_logo_url": _env("EHS_LOGO_URL") or None},
    }
