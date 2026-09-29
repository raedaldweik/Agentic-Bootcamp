"""Teams: one SAS Viya and SAS RAM environment per team, signed in with a team account.

The hackathon can run each team on its own pair of environments. Teams are
configured with environment variables, so a deployment's Variables tab is the
whole configuration:

    TEAM_COUNT=10                       how many teams exist (team1 .. team10)
    TEAM3_VIYA_URL=https://viya-...     what differs for team 3; any of
    TEAM3_RAM_URL=https://.../SASRetrievalAgentManager
    TEAM3_RAM_API_URL=https://.../SASRetrievalAgentManager/api/v1
    TEAM3_RAM_REALM=sas-iot             TEAM3_RAM_CLIENT_ID=sas-ram-api
    TEAM3_RAM_AUTH_FLOW=device          TEAM3_SAS_LOGON_URL=...
    TEAM3_PASSWORD=...                  default: the username, "team3"

A team signs in on the app with username ``team3`` and its password; the sign-in
is a cookie, and from then on the environment links and every RAM call resolve
their settings through the team first. A setting a team has no variable for
falls back to the plain one (VIYA_URL, RAM_URL, RAM_API_URL, ...), so the
variables can be added team by team as environments come up. With TEAM_COUNT
unset (or 0) and no TEAMn_ variable at all, nothing changes: one environment
for everyone, no team sign-in.

``TEAMS_JSON`` (a JSON list of rows with the same fields in lower case, plus
``id``, ``name`` and ``password``) is an alternative for bulk configuration; when
set it replaces the TEAMn_ variables.
"""
from __future__ import annotations

import hmac
import json
import os
import re
from contextvars import ContextVar
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
_TEAM_VAR = re.compile(r"^TEAM(\d+)_([A-Z_]+)$")

_current: ContextVar[str | None] = ContextVar("hackathon_team", default=None)
_cache: dict[str, Any] = {"key": None, "teams": []}


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _from_variables() -> list[dict]:
    """TEAM_COUNT teams, or as many as the highest TEAMn_ variable present."""
    numbers = {int(m.group(1)) for k in os.environ for m in [_TEAM_VAR.match(k)] if m}
    count = int(_env("TEAM_COUNT") or 0) or (max(numbers) if numbers else 0)
    rows = []
    for n in range(1, count + 1):
        row = {"id": str(n), "name": _env(f"TEAM{n}_NAME") or f"Team {n}",
               "username": f"team{n}", "password": _env(f"TEAM{n}_PASSWORD") or f"team{n}"}
        for field, var in FIELDS.items():
            row[field] = _env(f"TEAM{n}_{var}").rstrip("/")
        rows.append(row)
    return rows


def _from_json(raw: str) -> list[dict]:
    try:
        data = json.loads(raw)
    except ValueError:
        return []
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
        row = {"id": tid, "name": str(r.get("name") or f"Team {tid}").strip(),
               "username": str(r.get("username") or f"team{tid}").strip().lower()}
        row["password"] = str(r.get("password") or row["username"])
        for k in FIELDS:
            row[k] = str(r.get(k) or "").strip().rstrip("/")
        out.append(row)
    return out


def teams() -> list[dict]:
    raw = _env("TEAMS_JSON")
    key = ("json", raw) if raw else ("vars", tuple(sorted((k, v) for k, v in os.environ.items()
                                                          if k == "TEAM_COUNT" or _TEAM_VAR.match(k))))
    if _cache["key"] != key:
        _cache["teams"] = _from_json(raw) if raw else _from_variables()
        _cache["key"] = key
    return _cache["teams"]


def enabled() -> bool:
    return bool(teams())


def get(team_id: str | None) -> dict | None:
    if not team_id:
        return None
    return next((t for t in teams() if t["id"] == str(team_id)), None)


def authenticate(username: str, password: str) -> dict | None:
    """The team for a username/password pair, or None. Same-length comparison
    for both fields so a wrong guess takes as long as a right one."""
    u = (username or "").strip().lower()
    match = None
    for t in teams():
        ok_user = hmac.compare_digest(t["username"].encode(), u.encode())
        ok_pass = hmac.compare_digest(t["password"].encode(), (password or "").encode())
        if ok_user and ok_pass:
            match = t
    return match


def set_current(team_id: str | None) -> None:
    """Bind the current request to a team (the routers read the cookie)."""
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
    return _env(env_name) or default


def public(t: dict | None) -> dict | None:
    """What the browser may see of a team: no endpoints, no password."""
    if not t:
        return None
    return {"id": t["id"], "name": t["name"], "username": t["username"],
            "ready": bool(t["viya_url"] or t["ram_url"] or t["ram_api_url"])}
