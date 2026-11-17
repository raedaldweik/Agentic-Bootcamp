"""Conversations, questions in flight, and each browser's own records.

A question is submitted, answered in the background, and polled: the poll returns the
answer as far as it has been written, the steps taken so far and the card, so the
screen fills in as the work happens. Nothing here blocks a request on the model.

Built to be leaned on:
  - every browser has its own conversations and notebook; nothing is shared
  - a per-browser and a global rate limit, and a cap on questions in flight
  - a cap on concurrent model calls, so a burst queues briefly instead of failing
  - when the model cannot answer (no key, an outage, a refusal) the question is
    answered directly from the shop data and says so
  - after repeated model failures the model is skipped for a short while, so nobody
    waits on a timeout during an outage
  - state is saved to disk and survives a restart (on a host with a persistent disk)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from collections import OrderedDict, deque
from pathlib import Path
from typing import Any

from . import agent, direct, ops, router, scenario, tools
from .records import Notebook

log = logging.getLogger("sanad.engine")

STATE_FILE = Path(os.getenv("SANAD_STATE_FILE") or Path(__file__).resolve().parents[2] / "data" / "runtime" / "sanad_state.json")
PERSIST = os.getenv("SANAD_PERSIST", "true").lower() != "false"
MAX_OWNERS = 2000
MAX_SESSIONS = 30                 # per browser
MAX_TURNS = 60                    # per conversation
MAX_QUESTION_CHARS = 4000
RATE_PER_MIN = int(os.getenv("SANAD_RATE_PER_MIN", "30"))                 # per browser
GLOBAL_RATE_PER_MIN = int(os.getenv("SANAD_GLOBAL_RATE_PER_MIN", "240"))   # everyone together; bounds what a public address can spend
MAX_IN_FLIGHT = 3                 # per browser
MODEL_SLOTS = int(os.getenv("SANAD_MAX_CONCURRENCY", "24"))
SLOT_WAIT_S = 12.0
POLL_INTERVAL_S = 0.3
SAVE_DELAY_S = 4.0
FAST_PATH = os.getenv("SANAD_FAST_PATH", "").lower() in ("1", "true", "yes")
BREAKER_FAILURES = 3
BREAKER_OPEN_S = 30.0
CLOCK_MIN, CLOCK_MAX = "2026-10-20 00:00", "2026-11-20 00:00"


class Refused(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status
        self.message = message


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class Owner:
    """One browser."""

    def __init__(self) -> None:
        self.sessions: OrderedDict[str, dict] = OrderedDict()
        self.records: list[dict] = []
        self.stamps: deque[float] = deque()
        self.in_flight = 0
        self.seen = time.time()


class Engine:
    def __init__(self) -> None:
        self.owners: OrderedDict[str, Owner] = OrderedDict()
        self.turns: dict[str, dict] = {}              # turn id -> live turn
        self.tasks: dict[str, asyncio.Task] = {}
        self.global_stamps: deque[float] = deque()
        self._slots: asyncio.Semaphore | None = None
        self._failures = 0
        self._breaker_until = 0.0
        self._save_task: asyncio.Task | None = None
        self.model_check: dict[str, Any] = {"ok": None}
        self.stats = {"questions": 0, "model_answers": 0, "direct_answers": 0, "errors": 0, "started": _now_iso()}
        self._loaded = False

    # -- owners -------------------------------------------------------------
    def owner(self, owner_id: str) -> Owner:
        self._load()
        o = self.owners.get(owner_id)
        if o is None:
            o = self.owners[owner_id] = Owner()
            while len(self.owners) > MAX_OWNERS:
                old_id, old = self.owners.popitem(last=False)
                for s in old.sessions.values():
                    for t in s["turns"]:
                        self.turns.pop(t["queryId"], None)
        else:
            self.owners.move_to_end(owner_id)
        o.seen = time.time()
        return o

    # -- read ---------------------------------------------------------------
    def sessions(self, owner_id: str) -> list[dict]:
        o = self.owner(owner_id)
        out = [{"id": s["id"], "title": s["title"], "insertTimestamp": s["created"], "updateTimestamp": s["updated"],
                "turns": len(s["turns"]), "persona": s.get("persona")} for s in o.sessions.values() if s["turns"]]
        return sorted(out, key=lambda s: s["updateTimestamp"], reverse=True)

    def session_turns(self, owner_id: str, session_id: str) -> list[dict]:
        s = self.owner(owner_id).sessions.get(session_id)
        if not s:
            raise Refused(404, "That conversation no longer exists.")
        return [self._public(t) for t in s["turns"] if t["state"] != "running"]

    def delete_session(self, owner_id: str, session_id: str) -> None:
        s = self.owner(owner_id).sessions.pop(session_id, None)
        if s:
            for t in s["turns"]:
                self.cancel(owner_id, t["queryId"], quiet=True)
                self.turns.pop(t["queryId"], None)
            self._save_soon()

    def notebook(self, owner_id: str) -> list[dict]:
        return list(reversed(self.owner(owner_id).records))

    def notebook_add(self, owner_id: str, kind: str, title: str, detail: dict, persona_key: str, shop_time: str | None) -> dict:
        o = self.owner(owner_id)
        p = scenario.persona(persona_key)
        rec = Notebook(o.records).add("answer" if kind == "answer" else "note", title[:160], detail, by=f"{p['title']} {p['id']}",
                                      shop_time=ops.stamp(self._clock(shop_time)), status="Saved")
        self._save_soon()
        return rec

    def notebook_remove(self, owner_id: str, record_id: str) -> bool:
        ok = Notebook(self.owner(owner_id).records).remove(record_id)
        self._save_soon()
        return ok

    def reset(self, owner_id: str) -> None:
        o = self.owner(owner_id)
        for sid in list(o.sessions):
            self.delete_session(owner_id, sid)
        o.records.clear()
        self._save_soon()

    # -- submit -------------------------------------------------------------
    def submit(self, owner_id: str, content: str, *, persona_key: str | None, shop_time: str | None,
               session_id: str | None, attachments: list[dict] | None) -> dict:
        content = (content or "").strip()
        if not content:
            raise Refused(400, "Type or say a question first.")
        if len(content) > MAX_QUESTION_CHARS:
            raise Refused(413, f"That question is too long. Keep it under {MAX_QUESTION_CHARS:,} characters.")
        o = self.owner(owner_id)
        now = time.time()
        for stamps, limit, msg in ((o.stamps, RATE_PER_MIN, "You are sending questions faster than the assistant can answer. Give it a few seconds."),
                                   (self.global_stamps, GLOBAL_RATE_PER_MIN, "The assistant is very busy right now. Try again in a few seconds.")):
            while stamps and now - stamps[0] > 60:
                stamps.popleft()
            if len(stamps) >= limit:
                raise Refused(429, msg)
        if o.in_flight >= MAX_IN_FLIGHT:
            raise Refused(429, "Earlier questions are still being answered. Wait for one to finish, or stop it.")
        o.stamps.append(now)
        self.global_stamps.append(now)

        persona = scenario.persona(persona_key)
        clock = self._clock(shop_time)
        session = o.sessions.get(session_id) if session_id else None
        if session is None:
            session = {"id": str(uuid.uuid4()), "title": _title(content), "created": _now_iso(), "updated": _now_iso(),
                       "persona": persona["key"], "turns": []}
            o.sessions[session["id"]] = session
            while len(o.sessions) > MAX_SESSIONS:
                _, old = o.sessions.popitem(last=False)
                for t in old["turns"]:
                    self.cancel(owner_id, t["queryId"], quiet=True)
                    self.turns.pop(t["queryId"], None)
        o.sessions.move_to_end(session["id"])
        session["updated"] = _now_iso()
        turn = {"queryId": str(uuid.uuid4()), "querySessionId": session["id"], "owner": owner_id, "content": content,
                "persona": persona["key"], "personaTitle": persona["title"], "personaId": persona["id"],
                "shopTime": ops.stamp(clock), "shopTimeNice": ops.nice(clock), "state": "running", "text": "", "answer": None,
                "steps": [], "cards": [], "preview": [], "followups": [], "sources": [], "records": [], "usage": {}, "timing": {},
                "mode": None, "model": None, "notice": None, "errorText": None, "createdAt": _now_iso(), "_t0": time.perf_counter(),
                "attachments": [str(a.get("name", "attachment"))[:120] for a in attachments or []], "trace": {}}
        session["turns"].append(turn)
        for old_turn in session["turns"][:-MAX_TURNS]:
            self.turns.pop(old_turn["queryId"], None)
        del session["turns"][:-MAX_TURNS]
        self.turns[turn["queryId"]] = turn
        o.in_flight += 1
        self.stats["questions"] += 1
        task = asyncio.get_running_loop().create_task(self._run(o, session, turn, attachments or []))
        self.tasks[turn["queryId"]] = task
        task.add_done_callback(lambda _t, qid=turn["queryId"]: self.tasks.pop(qid, None))
        return {"queryId": turn["queryId"], "querySessionId": session["id"], "pollInterval": POLL_INTERVAL_S, "timeout": agent.TURN_BUDGET_S + 30}

    def status(self, owner_id: str, query_id: str) -> dict:
        t = self._turn(owner_id, query_id)
        if t["state"] == "running":
            return {"done": False, "text": t["text"], "steps": t["steps"], "cards": t["preview"],
                    "elapsedMs": round((time.perf_counter() - t["_t0"]) * 1000)}
        return {"done": True, "result": self._public(t)}

    def trace(self, owner_id: str, query_id: str) -> dict:
        t = self._turn(owner_id, query_id)
        return {"steps": t["steps"], **(t.get("trace") or {})}

    def cancel(self, owner_id: str, query_id: str, quiet: bool = False) -> dict:
        try:
            t = self._turn(owner_id, query_id)
        except Refused:
            if quiet:
                return {"ok": False}
            raise
        task = self.tasks.get(query_id)
        if t["state"] == "running" and task and not task.done():
            task.cancel()
        return {"ok": True}

    # -- the work -----------------------------------------------------------
    async def _run(self, o: Owner, session: dict, turn: dict, attachments: list[dict]) -> None:
        ctx = tools.Context(ops.shop(turn["shopTime"]), scenario.persona(turn["persona"]), Notebook(o.records))
        earlier = [t for t in session["turns"] if t is not turn and t["state"] == "done" and t.get("answer")]
        question = turn["content"]
        first_text: list[float] = []

        def emit(kind: str, payload: dict[str, Any]) -> None:
            if kind == "text":
                if payload["text"] and not first_text:
                    first_text.append(time.perf_counter())
                turn["text"] = payload["text"]
            elif kind == "step":
                step = next((s for s in turn["steps"] if s["id"] == payload["id"]), None)
                if step is None:
                    turn["steps"].append({k: v for k, v in payload.items() if v is not None})
                else:
                    step.update({k: v for k, v in payload.items() if v is not None})

        try:
            # 1. Fetch the views this question most likely needs: milliseconds, before any model call.
            try:
                matches = router.match(question, ctx.shop, ctx.persona, history=[t["content"] for t in earlier[-3:]])
            except Exception:                            # the pre-fetch is a head start, never a reason to fail
                log.exception("router failed; continuing without a pre-fetch")
                matches = []
            prefetched: list[tuple[str, dict]] = []
            strong: list[str] = []
            for i, m in enumerate(matches):
                t0 = time.perf_counter()
                try:
                    handle, result = tools.run_view(m["view"], m["args"], ctx)
                except Exception:
                    log.exception("pre-fetch of %s failed; continuing without it", m["view"])
                    continue
                ms = round((time.perf_counter() - t0) * 1000, 1)
                ctx.calls.append({"name": m["view"], "input": m["args"], "ok": True, "ms": ms, "prefetched": True,
                                  "output": {"card": handle if result.get("card") else None, "summary": result["summary"]}})
                emit("step", {"id": f"pre-{i}", "kind": "view", "tool": m["view"], "state": "done", "ms": ms,
                              "label": tools.LABELS.get(m["view"], m["view"]), "detail": tools.detail(m["view"], m["args"])})
                prefetched.append((handle, result))
                if m["strong"] and result.get("card"):
                    strong.append(handle)
            turn["preview"] = [ctx.card(h) for h in strong[:1]]

            # 2. Answer: the model when it is available, the views alone when it is not.
            out: dict[str, Any] | None = None
            notice = None
            use_model = agent.enabled() and time.time() >= self._breaker_until
            if use_model and FAST_PATH and len(strong) == 1 and len(question) <= 90 and not attachments:
                use_model = False                      # an exact standard question, answered from the view at once
            elif agent.enabled() and not use_model:
                notice = "The language model is recovering from an error, so this answer comes straight from the shop data."
            if use_model:
                slot = self._slot()
                try:
                    await asyncio.wait_for(slot.acquire(), timeout=SLOT_WAIT_S)
                except TimeoutError:
                    notice = "The assistant is very busy, so this answer comes straight from the shop data."
                else:
                    try:
                        out = await agent.run(question, ctx, history=[self._public(t) for t in earlier], prefetched=prefetched,
                                              attachments=attachments, emit=emit, fallback_cards=strong)
                        self._failures = 0
                        self.model_check = {"ok": True, "model": out.get("model"), "ms": (out.get("usage") or {}).get("model_ms")}
                    except agent.Unavailable as e:
                        log.warning("model unavailable (%s); answering directly", e.reason)
                        if e.outage:
                            self.model_check = {"ok": False, "error": e.public or e.reason}
                        if e.reason == "refusal":
                            out = {"text": e.public, "cards": [], "followups": []}
                        else:
                            if e.outage:                     # only a failing service trips the breaker, not one awkward question
                                self._failures += 1
                                if self._failures >= BREAKER_FAILURES:
                                    self._breaker_until = time.time() + BREAKER_OPEN_S
                                    self._failures = 0
                            notice = (e.public or "The language model could not complete this one.") + " This answer comes straight from the shop data."
                    finally:
                        slot.release()
            if out is None:
                turn["text"] = ""
                d = direct.answer(question, ctx, history=[t["content"] for t in earlier[-3:]], prefetched=prefetched, model_configured=agent.enabled())
                out = {**d, "usage": {}, "model": None, "llm_calls": []}
                turn["mode"] = "direct"
                self.stats["direct_answers"] += 1
            else:
                turn["mode"] = "model" if out.get("model") else "direct"
                self.stats["model_answers" if out.get("model") else "direct_answers"] += 1

            # 3. Assemble what the screen shows.
            cards = [c for c in (ctx.card(h) for h in out["cards"]) if c]
            followups = out.get("followups") or []
            if not followups:
                for h in out["cards"]:
                    followups += (ctx.views.get(h) or {}).get("followups") or []
            asked = direct._norm(question)
            followups = list(dict.fromkeys(f.strip() for f in followups if f and direct._norm(f) != asked))[:3]
            turn.update(answer=out["text"], text=out["text"], cards=cards, preview=[], followups=followups,
                        sources=_sources(ctx, out["cards"]), records=list(ctx.created), usage=out.get("usage") or {},
                        model=out.get("model"), notice=notice, state="done")
            turn["trace"] = {"toolCalls": ctx.calls, "llmCalls": out.get("llm_calls") or [],
                             "retrievalCalls": [{k: p[k] for k in ("title", "doc_id", "collection", "page", "section", "score")} | {"text": p["text"][:600]}
                                                for p in ctx.passages]}
        except asyncio.CancelledError:
            turn.update(state="cancelled", answer=(turn["text"] or "").strip() or "Stopped.", notice="Stopped before the answer was complete.", preview=[])
            for s in turn["steps"]:
                if s.get("state") == "running":
                    s["state"] = "error"
        except Exception:                                # never leave a question hanging
            log.exception("question failed")
            self.stats["errors"] += 1
            turn.update(state="error", answer=None, preview=[],
                        errorText="Something went wrong while answering. Please ask again.")
        finally:
            ctx.close()
            now = time.perf_counter()
            turn["timing"] = {"total_ms": round((now - turn["_t0"]) * 1000),
                              "first_text_ms": round((first_text[0] - turn["_t0"]) * 1000) if first_text else None}
            session["updated"] = _now_iso()
            o.in_flight = max(0, o.in_flight - 1)
            self._save_soon()

    def _slot(self) -> asyncio.Semaphore:
        if self._slots is None:
            self._slots = asyncio.Semaphore(MODEL_SLOTS)
        return self._slots

    # -- helpers ------------------------------------------------------------
    def _turn(self, owner_id: str, query_id: str) -> dict:
        self._load()
        t = self.turns.get(query_id)
        if not t or t["owner"] != owner_id:
            raise Refused(404, "That question is no longer available. Ask it again.")
        return t

    @staticmethod
    def _clock(shop_time: str | None):
        dt = ops.parse(shop_time)
        if not dt or not (ops.parse(CLOCK_MIN) <= dt <= ops.parse(CLOCK_MAX)):
            return ops.scenario_start()
        return dt.replace(second=0, microsecond=0)

    @staticmethod
    def _public(t: dict) -> dict:
        keep = ("queryId", "querySessionId", "content", "answer", "persona", "personaTitle", "personaId", "shopTime", "shopTimeNice",
                "cards", "followups", "sources", "steps", "records", "usage", "timing", "mode", "model", "notice", "errorText",
                "createdAt", "attachments", "state")
        return {k: t.get(k) for k in keep}

    # -- persistence --------------------------------------------------------
    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not PERSIST or not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
            for oid, od in (data.get("owners") or {}).items():
                o = Owner()
                o.records = od.get("records") or []
                for s in od.get("sessions") or []:
                    for t in s["turns"]:
                        t.setdefault("owner", oid)
                        t.setdefault("text", t.get("answer") or "")
                        t.setdefault("preview", [])
                        t.setdefault("trace", {})
                        t["_t0"] = 0.0
                        if t.get("state") == "running":      # the process stopped mid-answer
                            t.update(state="error", errorText="The assistant restarted before this answer finished. Please ask again.")
                        self.turns[t["queryId"]] = t
                    o.sessions[s["id"]] = s
                self.owners[oid] = o
            log.info("restored %d browsers from %s", len(self.owners), STATE_FILE)
        except Exception:
            log.exception("could not read saved state; starting empty")

    def _save_soon(self) -> None:
        if not PERSIST:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._save_task and not self._save_task.done():
            return

        async def later() -> None:
            await asyncio.sleep(SAVE_DELAY_S)
            snapshot = self._snapshot()                  # cheap copies, taken on the loop
            await asyncio.to_thread(_write, snapshot)    # serialising and writing happen off it

        self._save_task = loop.create_task(later())

    def _snapshot(self) -> dict:
        """What is saved: finished turns only, copied so nothing changes under the writer."""
        owners = {}
        for oid, o in list(self.owners.items())[-500:]:
            sessions = []
            for s in o.sessions.values():
                turns = [{k: v for k, v in t.items() if k not in ("_t0", "trace", "preview")} for t in s["turns"] if t["state"] != "running"]
                if turns:
                    sessions.append({**s, "turns": turns})
            if sessions or o.records:
                owners[oid] = {"sessions": sessions, "records": list(o.records)}
        return {"saved": _now_iso(), "owners": owners}

    def _dump(self) -> str:
        return json.dumps(self._snapshot(), default=str, ensure_ascii=False)

    # -- health -------------------------------------------------------------
    async def check_model(self) -> dict:
        self.model_check = await agent.self_test() if agent.enabled() else {"ok": False, "error": "no key"}
        return self.model_check

    def health(self) -> dict:
        live = agent.enabled()
        return {"status": "ok", "mode": "builtin", "assistant": scenario.AGENT["name"], "llm": live, **agent.describe(),
                "modelCheck": self.model_check if live else None, "fastPath": FAST_PATH,
                "degraded": bool(live and time.time() < self._breaker_until),
                "build": os.getenv("RAILWAY_GIT_COMMIT_SHA", "")[:7] or "local", "stats": self.stats}


def _write(snapshot: dict) -> None:
    try:
        text = json.dumps(snapshot, default=str, ensure_ascii=False)
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, STATE_FILE)
    except Exception:
        log.exception("could not save state")


def _title(content: str) -> str:
    t = re.sub(r"\s+", " ", content).strip()
    return t if len(t) <= 60 else t[:57].rsplit(" ", 1)[0] + "..."


def _sources(ctx: tools.Context, handles: list[str]) -> list[dict]:
    out: list[dict] = []
    seen: set[tuple] = set()
    for p in ctx.passages:
        key = (p["title"], p["page"], p["section"])
        if key not in seen:
            seen.add(key)
            out.append({"title": p["title"], "collection": p["collection"], "page": p["page"], "section": p["section"], "text": p["text"][:1200]})
    titled = {s["title"] for s in out}
    for h in handles:
        for title in (ctx.views.get(h) or {}).get("sources") or []:
            if title not in titled:
                titled.add(title)
                out.append({"title": title})
    out.append({"title": f"Shop data as of {ops.nice(ctx.shop.clock)}", "kind": "data"})
    return out


ENGINE = Engine()
