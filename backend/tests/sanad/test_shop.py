"""The shop itself: the data guard, the schedule, the views, the router and the tools."""
import json

import pytest

from services.sanad import corpus, dataset, ops, router, scenario, tools, views
from services.sanad.records import Notebook

MOMENTS = [m["ts"] for m in scenario.MOMENTS]


def ctx(ts="2026-10-28 09:30", role="manager", nb=None):
    return tools.Context(ops.shop(ts), scenario.persona(role), nb or Notebook())


# ── read-only SQL ────────────────────────────────────────────────────────
@pytest.mark.parametrize("sql", [
    "delete from engines", "update engines set status='x'", "drop table engines", "insert into engines values (1)",
    "pragma table_info(engines)", "attach database ':memory:' as x", "select 1; select 2", "create table t (a)", "",
])
def test_sql_refuses_anything_but_one_select(sql):
    snap = ops.shop().snapshot()
    with pytest.raises(dataset.QueryError):
        snap.run(sql)
    assert snap.run("select count(*) n from engines")["rows"][0]["n"] == 4


def test_sql_sees_only_events_up_to_the_shop_time():
    early = ops.shop("2026-10-28 09:30").snapshot().run("select count(*) n from approvals")["rows"][0]["n"]
    late = ops.shop("2026-10-29 10:00").snapshot().run("select count(*) n from approvals")["rows"][0]["n"]
    assert early == 0 and late == 5
    assert ops.shop("2026-10-28 12:15").snapshot().run("select now_ts() t")["rows"][0]["t"] == "2026-10-28 12:15"


# ── the schedule ─────────────────────────────────────────────────────────
@pytest.mark.parametrize("ts,finish,variance,status", [
    ("2026-10-27 12:00", "2026-11-03 22:00", 4.0, "Watch"),
    ("2026-10-28 09:30", "2026-11-05 06:00", 36.0, "At risk"),
    ("2026-10-28 11:30", "2026-11-03 20:00", 2.0, "Watch"),
    ("2026-10-28 13:30", "2026-11-03 16:00", -2.0, "Back on track"),
    ("2026-10-29 10:00", "2026-11-03 16:30", -1.5, "Back on track"),
])
def test_eng_204_forecast_follows_the_events(ts, finish, variance, status):
    f = ops.shop(ts).engine_status("ENG-204")
    assert (f["predicted_completion_ts"], f["variance_hours"], f["status"]) == (finish, variance, status)


def test_recovery_options_are_scheduled_not_typed():
    opts = {o["option"]: o for o in views.recovery_plan(ops.shop("2026-10-28 09:30"))["data"]["options"]}
    assert opts["A"]["predicted_completion_ts"] == "2026-11-04 10:00" and opts["A"]["cost_usd"] == 300
    assert opts["B"]["predicted_completion_ts"] == "2026-11-03 20:00" and opts["B"]["cost_usd"] == 2400
    assert opts["C"]["predicted_completion_ts"] == "2026-11-05 02:00"


def test_other_engines_do_not_drift_with_the_clock():
    for eid, finish in (("ENG-201", "2026-11-06 09:00"), ("ENG-209", "2026-11-13 15:00"), ("ENG-215", "2026-10-30 16:00")):
        assert {ops.shop(ts).forecast(eid)["predicted_completion_ts"] for ts in MOMENTS} == {finish}


def test_what_if_changes_nothing():
    shop = ops.shop("2026-10-28 11:30")
    before = shop.forecast("ENG-204")["predicted_completion_ts"]
    sim = views.simulate_schedule(shop, part_arrival="2026-11-03 14:00")["data"]
    assert sim["simulated"]["predicted_completion_ts"] > before and sim["change_hours"] == 4.0
    assert shop.forecast("ENG-204")["predicted_completion_ts"] == before


