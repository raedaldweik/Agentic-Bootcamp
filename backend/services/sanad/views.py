"""The standard views of the shop: each one answers a kind of question.

A view takes the shop as of a moment and returns
    data       the facts, compact, for the agent to reason over
    summary    the same facts as two or three plain sentences
    card       a visual card the chat renders (tiles, tables, flows, checklists ...)
    followups  natural next questions
    sources    the documents the answer rests on
Every figure comes from the shop state or the schedule; nothing is typed in here.
The views are what the agent reaches for first, and what answers on their own when
no language model is connected.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable

from . import ops
from .ops import Shop, nice, parse, stamp, hours_text, lc_first, uc_first

ASSISTANT_LIMITS = ("The Sanad Digital Assistant cannot approve deviations, certify work, accept findings "
                    "or release an engine. It can prepare the evidence and route it to the authorised role.")


# ─── Small helpers ───────────────────────────────────────────────────────
_STATUS_PHRASE = {"At risk": "at risk", "Watch": "on watch", "On track": "on track", "Back on track": "back on track"}


def _flat(text: str) -> str:
    """'approved (2 technicians)' -> 'approved, 2 technicians', so the phrase can sit inside brackets."""
    return re.sub(r"\s*\(([^()]*)\)", r", \1", text)


def _by(approver: str) -> str:
    """An approving role as it reads after 'by': 'the Supervisor', 'procurement and logistics'."""
    return "the " + approver if approver in ("Supervisor", "Engine Shop Manager") else lc_first(approver)


def _held(held_by: str | None, tasks: list[dict]) -> str:
    """What a task waits for, in words: 'task:FBR' -> 'After fan blade removal and inspection'."""
    kind, _, ref = (held_by or "plan").partition(":")
    if kind == "task":
        name = next((t["task"].split(":")[0] for t in tasks if t.get("task_id") == ref), ref)
        return f"After {lc_first(name)}"
    return {"part": f"Arrival of {ref}", "tool": f"Tool {ref} at the gate", "release": f"Work release of {ref}",
            "now": "The current shop time", "plan": "The plan"}.get(kind, held_by or "The plan")


def _tone(status: str) -> str:
    return {"On track": "good", "Back on track": "good", "Watch": "warn", "At risk": "bad"}.get(status, "info")


def _late(variance: float) -> str:
    if variance > 0:
        return f"{hours_text(variance)} late"
    if variance < 0:
        return f"{hours_text(variance)} ahead"
    return "on commitment"


def _due(eng: dict) -> str:
    return f"{eng['committed_tat_days']} days, due {nice(parse(eng['committed_completion_ts']))}"


def _usd(v: Any) -> str:
    try:
        n = float(v)
    except (TypeError, ValueError):
        return "No additional cost"
    return f"USD {n:,.0f}" if n else "No additional cost"


def _focus_engine(shop: Shop, engine_id: str | None) -> str:
    """The engine asked about, else the one furthest behind its commitment."""
    if engine_id and shop.engine(engine_id):
        return engine_id.upper()
    return max(shop.engine_ids(), key=lambda e: shop.forecast(e)["variance_hours"])


def _window(shop: Shop, engine_id: str) -> dict | None:
    return next((b for b in shop.rows("bay_slots", engine_id=engine_id) if "window" in b["activity"].lower()), None)


def _card(card_id: str, title: str, **kw: Any) -> dict:
    return {"kind": "card", "id": card_id, "title": title, **{k: v for k, v in kw.items() if v}}


def _not_found(view: str, what: str, known: list[str]) -> dict:
    return {"view": view, "data": {"error": f"{what} is not in the shop records.", "known": known},
            "summary": f"{what} is not in the shop records. Known: {', '.join(known)}.", "card": None,
            "followups": [], "sources": []}


# ─── 1. Engine status ────────────────────────────────────────────────────
def engine_status(shop: Shop, engine_id: str | None = None, **_: Any) -> dict:
    if engine_id and not shop.engine(engine_id):
        return _not_found("engine_status", f"Engine {engine_id}", shop.engine_ids())
    engines = [shop.engine_status(e) for e in shop.engine_ids()]
    green = [e for e in engines if e["status"] in ("On track", "Back on track")]
    off = [e for e in engines if e not in green]
    focus_id = _focus_engine(shop, engine_id)
    focus = next(e for e in engines if e["engine_id"] == focus_id)
    nxt = min(engines, key=lambda e: e["predicted_completion_ts"])
    recovery = recovery_actions(shop, focus_id)

    tiles = [
        {"label": "Engines in shop", "value": str(len(engines)), "icon": "engine", "tone": "info"},
        {"label": "On track", "value": f"{len(green)} of {len(engines)}", "icon": "check", "tone": "good" if not off else "warn"},
        ({"label": off[0]["status"], "value": ", ".join(e["engine_id"] for e in off), "icon": "alert", "tone": _tone(off[0]["status"])}
         if off else {"label": "At risk", "value": "None", "icon": "check", "tone": "good"}),
        {"label": "Next release", "value": nice(parse(nxt["predicted_completion_ts"]), with_year=False), "sub": nxt["engine_id"], "icon": "calendar", "tone": "info"},
    ]
    table = {"type": "table", "columns": ["Engine", "Status", "Committed TAT", "Predicted completion"],
             "rows": [[e["engine_id"], {"text": e["status"], "tone": _tone(e["status"])}, _due(e),
                       f"{nice(parse(e['predicted_completion_ts']))} ({_late(e['variance_hours'])})"] for e in engines],
             "highlight": [i for i, e in enumerate(engines) if e["engine_id"] == focus_id and (off or engine_id)]}
    reason = focus["driver"] if focus["variance_hours"] > 0 else "Forecast is inside the commitment"
    detail = {"type": "detail", "title": f"{focus['engine_id']} · {focus['engine_type']} · {focus['esn']}",
              "banner": {"tone": _tone(focus["status"]), "text": f"{focus['status']} · {reason}"},
              "items": [{"label": "Workstation", "value": focus["workstation"]},
                        {"label": "Repair stage", "value": focus["repair_stage"]},
                        {"label": "Current process", "value": focus["current_process"]},
                        {"label": "Committed TAT", "value": _due(focus)},
                        {"label": "Expected completion", "value": f"{nice(parse(focus['predicted_completion_ts']))} ({_late(focus['variance_hours'])})",
                         "tone": _tone(focus["status"])}],
              "progress": {"label": "Hours completed", "value": focus["hours_completed"], "max": focus["planned_hours"], "unit": "h",
                           "tone": _tone(focus["status"])}}
    blocks: list[dict] = [table, detail]
    if recovery:
        blocks.insert(0, {"type": "flow", "title": "Recovery actions", "items": recovery})

    if off:
        o = off[0]
        summary = (f"{o['engine_id']} needs attention: it is {_STATUS_PHRASE.get(o['status'], lc_first(o['status']))}, predicted {nice(parse(o['predicted_completion_ts']))}, "
                   f"{_late(o['variance_hours'])} against a commitment of {nice(parse(o['committed_completion_ts']))}. {o['driver']}. "
                   f"The other {len(green)} engines are on track; next release is {nxt['engine_id']} on {nice(parse(nxt['predicted_completion_ts']))}.")
    else:
        back = [e for e in engines if e["status"] == "Back on track"]
        lead = (f"{back[0]['engine_id']} is back in line with its commitment: predicted {nice(parse(back[0]['predicted_completion_ts']))}, "
                f"{_late(back[0]['variance_hours'])}. " if back else "")
        summary = f"{lead}All {len(engines)} engines are on track. Next release: {nxt['engine_id']} on {nice(parse(nxt['predicted_completion_ts']))}."
        if recovery:
            summary += " Recovery actions in force: " + "; ".join(f"{r['label']} ({_flat(lc_first(r['sub']))})" for r in recovery) + "."
    data = {"shop_time": shop.now,
            "engines": [{k: e[k] for k in ("engine_id", "engine_type", "esn", "customer", "workscope", "status", "committed_tat_days",
                                           "committed_completion_ts", "predicted_completion_ts", "variance_hours", "driver",
                                           "workstation", "repair_stage", "current_process", "hours_completed", "planned_hours")}
                        for e in engines],
            "focus_engine": focus_id, "recovery_actions": recovery}
    f = focus_id
    followups = ([f"What is the primary risk to {f}?", f"What has changed on {f} since yesterday?", f"Generate a recovery plan for {f}."]
                 if off else [f"What could still put {f} at risk?", f"What has changed on {f} since yesterday?", "Which engine is released next?"])
    title = "Engine status" if not engine_id else f"{focus_id} status"
    return {"view": "engine_status", "data": data, "summary": summary,
            "card": _card("engine_status", title, subtitle=f"Shop time {nice(shop.clock)}", tiles=tiles, blocks=blocks),
            "followups": followups, "sources": ["Shop Performance Standard SPS-2026"]}


def recovery_actions(shop: Shop, engine_id: str) -> list[dict]:
    """What has been done to recover an engine, as flow items."""
    out: list[dict] = []
    for a in shop.approvals(engine_id, "expedite"):
        sup = next((shop.part_supply(p["part_id"], engine_id) for p in shop.t["purchase_orders"] if p["engine_id"] == engine_id), None)
        part = sup["part_id"] if sup else "part"
        in_transit = bool(sup and sup["status"].lower().startswith("shipped"))
        out.append({"label": f"Expedite {part}", "sub": "Approved, in transit" if in_transit else "Approved", "state": "done", "icon": "plane"})
    for task in shop.rows("schedule_tasks", engine_id=engine_id):
        for need in (task["needs"] or "").split(";"):
            if need.startswith("tool:"):
                st = shop.tool_state(need[5:])
                gate = shop.engine(engine_id)["workstation"].split(",")[0]
                moved = any(e["event"] == "Handover signed" for e in st["events"])
                if moved and st["checked_in"] and st["location"].startswith(gate):
                    out.append({"label": f"Tool {st['tool_id']}", "sub": f"Transferred and checked in ({gate})", "state": "done", "icon": "wrench"})
    for a in shop.approvals(engine_id, "overtime"):
        out.append({"label": "Overtime", "sub": "Approved (2 technicians)", "state": "done", "icon": "users"})
    for a in shop.approvals(engine_id, "resequence"):
        out.append({"label": "Re-sequenced work", "sub": "Authorised by the supervisor", "state": "done", "icon": "route"})
    if out:
        fc = shop.forecast(engine_id)
        cur = next((t for t in fc["tasks"] if t["state"] == "in progress"), None) or next((t for t in fc["tasks"] if t["state"] == "planned"), None)
        if cur:
            out.append({"label": cur["task"].split(":")[0], "sub": "In progress" if cur["state"] == "in progress" else f"Next, from {nice(parse(cur['start_ts']), with_year=False)}",
                        "state": "current", "icon": "fan"})
    return out


# ─── 2. Delivery risk ────────────────────────────────────────────────────
def delivery_risk(shop: Shop, engine_id: str | None = None, **_: Any) -> dict:
    if engine_id and not shop.engine(engine_id):
        return _not_found("delivery_risk", f"Engine {engine_id}", shop.engine_ids())
    eid = _focus_engine(shop, engine_id)
    eng, fc = shop.engine(eid), shop.forecast(eid)
    drv = fc["driver"] or {}
    committed, predicted = parse(fc["committed_completion_ts"]), parse(fc["predicted_completion_ts"])
    win = _window(shop, eid)
    late = fc["variance_hours"] > 0
    data: dict[str, Any] = {"shop_time": shop.now, "engine_id": eid, "status": fc["status"],
                            "committed_completion_ts": fc["committed_completion_ts"], "predicted_completion_ts": fc["predicted_completion_ts"],
                            "variance_hours": fc["variance_hours"], "driver": drv,
                            "critical_path": [{k: t[k] for k in ("task", "start_ts", "end_ts", "state", "held_by")} for t in fc["tasks"]]}
    tiles = [{"label": "Engine", "value": eid, "sub": fc["status"], "icon": "alert" if late else "check", "tone": _tone(fc["status"])}]
    blocks: list[dict] = []
    levers: list[dict] = []
    sources = ["Shop Performance Standard SPS-2026"]

    if drv.get("kind") == "part":
        sup = shop.part_supply(drv["ref"], eid) or {}
        arrival = parse(sup.get("promised_arrival_ts"))
        tiles.append({"label": "Primary risk" if late else "Sets the finish date", "value": f"Component {drv['ref']}", "sub": drv.get("description", ""), "icon": "gear", "tone": "bad" if late else "info"})
        tiles.append({"label": "Part arrival", "value": nice(arrival), "sub": sup.get("status", ""), "icon": "calendar", "tone": "info"})
        data["part"] = {"part_id": drv["ref"], "description": drv.get("description"), "po_id": sup.get("po_id"), "supplier": sup.get("supplier"),
                        "promised_arrival_ts": sup.get("promised_arrival_ts"), "po_status": sup.get("status"), "po_note": sup.get("note")}
        if win:
            closes = parse(win["window_end"])
            inside = bool(arrival and arrival <= closes)
            tiles.append({"label": "Installation window closes", "value": nice(closes), "sub": "Arrival inside the window" if inside else "Arrival after the window",
                          "icon": "clock", "tone": "good" if inside else "bad"})
            data["installation_window"] = {"closes_ts": win["window_end"], "arrival_inside_window": inside, "workstation": win["workstation"]}
        levers = _levers(shop, eid)
        data["recovery_levers"] = levers
        sources.append("Recovery Planning Procedure RP-011")
    elif drv.get("kind") == "tool":
        st = shop.tool_state(drv["ref"])
        tiles.append({"label": "Primary risk" if late else "Sets the finish date", "value": f"Tool {drv['ref']}", "sub": st["tool"], "icon": "wrench", "tone": "bad" if late else "info"})
        tiles.append({"label": "Tool location", "value": st["location"], "sub": st["custody_event"], "icon": "pin", "tone": "info"})
        data["tool"] = {"tool_id": drv["ref"], "location": st["location"], "expected_available_ts": st["expected_available_ts"]}
        sources.append("Tool Control Procedure TC-003")

    path = [t for t in fc["tasks"] if t["state"] != "done"][-3:]
    blocks.append({"type": "flow", "title": "Critical path", "items": [
        {"label": t["task"].split(":")[0], "sub": f"to {nice(parse(t['end_ts']), with_year=False)}",
         "state": "risk" if late and t["held_by"] == f"{drv.get('kind')}:{drv.get('ref')}" else "pending"} for t in path]})
    blocks.append({"type": "compare", "items": [
        {"label": "Committed completion", "value": nice(committed), "tone": "info"},
        {"label": "Current forecast", "value": nice(predicted), "tone": _tone(fc["status"])}],
        "delta": {"text": _late(fc["variance_hours"]), "tone": _tone(fc["status"])}})
    if late and levers:
        blocks.append({"type": "options", "title": "Recovery actions", "items": [
            {"title": lv["title"], "text": lv["text"], "icon": lv["icon"]} for lv in levers]})

    if late:
        part_bit = ""
        if drv.get("kind") == "part":
            p = data["part"]
            part_bit = f" Current delivery information places its arrival on {nice(parse(p['promised_arrival_ts']))}"
            if win:
                part_bit += (", inside" if data["installation_window"]["arrival_inside_window"] else ", after") + f" the installation window that closes on {nice(parse(win['window_end']))}"
            part_bit += f". It is {drv['text'].split(' and is ')[-1]}, so it sits on the critical path."
        lever_bit = (" Recovery actions to evaluate: " + "; ".join(lc_first(lv["title"]) for lv in levers) + ". Each needs its own approval.") if levers else ""
        summary = (f"The primary risk to {eid} is {'component' if drv.get('kind') == 'part' else drv.get('kind', 'the plan')} {drv.get('ref', '')}."
                   f"{part_bit} The forecast is {nice(predicted)}, {_late(fc['variance_hours'])} against {nice(committed)}.{lever_bit}")
    else:
        buffer = -fc["variance_hours"]
        summary = (f"{eid} carries no delivery risk right now: it is predicted for {nice(predicted)}, {hours_text(buffer)} ahead of its commitment of {nice(committed)}. "
                   f"{drv.get('text', 'The planned sequence sets the finish')}. A slip there of more than {hours_text(buffer)} would breach the commitment.")
        data["buffer_hours"] = buffer
    followups = ([f"Generate a recovery plan for {drv['ref'] if drv.get('kind') == 'part' else eid}.", f"What has changed on {eid} since yesterday?", "Has the recovery option been approved?"]
                 if late else [f"What if {drv.get('ref', 'the part')} arrives four hours late?", f"Show me the recovery progress on {eid}.", "Show me the status of all the engines."])
    return {"view": "delivery_risk", "data": data, "summary": summary,
            "card": _card("delivery_risk", f"{eid} delivery risk", subtitle=f"Shop time {nice(shop.clock)}", tiles=tiles, blocks=blocks),
            "followups": followups, "sources": sources}


def _levers(shop: Shop, engine_id: str) -> list[dict]:
    """The recovery levers that exist for this engine's critical part, from the records."""
    fc = shop.forecast(engine_id)
    drv = fc["driver"] or {}
    out: list[dict] = []
    if drv.get("kind") != "part":
        return out
    part = drv["ref"]
    if any(i["on_hand"] and i["ready_at_gate_ts"] for i in shop.rows("inventory", part_id=part)):
        out.append({"title": "Check alternate stock", "text": "Identify an available unit from inventory", "icon": "box", "approval": "Inventory and configuration confirmation"})
    sup = shop.part_supply(part, engine_id)
    if sup and shop.rows("supplier_quotes", po_id=sup["po_id"]):
        out.append({"title": "Expedite shipment", "text": f"Accelerate supplier delivery of {part}", "icon": "plane", "approval": "Procurement and logistics"})
    if any(float(t["resequence_saving_h"] or 0) > 0 for t in shop.rows("schedule_tasks", engine_id=engine_id)):
        out.append({"title": "Re-sequence work", "text": "Adjust permitted tasks while the part is in transit", "icon": "route", "approval": "Supervisor"})
    return out


