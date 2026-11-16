"""The assistant: Claude working the shop tools, streamed.

Built for a short wait:
  - the views a question most likely needs are fetched before the model is called and
    handed to it, so most answers take one model call, not two
  - the answer streams, and the card that carries the detail is ready before the text
  - the instructions, the data schema and the tools never change between questions, so
    they are read from the prompt cache
  - answers are short by instruction: the card shows the table, the text says what it means

Configuration (environment):
  ANTHROPIC_API_KEY     required for this path; without it the direct answers are used
  SANAD_MODEL           model id, default claude-opus-5-5
  SANAD_EFFORT          low | medium | high, default low
  SANAD_FAST_MODE       true to request fast output (a premium-priced option)
  SANAD_FALLBACKS       false to switch off the server-side fallback model
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable

from . import corpus, ops, tools
from .ops import nice

log = logging.getLogger("sanad.agent")

MODEL = os.getenv("SANAD_MODEL", "").strip() or "claude-opus-5-5"
EFFORT = (os.getenv("SANAD_EFFORT", "").strip().lower() or "low")
FAST_MODE = os.getenv("SANAD_FAST_MODE", "").lower() in ("1", "true", "yes")
MAX_TOKENS = int(os.getenv("SANAD_MAX_TOKENS", "6000"))          # thinking and answer together
MAX_MODEL_CALLS = 6                                               # per question
REQUEST_TIMEOUT_S = float(os.getenv("SANAD_REQUEST_TIMEOUT", "60"))
TURN_BUDGET_S = float(os.getenv("SANAD_TURN_BUDGET", "90"))
HISTORY_TURNS = 8
HISTORY_CHARS = 12_000
FALLBACK_BETA = "server-side-fallback-2026-07-01"

# Request features the answer does not depend on. Each is switched off for the life of the
# process if the API rejects it for this model or account, so a parameter one model does not
# take costs a retry, not the answer.
def _defaults() -> dict[str, bool]:
    return {"fallbacks": os.getenv("SANAD_FALLBACKS", "true").lower() != "false", "speed": FAST_MODE,
            "eager": True, "cache": True, "effort": True}


_optional = _defaults()
_client = None


class Unavailable(Exception):
    """The model could not answer (no key, an API error, a refusal, out of time)."""

    def __init__(self, reason: str, *, public: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.public = public


def api_key() -> str:
    return (os.getenv("ANTHROPIC_API_KEY") or "").strip()


def enabled() -> bool:
    return bool(api_key())


def describe() -> dict[str, Any]:
    live = enabled()
    return {"model": MODEL if live else None, "effort": (EFFORT if _optional["effort"] else "default") if live else None,
            "fast_mode": bool(_optional["speed"]) if live else None,
            "features": {k: bool(v) for k, v in _optional.items()} if live else None}


def client():
    global _client
    if _client is None:
        import anthropic
        # The key and the address are passed explicitly, so a stray ANTHROPIC_BASE_URL on the
        # host cannot send the conversation somewhere else.
        _client = anthropic.AsyncAnthropic(api_key=api_key(), base_url=os.getenv("SANAD_ANTHROPIC_BASE_URL") or "https://api.anthropic.com",
                                           timeout=REQUEST_TIMEOUT_S, max_retries=2)
    return _client


def reset_client() -> None:
    """For tests: forget the client and the capability switches."""
    global _client
    _client = None
    _optional.update(_defaults())


# ─── Instructions ────────────────────────────────────────────────────────
_INSTRUCTIONS = """You are the Sanad Digital Assistant, working inside the Sanad MRO Intelligence Hub, the engine shop's operations assistant. The people who talk to you run and work in an aero-engine overhaul shop: the Engine Shop Manager, Supervisors and Technicians. They are busy, often on the shop floor, sometimes speaking to you rather than typing, and they read your answer on a tablet or hear it read aloud. They want the answer first, then the reason.

# Each question
Every message tells you who is asking (their role and staff id) and the shop time. The shop data is as it stood at that shop time: later events have not happened yet, so never describe them. The same question can have a different answer at a different shop time, and that is correct.

A message may also carry views that were fetched ahead of time because they looked relevant. When they answer the question, answer straight away without calling a tool. When they do not, ignore them and use your tools.

