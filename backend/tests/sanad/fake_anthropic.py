"""A stand-in for the Anthropic Messages API that speaks the real streaming wire format.

The assistant's own client (the official SDK) is pointed at this server, so the tests
exercise the real request building, stream parsing, tool loop and error handling without
a key. Each reply is scripted from the last user message.
"""
from __future__ import annotations

import json
import socket
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

app = FastAPI()
LOG: list[dict] = []          # every request body received
STATE = {"reject_fallbacks": False, "reject": "", "fail_next": 0, "delay": 0.0}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream(blocks: list[dict], stop_reason: str, model: str):
    yield _sse("message_start", {"type": "message_start", "message": {
        "id": f"msg_{int(time.time() * 1000)}", "type": "message", "role": "assistant", "model": model, "content": [],
        "stop_reason": None, "stop_sequence": None,
        "usage": {"input_tokens": 1200, "output_tokens": 1, "cache_read_input_tokens": 6000, "cache_creation_input_tokens": 0}}})
    for i, b in enumerate(blocks):
        if b["type"] == "thinking":
            yield _sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "thinking", "thinking": "", "signature": ""}})
            yield _sse("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "signature_delta", "signature": "sig-abc"}})
        elif b["type"] == "text":
            yield _sse("content_block_start", {"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}})
            text = b["text"]
            for j in range(0, len(text), 7):                    # small chunks, so markers arrive split
                if STATE["delay"]:
                    time.sleep(STATE["delay"])
                yield _sse("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": text[j:j + 7]}})
        elif b["type"] == "tool_use":
            yield _sse("content_block_start", {"type": "content_block_start", "index": i,
                                               "content_block": {"type": "tool_use", "id": b["id"], "name": b["name"], "input": {}}})
            raw = b.get("raw") or json.dumps(b["input"])
            for j in range(0, len(raw), 11):
                yield _sse("content_block_delta", {"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": raw[j:j + 11]}})
        yield _sse("content_block_stop", {"type": "content_block_stop", "index": i})
    yield _sse("message_delta", {"type": "message_delta", "delta": {"stop_reason": stop_reason, "stop_sequence": None}, "usage": {"output_tokens": 90}})
    yield _sse("message_stop", {"type": "message_stop"})


def _last_user(body: dict) -> tuple[str, list[dict]]:
    """(text of the last user message, tool results in it)."""
    content = body["messages"][-1]["content"]
    if isinstance(content, str):
        return content, []
    text = " ".join(b.get("text", "") for b in content if b.get("type") == "text")
    return text, [b for b in content if b.get("type") == "tool_result"]


def _question(body: dict) -> str:
    for m in reversed(body["messages"]):
        c = m["content"]
        text = c if isinstance(c, str) else " ".join(b.get("text", "") for b in c if b.get("type") == "text")
        if m["role"] == "user" and "<question>" in text:
            return text.split("<question>")[1].split("</question>")[0].strip()
    return ""