# ─── 3. What changed ─────────────────────────────────────────────────────
def forecast_changes(shop: Shop, engine_id: str | None = None, since: str | None = None, **_: Any) -> dict:
    if engine_id and not shop.engine(engine_id):
        return _not_found("forecast_changes", f"Engine {engine_id}", shop.engine_ids())
    eid = _focus_engine(shop, engine_id)
    since_dt = parse(since) or (shop.clock - timedelta(days=1))
    before = ops.shop(since_dt).forecast(eid)
    now = shop.forecast(eid)
    moves = [h for h in shop.forecast_history(eid) if stamp(since_dt) < h["ts"] <= shop.now]
    data = {"shop_time": shop.now, "engine_id": eid, "since_ts": stamp(since_dt),
            "then": {k: before[k] for k in ("predicted_completion_ts", "variance_hours", "status")},
            "now": {k: now[k] for k in ("predicted_completion_ts", "variance_hours", "status")},
            "committed_completion_ts": now["committed_completion_ts"], "changes": moves}
    changed = before["predicted_completion_ts"] != now["predicted_completion_ts"]
    if changed:
        why = " ".join(f"At {nice(parse(m['ts']), with_year=False)} the forecast recalculated to {nice(parse(m['predicted_completion_ts']), with_year=False)} "
                       f"({_late(m['variance_hours'])}) because of {m['why']}." for m in moves)
        summary = (f"At {nice(since_dt)} the predicted completion of {eid} was {nice(parse(before['predicted_completion_ts']))}, {_late(before['variance_hours'])}. "
                   f"It is now {nice(parse(now['predicted_completion_ts']))}, {_late(now['variance_hours'])}. {why}")
    else:
        summary = (f"Nothing has moved the forecast of {eid} since {nice(since_dt)}: it is still {nice(parse(now['predicted_completion_ts']))}, {_late(now['variance_hours'])}.")
    blocks = [{"type": "compare", "items": [
        {"label": f"Forecast at {nice(since_dt, with_year=False)}", "value": nice(parse(before['predicted_completion_ts'])), "sub": _late(before["variance_hours"]), "tone": _tone(before["status"])},
        {"label": "Forecast now", "value": nice(parse(now['predicted_completion_ts'])), "sub": _late(now["variance_hours"]), "tone": _tone(now["status"])}],
        "delta": {"text": f"Commitment {nice(parse(now['committed_completion_ts']))}", "tone": "info"}}]
    if moves:
        blocks.append({"type": "timeline", "title": "What moved the forecast", "items": [
            {"label": nice(parse(m["ts"]), with_year=False), "sub": f"{m['why']} → {nice(parse(m['predicted_completion_ts']), with_year=False)} ({_late(m['variance_hours'])})",
             "state": "risk" if m["variance_hours"] > ops.WATCH_HOURS else "done"} for m in moves]})
    return {"view": "forecast_changes", "data": data, "summary": summary,
            "card": _card("forecast_changes", f"{eid}: what changed", subtitle=f"Since {nice(since_dt)}", blocks=blocks),
            "followups": [f"What is the primary risk to {eid}?", f"Generate a recovery plan for {eid}.", "Show me the status of all the engines."],
            "sources": ["Shop Performance Standard SPS-2026"]}


