"""The shop as of a moment, and the schedule that follows from it.

`Shop(clock)` is everything recorded up to `clock`: the masters, plus every event
whose timestamp is not later. From that it derives the current state the way a
planning system would: where each tool is, what each purchase order now promises,
which readiness checks are complete, and, by scheduling each engine's remaining
tasks forward, when the engine will be finished.

The forecast is computed, not stored, so "what if the part arrives a day later?"
is the same calculation with one input changed.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta
from functools import lru_cache
from typing import Any

from . import dataset

FMT = "%Y-%m-%d %H:%M"
DAY_START, DAY_END = time(7, 30), time(17, 30)   # Gate day shift
WATCH_HOURS = 6.0                                # later than commitment by up to this is "Watch", beyond it "At risk"


def parse(ts: Any) -> datetime | None:
    if isinstance(ts, datetime):
        return ts
    if not ts:
        return None
    s = str(ts).strip().replace("T", " ")
    for f in (FMT, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:19] if f.endswith("%S") else s[:16] if f == FMT else s[:10], f)
        except ValueError:
            continue
    return None


def stamp(dt: datetime | None) -> str:
    return dt.strftime(FMT) if dt else ""


def nice(dt: datetime | None, *, with_year: bool = True) -> str:
    """3 Nov 2026 18:00"""
    if not dt:
        return ""
    return f"{dt.day} {dt.strftime('%b')}{' ' + str(dt.year) if with_year else ''} {dt.strftime('%H:%M')}"


def hours_text(h: float) -> str:
    """36 h, 90 min, 1.5 h"""
    a = abs(h)
    if a < 2 and abs(a * 60 - round(a * 60)) < 1e-6 and (a * 60) % 30 == 0 and a != 1:
        return f"{int(round(a * 60))} min"
    return f"{a:g} h" if abs(a - round(a, 1)) < 1e-9 else f"{a:.1f} h"


_PROPER = {"Gate"}                   # words that keep their capital mid-sentence ("Gate 1 bay reserved")


def lc_first(text: str) -> str:
    """Lower the first letter for mid-sentence use, unless the word is an identifier or acronym (P-4582, FPI)."""
    if not text:
        return text
    first = text.split(" ", 1)[0]
    if len(first) > 1 and (first.isupper() or any(ch.isdigit() for ch in first)):
        return text
    if first in _PROPER:
        return text
    return text[0].lower() + text[1:]


def uc_first(text: str) -> str:
    """Capital first letter, the rest untouched (str.capitalize would lower-case ids such as RS-72-21-08)."""
    return text[:1].upper() + text[1:]


def scenario_start() -> datetime:
    return parse(dataset.raw().get("scenario_start")) or datetime(2026, 10, 28, 9, 30)


# ─── Working time ────────────────────────────────────────────────────────
def add_work(start: datetime, hours: float, calendar: str, overtime: list[tuple[datetime, datetime]]) -> datetime:
    """When `hours` of work starting at `start` is finished on `calendar`."""
    if hours <= 0:
        return start
    if calendar != "day":
        return start + timedelta(hours=hours)
    remaining = timedelta(hours=hours)
    t = start
    for _ in range(400):                       # far more days than any plan here
        day = t.date()
        windows = [(datetime.combine(day, DAY_START), datetime.combine(day, DAY_END))]
        windows += [(a, b) for a, b in overtime if a.date() == day or b.date() == day]
        windows = _merge(windows)
        for a, b in windows:
            if b <= t:
                continue
            begin = max(a, t)
            if begin + remaining <= b:
                return begin + remaining
            remaining -= b - begin
            t = b
        nxt = datetime.combine(day + timedelta(days=1), time(0, 0))
        t = max(t, nxt) if t < nxt else t
        if t.date() == day:                    # overtime ran past midnight: continue from where it ended
            t = nxt
    return t


def _merge(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for a, b in sorted(windows):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


# ─── The shop as of a moment ─────────────────────────────────────────────
class Shop:
    def __init__(self, clock: datetime | str | None = None):
        self.clock: datetime = parse(clock) or scenario_start()
        self.now = stamp(self.clock)
        raw = dataset.raw()
        self.note = raw.get("note", "")
        self.t: dict[str, list[dict]] = {}
        for name, tab in raw["tables"].items():
            col = tab.get("event_time")
            rows = tab["rows"]
            if col:
                rows = [r for r in rows if (r.get(col) or "") <= self.now]
                rows = sorted(rows, key=lambda r: r.get(col) or "")
            self.t[name] = rows
        self._forecasts: dict[str, dict] = {}

    # -- lookups -----------------------------------------------------------
    def rows(self, table: str, **eq: Any) -> list[dict]:
        return [r for r in self.t.get(table, []) if all(r.get(k) == v for k, v in eq.items())]

    def one(self, table: str, **eq: Any) -> dict | None:
        found = self.rows(table, **eq)
        return found[0] if found else None

    def latest(self, table: str, **eq: Any) -> dict | None:
        found = self.rows(table, **eq)
        return found[-1] if found else None

    def engine(self, engine_id: str) -> dict | None:
        return self.one("engines", engine_id=(engine_id or "").upper())

    def engine_ids(self) -> list[str]:
        return [e["engine_id"] for e in self.t["engines"]]

    # -- supply ------------------------------------------------------------
    def part_supply(self, part_id: str, engine_id: str | None = None) -> dict | None:
        """The open purchase order for a part and what it currently promises."""
        for po in self.t["purchase_orders"]:
            if po["part_id"] != part_id or (engine_id and po["engine_id"] != engine_id):
                continue
            events = self.rows("po_events", po_id=po["po_id"])
            if not events:
                continue
            last = events[-1]
            # what the supplier promised before any recovery action on the order
            plain = [e for e in events if not e["event"].lower().startswith(("expedite", "shipped"))]
            return {**po, "promised_arrival_ts": last["promised_arrival_ts"], "status": last["event"],
                    "last_update_ts": last["ts"], "note": last["note"],
                    "unrecovered_arrival_ts": (plain[-1] if plain else last)["promised_arrival_ts"],
                    "events": events}
        return None

    # -- tools -------------------------------------------------------------
    def tool_state(self, tool_id: str) -> dict | None:
        tool = self.one("tools", tool_id=tool_id)
        if not tool:
            return None
        events = self.rows("tool_events", tool_id=tool_id)
        custody = [e for e in events if e["event"] in ("Issued", "Handover signed", "Checked in")]
        last_custody = custody[-1] if custody else None
        sightings = [e for e in events if e["event"] == "Camera detection"]
        expected = next((e["expected_available_ts"] for e in reversed(events) if e.get("expected_available_ts")), None)
        location = last_custody["location"] if last_custody else tool["home_location"]
        checked_in = bool(last_custody and last_custody["event"] == "Checked in")
        cal_due = parse(tool["calibration_due"])
        return {
            **tool,
            "location": location,
            "custodian": last_custody["custodian"] if last_custody else tool["home_location"],
            "custody_event": last_custody["event"] if last_custody else "At home location",
            "custody_ts": last_custody["ts"] if last_custody else "",
            "custody_source": last_custody["source"] if last_custody else "Tool control",
            "checked_in": checked_in or not last_custody,
            "last_sighting": sightings[-1] if sightings else None,
            "sighting_is_latest": bool(sightings and (not last_custody or sightings[-1]["ts"] > last_custody["ts"])),
            "expected_available_ts": None if checked_in else expected,
            "request": next((e for e in reversed(events) if e["event"] == "Tool request raised"), None),
            "calibration_ok": (not tool["calibration_required"]) or bool(cal_due and cal_due >= self.clock),
            "events": events,
        }

    def tool_ready_at(self, tool_id: str, gate: str, fallback: datetime) -> datetime:
        """When the tool is (or is expected to be) at `gate`."""
        st = self.tool_state(tool_id)
        if not st:
            return fallback
        if st["location"].lower().startswith(gate.lower()) and st["checked_in"]:
            return parse(st["custody_ts"]) or fallback
        exp = parse(st["expected_available_ts"])
        return exp or max(fallback, self.clock)

    # -- approvals ---------------------------------------------------------
    def approvals(self, engine_id: str | None = None, kind: str | None = None) -> list[dict]:
        return [a for a in self.t["approvals"]
                if (not engine_id or a["engine_id"] == engine_id) and (not kind or a["kind"] == kind)]

    def overtime_windows(self, engine_id: str) -> list[tuple[datetime, datetime]]:
        out = []
        for a in self.approvals(engine_id, "overtime"):
            s, e = parse(a["window_start"]), parse(a["window_end"])
            if s and e:
                out.append((s, e))
        return out

    # -- readiness ---------------------------------------------------------
    def readiness(self, job_card: str) -> list[dict]:
        latest: dict[int, dict] = {}
        for r in self.rows("readiness_events", job_card=job_card):
            latest[r["check_no"]] = r
        return [latest[k] for k in sorted(latest)]

    def released(self, job_card: str) -> dict | None:
        for a in self.t["approvals"]:
            if a["kind"] == "work_release" and job_card in a["subject"]:
                return a
        return None

    # -- the forecast ------------------------------------------------------
    def forecast(self, engine_id: str, **what_if: Any) -> dict:
        """Schedule the engine's remaining tasks forward and report when it finishes.

        what_if (all optional): part_arrival {part_id: datetime}, tool_available {tool_id: datetime},
        overtime (bool), resequence (bool), disposition (bool).
        """
        if not what_if and engine_id in self._forecasts:
            return self._forecasts[engine_id]
        eng = self.engine(engine_id)
        if not eng:
            raise KeyError(engine_id)
        gate = eng["workstation"].split(",")[0]
        committed = parse(eng["committed_completion_ts"])
        ot = self.overtime_windows(engine_id)
        if what_if.get("overtime") is False:
            ot = []
        elif what_if.get("overtime") is True and not ot:
            day = (self.clock if self.clock.time() < DAY_END else self.clock + timedelta(days=1)).date()
            ot = [(datetime.combine(day, DAY_END), datetime.combine(day + timedelta(days=1), time(7, 30)))]
        reseq = what_if["resequence"] if what_if.get("resequence") is not None else bool(self.approvals(engine_id, "resequence"))
        dispo = what_if["disposition"] if what_if.get("disposition") is not None else bool(self.approvals(engine_id, "disposition"))

        ends: dict[str, datetime] = {}
        tasks_out: list[dict] = []
        for task in sorted(self.rows("schedule_tasks", engine_id=engine_id), key=lambda r: r["seq"]):
            actual = {e["event"]: parse(e["ts"]) for e in self.rows("task_events", engine_id=engine_id, task_id=task["task_id"])}
            start = parse(task["planned_start"]) or datetime.min
            held_by = "plan" if task["planned_start"] else ""
            if task["depends_on"] and task["depends_on"] in ends and ends[task["depends_on"]] >= start:
                start, held_by = ends[task["depends_on"]], f"task:{task['depends_on']}"
            for need in [n for n in (task["needs"] or "").split(";") if n]:
                kind, _, ref = need.partition(":")
                when: datetime | None = None
                if kind == "part":
                    when = (what_if.get("part_arrival") or {}).get(ref)
                    if when is None:
                        sup = self.part_supply(ref, engine_id)
                        when = parse(sup["promised_arrival_ts"]) if sup else None
                elif kind == "tool":
                    when = (what_if.get("tool_available") or {}).get(ref) or self.tool_ready_at(ref, gate, start)
                elif kind == "release":
                    rel = self.released(ref)
                    when = parse(rel["ts"]) if rel else None      # not yet released: released as soon as the rest is ready
                if when and when > start:
                    start, held_by = when, need
            duration = float(task["duration_h"])
            if reseq:
                duration -= float(task["resequence_saving_h"] or 0)
            if dispo:
                duration += float(task["disposition_extra_h"] or 0)
            if "Started" in actual:
                start = actual["Started"]
            elif task["needs"] and start < self.clock and "Completed" not in actual:
                # an externally gated task that could have started but has no start recorded begins now
                start, held_by = self.clock, held_by or "now"
            end = actual.get("Completed") or add_work(start, duration, task["calendar"], ot)
            ends[task["task_id"]] = end
            state = ("done" if "Completed" in actual or end <= self.clock
                     else "in progress" if "Started" in actual or start <= self.clock else "planned")
            tasks_out.append({"task_id": task["task_id"], "task": task["task"], "start_ts": stamp(start), "end_ts": stamp(end),
                              "duration_h": duration, "calendar": task["calendar"], "state": state,
                              "held_by": held_by, "job_card": task["job_card"] or ""})

        predicted = max(ends.values()) if ends else committed
        variance = round((predicted - committed).total_seconds() / 3600, 2)
        status = "On track" if variance <= 0 else "Watch" if variance <= WATCH_HOURS else "At risk"
        result = {
            "engine_id": engine_id, "committed_completion_ts": stamp(committed), "predicted_completion_ts": stamp(predicted),
            "variance_hours": variance, "status": status, "tasks": tasks_out,
            "driver": self._driver(engine_id, tasks_out, what_if),
            "inputs": {"overtime": bool(ot), "resequenced": reseq, "disposition_in_force": dispo},
        }
        if not what_if:
            self._forecasts[engine_id] = result
        return result

    def _driver(self, engine_id: str, tasks: list[dict], what_if: dict) -> dict | None:
        """Walk back from the last task to the external gate that sets the finish date."""
        by_id = {t["task_id"]: t for t in tasks}
        t = tasks[-1] if tasks else None
        while t:
            held = t["held_by"]
            if held.startswith("task:"):
                t = by_id.get(held[5:])
                continue
            kind, _, ref = held.partition(":")
            if kind == "part":
                when = (what_if.get("part_arrival") or {}).get(ref)
                sup = self.part_supply(ref, engine_id)
                part = self.one("parts", part_id=ref) or {}
                when_ts = stamp(when) if when else (sup or {}).get("promised_arrival_ts", "")
                after = next((x["task"] for x in tasks if x["held_by"] == f"task:{t['task_id']}"), t["task"])
                return {"kind": "part", "ref": ref, "description": part.get("description", ""), "task": t["task"], "when_ts": when_ts,
                        "text": f"Component {ref} ({lc_first(part.get('description', 'part'))}) is due {nice(parse(when_ts))} "
                                f"and is required before {lc_first(after.split(':')[0])}"}
            if kind == "tool":
                tool = self.one("tools", tool_id=ref) or {}
                return {"kind": "tool", "ref": ref, "description": tool.get("tool", ""), "task": t["task"], "when_ts": t["start_ts"],
                        "text": f"Tool {ref} ({lc_first(tool.get('tool', 'tool'))}) is required for {lc_first(t['task'].split(':')[0])}"}
            if kind == "release":
                return {"kind": "release", "ref": ref, "task": t["task"], "when_ts": t["start_ts"],
                        "text": f"The work release for {ref} is required for {lc_first(t['task'].split(':')[0])}"}
            return {"kind": "plan", "ref": t["task_id"], "task": t["task"], "when_ts": t["start_ts"],
                    "text": f"The planned sequence sets the finish, from {lc_first(t['task'].split(':')[0])}"}
        return None

    # -- derived views -----------------------------------------------------
    def engine_status(self, engine_id: str) -> dict:
        eng = self.engine(engine_id)
        fc = self.forecast(engine_id)
        stage = self.latest("engine_stage_events", engine_id=engine_id) or {}
        prog = self.latest("progress_log", engine_id=engine_id) or {}
        status = fc["status"]
        if status == "On track" and self.was_off_track(engine_id):
            status = "Back on track"
        return {**eng, "status": status, "predicted_completion_ts": fc["predicted_completion_ts"],
                "variance_hours": fc["variance_hours"], "driver": (fc["driver"] or {}).get("text", ""),
                "repair_stage": stage.get("repair_stage", ""), "current_process": stage.get("current_process", ""),
                "hours_completed": prog.get("hours_completed", 0)}

    def trigger_times(self, engine_id: str) -> list[tuple[datetime, str]]:
        """Moments at which this engine's forecast may have been recalculated, with why."""
        eng = self.engine(engine_id)
        out: list[tuple[datetime, str]] = []
        pos = {p["po_id"] for p in self.t["purchase_orders"] if p["engine_id"] == engine_id}
        for e in self.t["po_events"]:
            if e["po_id"] in pos and e["event"] != "Order confirmed":
                out.append((parse(e["ts"]), f"{e['po_id']}: {e['event'].lower()} ({e['note']})"))
        for a in self.approvals(engine_id):
            out.append((parse(a["ts"]), f"{a['ref']}: {a['subject']} ({a['decision'].lower()} by {a['decided_by'].replace(' (', ', ').replace(')', '')})"))
        tools = {n.split(":")[1] for t in self.rows("schedule_tasks", engine_id=engine_id) for n in (t["needs"] or "").split(";") if n.startswith("tool:")}
        for e in self.t["tool_events"]:
            if e["tool_id"] in tools and e["event"] in ("Issued", "Handover signed", "Checked in"):
                out.append((parse(e["ts"]), f"Tool {e['tool_id']}: {e['event'].lower()} ({e['note']})"))
        for e in self.rows("task_events", engine_id=engine_id):
            out.append((parse(e["ts"]), f"{e['task_id']}: {e['event'].lower()} ({e['note']})"))
        return sorted([x for x in out if x[0]], key=lambda x: x[0])

    def forecast_history(self, engine_id: str) -> list[dict]:
        """The forecast after each trigger, keeping only the moments it actually moved."""
        out: list[dict] = []
        first = Shop(scenario_start() - timedelta(days=2))
        prev = first.forecast(engine_id)
        out.append({"ts": first.now, "why": "Plan baseline", "predicted_completion_ts": prev["predicted_completion_ts"],
                    "variance_hours": prev["variance_hours"], "status": prev["status"]})
        for when, why in self.trigger_times(engine_id):
            fc = _shop_at(stamp(when)).forecast(engine_id)
            if fc["predicted_completion_ts"] != out[-1]["predicted_completion_ts"]:
                out.append({"ts": stamp(when), "why": why, "predicted_completion_ts": fc["predicted_completion_ts"],
                            "variance_hours": fc["variance_hours"], "status": fc["status"]})
        return out

    def was_off_track(self, engine_id: str) -> bool:
        return any(h["variance_hours"] > WATCH_HOURS for h in self.forecast_history(engine_id)[:-1])

    # -- tables for ad-hoc SQL ----------------------------------------------
    def sql_tables(self) -> dict[str, list[dict]]:
        """Everything recorded so far, plus the derived current-state tables."""
        tables = dict(self.t)
        status, sched = [], []
        for eid in self.engine_ids():
            st = self.engine_status(eid)
            status.append({k: st[k] for k in ("engine_id", "engine_type", "esn", "customer", "status", "committed_completion_ts",
                                               "predicted_completion_ts", "variance_hours", "driver", "repair_stage",
                                               "current_process", "hours_completed", "planned_hours", "workstation")})
            for t in self.forecast(eid)["tasks"]:
                sched.append({"engine_id": eid, **{k: t[k] for k in ("task_id", "task", "start_ts", "end_ts", "duration_h", "state", "held_by", "job_card")}})
        tables["engine_status"] = status
        tables["engine_schedule"] = sched
        tool_rows = []
        for tool in self.t["tools"]:
            st = self.tool_state(tool["tool_id"])
            tool_rows.append({"tool_id": st["tool_id"], "tool": st["tool"], "location": st["location"], "custodian": st["custodian"],
                              "custody_event": st["custody_event"], "custody_ts": st["custody_ts"],
                              "last_camera_sighting_ts": (st["last_sighting"] or {}).get("ts", ""),
                              "expected_available_ts": st["expected_available_ts"] or "",
                              "calibration_due": st["calibration_due"] or "", "calibration_ok": int(st["calibration_ok"])})
        tables["tool_status"] = tool_rows
        tables["part_supply"] = [
            {k: s[k] for k in ("po_id", "part_id", "engine_id", "supplier", "promised_arrival_ts", "status", "last_update_ts", "work_order")}
            for s in (self.part_supply(po["part_id"], po["engine_id"]) for po in self.t["purchase_orders"]) if s]
        tables["readiness_status"] = [
            {k: r[k] for k in ("job_card", "check_no", "check_name", "detail", "owner", "state")}
            for jc in {r["job_card"] for r in self.t["readiness_events"]} for r in self.readiness(jc)]
        return tables

    def snapshot(self) -> dataset.Snapshot:
        return dataset.Snapshot(self.sql_tables(), now=self.now)


