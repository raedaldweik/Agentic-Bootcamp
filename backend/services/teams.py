"""Teams and environments: which SAS Viya and SAS RAM a browser talks to.

The hackathon has a handful of SAS environments (one Viya + one RAM each) and ten
teams. Teams are spread over the environments in order: team 1 on environment 1,
team 2 on 2, and when the environments run out it wraps, so with four
environments team 5 is back on 1 and two teams share it.

Everything is plain variables on the server, one per value:

    ENV1_VIYA_URL=https://viya-....engage.sas.com
    ENV1_RAM_URL=https://viya-....engage.sas.com/SASRetrievalAgentManager
    ENV2_VIYA_URL=...        ENV2_RAM_URL=...        (and so on, as many as exist)
    TEAM_PASSWORD=...        the one password every team signs in with
    TEAM_COUNT=10            how many teams (default 10)

Optional per environment: ENVn_RAM_API_URL (derived from the RAM address when
absent), ENVn_RAM_REALM and ENVn_RAM_CLIENT_ID (fall back to RAM_REALM and
RAM_CLIENT_ID). Optional per team: TEAMn_PASSWORD, TEAMn_ENV (pin a team to an
environment), TEAMn_NAME.

Teams sign in on the app as team1, team2, ... with TEAM_PASSWORD; the sign-in is
a cookie and the app shows nothing until it is there. The Viya and RAM sign-in
details are not shown anywhere in the app; they go on a slide. With no ENVn_
variables at all nothing changes: one environment from VIYA_URL / RAM_URL /
RAM_API_URL and no team sign-in.
"""
from __future__ import annotations

import hmac
import os
from contextvars import ContextVar

COOKIE = "hackathon_team"
COOKIE_MAX_AGE = 400 * 24 * 3600
RAM_API_SUFFIX = "/SASRetrievalAgentManager/api/v1"
MAX_ENVIRONMENTS = 50

# environment-row key -> process variable it stands in for
FIELDS = {"viya_url": "VIYA_URL", "ram_url": "RAM_URL", "ram_api_url": "RAM_API_URL",
          "ram_realm": "RAM_REALM", "ram_client_id": "RAM_CLIENT_ID"}
_ENV_TO_FIELD = {v: k for k, v in FIELDS.items()}

_current: ContextVar[str | None] = ContextVar("hackathon_team", default=None)


def _env(name: str) -> str:
    return (os.getenv(name) or "").strip()


def environments() -> list[dict]:
    """ENV1_, ENV2_, ... in order; the list ends at the first number with neither URL."""
    out: list[dict] = []
    for n in range(1, MAX_ENVIRONMENTS + 1):
        row = {"id": str(n)}
        for k, var in FIELDS.items():
            row[k] = _env(f"ENV{n}_{var}").rstrip("/")
        if not (row["viya_url"] or row["ram_url"]):
            break
        if row["ram_url"] and not row["ram_api_url"]:
            row["ram_api_url"] = row["ram_url"].split("/SASRetrievalAgentManager")[0] + RAM_API_SUFFIX
        out.append(row)
    return out


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
                    "password": _env(f"TEAM{n}_PASSWORD") or _env("TEAM_PASSWORD") or f"team{n}", "env": env})
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


def shared_with(t: dict) -> list[str]:
    return [o["name"] for o in teams() if o["id"] != t["id"] and o["env"]["id"] == t["env"]["id"]]


def public(t: dict | None) -> dict | None:
    """What the browser may see of a team: no endpoints, no password."""
    if not t:
        return None
    return {"id": t["id"], "name": t["name"], "username": t["username"],
            "environment": t["env"]["id"], "shared_with": shared_with(t),
            "ready": bool(t["env"]["viya_url"] or t["env"]["ram_url"])}