# ─── 4. Recovery plan ────────────────────────────────────────────────────
def recovery_options(shop: Shop, engine_id: str) -> list[dict]:
    """Options A, B and C for the engine's critical part, each scheduled forward to a finish date.
    Each option is measured from the unrecovered position, so the table reads the same before and after a decision."""
    fc = shop.forecast(engine_id)
    part = next((n.split(":")[1] for t in shop.rows("schedule_tasks", engine_id=engine_id) for n in (t["needs"] or "").split(";") if n.startswith("part:")), None)
    if not part:
        return []
    sup = shop.part_supply(part, engine_id)
    if not sup:
        return []
    base_arrival = parse(sup["unrecovered_arrival_ts"])
    out: list[dict] = []

    def run(**w: Any) -> dict:
        return shop.forecast(engine_id, **{"resequence": False, "part_arrival": {part: base_arrival}, **w})

    for inv in shop.rows("inventory", part_id=part):
        if inv["on_hand"] and inv["ready_at_gate_ts"]:
            f = run(part_arrival={part: parse(inv["ready_at_gate_ts"])})
            out.append({"option": "A", "kind": "alternate_stock", "title": "Alternate stock",
                        "action": f"Authorised stock transfer of one unit from {inv['location']}; at the gate from {nice(parse(inv['ready_at_gate_ts']))} after configuration confirmation",
                        "predicted_completion_ts": f["predicted_completion_ts"], "variance_hours": f["variance_hours"],
                        "cost_usd": inv["transfer_cost_usd"] or 0, "cost_note": "transfer", "approval_required": inv["approval_required"],
                        "status": "Available, not selected"})
            break
    for q in shop.rows("supplier_quotes", po_id=sup["po_id"]):
        f = run(part_arrival={part: parse(q["arrival_ts"])})
        ap = next((a for a in shop.approvals(engine_id, "expedite") if a["ref"] == q["quote_ref"]), None)
        out.append({"option": "B", "kind": "expedite", "title": "Supplier expedite",
                    "action": f"Expedite the supplier shipment ({q['option'].lower()}, {q['quote_ref']}); arrival {nice(parse(q['arrival_ts']))}",
                    "predicted_completion_ts": f["predicted_completion_ts"], "variance_hours": f["variance_hours"],
                    "cost_usd": q["fee_usd"], "cost_note": "expedite fee", "approval_required": "Procurement and logistics",
                    "status": f"Approved {nice(parse(ap['ts']))} ({ap['ref']})" if ap else f"Quoted, valid until {nice(parse(q['valid_until']))}",
                    "approved": bool(ap), "approval": ap})
    if any(float(t["resequence_saving_h"] or 0) > 0 for t in shop.rows("schedule_tasks", engine_id=engine_id)):
        f = run(resequence=True)
        ap = next(iter(shop.approvals(engine_id, "resequence")), None)
        out.append({"option": "C", "kind": "resequence", "title": "Re-sequence work",
                    "action": "Re-sequence permitted preparatory work while the part is in transit",
                    "predicted_completion_ts": f["predicted_completion_ts"], "variance_hours": f["variance_hours"],
                    "cost_usd": 0, "cost_note": "", "approval_required": "Supervisor",
                    "status": f"Authorised {nice(parse(ap['ts']))} ({ap['ref']})" if ap else "Available as a fallback, with supervisor authorisation",
                    "approved": bool(ap), "approval": ap})
    return out


def recovery_plan(shop: Shop, engine_id: str | None = None, **_: Any) -> dict:
    if engine_id and not shop.engine(engine_id):
        return _not_found("recovery_plan", f"Engine {engine_id}", shop.engine_ids())
    eid = _focus_engine(shop, engine_id)
    fc = shop.forecast(eid)
    opts = recovery_options(shop, eid)
    win = _window(shop, eid)
    committed = parse(fc["committed_completion_ts"])
    part = next((n.split(":")[1] for t in shop.rows("schedule_tasks", engine_id=eid) for n in (t["needs"] or "").split(";") if n.startswith("part:")), None)
    if not opts:
        return {"view": "recovery_plan", "data": {"engine_id": eid, "options": []},
                "summary": f"No recovery options are recorded for {eid}: it has no critical part with alternate stock, an expedite quotation or re-sequencable work.",
                "card": None, "followups": ["Show me the status of all the engines."], "sources": ["Recovery Planning Procedure RP-011"]}
    sup = shop.part_supply(part, eid) or {}
    approved = [o for o in opts if o.get("approved")]
    best = min(opts, key=lambda o: o["predicted_completion_ts"])
    cheapest = min((o for o in opts if o["cost_usd"]), key=lambda o: o["cost_usd"], default=None)
    data = {"shop_time": shop.now, "engine_id": eid, "component": part, "committed_completion_ts": fc["committed_completion_ts"],
            "current_forecast_ts": fc["predicted_completion_ts"], "current_variance_hours": fc["variance_hours"],
            "installation_window_closes_ts": win["window_end"] if win else None,
            "options": [{k: o[k] for k in ("option", "title", "action", "predicted_completion_ts", "variance_hours", "cost_usd", "approval_required", "status")} for o in opts],
            "approved": [{"option": o["option"], "ref": o["approval"]["ref"], "ts": o["approval"]["ts"], "decided_by": o["approval"]["decided_by"],
                          "work_order": o["approval"]["work_order"], "amount_usd": o["approval"]["amount_usd"]} for o in approved],
            "supply": {"po_id": sup.get("po_id"), "status": sup.get("status"), "promised_arrival_ts": sup.get("promised_arrival_ts"), "deliver_to": sup.get("deliver_to")},
            "note": "Options combine: re-sequencing (C) can run alongside A or B."}
    tiles = [{"label": "Options available", "value": str(len(opts)), "icon": "layers", "tone": "info"},
             {"label": "Lowest cost", "value": _usd(cheapest["cost_usd"]) if cheapest else "No cost", "sub": f"Option {cheapest['option']}" if cheapest else "", "icon": "coins", "tone": "good"},
             {"label": "Earliest finish", "value": nice(parse(best["predicted_completion_ts"]), with_year=False), "sub": f"Option {best['option']}, {_late(best['variance_hours'])}", "icon": "calendar", "tone": "info"}]
    if win:
        tiles.append({"label": "Window closes", "value": nice(parse(win["window_end"]), with_year=False), "icon": "clock", "tone": "warn"})
    blocks: list[dict] = [{"type": "table", "columns": ["Option", "Action", "Predicted completion", "Cost", "Approval required", "Status"],
                           "rows": [[o["option"], o["action"], f"{nice(parse(o['predicted_completion_ts']))} ({_late(o['variance_hours'])})",
                                     _usd(o["cost_usd"]) + (f" {o['cost_note']}" if o["cost_usd"] else ""), o["approval_required"],
                                     {"text": o["status"], "tone": "good" if o.get("approved") else "info"}] for o in opts],
                           "highlight": [i for i, o in enumerate(opts) if o.get("approved")] or [opts.index(best)]}]
    if approved:
        b = next((o for o in approved if o["kind"] == "expedite"), approved[0])
        ap = b["approval"]
        items = [{"label": sup.get("po_id", "Order"), "sub": "Updated", "state": "done"},
                 {"label": "Approved", "sub": nice(parse(ap["ts"]), with_year=False), "state": "done"},
                 {"label": "In transit" if sup.get("status", "").lower().startswith("shipped") else "Awaiting dispatch", "sub": part,
                  "state": "current"},
                 {"label": "Arrives", "sub": nice(parse(sup.get("promised_arrival_ts")), with_year=False), "state": "pending"}]
        if win:
            items.append({"label": "Installation window", "sub": f"Closes {nice(parse(win['window_end']), with_year=False)}", "state": "pending"})
        blocks.append({"type": "timeline", "title": "Approved recovery", "items": items})
        blocks.append({"type": "keyvalues", "title": "Approval record", "items": [
            {"label": "Chosen option", "value": f"Option {b['option']}: {lc_first(b['title'])}"},
            {"label": "Approval reference", "value": ap["ref"]},
            {"label": "Approved by", "value": ap["decided_by"]},
            {"label": "Cost recorded", "value": f"{_usd(ap['amount_usd'])} against {ap['work_order']}" if ap["amount_usd"] else "No additional cost"}]})
        summary = (f"Option {b['option']}, the {lc_first(b['title'])}, was approved on {nice(parse(ap['ts']))} under {ap['ref']} by {ap['decided_by']}. "
                   f"{part} is {'in transit and ' if sup.get('status', '').startswith('Shipped') else ''}expected at {sup.get('deliver_to', 'the gate')} on {nice(parse(sup.get('promised_arrival_ts')))}"
                   + (f", {'within' if parse(sup.get('promised_arrival_ts')) <= parse(win['window_end']) else 'after'} the installation window" if win else "") + ". "
                   + (f"The {_usd(ap['amount_usd'])} fee is recorded against {ap['work_order']}. " if ap["amount_usd"] else "")
                   + f"The forecast for {eid} is now {nice(parse(fc['predicted_completion_ts']))}, {_late(fc['variance_hours'])}. "
                   + " ".join((f"Option {o['option']} was authorised on {o['status'][len('Authorised '):]}." if o["status"].startswith("Authorised ")
                               else f"Option {o['option']} is {lc_first(o['status'])}.") for o in opts if o["option"] == "C"))
    else:
        summary = (f"{len(opts)} recovery options are available for {part} on {eid}, each scheduled forward to a finish date. "
                   + " ".join(f"Option {o['option']} ({lc_first(o['title'])}): {nice(parse(o['predicted_completion_ts']))}, {_late(o['variance_hours'])}, {lc_first(_usd(o['cost_usd']))}, approval by {_by(o['approval_required'])}." for o in opts)
                   + f" The commitment is {nice(committed)}. None is approved yet; the decision rests with the approving roles.")
        blocks.append({"type": "options", "items": [
            {"title": f"Option {o['option']}", "text": {"alternate_stock": "Lowest-cost route; move a unit from satellite stock", "expedite": "Expedite the supplier shipment",
                                                         "resequence": "Re-sequence permitted work; no direct cost"}[o["kind"]] + f"; {_late(o['variance_hours'])}",
             "icon": {"alternate_stock": "coins", "expedite": "plane", "resequence": "route"}[o["kind"]]} for o in opts]})
    followups = (["Show me the updated engine status and recovery progress.", f"What is now the best way to protect the committed delivery date?", f"What if {part} arrives four hours late?"]
                 if approved else ["Has the recovery option been approved?", "Which option protects the committed date at the lowest cost?", f"What if we combine options B and C?"])
    return {"view": "recovery_plan", "data": data, "summary": summary,
            "card": _card("recovery_plan", f"Recovery plan: {part} on {eid}", subtitle=f"Shop time {nice(shop.clock)}", tiles=tiles, blocks=blocks),
            "followups": followups, "sources": ["Recovery Planning Procedure RP-011", "Approval Authority Matrix QP-014"]}