@lru_cache(maxsize=256)
def _shop_at(ts: str) -> Shop:
    return Shop(ts)


def shop(clock: datetime | str | None = None) -> Shop:
    """A shop state for a moment. Cached per minute: the data on disk does not change."""
    return _shop_at(stamp(parse(clock) or scenario_start()))


DERIVED_TABLES = {
    "engine_status": ("Current status of every engine, computed from the schedule: one row per engine.", {
        "engine_id": "", "engine_type": "", "esn": "", "customer": "", "status": "On track, Watch, At risk or Back on track",
        "committed_completion_ts": "", "predicted_completion_ts": "Forecast completion from the schedule",
        "variance_hours": "Predicted minus committed, in hours (positive = late)", "driver": "What sets the finish date",
        "repair_stage": "", "current_process": "", "hours_completed": "", "planned_hours": "", "workstation": ""}),
    "engine_schedule": ("The forecast schedule of each engine's remaining tasks.", {
        "engine_id": "", "task_id": "", "task": "", "start_ts": "", "end_ts": "", "duration_h": "", "state": "done, in progress or planned",
        "held_by": "What sets this task's start: plan, task:<id>, part:<id>, tool:<id>, release:<job card> or now", "job_card": ""}),
    "tool_status": ("Where each tool is now, from the custody record.", {
        "tool_id": "", "tool": "", "location": "Location from the last custody record", "custodian": "", "custody_event": "",
        "custody_ts": "", "last_camera_sighting_ts": "A sighting only, not custody", "expected_available_ts": "",
        "calibration_due": "", "calibration_ok": "1 if in date or not required"}),
    "part_supply": ("What each open purchase order currently promises.", {
        "po_id": "", "part_id": "", "engine_id": "", "supplier": "", "promised_arrival_ts": "", "status": "Latest PO event",
        "last_update_ts": "", "work_order": ""}),
    "readiness_status": ("Current state of each job card's readiness checks.", {
        "job_card": "", "check_no": "", "check_name": "", "detail": "", "owner": "", "state": "done, blocked or pending"}),
}
for _n, (_d, _c) in DERIVED_TABLES.items():
    dataset.declare_columns(_n, list(_c.keys()))


def describe_schema() -> str:
    """The tables as the agent reads them. Stable text: it does not depend on the clock."""
    out: list[str] = []
    raw = dataset.raw()["tables"]
    for name, (desc, cols) in DERIVED_TABLES.items():
        out.append(f"TABLE {name} (computed): {desc}")
        out.extend(f"  - {c}" + (f": {n}" if n else "") for c, n in cols.items())
        out.append("")
    for name, t in raw.items():
        ev = f" Event table: only rows up to the current shop time are visible (time column {t['event_time']})." if t.get("event_time") else ""
        out.append(f"TABLE {name}: {t['description']}{ev}")
        out.extend(f"  - {c} {t['kinds'][c]}" + (f": {n}" if n else "") for c, n in t["columns"].items())
        out.append("")
    return "\n".join(out).strip()
