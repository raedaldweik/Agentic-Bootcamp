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

from . import corpus, ops, records, tools
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
            "eager": True, "cache": True, "ttl": True, "effort": True}


_optional = _defaults()
_client = None


class Unavailable(Exception):
    """The model could not answer (no key, an API error, a refusal, out of time)."""

    def __init__(self, reason: str, *, public: str = "", outage: bool = False, detail: str = ""):
        super().__init__(reason)
        self.reason = reason
        self.public = public
        self.outage = outage          # the service itself is the problem, not this one question
        self.detail = detail          # what the API said, for the operator (never contains the key)


def _clean_key(raw: str) -> str:
    """The key as it was meant: without the quotes, the variable name or the line breaks
    that tend to come along when a key is pasted into a settings page."""
    key = (raw or "").strip()
    for prefix in ("export ", "ANTHROPIC_API_KEY=", "ANTHROPIC_API_KEY:", "Bearer ", "bearer ", "x-api-key:", "X-Api-Key:"):
        if key.startswith(prefix):
            key = key[len(prefix):].strip()
    if len(key) >= 2 and key[0] == key[-1] and key[0] in "\"'`":
        key = key[1:-1]
    return "".join(key.split())                     # a key never contains spaces or line breaks


def api_key() -> str:
    return _clean_key(os.getenv("ANTHROPIC_API_KEY") or "")


def key_report() -> dict[str, Any]:
    """What can be said about the configured key without showing any of it: its kind,
    its length, whether it had to be tidied, and what to do if it is the wrong kind."""
    raw = os.getenv("ANTHROPIC_API_KEY") or ""
    key = api_key()
    if not key:
        return {"present": False, "kind": "missing", "length": 0, "tidied": False,
                "hint": "ANTHROPIC_API_KEY is not set on the server. Add it and redeploy."}
    if key.startswith("sk-ant-api"):
        kind, hint = "Anthropic API key", ("The key has the right form. If Anthropic rejects it, it was revoked, deleted, or copied incompletely: "
                                           "create a new key in the Claude Console (API keys), replace the variable and redeploy.")
        if not 90 <= len(key) <= 130:
            hint = f"The key has the right start but is {len(key)} characters, which is not the usual length, so it was probably copied incompletely. " + hint
    elif key.startswith("sk-ant-oat"):
        kind, hint = "Claude subscription token", ("This is a sign-in token from a Claude subscription, not an API key, and the API does not accept it here. "
                                                   "Create an API key in the Claude Console (API keys) and use that.")
    elif key.startswith("sk-ant-admin"):
        kind, hint = "Anthropic admin key", "This is an admin key, which manages an organisation and cannot call the model. Create a normal API key in the Claude Console and use that."
    elif key.startswith("sk-ant-"):
        kind, hint = "Anthropic key", ("The key has the form of an Anthropic key. If Anthropic rejects it, it was revoked, deleted, or copied incompletely: "
                                       "create a new API key in the Claude Console (API keys), replace the variable and redeploy.")
    elif key.startswith(("sk-", "AIza", "gsk_", "xai-")):
        kind, hint = "key from another provider", "This looks like a key from another AI provider. The assistant needs an Anthropic API key (it starts with sk-ant-api), from the Claude Console."
    else:
        kind, hint = "not an API key", "This does not look like an Anthropic API key (those start with sk-ant-api). Paste the whole key from the Claude Console, with nothing before or after it."
    return {"present": True, "kind": kind, "length": len(key), "tidied": raw.strip() != key, "hint": hint}


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
        # The SDK sends the key as a bearer token; it is also sent in the x-api-key header, the
        # long-standing way, so the key is accepted whichever of the two the account expects.
        _client = anthropic.AsyncAnthropic(api_key=api_key(), base_url=os.getenv("SANAD_ANTHROPIC_BASE_URL") or "https://api.anthropic.com",
                                           timeout=REQUEST_TIMEOUT_S, max_retries=2, default_headers={"X-Api-Key": api_key()})
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

A message may also carry views: some fetched ahead of time because they looked relevant to the question, some carried over from the previous answer in the conversation. When they answer the question, answer straight away without calling a tool. They are a head start, not a boundary: when the question is wider than a view you were handed (all the tools in the shop, when the view covers one job card), answer the question that was asked, with run_sql or another view. Never narrow a question to fit a view, and never mention a view that turned out not to apply.