# ─── 5. Protecting the commitment ────────────────────────────────────────
def protect_delivery(shop: Shop, engine_id: str | None = None, **_: Any) -> dict:
    """Reassess the plan: where the forecast stands with everything approved so far,
    which levers are still unused and what each would buy, and how much buffer is left."""
    if engine_id and not shop.engine(engine_id):
        return _not_found("protect_delivery", f"Engine {engine_id}", shop.engine_ids())
    eid = _focus_engine(shop, engine_id)
    fc = shop.forecast(eid)
    committed, predicted = parse(fc["committed_completion_ts"]), parse(fc["predicted_completion_ts"])
    opts = recovery_options(shop, eid)
    part = next((n.split(":")[1] for t in shop.rows("schedule_tasks", engine_id=eid) for n in (t["needs"] or "").split(";") if n.startswith("part:")), None)
    sup = shop.part_supply(part, eid) if part else None
    deps = [d for a in shop.approvals(eid, "disposition") for d in shop.rows("disposition_dependencies", ref=a["ref"])]
    cost = sum(float(a["amount_usd"] or 0) for a in shop.approvals(eid))

    # levers not yet in force, each simulated on top of the current position
    unused: list[dict] = []
    if not fc["inputs"]["resequenced"] and any(o["kind"] == "resequence" for o in opts):
        f = shop.forecast(eid, resequence=True)
        unused.append({"lever": "Re-sequence permitted preparatory work (option C)", "approval": "Supervisor", "cost_usd": 0,
                       "predicted_completion_ts": f["predicted_completion_ts"], "variance_hours": f["variance_hours"]})
    if not shop.approvals(eid, "expedite"):
        for o in opts:
            if o["kind"] in ("expedite", "alternate_stock"):
                unused.append({"lever": f"{o['title']} (option {o['option']})", "approval": o["approval_required"], "cost_usd": o["cost_usd"],
                               "predicted_completion_ts": o["predicted_completion_ts"], "variance_hours": o["variance_hours"]})
    if not fc["inputs"]["overtime"]:
        f = shop.forecast(eid, overtime=True)
        if f["predicted_completion_ts"] != fc["predicted_completion_ts"]:
            unused.append({"lever": "Authorise overtime at the gate", "approval": "Engine Shop Manager", "cost_usd": None,
                           "predicted_completion_ts": f["predicted_completion_ts"], "variance_hours": f["variance_hours"]})
    best = min(unused, key=lambda u: u["predicted_completion_ts"], default=None)

    # how exposed the forecast still is
    sens: list[dict] = []
    if sup:
        arr = parse(sup["promised_arrival_ts"])
        for slip in (4, 12):
            f = shop.forecast(eid, part_arrival={part: arr + timedelta(hours=slip)})
            sens.append({"what_if": f"{part} arrives {slip} h later ({nice(arr + timedelta(hours=slip), with_year=False)})",
                         "predicted_completion_ts": f["predicted_completion_ts"], "variance_hours": f["variance_hours"]})
    done_before = [t for t in fc["tasks"] if t is not fc["tasks"][-1]]
    critical_ready = parse(done_before[-1]["end_ts"]) if done_before else None
    actions = recovery_actions(shop, eid)
    data = {"shop_time": shop.now, "engine_id": eid, "committed_completion_ts": fc["committed_completion_ts"],
            "projected_completion_ts": fc["predicted_completion_ts"], "variance_hours": fc["variance_hours"], "status": fc["status"],
            "critical_work_ready_ts": stamp(critical_ready), "cost_of_recovery_usd": cost,
            "actions_in_force": [{"action": a["label"], "state": a["sub"]} for a in actions],
            "new_dependencies": [{k: d[k] for k in ("kind", "dependency", "where", "state")} for d in deps],
            "unused_levers": unused, "sensitivity": sens}
    tiles = [{"label": "New dependencies", "value": str(len(deps)), "sub": "From the disposition" if deps else "None added", "icon": "branch", "tone": "warn" if deps else "info"},
             {"label": "Cost of recovery", "value": _usd(cost) if cost else "USD 0", "sub": "Approved so far", "icon": "coins", "tone": "info"},
             {"label": "Critical work ready", "value": nice(critical_ready, with_year=False), "sub": "Before final test and release", "icon": "check", "tone": "good" if fc["variance_hours"] <= 0 else "warn"},
             {"label": "Projected completion", "value": nice(predicted, with_year=False), "sub": _late(fc["variance_hours"]), "icon": "calendar", "tone": _tone(fc["status"])}]
    blocks: list[dict] = []
    if fc["variance_hours"] <= 0:
        lead = f"The plan holds: {eid} is projected for {nice(predicted)}, {hours_text(-fc['variance_hours'])} ahead of its commitment."
        if deps:
            lead = ("The selected disposition adds process and material dependencies, so the plan has been reassessed. " + lead)
        blocks.append({"type": "callout", "tone": "good", "title": "Recovery plan summary", "text": lead + (
            " The approved actions still fit the plan: " + "; ".join(f"{a['label']} ({_flat(lc_first(a['sub']))})" for a in actions) + "." if actions else "")})
    else:
        lead = f"{eid} is projected for {nice(predicted)}, {_late(fc['variance_hours'])}."
        if best and best["variance_hours"] <= 0:
            lead += f" {best['lever']} would bring it to {nice(parse(best['predicted_completion_ts']))}, {_late(best['variance_hours'])}; it needs approval by {_by(best['approval'])}."
        elif best:
            lead += f" The strongest unused lever is {lc_first(best['lever'])}: {nice(parse(best['predicted_completion_ts']))}, {_late(best['variance_hours'])}."
        blocks.append({"type": "callout", "tone": "warn", "title": "Recovery plan summary", "text": lead})
    if actions:
        blocks.append({"type": "checklist", "title": "Key actions", "columns": ["Action", "Status"], "items": [
            {"label": a["label"], "detail": a["sub"], "state": "done" if a["state"] == "done" else "pending"} for a in actions]})
    if deps:
        blocks.append({"type": "table", "title": "New dependencies", "columns": ["Type", "Dependency", "Where", "State"],
                       "rows": [[uc_first(d["kind"]), d["dependency"], d["where"], {"text": d["state"], "tone": "good"}] for d in deps]})
    if unused:
        blocks.append({"type": "table", "title": "Levers not yet used", "columns": ["Lever", "Would finish", "Cost", "Approval"],
                       "rows": [[u["lever"], f"{nice(parse(u['predicted_completion_ts']))} ({_late(u['variance_hours'])})",
                                 _usd(u["cost_usd"]) if u["cost_usd"] is not None else "Labour cost", u["approval"]] for u in unused]})
    if sens:
        blocks.append({"type": "table", "title": "How much room is left", "columns": ["If", "Then"],
                       "rows": [[s["what_if"], {"text": f"{nice(parse(s['predicted_completion_ts']))} ({_late(s['variance_hours'])})",
                                                "tone": "good" if s["variance_hours"] <= 0 else "bad"}] for s in sens]})
    summary = lead + (f" Cost of recovery so far is {_usd(cost)}." if cost else "")
    if sens and fc["variance_hours"] <= 0:
        summary += (f" The buffer is {hours_text(-fc['variance_hours'])}: if {sens[0]['what_if']}, the finish moves to "
                    f"{nice(parse(sens[0]['predicted_completion_ts']))}, {_late(sens[0]['variance_hours'])}.")
    return {"view": "protect_delivery", "data": data, "summary": summary,
            "card": _card("protect_delivery", f"Protecting the commitment: {eid}", subtitle=f"Shop time {nice(shop.clock)}", tiles=tiles, blocks=blocks),
            "followups": ["Show me the updated engine status and recovery progress.", f"What if {part} arrives four hours late?" if part else f"What has changed on {eid} since yesterday?",
                          "Can I approve a deviation so the work can continue?"],
            "sources": ["Recovery Planning Procedure RP-011", "Shop Performance Standard SPS-2026"]}


