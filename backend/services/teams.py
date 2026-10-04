"""Teams and environments: which SAS Viya and SAS RAM a browser talks to.

The hackathon has a handful of SAS environments (one Viya + one RAM each) and ten
teams. Teams are spread over the environments in order: team 1 on environment 1,
team 2 on 2, and when the environments run out it wraps, so with four
environments team 5 is back on 1 and two teams share it.

Environments live in ``backend/data/environments.json`` (URLs only, nothing
secret), or in ``ENVIRONMENTS_JSON`` as the same list in one string. Each row:

    {"id": "3", "viya_url": "https://viya-....engage.sas.com",
     "ram_url": "https://viya-....engage.sas.com",
     "ram_api_url": "", "ram_realm": "", "ram_client_id": ""}     (the last three optional)

The RAM API address is derived from the RAM address when not given. Realm and
client fall back to RAM_REALM and RAM_CLIENT_ID. The sign-in names and passwords
shown next to the environment buttons come from VIYA_USER, VIYA_PASSWORD,
RAM_USER and RAM_PASSWORD on the server.

Teams: TEAM_COUNT of them (default 10 when environments exist), signing in on the
app as team1 / team1, team2 / team2, ... (TEAMn_PASSWORD changes one; TEAMn_ENV
pins a team to an environment). The sign-in is a cookie; the app shows nothing
else until it is there. With no environments configured nothing changes: one
environment from VIYA_URL / RAM_URL / RAM_API_URL and no team sign-in.
"""
from __future__ import annotations

import hmac
import json
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any

COOKIE = "hackathon_team"
COOKIE_MAX_AGE = 400 * 24 * 3600
DEFAULT_FILE = Path(__file__).resolve().parent.parent / "data" / "environments.json"
RAM_API_SUFFIX = "/SASRetrievalAgentManager/api/v1"

# environment-row key -> process variable it stands in for
FIELDS = {"viya_url": "VIYA_URL", "ram_url": "RAM_URL", "ram_api_url": "RAM_API_URL",
          "ram_realm": "RAM_REALM", "ram_client_id": "RAM_CLIENT_ID"}
_ENV_TO_FIELD = {v: k for k, v in FIELDS.items()}

_current: ContextVar[str | None] = ContextVar("hackathon_team", default=None)
_cache: dict[str, Any] = {"key": None, "envs": []}


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def _clean_envs(data: Any) -> list[dict]:
    rows = data.get("environments") if isinstance(data, dict) else data
    out: list[dict] = []
    for i, r in enumerate(rows or [], start=1):
        if not isinstance(r, dict):
            continue
        row = {"id": str(r.get("id") or i).strip()}
        for k in FIELDS:
            row[k] = str(r.get(k) or "").strip().rstrip("/")
        if row["ram_url"] and not row["ram_api_url"]:
            base = row["ram_url"].split("/SASRetrievalAgentManager")[0]
            row["ram_api_url"] = base + RAM_API_SUFFIX
        if row["viya_url"] or row["ram_url"]:
            out.append(row)
    return out


def environments() -> list[dict]:
    raw = _env("ENVIRONMENTS_JSON")
    if raw:
        key = ("json", raw)
        if _cache["key"] != key:
            try:
                _cache["envs"] = _clean_envs(json.loads(raw))
            except ValueError:
                _cache["envs"] = []
            _cache["key"] = key
        return _cache["envs"]
    path = Path(_env("ENVIRONMENTS_FILE") or DEFAULT_FILE)
    try:
        key = ("file", str(path), path.stat().st_mtime)
    except OSError:
        return []
    if _cache["key"] != key:
        try:
            _cache["envs"] = _clean_envs(json.loads(path.read_text()))
        except (OSError, ValueError):
            _cache["envs"] = []
        _cache["key"] = key
    return _cache["envs"]


def teams() -> list[dict]:
    envs = environments()
    if not envs:
        return []
    count = int(_env("TEAM_COUNT") or 10)
    out = []
    for n in range(1, count + 1):
        pinned = _env(f"TEAM{n}_ENV")
        env = next((e for e in envs if e["id"] == pinned), None) if pinned else None
        env = env or envs[(n - 1) % len(envs)]
        out.append({"id": str(n), "name": _env(f"TEAM{n}_NAME") or f"Team {n}", "username": f"team{n}",
                    "password": _env(f"TEAM{n}_PASSWORD") or f"team{n}", "env": env})
    return out


def enabled() -> bool:
    return bool(teams())


def get(team_id: str | None) -> dict | None:
    if not team_id:
        return None
    return next((t for t in teams() if t["id"] == str(team_id)), None)


def authenticate(username: str, password: str) -> dict | None:
    """The team for a username/password pair, or None. Same-length comparison for
    both fields so a wrong guess takes as long as a right one."""
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
    """A connection setting for the current request: the team's environment first,
    then the process environment, then the default."""
    t = current()
    field = _ENV_TO_FIELD.get(env_name)
    if t and field and t["env"].get(field):
        return t["env"][field]
    return _env(env_name) or default


def credentials() -> dict:
    """What a participant types into Viya and RAM; shown on the home page, never stored here."""
    return {"viya": {"username": _env("VIYA_USER"), "password": _env("VIYA_PASSWORD")},
            "ram": {"username": _env("RAM_USER"), "password": _env("RAM_PASSWORD")}}


def shared_with(t: dict) -> list[str]:
    return [o["name"] for o in teams() if o["id"] != t["id"] and o["env"]["id"] == t["env"]["id"]]


def public(t: dict | None) -> dict | None:
    """What the browser may see of a team: no endpoints, no password."""
    if not t:
        return None
    return {"id": t["id"], "name": t["name"], "username": t["username"],
            "environment": t["env"]["id"], "shared_with": shared_with(t),
            "ready": bool(t["env"]["viya_url"] or t["env"]["ram_url"])}