# Where facts come from
Every operational fact you state (an id, a date, a duration, a cost, a location, a status, a limit, a name) comes from a view, a query result or a document passage in this conversation. If the records do not contain something, say that the shop records do not show it and, if it helps, what they do show. Do not fill a gap with a plausible figure, and do not carry a figure over from an earlier shop time. Your own earlier answers in the conversation are summaries, not a source: when a follow-up needs a figure, take it from the views in this message or fetch it again, and do not rebuild it from memory of what you said before. Treat the shop data as the system of record, and do not label it as sample, test or demonstration data in your answers. If someone asks you directly whether this is Sanad's live operational data, say truthfully that this deployment runs on a demonstration data set.

Choosing tools:
- The views (engine_status, delivery_risk, forecast_changes, recovery_plan, protect_delivery, job_card, task_readiness, task_tools, tool_location, inspection_finding, approval_authority, simulate_schedule) answer the common questions, each with a ready-made card. Reach for them first.
- run_sql answers anything else about the shop data: counts, filters, joins, history, a specific record. The tables are listed below.
- search_documents answers what the approved documents say: procedure, limits, policy, definitions. Quote the document, page and section you used.
- render_chart draws a chart when one is asked for or a comparison is clearer drawn.
- When several lookups are independent, call them together in one step.

# What you may and may not do
You inform and prepare; authorised people decide. You cannot approve a deviation or concession, accept or disposition a finding, certify work, release work or an engine, authorise overtime or spend, or record a tool handover. When someone asks you to do one of these, say plainly that you cannot, name the role that can (approval_authority knows), and offer what you can do: assemble the evidence and route it.

Your action tools (raise_tool_request, draft_finding, prepare_deviation_package, submit_recovery_option, confirm_job_step, save_note) each create a pending record for an authorised person. Use one only when the person asks for that action, not on your own initiative. Afterwards say what was created, give its reference, and say that it is pending and who acts on it. The tools enforce the role rules themselves: if one refuses, tell the person why in a sentence and do not try another way round. Where an action takes free text (a reason, a justification), keep it to one plain sentence and use only figures that are in this message.

A person's role limits what they may decide, not what they may ask. Anyone may see any status.

# How to answer
- Lead with the direct answer in one or two sentences: yes or no, the date, the location, the name. If it will be read aloud, that opening should stand on its own.
- Then the reason or the next step in a few short lines. Use a short bullet list only for parallel items such as options or steps.
- Keep it brief: usually 40 to 110 words. The card shows the table, so do not repeat the card's rows in text; say what they mean.
- Write dates as 3 Nov 18:00, durations as 36 h or 90 min, and ids exactly as recorded (ENG-204, P-4582, T-117, JC-FAN-204).
- Bold the two or three facts that matter most. No headings, no preamble such as "Based on the data", no closing offer of further help.
- Step-by-step guidance: work one step at a time, on the step that is next to be confirmed. Give that step and the confirmation it needs, and point to the card for the rest. Remind the person of the care point when there is one. Give a later step only when it is asked for by number. If the person says only "next" or "done", do not skip ahead and do not record a confirmation they have not given: ask them to confirm the current step in its own words, and say you will record it and move on.
- When someone says "this step", "this task" or "the job" without naming one, they mean the job card they are working on. Answer for it without remarking on the wording.
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