# ─── 6. Job card ─────────────────────────────────────────────────────────
def job_card(shop: Shop, job_card: str | None = None, **_: Any) -> dict:
    jc = _job_card(shop, job_card)
    if not jc:
        return _not_found("job_card", f"Job card {job_card}", [j["job_card"] for j in shop.t["job_cards"]])
    jid = jc["job_card"]
    steps = sorted(shop.rows("job_card_steps", job_card=jid), key=lambda s: s["step_no"])
    checks = shop.readiness(jid)
    done = sum(1 for c in checks if c["state"] == "done")
    rel = shop.released(jid)
    ready = bool(checks) and done == len(checks) and bool(rel)
    finding = next((f for f in shop.t["findings"] if f["job_card"] == jid), None)
    data = {"shop_time": shop.now, "job_card": jid, "title": jc["title"], "revision": jc["revision"], "status": jc["status"], "engine_id": jc["engine_id"],
            "key_care_point": jc["key_care_point"], "est_hours": jc["est_hours"], "crew": jc["crew"],
            "steps": [{k: s[k] for k in ("step_no", "title", "instruction", "confirm")} for s in steps],
            "readiness": {"checks_complete": done, "checks_total": len(checks), "released": bool(rel),
                          "released_ts": rel["ts"] if rel else None, "ready_to_start": ready},
            "finding_recorded": finding["finding_id"] if finding else None}
    tiles = [{"label": "Job card", "value": jid, "sub": jc["title"], "icon": "doc", "tone": "info"},
             {"label": "Revision", "value": jc["revision"], "sub": "Latest approved", "icon": "layers", "tone": "info"},
             {"label": "Key care point", "value": "Caution", "sub": jc["key_care_point"], "icon": "shield", "tone": "good"},
             {"label": "Readiness", "value": "Released" if ready else f"{done} of {len(checks)}" if checks else "To confirm",
              "sub": f"Released {nice(parse(rel['ts']), with_year=False)}" if rel else "The supervisor releases the work once all checks are complete",
              "icon": "clipboard", "tone": "good" if ready else "warn"}]
    blocks: list[dict] = []
    if steps:
        blocks.append({"type": "steps", "title": f"Procedure ({len(steps)} steps)", "items": [
            {"n": s["step_no"], "title": s["title"], "text": s["instruction"], "confirm": s["confirm"]} for s in steps]})
    blocks.append({"type": "callout", "tone": "good" if ready else "warn", "title": "Outcome",
                   "text": (f"Revision {jc['revision']} is the approved instruction and the work is released. Follow it exactly and confirm each step before moving on."
                            if ready else
                            f"Revision {jc['revision']} is the approved instruction. Start only after all readiness checks are complete and the supervisor releases the work.")})
    if not steps:
        blocks.insert(0, {"type": "callout", "tone": "info", "title": "Steps",
                          "text": f"The step-by-step instruction for {jid} is in {jc['document']}. Its steps are not held in the shop system."})
    summary = (f"Job card {jid}, revision {jc['revision']} ({lc_first(jc['title'])}) is the approved instruction: "
               + (f"{len(steps)} steps, " if steps else "") + f"about {jc['est_hours']} working hours for a crew of {jc['crew']}. "
               f"Key care point: {lc_first(jc['key_care_point'])}. "
               + ("" if steps else f"Its steps are in {jc['document']}. ")
               + (f"All {len(checks)} readiness checks are complete and the work was released on {nice(parse(rel['ts']))}, so it can start with step 1: {lc_first(steps[0]['title'])}."
                  if ready and steps else
                  "No readiness checks are recorded for it yet and the work is not released, so it cannot start yet." if not checks else
                  f"{done} of {len(checks)} readiness checks are complete and the work is {'released' if rel else 'not yet released'}, so it cannot start yet."))
    return {"view": "job_card", "data": data, "summary": summary,
            "card": _card("job_card", f"{jid}: {jc['title']}", subtitle=f"Revision {jc['revision']} · {jc['document']}", tiles=tiles, blocks=blocks),
            "followups": ["Can I start fan blade removal now?", "Which tools does this step need?", "Guide me through the first step."] if not ready
            else ["Guide me through the fan blade removal step by step.", "Which tools does this step need?", "What are the inspection limits for a leading-edge scratch?"],
            "sources": [jc["document"], "Approved Maintenance Instructions: Fan Module, Revision C"]}


def _job_card(shop: Shop, ref: str | None) -> dict | None:
    """A job card by number, else by a word in its title, else the fan blade removal card."""
    cards = shop.t["job_cards"]
    if ref:
        r = ref.strip().upper()
        for j in cards:
            if j["job_card"] == r:
                return j
        for j in cards:
            if ref.lower() in j["title"].lower():
                return j
        return None
    return cards[0] if cards else None


# ─── 7. Readiness ────────────────────────────────────────────────────────
def task_readiness(shop: Shop, job_card: str | None = None, **_: Any) -> dict:
    jc = _job_card(shop, job_card)
    if not jc:
        return _not_found("task_readiness", f"Job card {job_card}", [j["job_card"] for j in shop.t["job_cards"]])
    jid, eid = jc["job_card"], jc["engine_id"]
    checks = shop.readiness(jid)
    if not checks:
        return {"view": "task_readiness", "data": {"job_card": jid, "checks": []},
                "summary": f"No readiness checks are recorded yet for {jid}.", "card": None, "followups": [], "sources": [jc["document"]]}
    done = [c for c in checks if c["state"] == "done"]
    blocked = [c for c in checks if c["state"] == "blocked"]
    rel = shop.released(jid)
    ready = len(done) == len(checks) and bool(rel)
    task = next((t for t in shop.rows("schedule_tasks", engine_id=eid) if t["job_card"] == jid), None)
    started = bool(task and shop.rows("task_events", engine_id=eid, task_id=task["task_id"]))
    # effort beyond the shift: schedule the task from its earliest start with no overtime
    overtime_h, start = 0.0, None
    ot_approved = next(iter(shop.approvals(eid, "overtime")), None)
    if task and not started:
        gate = shop.engine(eid)["workstation"].split(",")[0]
        start = shop.clock
        for need in (task["needs"] or "").split(";"):
            if need.startswith("tool:"):
                start = max(start, shop.tool_ready_at(need[5:], gate, start))
        shift_end = datetime.combine(start.date(), ops.DAY_END)
        in_shift = max(0.0, (shift_end - start).total_seconds() / 3600)
        overtime_h = round(max(0.0, float(task["duration_h"]) - in_shift), 1)
    data = {"shop_time": shop.now, "job_card": jid, "engine_id": eid, "ready_to_start": ready, "started": started,
            "checks_complete": len(done), "checks_total": len(checks),
            "checks": [{k: c[k] for k in ("check_no", "check_name", "detail", "owner", "state")} for c in checks],
            "released": bool(rel), "released_ts": rel["ts"] if rel else None,
            "blockers": [c["check_name"] + ": " + c["detail"] for c in blocked],
            "earliest_start_ts": stamp(start) if start else None, "task_hours": task["duration_h"] if task else None,
            "hours_beyond_shift_end": overtime_h, "shift_end": "17:30", "crew": jc["crew"],
            "overtime_approved": bool(ot_approved), "overtime_window": [ot_approved["window_start"], ot_approved["window_end"]] if ot_approved else None}
    status = "In progress" if started else "Ready" if ready else "Not ready"
    blocker = blocked[0] if blocked else None
    tiles = [{"label": "Status", "value": status, "sub": f"Released {nice(parse(rel['ts']), with_year=False)}" if rel else "The supervisor releases the work",
              "icon": "gear", "tone": "good" if ready or started else "bad"},
             {"label": "Checks complete", "value": f"{len(done)} of {len(checks)}", "sub": uc_first(", ".join(lc_first(c["check_name"]) for c in done[:3])) or "None yet",
              "icon": "clipboard", "tone": "good" if len(done) == len(checks) else "warn"},
             ({"label": "Blocker", "value": blocker["check_name"], "sub": blocker["detail"], "icon": "wrench", "tone": "bad"}
              if blocker else {"label": "Blocker", "value": "None", "sub": "No check is blocked", "icon": "check", "tone": "good"})]
    if overtime_h and not started:
        tiles.append({"label": "Overtime approved" if ot_approved else "Overtime needed", "value": hours_text(overtime_h),
                      "sub": f"Beyond the 17:30 shift end, {jc['crew']} technicians", "icon": "users", "tone": "good" if ot_approved else "warn"})
    blocks: list[dict] = [{"type": "checklist", "title": "Readiness checks", "columns": ["Readiness check", "Status", "Owner"],
                           "items": [{"label": c["check_name"], "detail": c["detail"], "owner": c["owner"], "state": c["state"]} for c in checks]}]
    nxt: list[str] = []
    for c in checks:
        if c["state"] == "blocked":
            nxt.append(f"Clear the blocker. {c['check_name']}: {lc_first(c['detail'])}. Owner: {c['owner']}.")
        elif c["state"] == "pending":
            nxt.append(f"{c['check_name']}: {lc_first(c['detail'])}. Owner: {c['owner']}.")
    if overtime_h and not ot_approved and not started:
        nxt.append(f"Ask the Engine Shop Manager to authorise overtime for {jc['crew']} technicians ({hours_text(overtime_h)} beyond the shift).")
    if not rel and not nxt:
        nxt.append("Ask the supervisor to release the work.")
    if nxt:
        blocks.append({"type": "list", "title": "Next actions", "tone": "good", "items": nxt})
    if started:
        summary = f"{jid} is in progress: all {len(checks)} readiness checks are complete and the work was released on {nice(parse(rel['ts']))}."
    elif ready:
        summary = f"Yes. All {len(checks)} readiness checks for {jid} are complete and the supervisor released the work on {nice(parse(rel['ts']))}. Start with step 1 of the job card."
    else:
        summary = (f"Not ready. {len(done)} of {len(checks)} readiness checks for {jid} are complete"
                   + (f"; the blocker is {blocker['check_name']} ({lc_first(blocker['detail'])})" if blocker else "") + ". "
                   + (f"From the earliest start at {nice(start, with_year=False)}, the {task['duration_h']:g} h task runs about {hours_text(overtime_h)} beyond the 17:30 shift end, "
                      f"so it needs {'the approved' if ot_approved else 'authorised'} overtime for {jc['crew']} technicians. " if overtime_h else "")
                   + "The supervisor releases the work once every check is complete.")
    return {"view": "task_readiness", "data": data, "summary": summary,
            "card": _card("task_readiness", f"Readiness: {jid}", subtitle=f"Shop time {nice(shop.clock)}", tiles=tiles, blocks=blocks),
            "followups": (["Guide me through the fan blade removal step by step.", "Which tools does this step need?", "What are the inspection limits for a leading-edge scratch?"]
                          if ready or started else ["Which tools does this step need?", "Where is tool T-117?", "Raise a handover request for T-117."]),
            "sources": [jc["document"], "Tool Control Procedure TC-003"]}


