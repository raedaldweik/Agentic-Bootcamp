"""The Sanad Digital Assistant API (mounted under /api/assistant).

A question is submitted and then polled; the poll returns the answer as far as it has
been written, the steps so far and the card. Each browser is its own user: an HttpOnly
cookie names it, and its conversations and notebook are visible to no one else.

Set SANAD_ACCESS_CODE to require a shared code before the assistant can be used, which
keeps a public address from spending the model key.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import os
import secrets

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile
from pydantic import BaseModel, Field

from services.sanad import attachments, corpus, scenario
from services.sanad.engine import ENGINE, MAX_QUESTION_CHARS, Refused

COOKIE = "sanad_sid"
ACCESS_COOKIE = "sanad_access"
COOKIE_MAX_AGE = 60 * 60 * 24 * 30
ACCESS_CODE = os.getenv("SANAD_ACCESS_CODE", "").strip()


def _access_token() -> str:
    return hashlib.sha256(f"sanad-access:{ACCESS_CODE}".encode()).hexdigest()


def _unlocked(request: Request) -> bool:
    return not ACCESS_CODE or hmac.compare_digest(request.cookies.get(ACCESS_COOKIE, ""), _access_token())


def _set_cookie(request: Request, response: Response, name: str, value: str) -> None:
    response.set_cookie(name, value, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https", path="/api/assistant")


async def browser(request: Request, response: Response) -> str:
    """This browser's id, created on first contact."""
    sid = request.cookies.get(COOKIE)
    if not sid or not (16 <= len(sid) <= 64):
        sid = secrets.token_urlsafe(24)
        _set_cookie(request, response, COOKIE, sid)
    return sid


async def member(request: Request, sid: str = Depends(browser)) -> str:
    """A browser that may use the assistant."""
    if not _unlocked(request):
        raise HTTPException(status_code=401, detail="access_code_required")
    return sid


router = APIRouter(prefix="/api/assistant", tags=["assistant"])


class Attachment(BaseModel):
    name: str = Field(max_length=200)
    text: str = Field(max_length=attachments.MAX_CHARS + 100)


class Question(BaseModel):
    content: str = Field(max_length=MAX_QUESTION_CHARS + 2000)
    querySessionId: str | None = Field(default=None, max_length=64)
    persona: str | None = Field(default=None, max_length=32)
    shopTime: str | None = Field(default=None, max_length=32)
    attachments: list[Attachment] | None = Field(default=None, max_length=3)


class Code(BaseModel):
    code: str = Field(max_length=200)


class Saved(BaseModel):
    kind: str = Field(default="note", max_length=20)
    title: str = Field(max_length=300)
    text: str = Field(default="", max_length=8000)
    persona: str | None = Field(default=None, max_length=32)
    shopTime: str | None = Field(default=None, max_length=32)
    queryId: str | None = Field(default=None, max_length=64)


def _guard(fn):
    try:
        return fn()
    except Refused as e:
        raise HTTPException(status_code=e.status, detail=e.message)


@router.get("/health")
async def health(request: Request, sid: str = Depends(browser)):
    return {**ENGINE.health(), "locked": not _unlocked(request)}


@router.post("/unlock")
async def unlock(body: Code, request: Request, response: Response, sid: str = Depends(browser)):
    if ACCESS_CODE and not hmac.compare_digest(body.code.strip().encode(), ACCESS_CODE.encode()):
        await asyncio.sleep(1.0)                         # guessing is slow
        raise HTTPException(status_code=403, detail="That access code is not right.")
    _set_cookie(request, response, ACCESS_COOKIE, _access_token())
    return {"ok": True}


@router.get("/config")
async def config(sid: str = Depends(member)):
    return {**scenario.public(), "agent": scenario.AGENT,
            "collections": [{"id": c["name"], "name": c["name"], "documents": c["documents"]} for c in corpus.collections()],
            "limits": {"questionChars": MAX_QUESTION_CHARS, "attachments": 3}}


@router.get("/sessions")
async def sessions(sid: str = Depends(member)):
    return ENGINE.sessions(sid)


@router.get("/sessions/{session_id}/queries")
async def session_queries(session_id: str, sid: str = Depends(member)):
    return _guard(lambda: ENGINE.session_turns(sid, session_id))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str, sid: str = Depends(member)):
    ENGINE.delete_session(sid, session_id)
    return {"ok": True}


@router.post("/query")
async def query(body: Question, sid: str = Depends(member)):
    return _guard(lambda: ENGINE.submit(sid, body.content, persona_key=body.persona, shop_time=body.shopTime,
                                        session_id=body.querySessionId,
                                        attachments=[a.model_dump() for a in body.attachments or []]))


@router.get("/query/{query_id}")
async def query_status(query_id: str, response: Response, sid: str = Depends(member)):
    response.headers["Cache-Control"] = "no-store"
    return _guard(lambda: ENGINE.status(sid, query_id))


@router.post("/query/{query_id}/cancel")
async def query_cancel(query_id: str, sid: str = Depends(member)):
    return _guard(lambda: ENGINE.cancel(sid, query_id))


@router.get("/query/{query_id}/trace")
async def query_trace(query_id: str, sid: str = Depends(member)):
    return _guard(lambda: ENGINE.trace(sid, query_id))


@router.get("/notebook")
async def notebook(sid: str = Depends(member)):
    return ENGINE.notebook(sid)


@router.post("/notebook")
async def notebook_add(body: Saved, sid: str = Depends(member)):
    return ENGINE.notebook_add(sid, body.kind, body.title, {"text": body.text, "queryId": body.queryId}, body.persona or "", body.shopTime)


@router.delete("/notebook/{record_id}")
async def notebook_remove(record_id: str, sid: str = Depends(member)):
    return {"ok": ENGINE.notebook_remove(sid, record_id)}


@router.post("/reset")
async def reset(sid: str = Depends(member)):
    """Forget this browser's conversations and notebook."""
    ENGINE.reset(sid)
    return {"ok": True}


@router.post("/extract")
async def extract(file: UploadFile = File(...), sid: str = Depends(member)):
    """Text out of an attached document, to send along with a question."""
    data = await file.read(attachments.MAX_BYTES + 1)
    try:
        return attachments.extract(file.filename or "attachment", data)
    except attachments.Unreadable as e:
        raise HTTPException(status_code=e.status, detail=e.message)