def script(body: dict) -> tuple[list[dict], str]:
    text, results = _last_user(body)
    q = _question(body).lower()
    think = {"type": "thinking"}
    if "loop forever" in q:                                       # never stops asking for tools
        return [think, {"type": "text", "text": "Checking again."},
                {"type": "tool_use", "id": f"toolu_loop{len(body['messages'])}", "name": "engine_status", "input": {}}], "tool_use"
    if results:                                                   # second round: write the answer from the tool results
        errors = [r for r in results if r.get("is_error")]
        if errors:
            return [think, {"type": "text", "text": "That could not be done: " + json.loads(errors[0]["content"])["error"] + "\n[[card:none]]\n[[next: Show me the status of all the engines.]]"}], "end_turn"
        payload = json.loads(results[0]["content"])
        if "rows" in payload:
            return [think, {"type": "text", "text": f"There are **{payload['rows'][0]['n']}** tools on the register.\n[[next: Where is tool T-117? | Which tools need calibration?]]"}], "end_turn"
        if payload.get("status") in ("raised", "drafted", "submitted", "routed", "confirmed"):
            return [think, {"type": "text", "text": f"Done: **{payload['reference']}** is raised and pending.\n[[next: Where is tool T-117?]]"}], "end_turn"
        cards = "".join(f"\n[[card:{json.loads(r['content']).get('card')}]]" for r in results if json.loads(r["content"]).get("card"))
        return [think, {"type": "text", "text": "Here is what the records show." + cards + "\n[[next: What is the primary risk to ENG-204?]]"}], "end_turn"
    if "weather" in q:
        return [think, {"type": "text", "text": "I cover this shop's engines, parts, tools, job cards, findings and approvals, so I can't help with the weather.\n[[card:none]]\n[[next: Show me the status of all the engines.]]"}], "end_turn"
    if "how many tools" in q:
        return [think, {"type": "text", "text": "Let me check."},
                {"type": "tool_use", "id": "toolu_sql1", "name": "run_sql", "input": {"sql": "select count(*) as n from tools"}}], "tool_use"
    if "compare" in q:
        return [think, {"type": "tool_use", "id": "toolu_a", "name": "engine_status", "input": {}},
                {"type": "tool_use", "id": "toolu_b", "name": "render_chart", "input": {
                    "title": "Hours late by engine", "type": "bar", "sql": "select engine_id, variance_hours from engine_status", "x": "engine_id", "y": ["variance_hours"]}}], "tool_use"
    if q.startswith("raise a handover request"):
        return [think, {"type": "tool_use", "id": "toolu_act", "name": "raise_tool_request", "input": {"tool_id": "T-117", "needed_at": "Gate 1"}}], "tool_use"
    if "confirm step" in q:
        return [think, {"type": "tool_use", "id": "toolu_step", "name": "confirm_job_step", "input": {"step_no": 1}}], "tool_use"
    if "bad input" in q:                                          # a tool input of the wrong type
        return [think, {"type": "tool_use", "id": "toolu_bad", "name": "confirm_job_step", "input": {"step_no": "first"}}], "tool_use"
    if "refuse" in q:
        return [], "refusal"
    if "truncate" in q:
        return [think, {"type": "tool_use", "id": "toolu_cut", "name": "run_sql", "input": {"sql": "select"}}], "max_tokens"
    if "<prefetched_views>" in text:
        handle = text.split('card="')[1].split('"')[0]
        return [think, {"type": "text", "text": f"**Answer from the pre-fetched view.** The detail is in the card.\n\n[[card:{handle}]]\n[[next: What has changed on ENG-204 since yesterday? | Generate a recovery plan for ENG-204.]]"}], "end_turn"
    return [think, {"type": "text", "text": "A plain answer with no card.\n[[next: Show me the status of all the engines.]]"}], "end_turn"


@app.post("/v1/messages")
async def messages(request: Request):
    body = await request.json()
    key = request.headers.get("x-api-key") or request.headers.get("authorization", "").removeprefix("Bearer ")
    LOG.append({"body": body, "beta": request.headers.get("anthropic-beta", ""), "key": key})
    if key != "test-key":
        return JSONResponse({"type": "error", "error": {"type": "authentication_error", "message": "invalid x-api-key"}}, status_code=401)
    if STATE["reject_fallbacks"] and "fallbacks" in body:
        return JSONResponse({"type": "error", "error": {"type": "invalid_request_error", "message": "fallbacks: this model does not support server-side fallbacks"}}, status_code=400)
    if STATE["reject"] == "effort" and "output_config" in body:
        return JSONResponse({"type": "error", "error": {"type": "invalid_request_error", "message": "output_config.effort: not supported on this model"}}, status_code=400)
    if STATE["reject"] == "unnamed" and ("cache_control" in body or any("eager_input_streaming" in t for t in body.get("tools", []))):
        return JSONResponse({"type": "error", "error": {"type": "invalid_request_error", "message": "Extra inputs are not permitted"}}, status_code=400)
    if STATE["fail_next"] > 0:
        STATE["fail_next"] -= 1
        return JSONResponse({"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}}, status_code=529)
    if not body.get("stream"):
        return {"id": "msg_x", "type": "message", "role": "assistant", "model": body["model"], "stop_reason": "end_turn", "stop_sequence": None,
                "content": [{"type": "text", "text": "ready"}], "usage": {"input_tokens": 9, "output_tokens": 2}}
    blocks, stop = script(body)
    return StreamingResponse(_stream(blocks, stop, body["model"]), media_type="text/event-stream")


def start() -> tuple[str, uvicorn.Server]:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    return f"http://127.0.0.1:{port}", server