# ─── 8. Tools for a task ─────────────────────────────────────────────────
def task_tools(shop: Shop, job_card: str | None = None, **_: Any) -> dict:
    jc = _job_card(shop, job_card)
    if not jc:
        return _not_found("task_tools", f"Job card {job_card}", [j["job_card"] for j in shop.t["job_cards"]])
    jid = jc["job_card"]
    gate = (shop.engine(jc["engine_id"]) or {}).get("workstation", "Gate 1").split(",")[0]
    listed = shop.rows("job_card_tools", job_card=jid)
    if not listed:
        return {"view": "task_tools", "data": {"job_card": jid, "tools": []}, "summary": f"{jid} lists no special tools.",
                "card": None, "followups": [], "sources": [jc["document"]]}
    section = listed[0]["section"]
    tools = []
    for row in listed:
        st = shop.tool_state(row["tool_id"])
        at_gate = st["location"].startswith(gate) and st["checked_in"]
        where = st["location"] if at_gate else (f"Not at {gate}" + (", tool request raised" if st["request"] else "") + f" (custody: {st['location']})")
        cal = "Not required" if not st["calibration_required"] else f"Valid to {nice(parse(st['calibration_due']))[:-6]}" if st["calibration_ok"] else f"Expired {st['calibration_due']}"
        tools.append({"tool_id": st["tool_id"], "tool": st["tool"], "used_for": st["used_for"], "location": where, "at_gate": at_gate,
                      "calibration": cal, "calibration_ok": st["calibration_ok"]})
    here = [t for t in tools if t["at_gate"]]
    missing = [t for t in tools if not t["at_gate"]]
    cal_bad = [t for t in tools if not t["calibration_ok"]]
    data = {"shop_time": shop.now, "job_card": jid, "section": section, "gate": gate, "tools": tools,
            "available_at_gate": len(here), "missing": [t["tool_id"] for t in missing], "substitution_permitted": False}
    tiles = [{"label": "Tools required", "value": str(len(tools)), "sub": f"{jid}, section {section}", "icon": "wrench", "tone": "info"},
             {"label": f"At {gate}", "value": f"{len(here)} of {len(tools)}", "sub": "Ready on the tool board" if not missing else "Checked in", "icon": "check", "tone": "good" if not missing else "warn"},
             ({"label": "Missing", "value": ", ".join(t["tool_id"] for t in missing), "sub": missing[0]["tool"], "icon": "alert", "tone": "bad"}
              if missing else {"label": "Missing", "value": "None", "sub": "All tools at the gate", "icon": "check", "tone": "good"}),
             {"label": "Calibration", "value": "In date" if not cal_bad else "Check", "sub": ", ".join(t["tool_id"] for t in tools if t["calibration"] != "Not required") + " checked",
              "icon": "calendar", "tone": "good" if not cal_bad else "bad"}]
    blocks = [{"type": "table", "title": f"Tools for {lc_first(jc['title'])} ({jid}, section {section})",
               "columns": ["Tool ID", "Tool", "Used for", "Location", "Calibration"],
               "rows": [[t["tool_id"], t["tool"], t["used_for"], {"text": t["location"], "tone": "good" if t["at_gate"] else "bad"}, t["calibration"]] for t in tools],
               "highlight": [i for i, t in enumerate(tools) if not t["at_gate"]]},
              {"type": "callout", "tone": "good" if not missing else "warn", "title": "Next step",
               "text": (f"All {len(tools)} tools are at {gate} and calibration is in date. The removal can start once the work is released."
                        if not missing else
                        f"Confirm that {missing[0]['tool_id']} is on the tool board and its calibration label is in date. No substitution is permitted; the task cannot start until it is checked in.")}]
    if missing:
        m = missing[0]
        summary = (f"{jid} lists {len(tools)} tools in section {section}. {len(here)} are available at {gate}. {m['tool_id']}, the {lc_first(m['tool'])}, is not at {gate}"
                   f"{', though its calibration is ' + lc_first(m['calibration']) if m['calibration_ok'] and m['calibration'] != 'Not required' else ''}. "
                   "No substitution is permitted, so the task cannot start until it is checked in.")
    else:
        summary = f"{jid} lists {len(tools)} tools in section {section}, and all of them are at {gate} with calibration in date."
    return {"view": "task_tools", "data": data, "summary": summary,
            "card": _card("task_tools", f"Tools: {jid}", subtitle=f"Shop time {nice(shop.clock)}", tiles=tiles, blocks=blocks),
            "followups": ([f"Where is tool {missing[0]['tool_id']}?", "Can I start fan blade removal now?", f"Raise a handover request for {missing[0]['tool_id']}."] if missing
                          else ["Can I start fan blade removal now?", "Guide me through the fan blade removal step by step.", "Which tools need calibration soon?"]),
            "sources": [jc["document"], "Tool Control Procedure TC-003"]}


# ─── 9. Where a tool is ──────────────────────────────────────────────────
def tool_location(shop: Shop, tool_id: str | None = None, **_: Any) -> dict:
    tid = (tool_id or "T-117").upper()
    st = shop.tool_state(tid)
    if not st:
        return _not_found("tool_location", f"Tool {tool_id}", [t["tool_id"] for t in shop.t["tools"]])
    sight = st["last_sighting"]
    exp = parse(st["expected_available_ts"])
    issued = next((e for e in st["events"] if e["event"] == "Issued"), None)
    signed = next((e for e in reversed(st["events"]) if e["event"] == "Handover signed"), None)
    data = {"shop_time": shop.now, "tool_id": tid, "tool": st["tool"], "used_for": st["used_for"],
            "custody": {"location": st["location"], "custodian": st["custodian"], "event": st["custody_event"], "ts": st["custody_ts"], "source": st["custody_source"]},
            "last_camera_sighting": ({"ts": sight["ts"], "location": sight["location"], "source": sight["source"],
                                      "newer_than_custody_record": st["sighting_is_latest"]} if sight else None),
            "expected_available_ts": st["expected_available_ts"], "tool_request": (st["request"] or {}).get("note"),
            "calibration_due": st["calibration_due"], "calibration_ok": st["calibration_ok"],
            "history": [{k: e[k] for k in ("ts", "event", "location", "custodian", "source", "note")} for e in st["events"]],
            "rule": "A camera detection is a sighting, not a custody change. Transfer needs physical verification and a signed handover (TC-003)."}
    in_use = bool(issued and not signed and not st["checked_in"])
    tiles = [{"label": tid, "value": st["tool"], "icon": "wrench", "tone": "info"},
             {"label": "Custody record", "value": st["location"], "sub": f"{st['custody_event']} {nice(parse(st['custody_ts']), with_year=False)}".strip(), "icon": "pin", "tone": "good" if st["checked_in"] else "info"}]
    if sight and st["sighting_is_latest"]:
        tiles.append({"label": "Last sighting", "value": sight["location"], "sub": f"Camera, {nice(parse(sight['ts']), with_year=False)}; not a handover", "icon": "camera", "tone": "warn"})
    if exp:
        tiles.append({"label": "Expected available", "value": nice(exp, with_year=False), "icon": "clock", "tone": "warn"})
    if st["calibration_required"]:
        tiles.append({"label": "Calibration valid until", "value": nice(parse(st["calibration_due"]))[:-6], "sub": "Fit for use" if st["calibration_ok"] else "Expired",
                      "icon": "shield", "tone": "good" if st["calibration_ok"] else "bad"})
    labels = {"Issued": "Issued", "Camera detection": "Detected", "Tool request raised": "Requested", "Handover signed": "Handover signed", "Checked in": "Checked in"}
    items = [{"label": labels.get(e["event"], e["event"]), "sub": f"{nice(parse(e['ts']), with_year=False)} · {e['location']} · {e['source']}",
              "state": "warn" if e["event"] == "Camera detection" else "done"} for e in st["events"]]
    if in_use and exp:
        items.append({"label": "Available", "sub": f"Expected {nice(exp, with_year=False)}", "state": "pending"})
    blocks: list[dict] = [{"type": "timeline", "title": "Custody trail", "items": items}]
    if in_use:
        blocks.append({"type": "flow", "title": "What happens next", "items": [
            {"label": "1. Detected", "sub": f"{sight['location']} at {sight['ts'][11:]}" if sight else st["location"], "state": "done", "icon": "camera"},
            {"label": "2. Verify at the bench", "sub": "Confirm the tool physically and by identity label", "state": "current", "icon": "users"},
            {"label": "3. Sign for pickup", "sub": "Complete the handover and update custody", "state": "pending", "icon": "clipboard"},
            {"label": "4. Transfer", "sub": "Record arrival at the requesting gate", "state": "pending", "icon": "route"}]})
        blocks.append({"type": "callout", "tone": "warn", "title": "Key point",
                       "text": "The camera alert is a detection, not a confirmed handover. The tool may have moved since, so physical verification and a signed handover are required before any transfer is recorded. Until then it stays assigned to its current custodian."})
        summary = (f"{tid} is away from its home location: {lc_first(issued['note'])} on {nice(parse(issued['ts']))}; custody is with {st['custodian']}. "
                   + (f"It was last detected at {sight['location']} at {sight['ts'][11:]} by the {sight['source']}; that is a sighting, not a confirmed handover, so the tool may have moved. " if sight else "")
                   + (f"It is expected to become available around {nice(exp)}. " if exp else "")
                   + ("A tool request is already raised (" + st["request"]["note"].split(":")[0] + "). " if st["request"] else "A controlled handover request can arrange the transfer. ")
                   + "A person must verify identity and location and sign the custody handover before the transfer is recorded.")
    else:
        blocks.append({"type": "callout", "tone": "good", "title": "Custody status",
                       "text": (f"{tid} is at {st['location']} by signed custody record ({lc_first(st['custody_event'])} {nice(parse(st['custody_ts']), with_year=False)}, {st['custody_source']})."
                                if st["custody_ts"] else f"{tid} is at its home location, {st['location']}. No issue or handover is recorded against it.")
                               + (" Calibration is in date." if st["calibration_required"] and st["calibration_ok"] else "")})
        summary = ((f"{tid} ({lc_first(st['tool'])}) is at {st['location']}: {lc_first(st['custody_event'])} on {nice(parse(st['custody_ts']))}, recorded by {st['custody_source']}."
                    if st["custody_ts"] else
                    f"{tid} ({lc_first(st['tool'])}) is at its home location, {st['location']}. No issue or handover is recorded against it.")
                   + (f" The handover from {signed['location']} was signed at {signed['ts'][11:]}." if signed else "")
                   + (f" Calibration is valid until {nice(parse(st['calibration_due']))[:-6]}." if st["calibration_required"] else ""))
    return {"view": "tool_location", "data": data, "summary": summary,
            "card": _card("tool_location", f"Tool {tid}: {st['tool']}", subtitle=f"Shop time {nice(shop.clock)}", tiles=tiles, blocks=blocks),
            "followups": (["Is the tool still at Gate 3?", f"Raise a handover request for {tid}.", "Can I start fan blade removal now?"] if in_use
                          else ["Can I start fan blade removal now?", "Which tools does this step need?", "Guide me through the fan blade removal step by step."]),
            "sources": ["Tool Control Procedure TC-003"]}


