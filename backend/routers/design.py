"""The Design Thinking Agent tab: the scripted Population Health Builder (services/design_studio.py).

  POST /api/design/chat      {session_id, message}  → NDJSON events
  GET  /api/design/state     ?session_id=           → stage, artefacts, facts
  POST /api/design/reset     {session_id}           → a fresh session
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services import design_studio, teams

router = APIRouter(prefix="/api/design", tags=["design"])


class ChatRequest(BaseModel):
    session_id: str = Field(default="default", max_length=80)
    message: str = Field(min_length=1, max_length=4000)


class SessionRef(BaseModel):
    session_id: str = Field(default="default", max_length=80)


def _bind(request: Request):
    # the team's Viya URL is what the "where to look" links point at
    teams.set_current(request.cookies.get(teams.COOKIE))


@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    _bind(request)

    async def stream():
        async for ev in design_studio.turn(req.session_id, req.message):
            yield json.dumps(ev, default=str) + "\n"
    return StreamingResponse(stream(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/state")
def state(session_id: str = "default"):
    return design_studio.session(session_id).public()


@router.post("/reset")
def reset(ref: SessionRef):
    return design_studio.reset(ref.session_id)
