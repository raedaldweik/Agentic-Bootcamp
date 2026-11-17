"""The assistant end to end: the engine, the HTTP API, and the model path against a
stand-in for the Anthropic API that speaks the real streaming format."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from services.sanad import agent, engine as engine_mod
from . import fake_anthropic as fake


@pytest.fixture(scope="module")
def api():
    url, server = fake.start()
    yield url
    server.should_exit = True


@pytest.fixture()
def model(api, monkeypatch):
    """The assistant with a model behind it (the stand-in)."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("SANAD_ANTHROPIC_BASE_URL", api)
    agent.reset_client()
    fake.LOG.clear()
    fake.STATE.update(reject_fallbacks=False, reject="", fail_next=0, delay=0.0)
    yield fake
    agent.reset_client()


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(engine_mod, "ENGINE", engine_mod.Engine())
    import routers.sanad as r
    monkeypatch.setattr(r, "ENGINE", engine_mod.ENGINE)
    import sanad_app
    with TestClient(sanad_app.app) as c:
        yield c


def ask(c, content, persona="manager", shop_time=None, session=None, expect=200):
    res = c.post("/api/assistant/query", json={"content": content, "persona": persona, "shopTime": shop_time, "querySessionId": session})
    assert res.status_code == expect, res.text
    if expect != 200:
        return res.json()
    sub = res.json()
    partials = []
    for _ in range(600):
        st = c.get(f"/api/assistant/query/{sub['queryId']}").json()
        if st["done"]:
            return {**st["result"], "_partials": partials}
        partials.append(st)
        time.sleep(0.01)
    raise AssertionError("the question never finished")


# ── without a model ──────────────────────────────────────────────────────
def test_standard_questions_are_answered_without_a_model(client):
    r = ask(client, "Show me the status of all the engines.")
    assert r["mode"] == "direct" and r["cards"][0]["id"] == "engine_status" and "ENG-204" in r["answer"]
    assert r["followups"] and r["timing"]["total_ms"] < 500
    r = ask(client, "Can I start fan blade removal now?", "technician", "2026-10-28 12:15")
    assert r["answer"].startswith("Not ready") and r["shopTime"] == "2026-10-28 12:15"
    assert "language model is not connected" in ask(client, "what's the weather in Abu Dhabi")["answer"]


def test_each_browser_is_its_own_user(client):
    r = ask(client, "Where is tool T-117?", "supervisor")
    assert len(client.get("/api/assistant/sessions").json()) == 1
    import sanad_app
    with TestClient(sanad_app.app) as other:
        assert other.get("/api/assistant/sessions").json() == []
        assert other.get(f"/api/assistant/query/{r['queryId']}").status_code == 404
        assert other.get(f"/api/assistant/sessions/{r['querySessionId']}/queries").status_code == 404


def test_conversation_history_and_delete(client):
    a = ask(client, "Show me the status of all the engines.")
    ask(client, "What is the primary risk to ENG-204?", session=a["querySessionId"])
    turns = client.get(f"/api/assistant/sessions/{a['querySessionId']}/queries").json()
    assert [t["content"] for t in turns] == ["Show me the status of all the engines.", "What is the primary risk to ENG-204?"]
    assert client.delete(f"/api/assistant/sessions/{a['querySessionId']}").json()["ok"]
    assert client.get("/api/assistant/sessions").json() == []


def test_bad_requests(client):
    assert ask(client, "   ", expect=400)["detail"]
    assert client.post("/api/assistant/query", json={"content": "x" * 7000}).status_code == 422
    assert client.post("/api/assistant/query", json={"content": "x" * 4500}).status_code == 413
    assert client.get("/api/assistant/query/unknown").status_code == 404
    r = ask(client, "Show me the status of all the engines.", shop_time="not a time")
    assert r["shopTime"] == "2026-10-28 09:30"                       # an unreadable time falls back to the start


def test_rate_limit(client, monkeypatch):
    monkeypatch.setattr(engine_mod, "RATE_PER_MIN", 3)
    for _ in range(3):
        ask(client, "Where is tool T-117?")
    assert "faster" in ask(client, "Where is tool T-117?", expect=429)["detail"]