# ─── 10. Inspection finding ──────────────────────────────────────────────
def inspection_finding(shop: Shop, engine_id: str | None = None, finding_id: str | None = None, **_: Any) -> dict:
    limits = shop.t["inspection_limits"]
    found = [f for f in shop.t["findings"] if (not finding_id or f["finding_id"] == finding_id.upper()) and (not engine_id or f["engine_id"] == engine_id.upper())]
    ref = limits[0]["reference"] if limits else ""
    if not found:
        rows = [[l["zone"], f"≤ {l['limit_mm']:.2f} mm", l["if_exceeded"]] for l in limits]
        return {"view": "inspection_finding",
                "data": {"shop_time": shop.now, "findings": [], "limits": [{k: l[k] for k in ("component", "damage", "zone", "limit_mm", "if_exceeded", "reference")} for l in limits]},
                "summary": (f"No inspection finding is recorded{' for ' + engine_id.upper() if engine_id else ''} at this point. "
                            f"For a fan blade leading-edge scratch the serviceable limit is {limits[0]['limit_mm']:.2f} mm depth in every zone ({ref}); above it, measure depth, length and position and raise a finding for disposition by Engineering or Quality. A crack at the blade base requires rejection regardless of scratch size."
                            if limits else "No inspection finding is recorded."),
                "card": _card("inspection_limits", "Fan blade leading-edge limits", subtitle=f"Inspection Standards Manual, {ref}",
                              blocks=[{"type": "table", "columns": ["Zone", "Serviceable limit", "If exceeded"], "rows": rows}]) if limits else None,
                "followups": ["Guide me through the fan blade removal step by step.", "Who can approve a deviation?", "Record an inspection finding."],
                "sources": ["Inspection Standards Manual, Chapter 72, Revision F"]}
    f = found[-1]
    zones = shop.rows("finding_measurements", finding_id=f["finding_id"])
    dispo = next((a for a in shop.approvals(f["engine_id"], "disposition") if f["finding_id"] in a["subject"]), None)
    above = [z for z in zones if z["result_mm"] > z["limit_mm"]]
    zrows = [{"zone": z["zone"], "name": z["zone_name"], "location": z["location"], "result_mm": z["result_mm"], "limit_mm": z["limit_mm"],
              "status": "above" if z["result_mm"] > z["limit_mm"] else "within"} for z in zones]
    data = {"shop_time": shop.now, "finding_id": f["finding_id"], "engine_id": f["engine_id"], "job_card": f["job_card"], "component": f["component"],
            "serial": f["serial"], "damage": f["damage"], "recorded_ts": f["ts"], "recorded_by": f["recorded_by"], "standard": f["standard"], "zones": zrows,
            "disposition": ({"ref": dispo["ref"], "ts": dispo["ts"], "decision": dispo["subject"], "decided_by": dispo["decided_by"]} if dispo else None),
            "status": "Dispositioned" if dispo else "Disposition pending" if above else "Within limits",
            "rule": "The technician records the finding; only an authorised Engineering or Quality role dispositions it (QP-014)."}
    tiles = [{"label": "Finding", "value": f["finding_id"], "sub": f"{f['damage']} · {f['component']}", "icon": "alert", "tone": "bad" if above else "good"},
             {"label": "Blade serial", "value": f["serial"], "sub": f["engine_id"], "icon": "fan", "tone": "info"},
             {"label": "Zones above limit", "value": f"{len(above)} of {len(zones)}", "sub": ", ".join(f"Zone {z['zone']}" for z in above) or "All within limit", "icon": "target", "tone": "bad" if above else "good"},
             {"label": "Disposition", "value": "Issued" if dispo else "Pending", "sub": dispo["ref"] if dispo else "Engineering / Quality", "icon": "shield", "tone": "good" if dispo else "warn"}]
    blocks: list[dict] = [{"type": "blade", "title": f"{f['damage']} · blade {f['serial']}", "serial": f["serial"], "damage": f["damage"], "standard": f["standard"],
                           "zones": [{**z, "caution": ("Above the zone limit. Measure depth, length and position; disposition pending." if z["status"] == "above" and not dispo else
                                                      "A crack at the blade base requires rejection regardless of scratch size." if z["zone"] == "C" else "")} for z in zrows]}]
    if dispo:
        blocks.append({"type": "callout", "tone": "good", "title": f"Disposition {dispo['ref']}",
                       "text": f"{uc_first(dispo['subject'].split(': ', 1)[-1])}. Issued {nice(parse(dispo['ts']))} by {dispo['decided_by']}."})
    elif above:
        blocks.append({"type": "callout", "tone": "warn", "title": "Disposition pending",
                       "text": "The finding is recorded, not accepted. Work on the affected blade stays on hold until an authorised Engineering or Quality role records a disposition."})
    zb = above[0] if above else None
    summary = (f"Finding {f['finding_id']} on {f['engine_id']}: {lc_first(f['damage'])} on {lc_first(f['component'])} serial {f['serial']}, recorded {nice(parse(f['ts']))} by {f['recorded_by']} under {f['job_card']}. "
               + " ".join(f"Zone {z['zone']} ({z['name'].lower()}) measures {z['result_mm']:.2f} mm against a limit of {z['limit_mm']:.2f} mm, {z['status']} limit." for z in zrows) + " "
               + (f"Disposition {dispo['ref']} was issued on {nice(parse(dispo['ts']))} by {dispo['decided_by']}: {dispo['subject'].split(': ', 1)[-1]}." if dispo else
                  "Disposition is pending with Engineering or Quality; the assistant and shop roles cannot accept the finding." if zb else "All zones are within limit."))
    return {"view": "inspection_finding", "data": data, "summary": summary,
            "card": _card("inspection_finding", f"Finding {f['finding_id']}", subtitle=f["standard"], tiles=tiles, blocks=blocks),
            "followups": (["What is now the best way to protect the committed delivery date?", "Show me the updated engine status and recovery progress.", "What does the disposition add to the plan?"] if dispo
                          else ["Can I approve a deviation so the work can continue?", "Prepare the deviation evidence package.", "What is now the best way to protect the committed delivery date?"]),
            "sources": ["Inspection Standards Manual, Chapter 72, Revision F", "Approval Authority Matrix QP-014"]}


# ─── 11. Who can approve ─────────────────────────────────────────────────
_AUTH_WORDS = {
    "Deviation or concession": ("deviation", "concession", "waiver"),
    "Acceptance or disposition of a finding": ("finding", "disposition", "accept"),
    "Certification of work": ("certif", "sign off", "sign-off", "crs"),
    "Release of an engine": ("release an engine", "release the engine", "engine release", "ship", "deliver"),
    "Work release at a workstation": ("release the work", "work release", "start work", "release work"),
    "Overtime": ("overtime",),
    "Supplier expedite spend": ("expedite", "spend", "freight"),
    "Alternate stock transfer": ("stock", "transfer", "inventory"),
    "Re-sequencing of permitted preparatory work": ("re-sequenc", "resequenc", "sequence"),
    "Tool custody handover": ("tool", "handover", "custody"),
}


