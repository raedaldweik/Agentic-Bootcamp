"""Pick a team: which SAS Viya and SAS RAM pair this browser talks to."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from services import teams

router = APIRouter(prefix="/api/teams", tags=["teams"])


def bind_team(request: Request) -> None:
    """Read the team cookie into the request context. Used as a dependency by
    every router whose answers depend on the team (links, RAM)."""
    teams.set_current(request.cookies.get(teams.COOKIE))


class Choice(BaseModel):
    id: str


@router.get("")
def list_teams(request: Request):
    bind_team(request)
    cur = teams.current()
    return {"enabled": teams.enabled(), "teams": teams.public(),
            "current": {"id": cur["id"], "name": cur["name"]} if cur else None}


@router.post("/select")
def select_team(choice: Choice, request: Request, response: Response):
    t = teams.get(choice.id)
    if not t:
        raise HTTPException(status_code=404, detail=f"No team {choice.id!r}.")
    response.set_cookie(teams.COOKIE, t["id"], max_age=teams.COOKIE_MAX_AGE, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https", path="/")
    return {"ok": True, "current": {"id": t["id"], "name": t["name"]}}


@router.delete("/select")
def clear_team(response: Response):
    response.delete_cookie(teams.COOKIE, path="/")
    return {"ok": True, "current": None}