def user_turn(question: str, ctx: tools.Context, prefetched: list[tuple[str, dict]], attachments: list[dict] | None = None,
              carried: list[tuple[str, dict]] | None = None) -> str:
    p = ctx.persona
    parts = [f"<asked_by>{p['title']} ({p['id']}). {p['authority']}</asked_by>",
             f"<shop_time>{ctx.shop.clock.strftime('%A')} {nice(ctx.shop.clock)}</shop_time>"]
    raised = [r for r in ctx.notebook.items[-8:] if r["kind"] not in ("answer", "note")]
    if raised:
        lines = "\n".join(f"- {r['id']} {r['label']}: {r['title']}. Raised by {r['by']} at shop time {r['shop_time']}. {records.since(r, ctx.shop)}" for r in raised)
        parts.append("<records_raised_through_you note=\"Raised earlier from this device. Each line says which role raised it, so do not call it "
                     f"'your' request unless that role is asking now.\">\n{lines}\n</records_raised_through_you>")

    def views_xml(items: list[tuple[str, dict]]) -> str:
        return "\n".join(f'<view name="{r["view"]}" card="{h if r.get("card") else "none"}">\n{tools.to_json(tools.view_payload(h, r))}\n</view>' for h, r in items)

    if prefetched:
        parts.append(f"<prefetched_views note=\"Fetched ahead because they looked relevant to this question.\">\n{views_xml(prefetched)}\n</prefetched_views>")
    if carried:
        parts.append("<context_views note=\"The views behind the previous answer in this conversation, refreshed for this shop time. "
                     f"Use them if this question follows on from it; otherwise ignore them.\">\n{views_xml(carried)}\n</context_views>")
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
            nexts.extend(q.strip(" \n\t-") for q in re.split(r"[|｜]", body) if q.strip(" \n\t-"))
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
              attachments: list[dict] | None, emit: Emit, fallback_cards: list[str] | None = None,
              carried: list[tuple[str, dict]] | None = None) -> dict[str, Any]:
    """Answer one question. Returns {text, cards, followups, usage, model, calls}.
    `emit(kind, payload)` reports progress: "text" {text}, "step" {...}. Raises Unavailable."""
    if not enabled():
        raise Unavailable("no api key")
    import anthropic

    messages: list[dict] = _history(history) + [{"role": "user", "content": user_turn(question, ctx, prefetched, attachments, carried)}]
    usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, "model_calls": 0, "model_ms": 0}
    llm_calls: list[dict] = []
    served_model = MODEL
    deadline = time.monotonic() + TURN_BUDGET_S
    json_retries = 0
    called_views: list[str] = []
    text = ""

    finished = False
    while usage["model_calls"] < MAX_MODEL_CALLS:
        if time.monotonic() > deadline:
            raise Unavailable("turn budget exceeded", public="The language model did not answer in time.", outage=True)
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
            raise Unavailable("the model took too long", public="The language model did not answer in time.", outage=True) from e
        except TypeError as e:                        # an SDK too old to know one of the optional parameters
            if _degrade(f"sdk: {e}"):
                continue
            raise Unavailable(f"sdk: {e}", outage=True) from e
        except anthropic.BadRequestError as e:
            if _degrade(str(e)):
                continue                              # an optional feature was rejected: retry without it
            log.warning("model rejected the request: %s", str(e)[:300])
            low = str(e).lower()
            if "credit" in low or "billing" in low:
                raise Unavailable("no credit", public="The language model account has no credit left.", outage=True, detail=_api_message(e)) from e
            raise Unavailable(f"bad request: {str(e)[:200]}", detail=_api_message(e)) from e
        except anthropic.AuthenticationError as e:
            raise Unavailable("the API key was rejected", public="The language model key was rejected.", outage=True, detail=_api_message(e)) from e
        except anthropic.PermissionDeniedError as e:
            raise Unavailable(f"permission denied: {str(e)[:160]}", public="The language model key is not permitted to use this model.", outage=True, detail=_api_message(e)) from e
        except anthropic.NotFoundError as e:
            raise Unavailable(f"model {MODEL} not found", public=f"The configured model ({MODEL}) is not available to this key.", outage=True, detail=_api_message(e)) from e
        except anthropic.RateLimitError as e:
            raise Unavailable("rate limited", public="The language model is rate limited right now.", outage=True, detail=_api_message(e)) from e
        except anthropic.APIStatusError as e:
            raise Unavailable(f"api status {e.status_code}", public="The language model is temporarily unavailable.", outage=True, detail=_api_message(e)) from e
        except anthropic.APIConnectionError as e:     # includes timeouts
            raise Unavailable(f"connection: {type(e).__name__}", public="The language model could not be reached.", outage=True) from e

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
            finished = True
            break
        if not tool_uses:
            finished = True
            break

        # Run the tools. Inputs were streamed eagerly, so each is validated before it runs.
        emit("text", {"text": ""})                     # anything written before a tool call is not the answer
        results = []
        for block in tool_uses:
            step_id = f"tool-{block.id}"
            args = block.input if isinstance(block.input, dict) else {}
            emit("step", {"id": step_id, "kind": _kind(block.name), "tool": block.name, "state": "running",
                          "label": tools.LABELS.get(block.name, block.name), "detail": tools.detail(block.name, args)})
            # off the event loop: a heavy query must not hold up everyone else's answers
            result, is_error = await asyncio.to_thread(tools.execute, block.name, block.input, ctx)
            if block.name in tools.VIEW_NAMES and not is_error and result.get("card"):
                called_views.append(result["card"])
            emit("step", {"id": step_id, "state": "error" if is_error else "done", "ms": ctx.calls[-1]["ms"],
                          "note": result.get("error") if is_error else None})
            results.append({"type": "tool_result", "tool_use_id": block.id, "content": tools.to_json(result), **({"is_error": True} if is_error else {})})
        messages.append({"role": "assistant", "content": response.content})
        messages.append({"role": "user", "content": results})
    if not finished:                                  # still asking for tools at the limit: whatever it wrote is not an answer
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