def test_access_code(client, monkeypatch):
    import routers.sanad as r
    monkeypatch.setattr(r, "ACCESS_CODE", "open-sesame")
    assert client.get("/api/assistant/health").json()["locked"] is True
    assert client.get("/api/assistant/config").status_code == 401
    assert client.post("/api/assistant/unlock", json={"code": "wrong"}).status_code == 403
    assert client.post("/api/assistant/unlock", json={"code": "open-sesame"}).json()["ok"]
    assert client.get("/api/assistant/config").status_code == 200


def test_notebook_and_reset(client):
    rec = client.post("/api/assistant/notebook", json={"kind": "answer", "title": "Engine status", "text": "ENG-204 is at risk"}).json()
    assert rec["id"].startswith("ANS-") and len(client.get("/api/assistant/notebook").json()) == 1
    assert client.delete(f"/api/assistant/notebook/{rec['id']}").json()["ok"]
    ask(client, "Where is tool T-117?")
    client.post("/api/assistant/reset")
    assert client.get("/api/assistant/sessions").json() == [] and client.get("/api/assistant/notebook").json() == []


# ── with a model (the stand-in API) ──────────────────────────────────────
def test_one_model_call_when_the_view_was_prefetched(client, model):
    r = ask(client, "What is the primary risk to ENG-204?")
    assert r["mode"] == "model" and r["model"] == agent.MODEL and r["usage"]["model_calls"] == 1
    assert r["answer"].startswith("**Answer from the pre-fetched view.**") and "[[" not in r["answer"]
    assert [c["id"] for c in r["cards"]] == ["delivery_risk"]
    assert r["followups"] == ["What has changed on ENG-204 since yesterday?", "Generate a recovery plan for ENG-204."]
    body = model.LOG[-1]["body"]
    assert body["model"] == "claude-opus-5-5" and body["stream"] is True and "thinking" not in body
    assert body["output_config"] == {"effort": "low"} and body["cache_control"] == {"type": "ephemeral"}
    assert body["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in model.LOG[-1]["beta"]
    assert all(t.get("eager_input_streaming") for t in body["tools"]) and len(body["tools"]) == 21
    assert "<shop_time>Wednesday 28 Oct 2026 09:30</shop_time>" in body["messages"][-1]["content"]
    assert "28 Oct" not in body["system"]                                  # the cached part never carries the clock


def test_markers_never_reach_the_screen_while_streaming(client, model):
    model.STATE["delay"] = 0.004
    r = ask(client, "What is the primary risk to ENG-204?")
    texts = [p["text"] for p in r["_partials"] if p["text"]]
    assert texts and all("[[" not in t and "]]" not in t for t in texts)
    assert any(p["cards"] for p in r["_partials"])                         # the card is on screen before the text is done
    assert r["timing"]["first_text_ms"] is not None


def test_tool_round_trip(client, model):
    r = ask(client, "How many tools are on the register?")
    assert r["answer"].startswith("There are **8** tools") and r["usage"]["model_calls"] == 2
    assert "Let me check" not in r["answer"]
    trace = client.get(f"/api/assistant/query/{r['queryId']}/trace").json()
    assert trace["toolCalls"][0]["name"] == "run_sql" and trace["toolCalls"][0]["ok"]
    second = model.LOG[-1]["body"]["messages"]
    assert second[-2]["role"] == "assistant" and second[-2]["content"][0]["type"] == "thinking"   # thinking goes back unchanged
    assert second[-1]["content"][0]["type"] == "tool_result"


def test_parallel_tools_and_a_chart(client, model):
    r = ask(client, "Compare the engines on hours late.")
    ids = [c["id"] for c in r["cards"]]
    assert "chart_1" in ids and r["cards"][ids.index("chart_1")]["kind"] == "chart"
    assert len(r["cards"][ids.index("chart_1")]["data"]) == 4


def test_actions_respect_roles_through_the_model(client, model):
    r = ask(client, "Raise a handover request for T-117.", "supervisor")
    assert "THR-0001" in r["answer"] and r["records"][0]["status"].startswith("Pending")
    assert client.get("/api/assistant/notebook").json()[0]["id"] == "THR-0001"
    r = ask(client, "Please confirm step 1.", "supervisor", "2026-10-28 13:30")
    assert "is for the Technician" in r["answer"] and not r["records"]
    r = ask(client, "Please confirm step 1.", "technician", "2026-10-28 12:15")
    assert "has not been released" in r["answer"] and not r["records"]
    r = ask(client, "Please confirm step 1.", "technician", "2026-10-28 13:30")
    assert "JCS-0001" in r["answer"]


def test_a_bad_tool_input_is_reported_not_run(client, model):
    r = ask(client, "bad input please")
    assert "step_no" in r["answer"] and r["mode"] == "model"


def test_history_is_sent_as_plain_text(client, model):
    a = ask(client, "What is the primary risk to ENG-204?")
    ask(client, "and what about the weather", session=a["querySessionId"])
    msgs = model.LOG[-1]["body"]["messages"]
    assert len(msgs) == 3 and msgs[0]["content"].startswith("[Engine Shop Manager, shop time 2026-10-28 09:30]")
    assert isinstance(msgs[1]["content"], str) and "card shown: delivery_risk" in msgs[1]["content"]


def test_rejected_optional_feature_is_dropped_and_the_question_still_answered(client, model):
    model.STATE["reject_fallbacks"] = True
    r = ask(client, "What is the primary risk to ENG-204?")
    assert r["mode"] == "model" and "fallbacks" not in model.LOG[-1]["body"]
    ask(client, "Where is tool T-117?")
    assert "fallbacks" not in model.LOG[-1]["body"]                        # remembered for the life of the process


def test_any_rejected_feature_costs_a_retry_not_the_answer(client, model):
    model.STATE["reject"] = "effort"
    r = ask(client, "What is the primary risk to ENG-204?")
    assert r["mode"] == "model" and "output_config" not in model.LOG[-1]["body"] and "cache_control" in model.LOG[-1]["body"]
    model.STATE["reject"] = "unnamed"                                      # a 400 that names nothing: the plain request must work
    r = ask(client, "Where is tool T-117?")
    body = model.LOG[-1]["body"]
    assert r["mode"] == "model" and "cache_control" not in body and "fallbacks" not in body
    assert not any("eager_input_streaming" in t for t in body["tools"])
    assert client.get("/api/assistant/health").json()["features"] == {"fallbacks": False, "speed": False, "eager": False, "cache": False, "effort": False}


def test_static_files_do_not_escape_the_build(client):
    import sanad_app
    if not sanad_app.FRONTEND_DIST.exists():
        pytest.skip("the chat is not built")
    for path in ("/%2e%2e/backend/sanad_app.py", "/..%2fbackend%2fsanad_app.py", "/assets/../../backend/sanad_app.py"):
        res = client.get(path)
        assert "FastAPI" not in res.text and "import" not in res.text[:200]


def test_transient_overload_is_retried(client, model):
    model.STATE["fail_next"] = 1
    assert ask(client, "What is the primary risk to ENG-204?")["mode"] == "model"


def test_outage_falls_back_to_the_shop_data(client, model, monkeypatch):
    model.STATE["fail_next"] = 99
    r = ask(client, "What is the primary risk to ENG-204?")
    assert r["mode"] == "direct" and r["answer"].startswith("The primary risk to ENG-204 is component P-4582")
    assert "straight from the shop data" in r["notice"] and r["cards"][0]["id"] == "delivery_risk"


def test_repeated_failures_skip_the_model_for_a_while(client, model, monkeypatch):
    monkeypatch.setattr(engine_mod, "BREAKER_FAILURES", 2)
    model.STATE["fail_next"] = 99
    ask(client, "Where is tool T-117?")
    ask(client, "Where is tool T-117?")
    n = len(model.LOG)
    r = ask(client, "Where is tool T-117?")
    assert len(model.LOG) == n and "recovering" in r["notice"]             # no call was made: nobody waits on a timeout
    assert client.get("/api/assistant/health").json()["degraded"] is True


def test_an_awkward_question_does_not_trip_the_breaker(client, model, monkeypatch):
    monkeypatch.setattr(engine_mod, "BREAKER_FAILURES", 2)
    for _ in range(3):
        r = ask(client, "truncate this")                                   # a per-question failure, not an outage
        assert r["mode"] == "direct"
    r = ask(client, "What is the primary risk to ENG-204?")
    assert r["mode"] == "model" and client.get("/api/assistant/health").json()["degraded"] is False


def test_a_model_that_never_stops_asking_for_tools_is_cut_off(client, model):
    r = ask(client, "loop forever please")
    assert r["mode"] == "direct" and r["answer"] and "Checking again" not in r["answer"]
    assert len([x for x in model.LOG if "loop forever" in str(x["body"]["messages"][-1])[:0] or True]) >= agent.MAX_MODEL_CALLS


def test_saved_state_holds_finished_turns_and_restores(client, model, tmp_path, monkeypatch):
    import json
    ask(client, "Where is tool T-117?", "supervisor")
    ask(client, "Raise a handover request for T-117.", "supervisor")
    snap = engine_mod.ENGINE._snapshot()
    owner = next(iter(snap["owners"].values()))
    assert len(owner["sessions"]) == 2 and owner["records"][0]["id"] == "THR-0001"
    assert all(t["state"] != "running" and "_t0" not in t for s in owner["sessions"] for t in s["turns"])
    path = tmp_path / "state.json"
    monkeypatch.setattr(engine_mod, "STATE_FILE", path)
    monkeypatch.setattr(engine_mod, "PERSIST", True)
    engine_mod._write(snap)
    fresh = engine_mod.Engine()
    oid = next(iter(json.loads(path.read_text())["owners"]))
    assert len(fresh.sessions(oid)) == 2 and fresh.notebook(oid)[0]["id"] == "THR-0001"
    qid = owner["sessions"][0]["turns"][0]["queryId"]
    assert fresh.status(oid, qid)["done"] is True


def test_wrong_key_is_survivable(client, model, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "wrong")
    agent.reset_client()
    r = ask(client, "Where is tool T-117?", "supervisor")
    assert r["mode"] == "direct" and "key was rejected" in r["notice"] and r["answer"].startswith("T-117 is away")


def test_refusal_and_truncation(client, model):
    assert ask(client, "refuse this")["answer"] == "I can't help with that request."
    r = ask(client, "truncate this")
    assert r["mode"] == "direct" and r["answer"]                           # a cut-off tool call is never run


def test_stop(client, model):
    model.STATE["delay"] = 0.05
    sub = client.post("/api/assistant/query", json={"content": "What is the primary risk to ENG-204?"}).json()
    time.sleep(0.4)
    assert client.post(f"/api/assistant/query/{sub['queryId']}/cancel").json()["ok"]
    for _ in range(200):
        st = client.get(f"/api/assistant/query/{sub['queryId']}").json()
        if st["done"]:
            break
        time.sleep(0.02)
    assert st["result"]["state"] == "cancelled" and "Stopped" in st["result"]["notice"]


def test_many_questions_at_once(client, model, monkeypatch):
    monkeypatch.setattr(engine_mod, "MAX_IN_FLIGHT", 100)
    monkeypatch.setattr(engine_mod, "MAX_SESSIONS", 100)
    monkeypatch.setattr(engine_mod, "RATE_PER_MIN", 1000)
    qs = ["Show me the status of all the engines.", "Where is tool T-117?", "Can I start fan blade removal now?", "What is the primary risk to ENG-204?"] * 10
    subs = [client.post("/api/assistant/query", json={"content": q}).json() for q in qs]
    done = {}
    for _ in range(600):
        for s in subs:
            if s["queryId"] not in done:
                st = client.get(f"/api/assistant/query/{s['queryId']}").json()
                if st["done"]:
                    done[s["queryId"]] = st["result"]
        if len(done) == len(subs):
            break
        time.sleep(0.02)
    assert len(done) == 40 and all(r["mode"] == "model" and r["cards"] for r in done.values())
