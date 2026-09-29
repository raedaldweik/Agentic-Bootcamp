"""Teams: one SAS Viya and SAS RAM environment per team.

The hackathon can run each team on its own pair of environments. A team is a row
in ``TEAMS_FILE`` (default ``backend/data/teams.json``) or in the ``TEAMS_JSON``
variable (the same list as a JSON string, for a deployment whose variables are
easier to edit than its files). A row carries what differs per team:

    {"id": "3", "name": "Team 3",
     "viya_url": "https://viya-....engage.sas.com",
     "ram_url": "https://ram-....sas.com/SASRetrievalAgentManager",
     "ram_api_url": "https://ram-....sas.com/SASRetrievalAgentManager/api/v1",
     "ram_realm": "sas-iot", "ram_client_id": "sas-ram-api",
     "ram_auth_flow": "device", "sas_logon_url": ""}

Anything a row leaves empty falls back to the process environment (VIYA_URL,
RAM_URL, RAM_API_URL, ...). A browser picks its team on the home page; the choice
is a cookie, and the environment links and every RAM call follow it. With no
teams configured nothing changes: one environment, from the process environment.
"""
from __future__ import annotations

import json
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any

COOKIE = "hackathon_team"
COOKIE_MAX_AGE = 400 * 24 * 3600

# row key -> environment variable it overrides
FIELDS = {
    "viya_url": "VIYA_URL",
    "ram_url": "RAM_URL",
    "ram_api_url": "RAM_API_URL",
    "ram_realm": "RAM_REALM",
    "ram_client_id": "RAM_CLIENT_ID",
    "ram_auth_flow": "RAM_AUTH_FLOW",
    "sas_logon_url": "SAS_LOGON_URL",
}
_ENV_TO_FIELD = {v: k for k, v in FIELDS.items()}

DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "teams.json"
_current: ContextVar[str | None] = ContextVar("hackathon_team", default=None)
_cache: dict[str, Any] = {"key": None, "teams": []}


def _rows() -> list[dict]:
    raw = os.getenv("TEAMS_JSON", "").strip()
    if raw:
        key = ("env", raw)
        if _cache["key"] != key:
            try:
                _cache["teams"] = _clean(json.loads(raw))
            except ValueError:
                _cache["teams"] = []
            _cache["key"] = key
        return _cache["teams"]
    path = Path(os.getenv("TEAMS_FILE") or DEFAULT_FILE)
    try:
        key = ("file", str(path), path.stat().st_mtime)
    except OSError:
        return []
    if _cache["key"] != key:
        try:
            _cache["teams"] = _clean(json.loads(path.read_text()))
        except (OSError, ValueError):
            _cache["teams"] = []
        _cache["key"] = key
    return _cache["teams"]


def _clean(data: Any) -> list[dict]:
    rows = data.get("teams") if isinstance(data, dict) else data
    out: list[dict] = []
    seen: set[str] = set()
    for i, r in enumerate(rows or [], start=1):
        if not isinstance(r, dict):
            continue
        tid = str(r.get("id") or i).strip()
        if not tid or tid in seen:
            continue
        seen.add(tid)
        row = {"id": tid, "name": str(r.get("name") or f"Team {tid}").strip()}
        for k in FIELDS:
            row[k] = str(r.get(k) or "").strip().rstrip("/")
        out.append(row)
    return out


def teams() -> list[dict]:
    return _rows()


def enabled() -> bool:
    return bool(_rows())


def get(team_id: str | None) -> dict | None:
    if not team_id:
        return None
    return next((t for t in _rows() if t["id"] == str(team_id)), None)


def set_current(team_id: str | None) -> None:
    """Bind the current request to a team (the router reads the cookie)."""
    _current.set(str(team_id) if team_id else None)


def current() -> dict | None:
    return get(_current.get())


def current_id() -> str | None:
    t = current()
    return t["id"] if t else None


def setting(env_name: str, default: str = "") -> str:
    """The team's value for a setting, else the process environment's, else default."""
    t = current()
    field = _ENV_TO_FIELD.get(env_name)
    if t and field and t.get(field):
        return t[field]
    return (os.getenv(env_name) or default).strip()


def public() -> list[dict]:
    """What the browser may see: no endpoints, only whether the team is wired up."""
    return [{"id": t["id"], "name": t["name"],
             "ready": bool(t["viya_url"] or t["ram_url"] or t["ram_api_url"])} for t in _rows()]