# ── the views ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("ts", MOMENTS + ["2026-10-27 08:00", "2026-11-10 09:00"])
@pytest.mark.parametrize("name", list(views.VIEWS))
def test_every_view_answers_at_every_moment(name, ts):
    args = {"tool_location": {"tool_id": "T-117"}, "approval_authority": {"action": "approve a deviation"}}.get(name, {})
    r = views.run(name, ops.shop(ts), **args)
    assert r["summary"] and isinstance(r["data"], dict)
    json.dumps(r)                                              # everything the screen gets is serialisable
    if r["card"]:
        assert r["card"]["kind"] == "card" and r["card"]["title"]


def test_unknown_ids_are_reported_not_invented():
    shop = ops.shop()
    assert "not in the shop records" in views.engine_status(shop, engine_id="ENG-999")["summary"]
    assert views.tool_location(shop, tool_id="T-999")["card"] is None


def test_video_storyline_facts():
    s = views.tool_location(ops.shop("2026-10-28 09:30"), tool_id="T-117")["data"]
    assert s["custody"]["location"] == "Gate 3" and s["last_camera_sighting"]["ts"] == "2026-10-28 09:12" and s["calibration_due"] == "2027-01-15"
    r = views.task_readiness(ops.shop("2026-10-28 12:15"))["data"]
    assert (r["checks_complete"], r["checks_total"], r["ready_to_start"], r["hours_beyond_shift_end"]) == (3, 6, False, 9.5)
    assert views.task_readiness(ops.shop("2026-10-28 13:30"))["data"]["ready_to_start"] is True
    f = views.inspection_finding(ops.shop("2026-10-28 16:00"))["data"]
    assert [z["status"] for z in f["zones"]] == ["within", "above", "within"] and f["disposition"] is None
    assert views.inspection_finding(ops.shop("2026-10-29 10:00"))["data"]["disposition"]
    assert len(views.task_tools(ops.shop())["data"]["tools"]) == 6


# ── the router ───────────────────────────────────────────────────────────
@pytest.mark.parametrize("question,view", [
    ("Show me the status of all the engines.", "engine_status"), ("What is the primary risk to ENG-204?", "delivery_risk"),
    ("What has changed on ENG-204 since yesterday?", "forecast_changes"), ("Generate a recovery plan for component P-4582.", "recovery_plan"),
    ("Has the recovery option been approved?", "recovery_plan"), ("I need to start the fan blade removal task. Please guide me.", "job_card"),
    ("Can I start fan blade removal now?", "task_readiness"), ("Which tools does this step need?", "task_tools"),
    ("Where is tool T-117?", "tool_location"), ("Is the tool still at Gate 3?", "tool_location"),
    ("Can I approve a deviation so the work can continue?", "approval_authority"),
    ("What is now the best way to protect the committed delivery date?", "protect_delivery"),
    ("Show me the updated engine status and recovery progress.", "engine_status"),
    ("how is engine 209 doing", "engine_status"), ("why is 204 late", "delivery_risk"),
    ("What if P-4582 arrives four hours later than promised?", None), ("Raise a handover request for T-117.", None),
    ("hello", None), ("what's the weather in Abu Dhabi", None),
    ("What does the tool control procedure say about camera detections?", None),
])
def test_router_picks_the_view(question, view):
    got = router.match(question, ops.shop("2026-10-28 12:15"), scenario.persona("manager"))
    assert (got[0]["view"] if got else None) == view


def test_router_carries_the_subject_from_earlier_turns():
    got = router.match("is it still there?", ops.shop(), scenario.persona("supervisor"), history=["Where is tool T-063?"])
    assert got == [] or got[0]["args"].get("tool_id") in (None, "T-063")
    got = router.match("where is it now?", ops.shop(), scenario.persona("supervisor"), history=["Tell me about tool T-063"])
    assert got and got[0]["args"]["tool_id"] == "T-063"


