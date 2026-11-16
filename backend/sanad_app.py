"""Sanad MRO Intelligence Hub: the standalone service.

    uvicorn sanad_app:app --host 0.0.0.0 --port 8000

Serves the Sanad Digital Assistant API under /api/assistant and the built chat
(sanad-chat/dist). It needs none of the hackathon app's models or data, so it starts in
about a second. See sanad-chat/README.md for the environment variables.

To run the same chat against SAS Retrieval Agent Manager instead of the built-in
assistant, set SANAD_AGENT=false and the RAM_* variables: the RAM proxy is mounted under
/api/ram and the chat uses it.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("sanad")

BUILT_IN = os.getenv("SANAD_AGENT", "true").lower() != "false"
USE_RAM = not BUILT_IN or bool(os.getenv("RAM_API_URL")) or os.getenv("RAM_MOCK", "").lower() == "true"
FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST") or (Path(__file__).resolve().parent.parent / "sanad-chat" / "dist"))


@asynccontextmanager
async def lifespan(app: FastAPI):
    t0 = time.time()
    tasks: list[asyncio.Task] = []
    if BUILT_IN:
        from services.sanad import agent, corpus, ops
        from services.sanad.engine import ENGINE
        shop = ops.shop()
        log.info("shop data loaded: %d engines, %d tables, %d documents (%.2fs)", len(shop.engine_ids()), len(shop.sql_tables()),
                 sum(len(c["documents"]) for c in corpus.collections()), time.time() - t0)
        agent.system_prompt()
        if agent.enabled():
            async def check() -> None:
                res = await ENGINE.check_model()
                if res.get("ok"):
                    log.info("model ready: %s answered in %s ms (effort %s%s)", res["model"], res["ms"], agent.EFFORT,
                             ", fast mode" if agent.FAST_MODE else "")
                else:
                    log.warning("model check FAILED (%s). Questions are answered from the shop data until it works.", res.get("error"))
            tasks.append(asyncio.create_task(check()))
        else:
            log.warning("ANTHROPIC_API_KEY is not set: standard questions are answered from the shop data; free-form questions need the key.")
    if USE_RAM:
        from services import ram_client
        tasks.append(asyncio.create_task(ram_client.keepalive_loop()))
    log.info("ready in %.2fs on port %s (%s)", time.time() - t0, os.getenv("PORT", "8000"), "built-in assistant" if BUILT_IN else "SAS RAM")
    try:
        yield
    finally:
        for t in tasks:
            t.cancel()


app = FastAPI(title="Sanad MRO Intelligence Hub", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1200)

if BUILT_IN:
    from routers import sanad as sanad_router
    app.include_router(sanad_router.router)
if USE_RAM:
    from routers import ram as ram_router
    app.include_router(ram_router.router)


@app.get("/api/health")
def health():
    out = {"status": "ok", "app": "sanad", "assistant": "built-in" if BUILT_IN else "ram",
           "build": os.getenv("RAILWAY_GIT_COMMIT_SHA", "")[:7] or "local"}
    if BUILT_IN:
        from services.sanad import agent
        out["llm"] = agent.enabled()
    return out


@app.middleware("http")
async def headers(request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    return response


@app.api_route("/api/{rest:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def no_such_api(rest: str):
    return JSONResponse({"detail": "Not found"}, status_code=404)


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")
    _REVALIDATE = {"Cache-Control": "no-cache"}

    @app.get("/{path:path}")
    def spa(path: str):
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate, headers=_REVALIDATE)
        return FileResponse(FRONTEND_DIST / "index.html", headers=_REVALIDATE)