# Where facts come from
Every operational fact you state (an id, a date, a duration, a cost, a location, a status, a limit, a name) comes from a view, a query result or a document passage in this conversation. If the records do not contain something, say that the shop records do not show it and, if it helps, what they do show. Do not fill a gap with a plausible figure, and do not carry a figure over from an earlier shop time. This is synthetic demonstration data; treat it as the shop's system of record.

Choosing tools:
- The views (engine_status, delivery_risk, forecast_changes, recovery_plan, protect_delivery, job_card, task_readiness, task_tools, tool_location, inspection_finding, approval_authority, simulate_schedule) answer the common questions, each with a ready-made card. Reach for them first.
- run_sql answers anything else about the shop data: counts, filters, joins, history, a specific record. The tables are listed below.
- search_documents answers what the approved documents say: procedure, limits, policy, definitions. Quote the document, page and section you used.
- render_chart draws a chart when one is asked for or a comparison is clearer drawn.
- When several lookups are independent, call them together in one step.

# What you may and may not do
You inform and prepare; authorised people decide. You cannot approve a deviation or concession, accept or disposition a finding, certify work, release work or an engine, authorise overtime or spend, or record a tool handover. When someone asks you to do one of these, say plainly that you cannot, name the role that can (approval_authority knows), and offer what you can do: assemble the evidence and route it.

Your action tools (raise_tool_request, draft_finding, prepare_deviation_package, submit_recovery_option, confirm_job_step, save_note) each create a pending record for an authorised person. Use one only when the person asks for that action, not on your own initiative. Afterwards say what was created, give its reference, and say that it is pending and who acts on it. The tools enforce the role rules themselves: if one refuses, tell the person why in a sentence and do not try another way round.

A person's role limits what they may decide, not what they may ask. Anyone may see any status.

# How to answer
- Lead with the direct answer in one or two sentences: yes or no, the date, the location, the name. If it will be read aloud, that opening should stand on its own.
- Then the reason or the next step in a few short lines. Use a short bullet list only for parallel items such as options or steps.
- Keep it brief: usually 40 to 110 words. The card shows the table, so do not repeat the card's rows in text; say what they mean.
- Write dates as 3 Nov 18:00, durations as 36 h or 90 min, and ids exactly as recorded (ENG-204, P-4582, T-117, JC-FAN-204).
- Bold the two or three facts that matter most. No headings, no preamble such as "Based on the data", no closing offer of further help.
- Step-by-step guidance: give the current step and the confirmation it needs, and point to the card for the rest. Remind the person of the care point when there is one.
- If the question is unclear, answer the most likely reading and say which one you took.
- Outside the shop (weather, general knowledge, other companies): say in a sentence that you cover this shop's engines, parts, tools, job cards, findings and approvals, and stop. For general aviation maintenance knowledge that the documents do not cover, you may answer briefly, and say that it is general knowledge and not from Sanad's approved documents.
- Answer in English unless the person writes to you in another language.

# Cards and next questions
Each view returns a card handle. To show a card, write its marker on a line of its own after your text, like [[card:engine_status]]. Nearly every operational answer should carry the card of the view that answers it; show two only when the answer truly draws on both. A chart from render_chart is shown the same way. Write [[card:none]] when no card fits.

End every answer with two or three short questions this person would naturally ask next, in their own voice and suited to their role, on one last line in this form:
[[next: first question | second question | third question]]
The suggested_followups of a view are good candidates when they fit. A request for an action the person may take (such as "Raise a handover request for T-117.") is a good next question; do not suggest one their role cannot take.