# ── documents ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("query,doc", [
    ("is a camera detection a confirmed handover", "TC-003"), ("who can approve a deviation", "QP-014"),
    ("leading edge scratch limit zone B", "ISM-72"), ("what can the digital assistant not do", "DA-001"),
])
def test_document_search_finds_the_right_document(query, doc):
    assert corpus.search(query)[0]["doc_id"].startswith(doc)


# ── tools and their role rules ───────────────────────────────────────────
def test_tool_inputs_are_validated():
    c = ctx()
    for name, args in (("tool_location", {}), ("nope", {}), ("confirm_job_step", {"step_no": "first"}), ("submit_recovery_option", {"option": "Z"}),
                       ("run_sql", {"sql": "drop table engines"}), ("render_chart", {"title": "t", "type": "bar", "sql": "select engine_id, status from engine_status", "x": "engine_id", "y": ["status"]})):
        result, is_error = tools.execute(name, args, c)
        assert is_error and result["error"], name
    assert not c.created


def test_actions_create_pending_records_and_nothing_else():
    c = ctx("2026-10-28 09:30", "supervisor")
    before = c.shop.tool_state("T-117")["location"]
    result, is_error = tools.execute("raise_tool_request", {"tool_id": "t-117"}, c)
    assert not is_error and result["status"] == "raised" and result["record"]["status"].startswith("Pending")
    assert c.shop.tool_state("T-117")["location"] == before            # a request moves nothing
    assert tools.execute("raise_tool_request", {"tool_id": "T-117"}, c)[0]["status"] == "already_raised"
    assert tools.execute("raise_tool_request", {"tool_id": "T-208"}, c)[1]             # already at the gate
    assert len(c.notebook.items) == 1


@pytest.mark.parametrize("role,tool,args,allowed", [
    ("manager", "draft_finding", {"component": "Fan 1 blade", "description": "scratch"}, False),
    ("supervisor", "confirm_job_step", {"step_no": 1}, False),
    ("technician", "submit_recovery_option", {"option": "B"}, False),
    ("supervisor", "submit_recovery_option", {"option": "B"}, False),
    ("supervisor", "submit_recovery_option", {"option": "C"}, True),
    ("manager", "submit_recovery_option", {"option": "B"}, True),
    ("technician", "draft_finding", {"component": "Fan 1 blade", "description": "scratch", "zone": "B", "measured_mm": 0.8}, True),
])
def test_role_rules_are_enforced_in_code(role, tool, args, allowed):
    c = ctx("2026-10-28 09:30", role)
    result, is_error = tools.execute(tool, args, c)
    assert is_error is (not allowed), result
    assert bool(c.created) is allowed


def test_steps_only_after_release_and_in_order():
    nb = Notebook()
    assert tools.execute("confirm_job_step", {"step_no": 1}, ctx("2026-10-28 12:15", "technician", nb))[1]      # not released yet
    c = ctx("2026-10-28 13:30", "technician", nb)
    assert tools.execute("confirm_job_step", {"step_no": 2}, c)[1]                                             # out of order
    assert tools.execute("confirm_job_step", {"step_no": 1}, c)[0]["status"] == "confirmed"
    assert tools.execute("confirm_job_step", {"step_no": 2}, c)[0]["next_step"]["step_no"] == 3


def test_deviation_package_needs_a_recorded_finding_and_never_approves():
    assert tools.execute("prepare_deviation_package", {}, ctx("2026-10-28 09:30", "supervisor"))[1]
    result, is_error = tools.execute("prepare_deviation_package", {}, ctx("2026-10-28 16:00", "supervisor"))
    assert not is_error and result["status"] == "routed" and "pending" in result["record"]["status"].lower()
    assert "Nothing is approved" in result["note"]


# ── what people read ─────────────────────────────────────────────────────
def _every_text(value, out):
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for k, v in value.items():
            if k not in ("kind", "id", "type", "icon", "tone", "state", "zone", "status"):
                _every_text(v, out)
    elif isinstance(value, list):
        for v in value:
            _every_text(v, out)