# How each decision reads after "may ...", and whether work waits on it.
_AUTH_VERB = {
    "Deviation or concession": ("approve a deviation or concession", True),
    "Acceptance or disposition of a finding": ("accept or disposition a finding", True),
    "Certification of work": ("certify work", False),
    "Release of an engine": ("release an engine", False),
    "Work release at a workstation": ("release work at a workstation", True),
    "Overtime": ("authorise overtime", False),
    "Supplier expedite spend": ("approve supplier expedite spend", False),
    "Alternate stock transfer": ("approve an alternate stock transfer", False),
    "Re-sequencing of permitted preparatory work": ("authorise re-sequencing of permitted preparatory work", False),
    "Tool custody handover": ("record a tool custody handover", False),
}


def _a(noun: str) -> str:
    return ("an " if noun[:1].lower() in "aeiou" else "a ") + noun


def _who_cannot(nots: list[str]) -> str:
    """The 'who may not' column as a sentence."""
    if not nots:
        return ""
    if nots == ["Anyone else"]:
        return "No one else may. "
    if nots == ["Shop roles"]:
        return "Shop roles cannot. "
    if nots == ["Camera detection alone"]:
        return "A camera detection alone is not a handover. "
    return f"{uc_first(_a(' or '.join(lc_first(n) for n in nots)))} cannot. "


def _who(authority: str) -> str:
    """The approving role as the subject of a sentence: 'an authorised Engineering or Quality role',
    'the Supervisor', 'Procurement, with logistics confirmation,' (the aside closed by a comma)."""
    if authority.startswith("Authorised"):
        return "an " + lc_first(authority)
    if authority.startswith("Releasing custodian"):
        return "the releasing custodian and the receiving person, both signing,"
    if authority in ("Supervisor", "Engine Shop Manager"):
        return "the " + authority
    text = lc_first(authority) if authority.startswith("Certifying") else authority
    return text + "," if "," in text else text


def approval_authority(shop: Shop, action: str | None = None, role: str | None = None, **_: Any) -> dict:
    matrix = shop.t["approval_matrix"]
    q = (action or "").lower()
    hits = [m for m in matrix if any(w in q for w in _AUTH_WORDS.get(m["action"], ()))] if q else []
    rows = hits or matrix
    data = {"matrix": [{k: m[k] for k in ("action", "authority", "cannot_approve", "reference")} for m in rows],
            "assistant_limits": ASSISTANT_LIMITS, "asked_about": action or "all actions", "your_role": role}
    top = rows[0]
    tiles = []
    if hits:
        tiles = [{"label": "Request type", "value": top["action"], "icon": "doc", "tone": "info"},
                 {"label": "Approval authority", "value": top["authority"], "sub": top["reference"], "icon": "shield", "tone": "good"},
                 {"label": "Cannot approve", "value": top["cannot_approve"].replace("; Sanad Digital Assistant", ""), "sub": "Nor the Sanad Digital Assistant", "icon": "x", "tone": "bad"},
                 {"label": "The assistant can", "value": "Prepare evidence", "sub": "And route it for review", "icon": "clipboard", "tone": "info"}]
    blocks = [{"type": "table", "title": "Approval authority matrix (QP-014)", "columns": ["Action", "Who may approve", "Who may not", "Reference"],
               "rows": [[m["action"], m["authority"], m["cannot_approve"], m["reference"]] for m in rows]},
              {"type": "callout", "tone": "info", "title": "What the assistant can and cannot do", "text": ASSISTANT_LIMITS}]
    if hits:
        nots = [n for n in top["cannot_approve"].split("; ") if "Assistant" not in n]
        verb, holds_work = _AUTH_VERB.get(top["action"], (f"approve {_a(lc_first(top['action']))}", False))
        under = f"the approval authority matrix ({top['reference']})" if top["reference"].startswith("QP-014") else top["reference"]
        summary = (f"Only {_who(top['authority'])} may {verb} under {under}. "
                   + _who_cannot(nots) + ASSISTANT_LIMITS
                   + (" Work on the affected step stays on hold until the decision is recorded." if holds_work else ""))
    else:
        summary = "The approval authority matrix (QP-014) sets who may approve each kind of decision. " + ASSISTANT_LIMITS
    return {"view": "approval_authority", "data": data, "summary": summary,
            "card": _card("approval_authority", "Approval authority", subtitle="Approval Authority Matrix QP-014", tiles=tiles, blocks=blocks),
            "followups": ["Prepare the deviation evidence package.", "What is now the best way to protect the committed delivery date?", "Who can authorise overtime?"],
            "sources": ["Approval Authority Matrix QP-014", "Deviation and Concession Process QP-021", "Sanad Digital Assistant Governance Policy DA-001"]}


# ─── 12. What-if ─────────────────────────────────────────────────────────
def simulate_schedule(shop: Shop, engine_id: str | None = None, part_arrival: str | None = None, tool_available: str | None = None,
                      overtime: bool | None = None, resequence: bool | None = None, disposition: bool | None = None, **_: Any) -> dict:
    if engine_id and not shop.engine(engine_id):
        return _not_found("simulate_schedule", f"Engine {engine_id}", shop.engine_ids())
    eid = _focus_engine(shop, engine_id)
    tasks = shop.rows("schedule_tasks", engine_id=eid)
    part = next((n.split(":")[1] for t in tasks for n in (t["needs"] or "").split(";") if n.startswith("part:")), None)
    tool = next((n.split(":")[1] for t in tasks for n in (t["needs"] or "").split(";") if n.startswith("tool:")), None)
    what_if: dict[str, Any] = {}
    changed: list[str] = []
    pa, ta = parse(part_arrival), parse(tool_available)
    if part_arrival and not pa or tool_available and not ta:
        return {"view": "simulate_schedule", "data": {"error": "Give times as YYYY-MM-DD HH:MM."},
                "summary": "The time could not be read. Give times as YYYY-MM-DD HH:MM.", "card": None, "followups": [], "sources": []}
    if pa and part:
        what_if["part_arrival"] = {part: pa}; changed.append(f"{part} arrives {nice(pa)}")
    if ta and tool:
        what_if["tool_available"] = {tool: ta}; changed.append(f"{tool} is at the gate from {nice(ta)}")
    for key, val, yes, no in (("overtime", overtime, "overtime is authorised", "overtime is not authorised"),
                              ("resequence", resequence, "permitted work is re-sequenced", "work is not re-sequenced"),
                              ("disposition", disposition, "a blade repair disposition is in force", "no repair disposition is in force")):
        if val is not None:
            what_if[key] = bool(val); changed.append(yes if val else no)
    base = shop.forecast(eid)
    sim = shop.forecast(eid, **what_if) if what_if else base
    delta = round(sim["variance_hours"] - base["variance_hours"], 2)
    data = {"shop_time": shop.now, "engine_id": eid, "assumptions": changed or ["no change: the current plan"],
            "committed_completion_ts": base["committed_completion_ts"],
            "current": {k: base[k] for k in ("predicted_completion_ts", "variance_hours", "status")},
            "simulated": {k: sim[k] for k in ("predicted_completion_ts", "variance_hours", "status")},
            "change_hours": delta, "driver": (sim["driver"] or {}).get("text"),
            "schedule": [{k: t[k] for k in ("task", "start_ts", "end_ts", "state", "held_by")} for t in sim["tasks"]],
            "note": "A simulation only. Nothing in the plan changes; any of these actions needs its own approval."}
    blocks = [{"type": "compare", "items": [
        {"label": "Current forecast", "value": nice(parse(base["predicted_completion_ts"])), "sub": _late(base["variance_hours"]), "tone": _tone(base["status"])},
        {"label": "Simulated", "value": nice(parse(sim["predicted_completion_ts"])), "sub": _late(sim["variance_hours"]), "tone": _tone(sim["status"])}],
        "delta": {"text": "No change" if not delta else f"{hours_text(delta)} {'later' if delta > 0 else 'earlier'}", "tone": "bad" if delta > 0 else "good" if delta < 0 else "info"}},
        {"type": "table", "title": "Simulated schedule", "columns": ["Task", "Start", "Finish", "Held by"],
         "rows": [[t["task"].split(":")[0], nice(parse(t["start_ts"]), with_year=False), nice(parse(t["end_ts"]), with_year=False), _held(t["held_by"], sim["tasks"])] for t in sim["tasks"]]},
        {"type": "callout", "tone": "info", "title": "Simulation only", "text": "Nothing in the plan has changed. Each of these actions needs its own approval from the authorised role."}]
    drv_text = (sim["driver"] or {}).get("text", "The planned sequence sets the finish")
    summary = (f"If {' and '.join(changed) if changed else 'nothing changes'}, {eid} would finish {nice(parse(sim['predicted_completion_ts']))}, {_late(sim['variance_hours'])}; "
               f"the commitment is {nice(parse(base['committed_completion_ts']))}. "
               + (f"That is {hours_text(delta)} {'later' if delta > 0 else 'earlier'} than the current forecast of {nice(parse(base['predicted_completion_ts']))}." if delta else
                  "That is the current forecast." if not changed else
                  f"That is the same as the current forecast, because this does not move what sets the finish date. {drv_text}.")
               + " This is a simulation; nothing has changed in the plan.")
    return {"view": "simulate_schedule", "data": data, "summary": summary,
            "card": _card("simulate_schedule", f"What if: {eid}", subtitle="; ".join(changed) or "Current plan", blocks=blocks),
            "followups": [f"What is now the best way to protect the committed delivery date?", "Show me the status of all the engines.", f"Generate a recovery plan for {eid}."],
            "sources": ["Shop Performance Standard SPS-2026"]}


VIEWS: dict[str, Callable[..., dict]] = {
    "engine_status": engine_status, "delivery_risk": delivery_risk, "forecast_changes": forecast_changes,
    "recovery_plan": recovery_plan, "protect_delivery": protect_delivery, "job_card": job_card,
    "task_readiness": task_readiness, "task_tools": task_tools, "tool_location": tool_location,
    "inspection_finding": inspection_finding, "approval_authority": approval_authority, "simulate_schedule": simulate_schedule,
}


def run(name: str, shop: Shop, **args: Any) -> dict:
    return VIEWS[name](shop, **{k: v for k, v in args.items() if v is not None})