Write nothing before a tool call: no announcement of what you are about to look up."""


def system_prompt() -> str:
    """Stable text: nothing here depends on the question, the role or the clock."""
    return "\n\n".join([
        _INSTRUCTIONS,
        "# The shop tables (for run_sql and render_chart)\nSQLite. Times are text as YYYY-MM-DD HH:MM and compare correctly as text. "
        "now_ts() is the shop time. Event tables show only what has happened up to the shop time.\n\n" + ops.describe_schema(),
        "# The approved documents (for search_documents)\n" + corpus.catalogue(),
    ])


# ─── Messages ────────────────────────────────────────────────────────────
def _history(history: list[dict]) -> list[dict]:
    """Earlier turns of the conversation as plain text, oldest first, inside a budget."""
    kept: list[dict] = []
    used = 0
    for turn in reversed(history[-HISTORY_TURNS:]):
        q, a = (turn.get("content") or "").strip(), (turn.get("answer") or "").strip()
        if not q or not a:
            continue
        used += len(q) + len(a)
        if used > HISTORY_CHARS and kept:
            break
        shown = ", ".join(c.get("id", "") for c in turn.get("cards") or [] if c.get("id"))
        kept.append({"q": f"[{turn.get('personaTitle') or 'User'}, shop time {turn.get('shopTime') or ''}]\n{q[:3000]}",
                     "a": a[:3000] + (f"\n(card shown: {shown})" if shown else "")})
    out: list[dict] = []
    for t in reversed(kept):
        out.append({"role": "user", "content": t["q"]})
        out.append({"role": "assistant", "content": t["a"]})
    return out


def user_turn(question: str, ctx: tools.Context, prefetched: list[tuple[str, dict]], attachments: list[dict] | None = None) -> str:
    p = ctx.persona
    parts = [f"<asked_by>{p['title']} ({p['id']}). {p['authority']}</asked_by>",
             f"<shop_time>{ctx.shop.clock.strftime('%A')} {nice(ctx.shop.clock)}</shop_time>"]
    if ctx.notebook.items:
        mine = "\n".join(f"- {r['id']} {r['label']}: {r['title']} ({r['status']})" for r in ctx.notebook.items[-8:] if r["kind"] not in ("answer",))
        if mine:
            parts.append(f"<my_pending_records note=\"Raised earlier by this person through you. Pending, not decided.\">\n{mine}\n</my_pending_records>")
    if prefetched:
        views_xml = "\n".join(
            f'<view name="{r["view"]}" card="{h if r.get("card") else "none"}">\n{tools.to_json(tools.view_payload(h, r))}\n</view>'
            for h, r in prefetched)
        parts.append(f"<prefetched_views>\n{views_xml}\n</prefetched_views>")
    for a in attachments or []:
        parts.append(f'<attached_document name="{str(a.get("name", "attachment"))[:120]}">\n{str(a.get("text", ""))[:20000]}\n</attached_document>')
    parts.append(f"<question>\n{question.strip()}\n</question>")
    return "\n".join(parts)


# ─── Markers ─────────────────────────────────────────────────────────────
_MARKER = re.compile(r"[ \t]*\[\[\s*(card|next|follow-?ups?)\s*:\s*(.*?)\]\][ \t]*\n?", re.S | re.I)
_OPEN = re.compile(r"\[\[[^\]]*\]?$|\[$", re.S)


def parse_answer(text: str) -> tuple[str, list[str], list[str]]:
    """(the answer without its markers, card handles in order, next questions)."""
    cards: list[str] = []
    nexts: list[str] = []
    for kind, body in _MARKER.findall(text):
        if kind.lower() == "card":
            cards.extend(h.strip() for h in re.split(r"[,\s]+", body) if h.strip())
        else:
            nexts.extend(q.strip(" \n\t-") for q in body.split("|") if q.strip(" \n\t-"))
    clean = _MARKER.sub("", text)
    clean = re.sub(r"\n{3,}", "\n\n", clean).strip()
    return clean, cards, nexts[:4]


def visible(partial: str) -> str:
    """A partly streamed answer as it should look on screen: no markers, no half marker."""
    out = _MARKER.sub("", partial)
    out = _OPEN.sub("", out)
    return re.sub(r"\n{3,}", "\n\n", out).rstrip()


# ─── The loop ────────────────────────────────────────────────────────────
Emit = Callable[[str, dict[str, Any]], None]


async def run(question: str, ctx: tools.Context, *, history: list[dict], prefetched: list[tuple[str, dict]],
              attachments: list[dict] | None, emit: Emit, fallback_cards: list[str] | None = None) -> dict[str, Any]:
    """Answer one question. Returns {text, cards, followups, usage, model, calls}.
    `emit(kind, payload)` reports progress: "text" {text}, "step" {...}. Raises Unavailable."""
    if not enabled():
        raise Unavailable("no api key")
    import anthropic

    messages: list[dict] = _history(history) + [{"role": "user", "content": user_turn(question, ctx, prefetched, attachments)}]
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "model_calls": 0, "model_ms": 0}
    llm_calls: list[dict] = []
    served_model = MODEL
    deadline = time.monotonic() + TURN_BUDGET_S
    json_retries = 0
    called_views: list[str] = []
    text = ""

    for _ in range(MAX_MODEL_CALLS):
        if time.monotonic() > deadline:
            raise Unavailable("turn budget exceeded")
        t0 = time.perf_counter()
        first_token_ms: float | None = None
        text = ""
        emit("step", {"id": f"model-{usage['model_calls'] + 1}", "kind": "model", "label": "Thinking" if usage["model_calls"] == 0 else "Writing the answer", "state": "running"})
        try:
            async with asyncio.timeout(max(5.0, deadline - time.monotonic())):
                async with client().beta.messages.stream(**_request(messages)) as stream:
                    async for event in stream:
                        if event.type == "text":
                            if first_token_ms is None:
                                first_token_ms = round((time.perf_counter() - t0) * 1000)
                            text += event.text
                            emit("text", {"text": visible(text)})
                    response = await stream.get_final_message()
            json_retries = 0
        except ValueError as e:                       # tool input the SDK could not parse at all: ask again
            json_retries += 1
            if json_retries > 2:
                raise Unavailable(f"unparseable tool input: {e}") from e
            continue
        except TimeoutError as e:
            raise Unavailable("the model took too long") from e
        except anthropic.BadRequestError as e:
            if _degrade(str(e)):
                continue                              # an optional feature was rejected: retry without it
            log.warning("model rejected the request: %s", str(e)[:300])
            raise Unavailable(f"bad request: {str(e)[:200]}") from e
        except anthropic.AuthenticationError as e:
            raise Unavailable("the API key was rejected", public="The language model key was rejected.") from e
        except anthropic.PermissionDeniedError as e:
            raise Unavailable(f"permission denied: {str(e)[:160]}") from e
        except anthropic.NotFoundError as e:
            raise Unavailable(f"model {MODEL} not found", public=f"The configured model ({MODEL}) is not available to this key.") from e
        except anthropic.RateLimitError as e:
            raise Unavailable("rate limited", public="The language model is rate limited right now.") from e
        except anthropic.APIStatusError as e:
            raise Unavailable(f"api status {e.status_code}", public="The language model is temporarily unavailable.") from e
        except anthropic.APIConnectionError as e:     # includes timeouts
            raise Unavailable(f"connection: {type(e).__name__}", public="The language model could not be reached.") from e

        ms = round((time.perf_counter() - t0) * 1000)
        u = response.usage
        usage["model_calls"] += 1
        usage["model_ms"] += ms
        for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
            usage[k] += int(getattr(u, k, 0) or 0)
        served_model = getattr(response, "model", None) or served_model
        tool_uses = [b for b in response.content if b.type == "tool_use"]
        llm_calls.append({"model": served_model, "ms": ms, "first_token_ms": first_token_ms, "stop_reason": response.stop_reason,
                          "input_tokens": int(getattr(u, "input_tokens", 0) or 0), "output_tokens": int(getattr(u, "output_tokens", 0) or 0),
                          "cache_read_input_tokens": int(getattr(u, "cache_read_input_tokens", 0) or 0),
                          "tool_calls": [b.name for b in tool_uses]})
        emit("step", {"id": f"model-{usage['model_calls']}", "kind": "model", "state": "done", "ms": ms,
                      "label": "Chose what to look up" if tool_uses and response.stop_reason == "tool_use" else "Wrote the answer"})

        if response.stop_reason == "refusal":
            raise Unavailable("refusal", public="I can't help with that request.")
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            continue
        if response.stop_reason == "max_tokens":
            if tool_uses or not text.strip():
                raise Unavailable("ran out of output tokens")
            text += "\n\n_The answer was cut short. Ask me to continue._"
            break
        if not tool_uses:
            break

        # Run the tools. Inputs were streamed eagerly, so each is validated before it runs.
        emit("text", {"text": ""})                     # anything written before a tool call is not the answer
        results = []
        for block in tool_uses:
            step_id = f"tool-{block.id}"
            args = block.input if isinstance(block.input, dict) else {}
            emit("step", {"id": step_id, "kind": _kind(block.name), "tool": block.name, "state": "running",
                          "label": tools.LABELS.get(block.name, block.name), "detail": tools.detail(block.name, args)})
            result, is_error = tools.execute(block.name, block.input, ctx)
            if block.name in tools.VIEW_NAMES and not is_error and result.get("card"):
                called_views.append(result["card"])
            emit("step", {"id": step_id, "state": "error" if is_error else "done", "ms": ctx.calls[-1]["ms"],
                          "note": result.get("error") if is_error else None})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": tools.to_json(result), **({"is_error": True} if is_error else {})})
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": results})
    else:
        if not text.strip():
            raise Unavailable("too many tool rounds")

    clean, wanted, nexts = parse_answer(text)
    if not clean:
        raise Unavailable("empty answer")
    suppress = any(w.lower() == "none" for w in wanted)
    cards = [h for h in dict.fromkeys(wanted) if ctx.card(h)]
    if not cards and not suppress:
        # the model showed nothing: fall back to what it looked up itself, then to a confident pre-fetch
        cards = called_views[-1:] or list(ctx.charts)[-1:] or [h for h in (fallback_cards or []) if ctx.card(h)][:1]
    for h in ctx.charts:                              # a chart it drew is always shown
        if h not in cards:
            cards.append(h)
    return {"text": clean, "cards": cards[:3], "followups": nexts, "usage": usage, "model": served_model, "llm_calls": llm_calls}


def _kind(name: str) -> str:
    if name in tools.VIEW_NAMES:
        return "view"
    if name in tools.ACTION_NAMES:
        return "action"
    return {"run_sql": "sql", "search_documents": "search", "render_chart": "chart"}.get(name, "tool")


def _request(messages: list[dict]) -> dict[str, Any]:
    schemas = tools.SCHEMAS if _optional["eager"] else [{k: v for k, v in t.items() if k != "eager_input_streaming"} for t in tools.SCHEMAS]
    req: dict[str, Any] = {"model": MODEL, "max_tokens": MAX_TOKENS, "system": system_prompt(), "tools": schemas, "messages": messages}
    if _optional["cache"]:
        req["cache_control"] = {"type": "ephemeral"}   # caches the instructions, schema, tools and the conversation so far
    if _optional["effort"]:
        req["output_config"] = {"effort": EFFORT}
    betas: list[str] = []
    if _optional["fallbacks"]:
        req["fallbacks"] = "default"
        betas.append(FALLBACK_BETA)
    if _optional["speed"]:
        req["speed"] = "fast"
    if betas:
        req["betas"] = betas
    return req


def _degrade(error_text: str) -> bool:
    """An optional request feature was rejected: switch it off and say so. True if something changed."""
    low = error_text.lower()
    for key, words in (("fallbacks", ("fallback",)), ("speed", ("speed", "fast mode", "fast-mode")), ("eager", ("eager_input_streaming",)),
                       ("cache", ("cache_control",)), ("effort", ("output_config", "effort"))):
        if _optional[key] and any(w in low for w in words):
            _optional[key] = False
            log.warning("the API rejected `%s` for %s; continuing without it (%s)", key, MODEL, error_text[:200])
            return True
    if any(_optional.values()) and not any(w in low for w in ("credit", "billing", "prompt is too long", "max_tokens")):
        # It did not say which. Fall back to the plainest request there is; that one has to work.
        for key in _optional:
            _optional[key] = False
        log.warning("the API rejected the request for %s without naming a feature; continuing with the plain request (%s)", MODEL, error_text[:200])
        return True
    return False


async def self_test() -> dict[str, Any]:
    """One tiny call, to learn at start-up whether the key and model work."""
    if not enabled():
        return {"ok": False, "error": "ANTHROPIC_API_KEY is not set"}
    import anthropic
    t0 = time.perf_counter()
    try:
        r = await client().messages.create(model=MODEL, max_tokens=200, output_config={"effort": "low"},
                                           messages=[{"role": "user", "content": "Reply with the single word: ready"}])
        return {"ok": True, "model": r.model, "ms": round((time.perf_counter() - t0) * 1000)}
    except anthropic.APIError as e:
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