def _allowed_times():
    from datetime import timedelta
    t, end = ops.parse(scenario.CLOCK_MIN), ops.parse(scenario.CLOCK_MAX)
    while t <= end:
        yield ops.stamp(t)
        t += timedelta(minutes=95)
    yield scenario.CLOCK_MAX


BAD_WORDING = [
    r"\bit is watch\b", r"\b[Aa]n anyone\b", r"\bA shop roles\b", r" on , ", r"\b0 of 0\b", r"\b0 steps\b", r"  ", r" ,", r"\(\)", r"\bwould give\b",
    r"\ban overtime\b", r"\brs-\d", r"\bgate \d", r"\btask:[A-Z]", r"\bpart:P", r"\bNone\b(?! (is|yet|added))", r"\bnan\b", r"\{|\}", r"\bis authorised \d",
    r"sets the finish date, so", r"still sets the finish", r"\bIf no \w+,", r"\([^()]*\([^()]*\)[^()]*\)",
]
VARIANTS = {
    "engine_status": [{}, {"engine_id": "ENG-204"}, {"engine_id": "ENG-215"}], "delivery_risk": [{}, {"engine_id": "ENG-201"}], "forecast_changes": [{}],
    "recovery_plan": [{}, {"engine_id": "ENG-209"}], "protect_delivery": [{}], "job_card": [{}, {"job_card": "JC-FAN-231"}], "task_readiness": [{}],
    "task_tools": [{}], "tool_location": [{"tool_id": t} for t in ("T-117", "T-063", "T-208", "T-615", "K-014")], "inspection_finding": [{}],
    "approval_authority": [{"action": a} for a in ("approve a deviation", "accept the finding", "certify the work", "release the engine", "release the work",
                                                   "authorise overtime", "expedite spend", "stock transfer", "re-sequence work", "tool handover", "anything")],
    "simulate_schedule": [{"part_arrival": "2026-11-03 14:00"}, {"overtime": False}, {"resequence": False, "disposition": True}, {}],
}


def test_every_answer_in_the_allowed_period_reads_properly():
    import re
    faults = []
    for ts in _allowed_times():
        shop = ops.shop(ts)
        for name, sets in VARIANTS.items():
            for args in sets:
                r = views.run(name, shop, **args)
                texts = [r["summary"]]
                _every_text(r["card"], texts)
                for text in texts:
                    for pattern in BAD_WORDING:
                        if text in ("None", "None yet", "None added"):       # a tile that honestly says there is none
                            continue
                        if re.search(pattern, text):
                            faults.append(f"{name} @ {ts}: /{pattern}/ in: {text[:140]}")
                    if text and text == r["summary"]:
                        assert text[0].isupper() or text[0].isdigit(), text[:60]
                        assert text.rstrip().endswith("."), f"{name} @ {ts}: summary does not end with a full stop: ...{text[-60:]}"
    assert not faults, "\n".join(sorted(set(faults))[:25])


def test_nothing_drifts_for_want_of_data_inside_the_allowed_period():
    """Inside the period a person may choose, no forecast is in the past and ENG-204 is never later than the slip made it."""
    for ts in _allowed_times():
        shop = ops.shop(ts)
        for eid in shop.engine_ids():
            f = shop.forecast(eid)
            assert f["predicted_completion_ts"] > ts, (eid, ts, f["predicted_completion_ts"])
        assert shop.forecast("ENG-204")["variance_hours"] <= 36.0, ts
        assert all(shop.forecast(e)["variance_hours"] <= 0 for e in ("ENG-201", "ENG-209", "ENG-215")), ts


def test_the_story_moments_sit_inside_the_allowed_period():
    assert all(scenario.CLOCK_MIN <= m["ts"] <= scenario.CLOCK_MAX for m in scenario.MOMENTS)
    assert scenario.public()["clock"] == {"min": "2026-10-27 16:00", "max": "2026-10-30 12:00", "minNice": "27 Oct 16:00", "maxNice": "30 Oct 12:00"}
