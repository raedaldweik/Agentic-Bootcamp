"""The tools the assistant works with, and the context one question runs in.

Three kinds:
  views      the standard answers (status, risk, recovery, readiness ...), each with a card
  open       read-only SQL over the shop tables, search over the approved documents, charts
  actions    raise a request, draft a finding, route an evidence package. Every action
             creates a pending record for an authorised person. None of them approves,
             certifies, accepts or releases anything, and the role checks are enforced
             here, in code, whatever the model was told.

Tool inputs arrive from a model, so each one is validated before it runs.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from . import corpus, dataset, ops, views
from .ops import Shop, nice, parse
from .records import Notebook

MAX_SQL_ROWS_TO_MODEL = 60
MAX_CHART_ROWS = 60
CHART_TYPES = ("bar", "line", "area", "pie", "scatter")


@dataclass
class Context:
    """Everything one question can see and touch."""
    shop: Shop
    persona: dict[str, Any]
    notebook: Notebook
    views: dict[str, dict] = field(default_factory=dict)      # card handle -> view result
    charts: dict[str, dict] = field(default_factory=dict)     # card handle -> chart spec
    passages: list[dict] = field(default_factory=list)        # document passages read
    created: list[dict] = field(default_factory=list)         # records created this turn
    calls: list[dict] = field(default_factory=list)           # the trace of tool calls
    _snapshot: dataset.Snapshot | None = None

    def snapshot(self) -> dataset.Snapshot:
        if self._snapshot is None:
            self._snapshot = self.shop.snapshot()
        return self._snapshot

    def close(self) -> None:
        if self._snapshot is not None:
            self._snapshot.close()
            self._snapshot = None

    def add_view(self, result: dict) -> str:
        """Keep a view result and return the handle its card is shown by."""
        base = result["view"]
        handle, n = base, 1
        while handle in self.views:
            n += 1
            handle = f"{base}_{n}"
        self.views[handle] = result
        return handle

    def card(self, handle: str) -> dict | None:
        if handle in self.charts:
            return self.charts[handle]
        v = self.views.get(handle)
        return v.get("card") if v else None

    def handles(self) -> list[str]:
        return [h for h, v in self.views.items() if v.get("card")] + list(self.charts)


class ToolError(Exception):
    """A refusal or a bad input, reported back to the model as an error result."""


# ─── Schemas ─────────────────────────────────────────────────────────────
def _tool(name: str, description: str, props: dict[str, Any] | None = None, required: list[str] | None = None) -> dict:
    return {"name": name, "description": description, "eager_input_streaming": True,
            "input_schema": {"type": "object", "properties": props or {}, "required": required or [], "additionalProperties": False}}


_ENG = {"type": "string", "description": "Engine id such as ENG-204. Omit for the engine that most needs attention."}
_JC = {"type": "string", "description": "Job card id such as JC-FAN-204. Omit for the fan blade removal job card."}
_TS = "Shop time as YYYY-MM-DD HH:MM."

SCHEMAS: list[dict] = [
    _tool("engine_status", "Status of every engine in the shop against its committed date: forecast, hours late or ahead, what sets the date, stage, progress, next release. With engine_id, one engine in detail including recovery progress.", {"engine_id": {"type": "string", "description": "One engine, such as ENG-204. Omit for all engines."}}),
    _tool("delivery_risk", "The primary risk to an engine's committed delivery: what drives the forecast, the constraint chain, and the other open risks (parts, tools, findings).", {"engine_id": _ENG}),
    _tool("forecast_changes", "What changed on an engine since an earlier moment: events, and how each moved the forecast.", {"engine_id": _ENG, "since": {"type": "string", "description": f"Compare against this moment. {_TS} Omit for the start of the previous day."}}),
    _tool("recovery_plan", "Recovery options for the late component on an engine, each scheduled forward to a finish date with cost and approving role, plus which options are approved and by whom.", {"engine_id": _ENG}),
    _tool("protect_delivery", "The best remaining ways to protect the committed delivery date now: levers still open, what each is worth in hours, and who authorises it.", {"engine_id": _ENG}),
    _tool("job_card", "The approved job card: steps in order with the confirmation each needs, care points, crew and hours. Use for step-by-step guidance.", {"job_card": _JC}),
    _tool("task_readiness", "Whether a task can start now: the readiness checks, blockers, work release, earliest start, and overtime need.", {"job_card": _JC}),
    _tool("task_tools", "The tools a job card needs and whether each is at the workstation and in calibration.", {"job_card": _JC}),
    _tool("tool_location", "Where a tool is: the custody record, the latest camera sighting, open requests, expected availability and calibration.", {"tool_id": {"type": "string", "description": "Tool id such as T-117."}}, ["tool_id"]),
    _tool("inspection_finding", "The inspection finding on an engine: measurements per blade zone against the limits of the Inspection Standards Manual, and the disposition status. Before a finding is recorded it returns the applicable limits.", {"engine_id": _ENG, "finding_id": {"type": "string", "description": "Finding id such as FND-2026-0412."}}),
    _tool("approval_authority", "Who may approve a kind of decision (deviation, overtime, work release, expedite spend, re-sequencing, certification, engine release, tool handover) under the approval authority matrix, and whether the person asking may.", {"action": {"type": "string", "description": "The decision, in the user's words."}, "role": {"type": "string", "description": "Role to check, if not the person asking."}}, ["action"]),
    _tool("simulate_schedule", "What-if on an engine's schedule. Changes nothing. Give only the assumptions that differ from today.", {
        "engine_id": _ENG,
        "part_arrival": {"type": "string", "description": f"Assume the late component arrives at this time. {_TS}"},
        "tool_available": {"type": "string", "description": f"Assume the missing tool is at the gate from this time. {_TS}"},
        "overtime": {"type": "boolean", "description": "Assume overtime is (true) or is not (false) authorised."},
        "resequence": {"type": "boolean", "description": "Assume permitted work is (true) or is not (false) re-sequenced."},
        "disposition": {"type": "boolean", "description": "Assume a blade repair disposition is (true) or is not (false) in force."}}),
    _tool("run_sql", "Run one read-only SQLite SELECT over the shop tables listed in the system prompt, as of the current shop time. Use for anything the views do not answer: counts, filters, joins, history. now_ts() returns the shop time.", {"sql": {"type": "string", "description": "A single SELECT or WITH statement."}}, ["sql"]),
    _tool("search_documents", "Search the approved documents (job cards, maintenance instructions, inspection standards, quality and tool-control procedures, governance policy). Returns passages with document, page and section. Use for procedure, limits, policy and 'what does the manual say' questions.", {
        "query": {"type": "string", "description": "What to look for, in plain words."},
        "collection": {"type": "string", "description": "Optional: restrict to one collection by name."}}, ["query"]),
    _tool("render_chart", "Draw a chart from a read-only SQL query and show it with the answer. Use when the person asks for a chart, a comparison or a trend.", {
        "title": {"type": "string"}, "subtitle": {"type": "string"},
        "type": {"type": "string", "enum": list(CHART_TYPES)},
        "sql": {"type": "string", "description": "A single SELECT returning the rows to plot."},
        "x": {"type": "string", "description": "Column for the category or x axis."},
        "y": {"type": "array", "items": {"type": "string"}, "description": "One or more numeric columns to plot."},
        "stacked": {"type": "boolean"}}, ["title", "type", "sql", "x", "y"]),
    _tool("raise_tool_request", "Raise a tool handover request with Tool Control on the person's behalf. Creates a pending request only: the handover itself needs physical verification and both signatures.", {
        "tool_id": {"type": "string"}, "needed_at": {"type": "string", "description": "Where it is needed, such as Gate 1."},
        "reason": {"type": "string"}}, ["tool_id"]),
    _tool("draft_finding", "Record a draft inspection finding for the technician performing the task. A draft only: it is not accepted or dispositioned.", {
        "engine_id": _ENG, "component": {"type": "string"}, "description": {"type": "string", "description": "What was observed."},
        "zone": {"type": "string", "description": "Blade zone A, B or C, if it applies."},
        "measured_mm": {"type": "number", "description": "Measured depth in millimetres, if measured."}}, ["component", "description"]),
    _tool("prepare_deviation_package", "Assemble the evidence package for a finding (measurements, limits, standard, schedule impact) and route it to Engineering / Quality for disposition. It requests a decision; it does not make one.", {
        "finding_id": {"type": "string", "description": "Omit for the open finding on the engine."}}),
    _tool("submit_recovery_option", "Submit a recovery option (A, B or C) to its approving role for a decision. Creates a pending submission only.", {
        "engine_id": _ENG, "option": {"type": "string", "enum": ["A", "B", "C"]},
        "justification": {"type": "string"}}, ["option"]),
    _tool("confirm_job_step", "Record the technician's confirmation that a job card step is complete. Only after the work is released, and in step order.", {
        "job_card": _JC, "step_no": {"type": "integer", "minimum": 1}}, ["step_no"]),
    _tool("save_note", "Save a short note to the person's notebook.", {"text": {"type": "string"}}, ["text"]),
]
VIEW_NAMES = tuple(views.VIEWS)
ACTION_NAMES = ("raise_tool_request", "draft_finding", "prepare_deviation_package", "submit_recovery_option", "confirm_job_step", "save_note")
_BY_NAME = {t["name"]: t for t in SCHEMAS}

LABELS = {
    "engine_status": "Reading engine status", "delivery_risk": "Tracing the delivery risk", "forecast_changes": "Comparing against the earlier forecast",
    "recovery_plan": "Scheduling the recovery options", "protect_delivery": "Weighing the remaining levers", "job_card": "Opening the job card",
    "task_readiness": "Checking task readiness", "task_tools": "Checking the tool board", "tool_location": "Tracing tool custody",
    "inspection_finding": "Reading the inspection finding", "approval_authority": "Checking the approval authority matrix",
    "simulate_schedule": "Running the schedule what-if", "run_sql": "Querying shop data", "search_documents": "Searching the approved documents",
    "render_chart": "Drawing the chart", "raise_tool_request": "Raising the tool request", "draft_finding": "Recording the draft finding",
    "prepare_deviation_package": "Assembling the evidence package", "submit_recovery_option": "Submitting the option for approval",
    "confirm_job_step": "Recording the step confirmation", "save_note": "Saving the note",
}


# ─── Validation ──────────────────────────────────────────────────────────
_TYPES: dict[str, Callable[[Any], bool]] = {
    "string": lambda v: isinstance(v, str), "boolean": lambda v: isinstance(v, bool),
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "array": lambda v: isinstance(v, list),
}


def validate(name: str, args: Any) -> dict[str, Any]:
    """Check a tool input against its schema. Raises ToolError naming what is wrong."""
    spec = _BY_NAME.get(name)
    if spec is None:
        raise ToolError(f"There is no tool named {name}.")
    if not isinstance(args, dict):
        raise ToolError("The input must be a JSON object.")
    schema = spec["input_schema"]
    props = schema["properties"]
    clean: dict[str, Any] = {}
    for key, val in args.items():
        if key not in props:
            continue                                   # an extra key is dropped, not an error
        if val is None or val == "":
            continue
        kind = props[key]["type"]
        if kind in ("number", "integer") and isinstance(val, str) and re.fullmatch(r"-?\d+(\.\d+)?", val.strip()):
            val = float(val) if kind == "number" else int(float(val))
        if kind == "boolean" and isinstance(val, str) and val.lower() in ("true", "false"):
            val = val.lower() == "true"
        if not _TYPES[kind](val):
            raise ToolError(f"`{key}` must be a {kind}.")
        if "enum" in props[key] and val not in props[key]["enum"]:
            if isinstance(val, str) and val.upper() in props[key]["enum"]:
                val = val.upper()
            else:
                raise ToolError(f"`{key}` must be one of {', '.join(map(str, props[key]['enum']))}.")
        if kind == "array" and not all(isinstance(x, str) for x in val):
            raise ToolError(f"`{key}` must be a list of strings.")
        if isinstance(val, str):
            val = val.strip()[:4000]
        clean[key] = val
    missing = [k for k in schema["required"] if k not in clean]
    if missing:
        raise ToolError(f"Missing required input: {', '.join(missing)}.")
    return clean


# ─── Execution ───────────────────────────────────────────────────────────
def execute(name: str, args: Any, ctx: Context) -> tuple[dict[str, Any], bool]:
    """Run one tool. Returns (result for the model, is_error). Never raises."""
    t0 = time.perf_counter()
    call = {"name": name, "input": args if isinstance(args, dict) else {"_raw": str(args)[:300]}, "ok": True}
    try:
        clean = validate(name, args)
        call["input"] = clean
        if name in views.VIEWS:
            out = _view(name, clean, ctx)
        else:
            out = _HANDLERS[name](clean, ctx)
        result, is_error = out, False
    except ToolError as e:
        result, is_error = {"error": str(e)}, True
    except dataset.QueryError as e:
        result, is_error = {"error": str(e)}, True
    except Exception as e:                                # a bug in a tool must not end the answer
        result, is_error = {"error": f"The tool failed: {type(e).__name__}."}, True
        call["exception"] = f"{type(e).__name__}: {e}"[:300]
    call.update(ok=not is_error, ms=round((time.perf_counter() - t0) * 1000, 1), output=_brief(name, result))
    ctx.calls.append(call)
    return result, is_error


def detail(name: str, args: dict[str, Any]) -> str:
    """A short human label for what a call is about ("ENG-204", "T-117")."""
    for key in ("engine_id", "tool_id", "job_card", "finding_id", "option", "query", "title", "action"):
        v = args.get(key) if isinstance(args, dict) else None
        if v:
            return str(v)[:70]
    return ""


def _brief(name: str, result: dict) -> Any:
    """What the trace keeps of a result: enough to inspect, not the whole payload."""
    if "error" in result:
        return {"error": result["error"]}
    if name in views.VIEWS:
        return {"card": result.get("card"), "summary": result.get("summary")}
    if name == "run_sql":
        return {"columns": result["columns"], "row_count": result["row_count"], "rows": result["rows"][:8]}
    if name == "search_documents":
        return {"passages": [{k: p[k] for k in ("title", "page", "section")} for p in result["passages"]]}
    return result


def run_view(name: str, args: dict[str, Any], ctx: Context) -> tuple[str, dict]:
    """Run a view outside the model loop (pre-fetch, direct mode). Returns (handle, result)."""
    result = views.run(name, ctx.shop, **args)
    return ctx.add_view(result), result


def view_payload(handle: str, result: dict) -> dict[str, Any]:
    """A view result as the model reads it."""
    return {"card": handle if result.get("card") else None, "summary": result["summary"], "data": result["data"],
            "suggested_followups": result.get("followups") or [], "sources": result.get("sources") or []}


def _view(name: str, args: dict[str, Any], ctx: Context) -> dict[str, Any]:
    handle, result = run_view(name, args, ctx)
    return view_payload(handle, result)


def _run_sql(args: dict, ctx: Context) -> dict:
    out = ctx.snapshot().run(args["sql"])
    if out["row_count"] > MAX_SQL_ROWS_TO_MODEL:
        out = {**out, "rows": out["rows"][:MAX_SQL_ROWS_TO_MODEL], "row_count": MAX_SQL_ROWS_TO_MODEL, "truncated": True}
    return {**out, "shop_time": ctx.shop.now}


def _search(args: dict, ctx: Context) -> dict:
    hits = corpus.search(args["query"], collection=args.get("collection"), top_k=4)
    for h in hits:
        if not any(p["doc_id"] == h["doc_id"] and p["page"] == h["page"] and p["section"] == h["section"] for p in ctx.passages):
            ctx.passages.append(h)
    return {"passages": [{"document": h["title"], "doc_id": h["doc_id"], "collection": h["collection"], "title": h["title"],
                          "page": h["page"], "section": h["section"], "text": h["text"][:1400]} for h in hits],
            "note": None if hits else "Nothing in the approved documents matches. Say so rather than answering from general knowledge."}


def _chart(args: dict, ctx: Context) -> dict:
    out = ctx.snapshot().run(args["sql"], max_rows=MAX_CHART_ROWS)
    if not out["rows"]:
        raise ToolError("The query returned no rows, so there is nothing to plot.")
    x, ys = args["x"], args["y"]
    cols = out["columns"]
    for c in [x, *ys]:
        if c not in cols:
            raise ToolError(f"Column `{c}` is not in the query result. Columns: {', '.join(cols)}.")
    if not ys:
        raise ToolError("Give at least one y column.")
    for y in ys:
        if not all(isinstance(r[y], (int, float)) or r[y] is None for r in out["rows"]):
            raise ToolError(f"Column `{y}` is not numeric, so it cannot be plotted. Cast or aggregate it in the SQL.")
    if args["type"] == "pie" and len(ys) != 1:
        raise ToolError("A pie chart takes exactly one y column.")
    handle = f"chart_{len(ctx.charts) + 1}"
    ctx.charts[handle] = {"kind": "chart", "id": handle, "type": args["type"], "title": args["title"][:120],
                          "subtitle": (args.get("subtitle") or f"Shop time {nice(ctx.shop.clock)}")[:160],
                          "data": [{c: r[c] for c in [x, *ys]} for r in out["rows"]], "xKey": x, "yKeys": ys,
                          "stacked": bool(args.get("stacked"))}
    return {"card": handle, "rows_plotted": len(out["rows"]), "preview": out["rows"][:6],
            "note": f"The chart is ready. Show it by writing [[card:{handle}]] on its own line."}


# ─── Actions: pending records only ───────────────────────────────────────
def _who(ctx: Context) -> str:
    return f"{ctx.persona['title']} {ctx.persona['id']}"


def _record(ctx: Context, kind: str, title: str, detail_: dict, status: str) -> dict:
    rec = ctx.notebook.add(kind, title, detail_, by=_who(ctx), shop_time=ctx.shop.now, status=status)
    ctx.created.append(rec)
    return rec


def _require(ctx: Context, roles: tuple[str, ...], what: str) -> None:
    if ctx.persona["key"] not in roles:
        allowed = " or ".join(r.title() if r != "manager" else "Engine Shop Manager" for r in roles)
        raise ToolError(f"Not done. {what} is for the {allowed}; you are signed in as {ctx.persona['title']}. "
                        "Nothing was recorded. Offer to show the information instead, or name who to ask.")


def _engine(ctx: Context, engine_id: str | None) -> str:
    if engine_id:
        if not ctx.shop.engine(engine_id.upper()):
            raise ToolError(f"Engine {engine_id} is not in the shop records. Known: {', '.join(ctx.shop.engine_ids())}.")
        return engine_id.upper()
    return views._focus_engine(ctx.shop, None)


def _raise_tool_request(args: dict, ctx: Context) -> dict:
    tid = args["tool_id"].upper()
    st = ctx.shop.tool_state(tid)
    if not st:
        raise ToolError(f"Tool {args['tool_id']} is not in the tool register. Known: {', '.join(t['tool_id'] for t in ctx.shop.t['tools'])}.")
    if st["checked_in"]:
        raise ToolError(f"No request needed: {tid} is checked in at {st['location']} (custody record {st['custody_ts'] or 'home location'}). Nothing was recorded.")
    existing = ctx.notebook.find("tool_request", tool_id=tid)
    if existing:
        return {"status": "already_raised", "reference": existing["id"], "record": existing,
                "note": "This person already raised this request. No duplicate was created."}
    open_ref = (st["request"] or {}).get("note", "").split(":")[0] or None
    where = args.get("needed_at") or "Gate 1"
    rec = _record(ctx, "tool_request", f"Handover request for {tid} at {where}", {
        "tool_id": tid, "tool": st["tool"], "needed_at": where, "reason": args.get("reason") or "Required for the next task",
        "current_custodian": st["custodian"], "current_location": st["location"], "expected_available_ts": st["expected_available_ts"],
        "follows_up": open_ref, "routed_to": "Tool Control"},
        "Pending: Tool Control to verify the tool and both parties to sign the handover")
    return {"status": "raised", "reference": rec["id"], "record": rec, "existing_shop_request": open_ref,
            "note": "A request only. The tool has not moved and custody is unchanged until the handover is physically verified and signed (TC-003)."}


def _draft_finding(args: dict, ctx: Context) -> dict:
    _require(ctx, ("technician",), "Recording an inspection finding")
    eid = _engine(ctx, args.get("engine_id"))
    zone = (args.get("zone") or "").strip().upper()[:1]
    measured = args.get("measured_mm")
    assessment = None
    if zone and measured is not None:
        lim = next((l for l in ctx.shop.t["inspection_limits"] if l["zone"].upper().startswith(zone)), None)
        if lim:
            over = float(measured) > float(lim["limit_mm"])
            assessment = {"zone": lim["zone"], "limit_mm": lim["limit_mm"], "measured_mm": measured,
                          "result": "above limit" if over else "within limit", "reference": f"{lim['manual']}, {lim['reference']}",
                          "if_exceeded": lim["if_exceeded"] if over else None}
    rec = _record(ctx, "finding_draft", f"Draft finding on {eid}: {args['component']}", {
        "engine_id": eid, "component": args["component"], "description": args["description"], "zone": zone or None,
        "measured_mm": measured, "assessment": assessment, "routed_to": "Engineering / Quality"},
        "Draft: the technician signs it in the maintenance system; disposition is by Engineering / Quality")
    return {"status": "drafted", "reference": rec["id"], "record": rec,
            "note": "A draft only. It is not an accepted finding and no disposition has been made (QP-014 section 4.3)."}


def _deviation_package(args: dict, ctx: Context) -> dict:
    fid = (args.get("finding_id") or "").upper() or None
    findings = ctx.shop.t["findings"]
    finding = next((f for f in findings if f["finding_id"] == fid), None) if fid else (findings[-1] if findings else None)
    if not finding:
        draft = ctx.notebook.find("finding_draft")
        if fid or not draft:
            raise ToolError(f"There is no {'finding ' + fid if fid else 'recorded finding'} at shop time {nice(ctx.shop.clock)}, "
                            "so there is nothing to build an evidence package from. Nothing was recorded.")
        raise ToolError(f"Only a draft finding exists ({draft['id']}). The technician must sign the finding before an evidence package can be routed. Nothing was recorded.")
    existing = ctx.notebook.find("deviation_package", finding_id=finding["finding_id"])
    if existing:
        return {"status": "already_prepared", "reference": existing["id"], "record": existing, "note": "No duplicate was created."}
    v = views.inspection_finding(ctx.shop, finding_id=finding["finding_id"])["data"]
    fc = ctx.shop.forecast(finding["engine_id"])
    dispo = v.get("disposition")
    rec = _record(ctx, "deviation_package", f"Evidence package for {finding['finding_id']}", {
        "finding_id": finding["finding_id"], "engine_id": finding["engine_id"], "component": finding["component"], "serial": finding["serial"],
        "damage": finding["damage"], "measurements": v.get("zones"), "standard": finding["standard"],
        "schedule": {"committed": fc["committed_completion_ts"], "forecast": fc["predicted_completion_ts"], "variance_hours": fc["variance_hours"]},
        "existing_disposition": dispo, "routed_to": "Engineering / Quality (authorised under QP-014 section 4.2)"},
        "Routed to Engineering / Quality: decision pending")
    return {"status": "routed", "reference": rec["id"], "record": rec,
            "note": "The package requests a decision. Nothing is approved; only an authorised Engineering or Quality role can disposition the finding or grant a deviation."}


def _submit_option(args: dict, ctx: Context) -> dict:
    _require(ctx, ("manager", "supervisor"), "Submitting a recovery option")
    eid = _engine(ctx, args.get("engine_id"))
    plan = views.recovery_plan(ctx.shop, engine_id=eid)["data"]
    opt = next((o for o in plan.get("options") or [] if o["option"] == args["option"]), None)
    if not opt:
        raise ToolError(f"There is no recovery option {args['option']} open for {eid}. Nothing was recorded.")
    if ctx.persona["key"] == "supervisor" and args["option"] != "C":
        raise ToolError("Not done. A supervisor may put forward option C (re-sequencing), which is within the supervisor's authority. "
                        "Options A and B commit spend and are submitted by the Engine Shop Manager. Nothing was recorded.")
    status_lc = str(opt.get("status", "")).lower()
    if status_lc.startswith(("approved", "authorised")):
        return {"status": "already_approved", "option": opt, "note": "This option is already approved in the shop records. Nothing new was submitted."}
    existing = ctx.notebook.find("recovery_submission", engine_id=eid, option=args["option"])
    if existing:
        return {"status": "already_submitted", "reference": existing["id"], "record": existing, "note": "No duplicate was created."}
    rec = _record(ctx, "recovery_submission", f"Option {opt['option']} ({opt['title']}) for {eid}", {
        "engine_id": eid, "option": opt["option"], "title": opt["title"], "action": opt["action"],
        "predicted_completion_ts": opt["predicted_completion_ts"], "variance_hours": opt["variance_hours"], "cost_usd": opt["cost_usd"],
        "justification": args.get("justification"), "routed_to": opt["approval_required"]},
        f"Submitted to {opt['approval_required']}: decision pending")
    return {"status": "submitted", "reference": rec["id"], "record": rec,
            "note": f"Submitted for a decision by {opt['approval_required']}. It is not approved, and the forecast does not change until it is."}


def _confirm_step(args: dict, ctx: Context) -> dict:
    _require(ctx, ("technician",), "Confirming a job card step")
    jc = views._job_card(ctx.shop, args.get("job_card"))
    if not jc:
        raise ToolError(f"Job card {args.get('job_card')} is not in the shop records.")
    jid = jc["job_card"]
    steps = ctx.shop.rows("job_card_steps", job_card=jid)
    step = next((s for s in steps if s["step_no"] == args["step_no"]), None)
    if not step:
        raise ToolError(f"{jid} has steps 1 to {len(steps)}; there is no step {args['step_no']}.")
    release = ctx.shop.released(jid)
    if not release:
        blockers = [f"{c['check_name']} ({c['detail']})" for c in ctx.shop.readiness(jid) if c["state"] != "done"]
        raise ToolError(f"Not recorded. {jid} has not been released by the supervisor at shop time {nice(ctx.shop.clock)}"
                        + (f"; open checks: {'; '.join(blockers)}" if blockers else "") + ". No step can be confirmed before release.")
    done = {r["detail"]["step_no"] for r in ctx.notebook.of("step_confirmation") if r["detail"].get("job_card") == jid}
    if args["step_no"] in done:
        return {"status": "already_confirmed", "step_no": args["step_no"], "note": "This step is already confirmed in your notebook."}
    if any(n not in done for n in range(1, args["step_no"])):
        nxt = min(n for n in range(1, args["step_no"]) if n not in done)
        raise ToolError(f"Not recorded. Steps are confirmed in order and step {nxt} is not confirmed yet.")
    rec = _record(ctx, "step_confirmation", f"{jid} step {step['step_no']}: {step['title']}", {
        "job_card": jid, "step_no": step["step_no"], "title": step["title"], "confirmation": step["confirm"], "release": release["ref"]},
        "Recorded by the technician: certification of the task remains with certifying staff")
    nxt_step = next((s for s in steps if s["step_no"] == step["step_no"] + 1), None)
    return {"status": "confirmed", "reference": rec["id"], "record": rec,
            "next_step": {k: nxt_step[k] for k in ("step_no", "title", "instruction", "confirm")} if nxt_step else None,
            "note": "A step confirmation is the technician's record. It does not certify the work."}


def _save_note(args: dict, ctx: Context) -> dict:
    rec = _record(ctx, "note", args["text"][:80], {"text": args["text"][:2000]}, "Saved")
    return {"status": "saved", "reference": rec["id"]}


_HANDLERS: dict[str, Callable[[dict, Context], dict]] = {
    "run_sql": _run_sql, "search_documents": _search, "render_chart": _chart,
    "raise_tool_request": _raise_tool_request, "draft_finding": _draft_finding, "prepare_deviation_package": _deviation_package,
    "submit_recovery_option": _submit_option, "confirm_job_step": _confirm_step, "save_note": _save_note,
}


def to_json(result: dict) -> str:
    return json.dumps(result, default=str, ensure_ascii=False, separators=(",", ":"))