def _system() -> Any:
    """The instructions, schema and document list, marked as the fixed part of every request.

    Tools and system are rendered first and never change, so the marker here caches both. Every
    question after the first reads them back instead of paying for them again, whatever the
    question is. The entry is kept for an hour, because people pause between questions."""
    if not _optional["cache"]:
        return system_prompt()
    mark: dict[str, Any] = {"type": "ephemeral"}
    if _optional["ttl"]:
        mark["ttl"] = "1h"
    return [{"type": "text", "text": system_prompt(), "cache_control": mark}]


def _request(messages: list[dict], *, tail_cache: bool = True) -> dict[str, Any]:
    schemas = tools.SCHEMAS if _optional["eager"] else [{k: v for k, v in t.items() if k != "eager_input_streaming"} for t in tools.SCHEMAS]
    req: dict[str, Any] = {"model": MODEL, "max_tokens": MAX_TOKENS, "system": _system(), "tools": schemas, "messages": messages}
    if _optional["cache"] and tail_cache:
        # the automatic breakpoint, on the end of the conversation: read back by the next model call of the same question
        req["cache_control"] = {"type": "ephemeral"}
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
    if low.startswith("sdk:") and any(_optional.values()):
        for key in _optional:
            _optional[key] = False
        log.warning("the installed anthropic SDK does not take an optional parameter; continuing with the plain request (%s). "
                    "Upgrade it: pip install -U 'anthropic>=2.8'", error_text[:200])
        return True
    for key, words in (("fallbacks", ("fallback",)), ("speed", ("speed", "fast mode", "fast-mode")), ("eager", ("eager_input_streaming",)),
                       ("ttl", ("ttl",)), ("cache", ("cache_control",)), ("effort", ("output_config", "effort"))):
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


async def warm() -> dict[str, Any]:
    """Put the fixed part of the prompt in the cache (or refresh it there), without generating anything.
    Called at start-up and while the service is in use, so the first question after a pause is as
    quick as the rest. Costs a cache read when the entry is still there, a cache write when it is not."""
    if not enabled() or not _optional["cache"]:
        return {"ok": False, "skipped": True}
    import anthropic
    req = _request([{"role": "user", "content": "warm"}], tail_cache=False)
    req["max_tokens"] = 0
    try:
        r = await client().beta.messages.create(**req)
        u = r.usage
        return {"ok": True, "read": int(getattr(u, "cache_read_input_tokens", 0) or 0), "wrote": int(getattr(u, "cache_creation_input_tokens", 0) or 0)}
    except (anthropic.APIError, TypeError) as e:           # never worth failing over: the next question simply writes the cache itself
        return {"ok": False, "error": f"{type(e).__name__}: {str(e)[:160]}"}


def _api_message(e: Exception) -> str:
    """What the API said, short enough to show an operator. It never contains the key."""
    body = getattr(e, "body", None)
    msg = ""
    if isinstance(body, dict):
        err = body.get("error") if isinstance(body.get("error"), dict) else body
        msg = str(err.get("message") or "")
    status = getattr(e, "status_code", None)
    text = msg or str(e)
    return (f"{status}: " if status else "") + re.sub(r"sk-[A-Za-z0-9_\-]{6,}", "sk-...", text)[:260]


async def self_test() -> dict[str, Any]:
    """One tiny call, to learn at start-up whether the key and model work."""
    if not enabled():
        return {"ok": False, "error": "ANTHROPIC_API_KEY is not set", "detail": ""}
    import anthropic
    t0 = time.perf_counter()
    try:
        # the plainest request there is, so the check says whether the key and model work and nothing else
        r = await client().messages.create(model=MODEL, max_tokens=512,
                                           messages=[{"role": "user", "content": "Reply with the single word: ready"}])
        return {"ok": True, "model": r.model, "ms": round((time.perf_counter() - t0) * 1000)}
    except anthropic.AuthenticationError as e:
        return {"ok": False, "error": "The language model key was rejected.", "detail": _api_message(e)}
    except anthropic.PermissionDeniedError as e:
        return {"ok": False, "error": "The language model key is not permitted to use this model.", "detail": _api_message(e)}
    except anthropic.NotFoundError as e:
        return {"ok": False, "error": f"The configured model ({MODEL}) is not available to this key.", "detail": _api_message(e)}
    except anthropic.RateLimitError as e:
        return {"ok": False, "error": "The language model is rate limited right now.", "detail": _api_message(e)}
    except anthropic.APIStatusError as e:
        low = str(e).lower()
        public = "The language model account has no credit left." if ("credit" in low or "billing" in low) else "The language model is temporarily unavailable."
        return {"ok": False, "error": public, "detail": _api_message(e)}
    except anthropic.APIError as e:
        return {"ok": False, "error": "The language model could not be reached.", "detail": f"{type(e).__name__}: {str(e)[:200]}"}
