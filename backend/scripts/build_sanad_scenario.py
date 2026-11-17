"""Write the Sanad MRO scenario dataset (backend/data/sanad/*.csv + schema.json).

A small, hand-authored and internally consistent shop: four engines in the command
centre, with ENG-204 (TF-35) at risk because part P-4582 slips, tool T-117 is in use
elsewhere and a fan blade finding needs a disposition. Everything that changes over
time is an EVENT with a timestamp, so the application can show the shop "as of" any
moment and the same question gets a different, correct answer as the day unfolds.

Nothing here is real Sanad data: engine types, serials, customers, suppliers, part and
tool numbers, people and documents are all fictional.

    python -m scripts.build_sanad_scenario
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "data" / "sanad"

TABLES: dict[str, dict] = {}


def table(name: str, description: str, columns: dict[str, str], rows: list[list], event_time: str | None = None):
    TABLES[name] = {"description": description, "columns": columns, "rows": rows, "event_time": event_time}


# ─── Masters ─────────────────────────────────────────────────────────────
table("engines", "Engines in the shop (the command-centre list). One row per engine.", {
    "engine_id": "Shop reference, e.g. ENG-204",
    "engine_type": "Engine model (fictional types TF-35, TF-50)",
    "esn": "Engine serial number",
    "customer": "Operator (fictional)",
    "workscope": "Overhaul, Performance restoration or Hospital visit",
    "induction_ts": "When the engine was inducted",
    "committed_tat_days": "Committed turnaround time in days",
    "committed_completion_ts": "Committed completion (delivery) date and time",
    "workstation": "Gate and bay where the engine is worked",
    "planned_hours": "Planned labour hours for the visit",
    "work_order": "Work order number",
}, [
    ["ENG-201", "TF-35", "ESN-326918", "Altair Airways", "Performance restoration", "2026-09-22 18:00", 45, "2026-11-06 18:00", "Gate 2, Core Module Bay", 610, "WO-2026-04388"],
    ["ENG-204", "TF-35", "ESN-327104", "Meridian Air", "Overhaul", "2026-09-24 18:00", 40, "2026-11-03 18:00", "Gate 1, Fan Module Bay", 540, "WO-2026-04417"],
    ["ENG-209", "TF-50", "ESN-510233", "Zephyr Airlines", "Overhaul", "2026-09-25 18:00", 50, "2026-11-14 18:00", "Gate 4, LPT Module Bay", 720, "WO-2026-04431"],
    ["ENG-215", "TF-35", "ESN-326771", "Borealis Airlines", "Hospital visit", "2026-09-26 18:00", 35, "2026-10-31 18:00", "Gate 5, Final Assembly", 430, "WO-2026-04452"],
])

table("schedule_tasks", "Remaining planned work per engine, as a task network. The forecast is computed from this plus the live events.", {
    "engine_id": "Engine",
    "task_id": "Task code, unique within the engine",
    "seq": "Order in the plan",
    "task": "What the task is",
    "duration_h": "Working hours needed",
    "calendar": "day = Gate day shift 07:30-17:30 (plus approved overtime); continuous = round-the-clock coverage",
    "depends_on": "Predecessor task_id (blank for none)",
    "needs": "External gate: part:<id> (must have arrived), tool:<id> (must be at the gate), release:<job card> (supervisor release)",
    "planned_start": "Earliest planned start (blank = as soon as predecessors finish)",
    "job_card": "Job card, where one applies",
    "resequence_saving_h": "Hours saved on this task when permitted preparatory work is re-sequenced",
    "disposition_extra_h": "Hours added to this task when a blade repair disposition is in force",
}, [
    ["ENG-204", "FBR", 1, "Fan blade removal and inspection", 14, "day", "", "tool:T-117;release:JC-FAN-204", "2026-10-28 07:30", "JC-FAN-204", 0, 0],
    ["ENG-204", "BLP", 2, "Blade processing: clean, NDT, repair, moment weigh, map", 110, "continuous", "FBR", "", "", "", 0, 8],
    ["ENG-204", "INS", 3, "P-4582 installation (fan retaining ring)", 2, "continuous", "BLP", "part:P-4582", "", "JC-FAN-231", 0, 0],
    ["ENG-204", "RFM", 4, "Fan module reassembly", 4, "continuous", "INS", "", "", "JC-FAN-232", 2, 0],
    ["ENG-204", "FTR", 5, "Final test and release", 4, "continuous", "RFM", "", "", "", 2, 0.5],
    ["ENG-201", "CMR", 1, "Core module reassembly", 60, "continuous", "", "", "2026-11-02 09:00", "", 0, 0],
    ["ENG-201", "FAS", 2, "Final assembly", 24, "continuous", "CMR", "", "", "", 0, 0],
    ["ENG-201", "FTR", 3, "Final test and release", 12, "continuous", "FAS", "", "", "", 0, 0],
    ["ENG-209", "LPR", 1, "LPT module repair", 120, "continuous", "", "", "2026-11-05 03:00", "", 0, 0],
    ["ENG-209", "MRA", 2, "Module reassembly", 48, "continuous", "LPR", "", "", "", 0, 0],
    ["ENG-209", "FAS", 3, "Final assembly", 24, "continuous", "MRA", "", "", "", 0, 0],
    ["ENG-209", "FTR", 4, "Final test and release", 12, "continuous", "FAS", "", "", "", 0, 0],
    ["ENG-215", "FAC", 1, "Final assembly close-up", 24, "continuous", "", "", "2026-10-29 06:00", "", 0, 0],
    ["ENG-215", "FTR", 2, "Final test and release", 10, "continuous", "FAC", "", "", "", 0, 0],
])

table("bay_slots", "Reserved workstation windows. The installation window is the booked fan-module reassembly slot.", {
    "engine_id": "Engine", "workstation": "Gate and bay", "activity": "What the slot is for",
    "window_start": "Slot opens", "window_end": "Slot closes (after this the bay is allocated to other work)",
}, [
    ["ENG-204", "Gate 1, Fan Module Bay", "Installation window: P-4582 fit and fan module reassembly", "2026-11-02 08:00", "2026-11-04 12:00"],
    ["ENG-215", "Gate 5, Final Assembly", "Final assembly and test cell slot", "2026-10-29 06:00", "2026-10-31 12:00"],
    ["ENG-201", "Gate 2, Core Module Bay", "Core module reassembly slot", "2026-11-02 09:00", "2026-11-05 12:00"],
    ["ENG-209", "Gate 4, LPT Module Bay", "LPT module repair slot", "2026-11-05 03:00", "2026-11-11 12:00"],
])

table("parts", "Part master for the parts that matter to the engines in the shop.", {
    "part_id": "Part number", "description": "What it is", "engine_type": "Engine model", "module": "Engine module",
    "note": "Why it matters",
}, [
    ["P-4582", "Fan retaining ring, front", "TF-35", "Fan module", "Required before fan module reassembly; no approved substitute"],
    ["P-2210", "Spinner O-ring set", "TF-35", "Fan module", "Replace on every spinner removal"],
    ["P-3391", "Fan blade lock plate", "TF-35", "Fan module", "Inspect and reuse within limits"],
    ["P-7714", "Annulus filler", "TF-35", "Fan module", "Inspect and reuse within limits"],
    ["P-6120", "LPT stage 2 seal segment", "TF-50", "LPT module", "On order for ENG-209"],
])

table("inventory", "Stock by location. ready_at_gate_ts is when a unit could be at the workstation if it is requested.", {
    "part_id": "Part number", "location": "Store", "on_hand": "Units on hand", "stock_status": "Serviceability / hold status",
    "ready_at_gate_ts": "Earliest time a unit could be at the gate, including any confirmation and transfer (blank if none on hand)",
    "transfer_cost_usd": "Cost of an authorised transfer", "approval_required": "Who must approve the use of this stock",
}, [
    ["P-4582", "Main Store AUH", 0, "No stock", "", "", ""],
    ["P-4582", "AUH-Satellite Store", 1, "Serviceable; available 28 Oct 2026; configuration confirmation required before issue", "2026-11-04 00:00", 300, "Inventory and configuration confirmation"],
    ["P-2210", "Gate 1 stores", 6, "Serviceable", "2026-10-28 08:00", 0, "None"],
    ["P-3391", "Main Store AUH", 14, "Serviceable", "2026-10-28 12:00", 0, "None"],
    ["P-7714", "Main Store AUH", 9, "Serviceable", "2026-10-28 12:00", 0, "None"],
    ["P-6120", "Main Store AUH", 0, "No stock", "", "", ""],
])

table("purchase_orders", "Open purchase orders for critical parts.", {
    "po_id": "Purchase order", "part_id": "Part", "qty": "Quantity", "supplier": "Supplier (fictional)",
    "engine_id": "Engine the part is for", "work_order": "Work order charged", "deliver_to": "Delivery point",
}, [
    ["PO-2026-11873", "P-4582", 1, "Halcyon Aero Components", "ENG-204", "WO-2026-04417", "Gate 1 receiving"],
    ["PO-2026-11902", "P-6120", 4, "Northfield Castings", "ENG-209", "WO-2026-04431", "Gate 4 receiving"],
])

table("po_events", "Purchase order history. The latest row per PO gives the current promised arrival.", {
    "ts": "When it happened", "po_id": "Purchase order", "event": "What happened",
    "promised_arrival_ts": "Promised arrival at the delivery point after this event", "note": "Detail", "source": "Who or what recorded it",
}, [
    ["2026-10-12 10:15", "PO-2026-11873", "Order confirmed", "2026-11-03 12:00", "Standard freight to Gate 1 receiving", "Procurement"],
    ["2026-10-28 08:40", "PO-2026-11873", "Delivery date updated", "2026-11-04 20:00", "Supplier rescheduled dispatch; arrival moved from 3 Nov 12:00 to 4 Nov 20:00", "Supplier portal"],
    ["2026-10-28 11:05", "PO-2026-11873", "Expedite approved", "2026-11-03 10:00", "Priority air freight under EXQ-0592; expedite fee USD 2,400 recorded against WO-2026-04417", "Procurement"],
    ["2026-10-28 11:20", "PO-2026-11873", "Shipped, in transit", "2026-11-03 10:00", "Airway bill issued; expected at Gate 1", "Logistics"],
    ["2026-10-20 09:30", "PO-2026-11902", "Order confirmed", "2026-11-04 12:00", "Standard freight to Gate 4 receiving", "Procurement"],
], event_time="ts")

table("supplier_quotes", "Expedite quotations received from suppliers.", {
    "ts": "When the quote was received", "quote_ref": "Quotation reference", "po_id": "Purchase order", "option": "What is offered",
    "arrival_ts": "Arrival at the delivery point if accepted", "fee_usd": "Expedite fee", "valid_until": "Quote validity",
}, [
    ["2026-10-28 09:05", "EXQ-0592", "PO-2026-11873", "Priority air freight", "2026-11-03 10:00", 2400, "2026-10-28 16:00"],
], event_time="ts")

table("tools", "Tool master.", {
    "tool_id": "Tool number", "tool": "Name", "used_for": "Purpose", "calibration_required": "1 if the tool is calibrated",
    "calibration_due": "Calibration valid to (blank if not required)", "home_location": "Where it normally lives",
}, [
    ["T-117", "Fan blade extractor", "Pulling each blade out of its disk slot", 1, "2027-01-15", "Main tool crib"],
    ["T-208", "Lock plate removal tool", "Releasing the blade retaining lock plates", 0, "", "Gate 1 tool board"],
    ["T-063", "Torque wrench, 50-250 lbf-in", "Removing and refitting the spinner fasteners", 1, "2026-12-12", "Gate 1 tool board"],
    ["T-311", "Blade support fixture", "Supporting the blade so the root is not damaged", 0, "", "Gate 1 tool board"],
    ["T-529", "Padded blade storage rack", "Keeping the removed blades in slot order", 0, "", "Gate 1 bay"],
    ["K-014", "Protective cover kit", "Covering the fan case liner, spinner and adjacent blades", 0, "", "Gate 1 stores"],
    ["T-402", "Borescope kit", "Internal visual inspection", 1, "2026-11-20", "Gate 3 bench"],
    ["T-615", "Moment weighing rig", "Blade moment weighing", 1, "2027-03-02", "Gate 3 bench"],
])

table("job_card_tools", "Tools each job card calls for.", {
    "job_card": "Job card", "section": "Section of the job card", "tool_id": "Tool",
}, [["JC-FAN-204", 2, t] for t in ("T-117", "T-208", "T-063", "T-311", "T-529", "K-014")])

table("tool_events", "Tool custody and sighting history. A camera detection is a sighting, not a custody change.", {
    "ts": "When it happened", "tool_id": "Tool", "event": "Issued, Camera detection, Tool request raised, Handover signed or Checked in",
    "location": "Where the tool was at this event", "custodian": "Who holds custody after this event", "source": "Record that says so",
    "expected_available_ts": "For an issue: when the tool is expected back", "note": "Detail",
}, [
    ["2026-10-27 16:00", "T-208", "Checked in", "Gate 1 tool board", "Gate 1 tool board", "Tool control", "", ""],
    ["2026-10-27 16:00", "T-063", "Checked in", "Gate 1 tool board", "Gate 1 tool board", "Tool control", "", "Calibration label in date"],
    ["2026-10-27 16:00", "T-311", "Checked in", "Gate 1 tool board", "Gate 1 tool board", "Tool control", "", ""],
    ["2026-10-27 16:00", "T-529", "Checked in", "Gate 1 bay", "Gate 1 bay", "Tool control", "", ""],
    ["2026-10-27 16:00", "K-014", "Checked in", "Gate 1 stores", "Gate 1 stores", "Tool control", "", ""],
    ["2026-10-27 07:22", "T-117", "Issued", "Gate 3", "TEC-1187", "Issuance log", "2026-10-28 13:00", "Issued from the main tool crib for a spare fan module task (JC-FAN-198)"],
    ["2026-10-28 09:12", "T-117", "Camera detection", "Gate 3 bench", "TEC-1187", "Gate 3 bench camera", "2026-10-28 13:00", "Detection only; custody unchanged"],
    ["2026-10-28 09:20", "T-117", "Tool request raised", "Gate 3 bench", "TEC-1187", "Tool control", "2026-10-28 13:00", "TR-2026-0718: requested at Gate 1 for JC-FAN-204 by TEC-1142"],
    ["2026-10-28 12:50", "T-117", "Handover signed", "Gate 3 bench", "SUP-0210", "Tool control", "", "Identity label verified at the bench; custody signed over by TEC-1187"],
    ["2026-10-28 12:58", "T-117", "Checked in", "Gate 1 tool board", "Gate 1 tool board", "Tool control", "", "Arrival recorded at Gate 1; calibration label in date"],
    ["2026-10-26 14:00", "T-402", "Checked in", "Gate 3 bench", "Gate 3 bench", "Tool control", "", ""],
    ["2026-10-26 14:00", "T-615", "Checked in", "Gate 3 bench", "Gate 3 bench", "Tool control", "", ""],
], event_time="ts")

table("job_cards", "Approved job cards.", {
    "job_card": "Job card number", "title": "Task", "revision": "Latest approved revision", "status": "Approval status",
    "engine_id": "Engine", "module": "Module", "key_care_point": "The care point the job card stresses",
    "est_hours": "Estimated working hours for the crew", "crew": "Technicians needed", "document": "Source document title",
}, [
    ["JC-FAN-204", "Engine fan blade removal", "C", "Approved", "ENG-204", "Fan module", "Avoid damaging the O-ring and adjacent parts", 14, 2, "JC-FAN-204 Fan Blade Removal, Revision C"],
    ["JC-FAN-231", "Install fan retaining ring P-4582", "B", "Approved", "ENG-204", "Fan module", "Fit only a ring with confirmed configuration", 2, 2, "Approved Maintenance Instructions: Fan Module, Revision C"],
    ["JC-FAN-232", "Fan module reassembly", "C", "Approved", "ENG-204", "Fan module", "Refit blades in mapped slot order", 4, 2, "Approved Maintenance Instructions: Fan Module, Revision C"],
])

table("job_card_steps", "The steps of each job card, in order.", {
    "job_card": "Job card", "step_no": "Step number", "title": "Step title", "instruction": "What to do", "confirm": "What to confirm before moving on",
}, [
    ["JC-FAN-204", 1, "Verify before starting", "Confirm the work is released, revision C is at the work stand, and all six tools are on the Gate 1 tool board, including T-117.", "Release, revision and tools confirmed"],
    ["JC-FAN-204", 2, "Protect the work area", "Fit the protective cover kit (K-014) over the fan case liner, spinner and adjacent blades. Position the padded blade storage rack (T-529) beside the stand.", "Covers fitted and rack in position"],
    ["JC-FAN-204", 3, "Remove the spinner", "Remove the spinner fasteners with the torque wrench (T-063) in the sequence shown. Lift the spinner clear without touching the O-ring seat. Bag and tag the fasteners and discard the O-ring.", "Spinner removed; O-ring seat undamaged"],
    ["JC-FAN-204", 4, "Release the lock plates", "Release the blade retaining lock plates with the lock plate removal tool (T-208), one blade position at a time. Do not lever against the disk.", "Lock plates released and tagged by position"],
    ["JC-FAN-204", 5, "Extract the blades", "Support each blade with the blade support fixture (T-311) and pull it from its disk slot with the fan blade extractor (T-117). Place each blade on the rack in slot order.", "All blades on the rack in slot order"],
    ["JC-FAN-204", 6, "Inspect and record", "Inspect each blade against Inspection Standards Manual Chapter 72, Revision F, Table 72-21-3. Record any finding with depth, length and position. Do not disposition a finding.", "Inspection recorded; findings raised"],
])

table("readiness_events", "Readiness checks for a job card. The latest row per check gives its current state.", {
    "ts": "When the state was recorded", "job_card": "Job card", "check_no": "Check number (1-6)", "check_name": "The readiness check",
    "detail": "Current detail", "owner": "Who owns the check", "state": "done, blocked or pending",
}, [
    ["2026-10-27 15:00", "JC-FAN-204", 1, "Work authorisation", "Required before release", "Supervisor", "done"],
    ["2026-10-27 15:05", "JC-FAN-204", 2, "Job card JC-FAN-204", "Available, revision C", "Planning", "done"],
    ["2026-10-27 15:10", "JC-FAN-204", 3, "Technician qualification", "Confirmed for fan blade task", "Training records", "done"],
    ["2026-10-27 15:15", "JC-FAN-204", 4, "Tool T-117", "Planned from the main tool crib", "Tool control", "pending"],
    ["2026-10-27 15:15", "JC-FAN-204", 5, "Work area", "Gate 1 bay reserved", "Supervisor", "pending"],
    ["2026-10-27 15:15", "JC-FAN-204", 6, "Safety precautions", "To confirm before start", "Technician", "pending"],
    ["2026-10-28 09:20", "JC-FAN-204", 4, "Tool T-117", "Not at Gate 1, tool request raised", "Tool control", "blocked"],
    ["2026-10-28 12:58", "JC-FAN-204", 4, "Tool T-117", "Checked in at the Gate 1 tool board; calibration in date", "Tool control", "done"],
    ["2026-10-28 12:59", "JC-FAN-204", 5, "Work area", "Gate 1 bay confirmed clear", "Supervisor", "done"],
    ["2026-10-28 13:00", "JC-FAN-204", 6, "Safety precautions", "Confirmed at start by TEC-1142", "Technician", "done"],
], event_time="ts")

table("approvals", "Decisions recorded by authorised people. The assistant never creates rows here.", {
    "ts": "When the decision was recorded", "ref": "Reference", "kind": "expedite, work_release, overtime, resequence or disposition",
    "subject": "What was decided", "decision": "The decision", "decided_by": "Role that decided", "engine_id": "Engine",
    "work_order": "Work order charged, if any", "amount_usd": "Amount, if any", "window_start": "For overtime: start", "window_end": "For overtime: end",
}, [
    ["2026-10-28 11:05", "EXQ-0592", "expedite", "Recovery option B: expedite the supplier shipment of P-4582", "Approved", "Procurement, with logistics confirmation", "ENG-204", "WO-2026-04417", 2400, "", ""],
    ["2026-10-28 13:00", "WR-2026-2204", "work_release", "Work release for JC-FAN-204 at Gate 1", "Released", "Supervisor SUP-0210", "ENG-204", "", "", "", ""],
    ["2026-10-28 13:10", "OT-2026-0311", "overtime", "Overtime for two technicians at Gate 1 to complete fan blade removal", "Approved", "Engine Shop Manager MGR-0107", "ENG-204", "WO-2026-04417", "", "2026-10-28 17:30", "2026-10-29 03:00"],
    ["2026-10-28 13:20", "RSQ-0147", "resequence", "Recovery option C: re-sequence permitted preparatory work", "Authorised", "Supervisor SUP-0210", "ENG-204", "", 0, "", ""],
    ["2026-10-29 08:30", "DEV-2026-0093", "disposition", "Finding FND-2026-0412: blend repair to repair scheme RS-72-21-08, then re-inspection", "Disposition issued", "Quality Engineer QE-0318 (Engineering / Quality)", "ENG-204", "", "", "", ""],
], event_time="ts")

table("disposition_dependencies", "What a finding disposition adds to the plan.", {
    "ts": "When the dependency was created", "ref": "Disposition reference", "kind": "process or material",
    "dependency": "What is now needed", "where": "Gate or store", "state": "Current state",
}, [
    ["2026-10-29 08:30", "DEV-2026-0093", "process", "Blend repair to RS-72-21-08 and FPI re-inspection of blade M3-204-12-78", "Gate 3 inspection slot, 30 Oct 10:00-18:00 (moved 2 h, within tolerance)", "Scheduled"],
    ["2026-10-29 08:30", "DEV-2026-0093", "material", "Leading-edge blend kit BK-72-08", "Gate 3 stores, 3 on hand", "Available"],
], event_time="ts")

table("task_events", "Actual task progress recorded on the shop floor.", {
    "ts": "When it happened", "engine_id": "Engine", "task_id": "Task code", "event": "Started or Completed", "note": "Detail",
}, [
    ["2026-10-28 13:00", "ENG-204", "FBR", "Started", "Fan blade removal started at Gate 1 (JC-FAN-204)"],
    ["2026-10-29 03:00", "ENG-204", "FBR", "Completed", "All blades removed and inspected; one finding raised"],
], event_time="ts")

table("progress_log", "Labour hours booked per engine. The latest row per engine gives hours completed.", {
    "ts": "When booked", "engine_id": "Engine", "hours_completed": "Cumulative labour hours completed",
}, [
    ["2026-10-27 17:30", "ENG-201", 402], ["2026-10-28 17:30", "ENG-201", 421], ["2026-10-29 09:00", "ENG-201", 426],
    ["2026-10-27 17:30", "ENG-204", 380], ["2026-10-28 08:00", "ENG-204", 388], ["2026-10-28 17:30", "ENG-204", 397],
    ["2026-10-29 03:00", "ENG-204", 416], ["2026-10-29 09:00", "ENG-204", 419],
    ["2026-10-27 17:30", "ENG-209", 318], ["2026-10-28 17:30", "ENG-209", 337], ["2026-10-29 09:00", "ENG-209", 342],
    ["2026-10-27 17:30", "ENG-215", 371], ["2026-10-28 17:30", "ENG-215", 389], ["2026-10-29 09:00", "ENG-215", 394],
], event_time="ts")

table("engine_stage_events", "Repair stage history. The latest row per engine gives the current stage.", {
    "ts": "When the stage changed", "engine_id": "Engine", "repair_stage": "Stage", "current_process": "What is happening now",
}, [
    ["2026-10-25 08:00", "ENG-201", "Repair, Core Module", "Core module repair; reassembly from 2 Nov"],
    ["2026-10-26 08:00", "ENG-204", "Disassembly, Fan Module", "Fan module disassembly; fan blade removal next (JC-FAN-204)"],
    ["2026-10-28 13:00", "ENG-204", "Disassembly, Fan Module", "Fan blade removal in progress (JC-FAN-204)"],
    ["2026-10-29 03:00", "ENG-204", "Inspection, Fan Blades", "Blade cleaning, NDT and repair; P-4582 fit and reassembly from 3 Nov"],
    ["2026-10-24 08:00", "ENG-209", "Inspection, LPT Module", "LPT module inspection; repair from 5 Nov"],
    ["2026-10-27 08:00", "ENG-215", "Assembly, Final", "Final assembly; test cell run from 30 Oct"],
], event_time="ts")

table("findings", "Inspection findings raised on the shop floor.", {
    "ts": "When recorded", "finding_id": "Finding reference", "engine_id": "Engine", "job_card": "Job card it was found under",
    "component": "Component", "serial": "Component serial number", "damage": "Type of damage", "recorded_by": "Who recorded it",
    "standard": "Standard it was assessed against",
}, [
    ["2026-10-28 15:40", "FND-2026-0412", "ENG-204", "JC-FAN-204", "Fan 1 blade", "M3-204-12-78", "Leading-edge scratch", "TEC-1142", "Inspection Standards Manual, Chapter 72, Revision F, Table 72-21-3"],
], event_time="ts")

table("finding_measurements", "Measurements taken for each finding, by blade zone.", {
    "finding_id": "Finding", "zone": "Blade zone letter", "zone_name": "Zone name", "location": "Where on the blade",
    "result_mm": "Measured scratch depth in mm", "limit_mm": "Serviceable limit in mm for this zone",
}, [
    ["FND-2026-0412", "A", "Tip", "Leading edge, outer span", 0.14, 0.25],
    ["FND-2026-0412", "B", "Mid-span", "Leading edge, mid span", 0.80, 0.25],
    ["FND-2026-0412", "C", "Root", "Leading edge, inner span", 0.22, 0.25],
])

table("inspection_limits", "Serviceable limits from the Inspection Standards Manual.", {
    "manual": "Manual", "reference": "Chapter, revision and table", "component": "Component", "damage": "Damage type",
    "zone": "Blade zone", "limit_mm": "Serviceable limit in mm", "if_exceeded": "What the manual requires when the limit is exceeded",
}, [
    ["Inspection Standards Manual", "Chapter 72, Revision F, Table 72-21-3", "Fan 1 blade", "Leading-edge scratch", "A (tip)", 0.25, "Measure depth, length and position; raise a finding; disposition by Engineering / Quality"],
    ["Inspection Standards Manual", "Chapter 72, Revision F, Table 72-21-3", "Fan 1 blade", "Leading-edge scratch", "B (mid-span)", 0.25, "Measure depth, length and position; raise a finding; disposition by Engineering / Quality"],
    ["Inspection Standards Manual", "Chapter 72, Revision F, Table 72-21-3", "Fan 1 blade", "Leading-edge scratch", "C (root)", 0.25, "Measure depth, length and position; raise a finding. A crack at the blade base requires rejection regardless of scratch size"],
])

table("staff", "People in the scenario, by role identifier. No personal names are held.", {
    "staff_id": "Role identifier", "role": "Role", "area": "Where they work", "qualifications": "Relevant qualifications",
    "assigned_job_card": "Job card they are assigned to, if any", "assigned_engine": "Engine they are assigned to, if any",
}, [
    ["MGR-0107", "Engine Shop Manager", "Command centre", "Shop management; overtime authorisation", "", ""],
    ["SUP-0210", "Supervisor", "Gates 1-3", "Work release; re-sequencing of permitted preparatory work", "", "ENG-204"],
    ["TEC-1142", "Technician", "Gate 1", "TF-35 fan blade removal and inspection", "JC-FAN-204", "ENG-204"],
    ["TEC-1163", "Technician", "Gate 1", "TF-35 fan module", "JC-FAN-204", "ENG-204"],
    ["TEC-1187", "Technician", "Gate 3", "TF-35 fan module; spare module repair", "JC-FAN-198", ""],
    ["QE-0318", "Quality Engineer", "Engineering / Quality", "Deviation and disposition authority under QP-014", "", ""],
    ["PRC-0044", "Procurement Lead", "Procurement", "Supplier expedite spend", "", ""],
    ["LOG-0061", "Logistics Coordinator", "Logistics", "Freight confirmation", "", ""],
])

table("approval_matrix", "Who may approve what, from the Approval Authority Matrix (QP-014).", {
    "action": "The action or decision", "authority": "Role that may approve it", "cannot_approve": "Roles that may not",
    "reference": "Where it is written",
}, [
    ["Deviation or concession", "Authorised Engineering or Quality role", "Technician; Supervisor; Sanad Digital Assistant", "QP-014 section 4.2"],
    ["Acceptance or disposition of a finding", "Authorised Engineering or Quality role", "Technician; Supervisor; Sanad Digital Assistant", "QP-014 section 4.3"],
    ["Certification of work", "Certifying staff", "Anyone else; Sanad Digital Assistant", "QP-014 section 4.5"],
    ["Release of an engine", "Certifying staff with Quality release", "Anyone else; Sanad Digital Assistant", "QP-014 section 4.6"],
    ["Work release at a workstation", "Supervisor", "Technician; Sanad Digital Assistant", "QP-014 section 5.1"],
    ["Overtime", "Engine Shop Manager", "Supervisor; Technician; Sanad Digital Assistant", "QP-014 section 5.3"],
    ["Supplier expedite spend", "Procurement, with logistics confirmation", "Shop roles; Sanad Digital Assistant", "QP-014 section 6.1"],
    ["Alternate stock transfer", "Inventory control, with configuration confirmation", "Shop roles; Sanad Digital Assistant", "QP-014 section 6.2"],
    ["Re-sequencing of permitted preparatory work", "Supervisor", "Technician; Sanad Digital Assistant", "QP-014 section 5.2"],
    ["Tool custody handover", "Releasing custodian and receiving person, both signing", "Camera detection alone; Sanad Digital Assistant", "TC-003 section 3.4"],
])


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob("*.csv"):
        old.unlink()
    schema = {
        "note": "Scenario data set for the Sanad MRO Intelligence Hub.",
        "scenario_start": "2026-10-28 09:30",
        "tables": {},
    }
    for name, t in TABLES.items():
        with (OUT / f"{name}.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(list(t["columns"].keys()))
            for row in t["rows"]:
                assert len(row) == len(t["columns"]), (name, row)
                w.writerow(row)
        schema["tables"][name] = {"description": t["description"], "columns": t["columns"],
                                  **({"event_time": t["event_time"]} if t["event_time"] else {})}
    (OUT / "schema.json").write_text(json.dumps(schema, indent=2) + "\n")
    print(f"wrote {len(TABLES)} tables to {OUT}")
    for name, t in TABLES.items():
        print(f"  {name:22s} {len(t['rows']):3d} rows" + ("  (events)" if t["event_time"] else ""))


if __name__ == "__main__":
    main()
