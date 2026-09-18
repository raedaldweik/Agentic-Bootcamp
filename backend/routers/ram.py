"""SAS Retrieval Agent Manager proxy routes (mounted under /api/ram).

Thin layer over services.ram_client — the browser never talks to RAM directly.
"""
from __future__ import annotations

import io
import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile, File
from pydantic import BaseModel

from services import ram_client as ram

# Each browser carries its own RAM identity: an HttpOnly cookie names the
# session the client keeps that browser's tokens under. Set on the first call
# (the health check), read on every call after.
SESSION_COOKIE = "ram_sid"
SESSION_MAX_AGE = 60 * 60 * 24 * 30


async def _bind_session(request: Request, response: Response) -> None:
    sid = request.cookies.get(SESSION_COOKIE)
    if not sid or len(sid) < 16:
        sid = secrets.token_urlsafe(24)
        response.set_cookie(SESSION_COOKIE, sid, max_age=SESSION_MAX_AGE, httponly=True, samesite="lax",
                            secure=request.url.scheme == "https", path="/api/ram")
    ram.set_session_id(sid)


router = APIRouter(prefix="/api/ram", tags=["ram"], dependencies=[Depends(_bind_session)])

# Attached documents are inlined into the query text — keep them inside a
# sane prompt budget for the agent's LLM.
MAX_ATTACH_CHARS = 20_000


class Attachment(BaseModel):
    name: str
    text: str


class QueryRequest(BaseModel):
    content: str
    agentId: str | None = None
    collectionIds: list[str] | None = None
    querySessionId: str | None = None
    attachments: list[Attachment] | None = None
    # UI language ("en" / "ar"). Accepted for compatibility with the SAS RAM
    # frontend; RAM agents decide the answer language themselves, so it is ignored.
    language: str | None = "en"


class AuthCode(BaseModel):
    code: str


class SavedSession(BaseModel):
    session: dict


def _wrap(coro):
    async def run():
        try:
            return await coro
        except ram.RamError as e:
            raise HTTPException(status_code=e.status if 400 <= e.status < 600 else 502, detail=e.message)
        except Exception as e:  # network errors, DNS, TLS …
            raise HTTPException(status_code=502, detail=f"Could not reach SAS RAM: {e}")
    return run()


@router.get("/health")
async def health():
    return await ram.status_async()


# ─── Interactive sign-in ─────────────────────────────────────────────
@router.post("/auth/device/start")
async def auth_device_start():
    return await _wrap(ram.device_start())


@router.post("/auth/device/poll")
async def auth_device_poll():
    res = await _wrap(ram.device_poll())
    if res.get("ok"):
        res["session"] = ram.export_session()
    return res


@router.post("/auth/viya/code")
async def auth_viya_code(body: AuthCode):
    if not body.code.strip():
        raise HTTPException(status_code=400, detail="Paste the authorization code first.")
    res = await _wrap(ram.viya_code_exchange(body.code))
    if res.get("ok"):
        res["session"] = ram.export_session()
    return res


@router.post("/auth/signout")
async def auth_signout(response: Response):
    """Sign this browser out of RAM: revoke and forget its session, and drop
    the session cookie so the next visit starts a fresh identity."""
    res = await _wrap(ram.sign_out())
    response.delete_cookie(SESSION_COOKIE, path="/api/ram")
    return res


@router.post("/auth/restore")
async def auth_restore(body: SavedSession):
    """Hand back the session this browser saved after signing in, so a
    backend that restarted on a fresh container picks it up without a new
    sign-in. Validated with the identity provider before it is accepted."""
    return await _wrap(ram.restore_session(body.session))


# ─── Attachments (ad-hoc documents, inlined into the query) ─────────
@router.post("/extract")
async def extract(file: UploadFile = File(...)):
    """Extract plain text from an uploaded document so it can be sent
    inline with a question. RAM's query API is text-only, so this is how
    ad-hoc files reach the agent without indexing them into a collection."""
    data = await file.read()
    name = file.filename or "attachment"
    ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""

    if ext == "pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(data))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not read PDF: {e}")
        if not text.strip():
            raise HTTPException(status_code=422, detail=(
                "This PDF contains no extractable text (it looks scanned). "
                "OCR isn't available, so the assistant can't read it."))
    elif ext == "docx":
        try:
            from docx import Document
        except ImportError:
            raise HTTPException(status_code=415, detail="DOCX support requires python-docx (pip install python-docx).")
        try:
            doc = Document(io.BytesIO(data))
            text = "\n".join(p.text for p in doc.paragraphs)
        except Exception as e:
            raise HTTPException(status_code=422, detail=f"Could not read DOCX: {e}")
    elif ext in ("txt", "md", "csv", "json", "log", "xml", "html", "yaml", "yml", "sas", "sql", "py"):
        text = data.decode("utf-8", errors="replace")
    elif ext in ("png", "jpg", "jpeg", "gif", "bmp", "webp", "tif", "tiff"):
        raise HTTPException(status_code=415, detail=(
            "Images can't be read — RAM's query API is text-only and there is no "
            "OCR/vision step. Export the content as a PDF or text file instead."))
    else:
        raise HTTPException(status_code=415, detail=f"Unsupported file type: .{ext or '?'}")

    truncated = len(text) > MAX_ATTACH_CHARS
    return {"name": name, "text": text[:MAX_ATTACH_CHARS], "chars": len(text), "truncated": truncated}


# ─── RAM proxy ───────────────────────────────────────────────────────
@router.get("/agents")
async def agents():
    return await _wrap(ram.list_agents())


@router.get("/collections")
async def collections():
    return await _wrap(ram.list_collections())


@router.get("/sessions")
async def sessions():
    return await _wrap(ram.list_sessions())


@router.get("/sessions/{session_id}/queries")
async def session_queries(session_id: str):
    return await _wrap(ram.list_session_queries(session_id))


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: str):
    """Delete a query session in RAM itself — the conversation is removed
    from RAM's history, not just hidden in this browser."""
    return await _wrap(ram.delete_session(session_id))


@router.post("/query")
async def query(body: QueryRequest):
    """Submit a query asynchronously. Returns {queryId, querySessionId,
    pollInterval, timeout} — poll GET /api/ram/query/{queryId} for the result
    (a `result` key is included directly when RAM answered inline)."""
    if not body.content.strip():
        raise HTTPException(status_code=400, detail="Empty query.")
    content = body.content
    if body.attachments:
        for a in body.attachments:
            content += f"\n\n--- Attached document: {a.name} ---\n{a.text[:MAX_ATTACH_CHARS]}\n--- End of attached document ---"
        content += "\n\nUse the attached document content above to answer the question where relevant."
    return await _wrap(ram.submit_query(
        content,
        agent_id=body.agentId,
        collection_ids=body.collectionIds,
        session_id=body.querySessionId,
    ))


@router.get("/query/{query_id}")
async def query_status(query_id: str):
    return await _wrap(ram.query_status(query_id))


@router.get("/query/{query_id}/trace")
async def query_trace(query_id: str):
    return await _wrap(ram.query_trace(query_id))
