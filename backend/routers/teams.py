"""Team sign-in: which SAS Viya and SAS RAM pair this browser talks to."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from services import teams

router = APIRouter(prefix="/api/teams", tags=["teams"])


def bind_team(request: Request) -> None:
    """Read the team cookie into the request context. Every router whose answers
    depend on the team (links, RAM) does this first."""
    teams.set_current(request.cookies.get(teams.COOKIE))


class Login(BaseModel):
    username: str
    password: str


@router.get("")
def state(request: Request):
    bind_team(request)
    return {"enabled": teams.enabled(), "count": len(teams.teams()),
            "current": teams.public(teams.current())}


@router.post("/login")
def login(body: Login, request: Request, response: Response):
    t = teams.authenticate(body.username, body.password)
    if not t:
        raise HTTPException(status_code=401, detail="Wrong team name or password.")
    response.set_cookie(teams.COOKIE, t["id"], max_age=teams.COOKIE_MAX_AGE, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https", path="/")
    return {"ok": True, "current": teams.public(t)}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(teams.COOKIE, path="/")
    return {"ok": True, "current": None}
