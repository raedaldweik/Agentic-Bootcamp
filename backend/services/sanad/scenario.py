"""Who is asking, and when: the personas and the moments of the demonstration day.

The three personas are the roles in the scenario. Each carries the questions that
role would naturally ask, shown as one-click prompts. The moments are points on the
shop clock worth jumping to; the clock can also be set to any other time.
"""
from __future__ import annotations

from typing import Any

from . import ops

PERSONAS: dict[str, dict[str, Any]] = {
    "manager": {
        "key": "manager", "id": "MGR-0107", "title": "Engine Shop Manager", "short": "Manager", "initials": "MG",
        "blurb": "Monitors engine status, identifies delivery risks, evaluates recovery options and tracks the approved recovery plan.",
        "authority": "May authorise overtime. Cannot approve deviations, accept findings, certify work or release an engine.",
        "suggestions": [
            {"tag": "STATUS", "title": "Status of all engines", "prompt": "Show me the status of all the engines."},
            {"tag": "RISK", "title": "Primary risk to ENG-204", "prompt": "What is the primary risk to ENG-204?"},
            {"tag": "CHANGE", "title": "What changed since yesterday", "prompt": "What has changed on ENG-204 since yesterday?"},
            {"tag": "RECOVERY", "title": "Recovery plan for P-4582", "prompt": "Generate a recovery plan for component P-4582."},
            {"tag": "APPROVAL", "title": "Has the option been approved?", "prompt": "Has the recovery option been approved?"},
            {"tag": "PROGRESS", "title": "Updated status and recovery", "prompt": "Show me the updated engine status and recovery progress."},
        ],
    },
    "technician": {
        "key": "technician", "id": "TEC-1142", "title": "Technician", "short": "Technician", "initials": "TE",
        "blurb": "Gets step-by-step guidance for fan blade removal, checks tool readiness and records the inspection finding.",
        "authority": "Records findings and confirms job card steps. Cannot release work, disposition findings or approve deviations.",
        "suggestions": [
            {"tag": "GUIDE", "title": "Start fan blade removal", "prompt": "I need to start the fan blade removal task. Please guide me."},
            {"tag": "READY", "title": "Can I start now?", "prompt": "Can I start fan blade removal now?"},
            {"tag": "TOOLS", "title": "Tools for this step", "prompt": "Which tools does this step need?"},
            {"tag": "STEPS", "title": "Step-by-step guidance", "prompt": "Guide me through the fan blade removal step by step."},
            {"tag": "LIMITS", "title": "Leading-edge scratch limits", "prompt": "What are the inspection limits for a leading-edge scratch on a fan blade?"},
            {"tag": "FINDING", "title": "Show the blade finding", "prompt": "Show me the inspection finding on ENG-204."},
        ],
    },
    "supervisor": {
        "key": "supervisor", "id": "SUP-0210", "title": "Supervisor", "short": "Supervisor", "initials": "SU",
        "blurb": "Locates the missing tool, tracks the updated forecast and protects the committed delivery date.",
        "authority": "Releases work and authorises re-sequencing of permitted preparatory work. Cannot approve deviations, overtime or spend.",
        "suggestions": [
            {"tag": "TOOL", "title": "Where is T-117?", "prompt": "Where is tool T-117?"},
            {"tag": "CUSTODY", "title": "Still at Gate 3?", "prompt": "Is the tool still at Gate 3?"},
            {"tag": "DEVIATION", "title": "Can I approve a deviation?", "prompt": "Can I approve a deviation so the work can continue?"},
            {"tag": "PROTECT", "title": "Protect the delivery date", "prompt": "What is now the best way to protect the committed delivery date?"},
            {"tag": "WHAT IF", "title": "If the part is 4 hours late", "prompt": "What if P-4582 arrives four hours later than promised?"},
            {"tag": "STATUS", "title": "Status of all engines", "prompt": "Show me the status of all the engines."},
        ],
    },
}
DEFAULT_PERSONA = "manager"

MOMENTS: list[dict[str, str]] = [
    {"id": "m1", "ts": "2026-10-28 09:30", "label": "Morning review", "detail": "The P-4582 delivery has just slipped"},
    {"id": "m2", "ts": "2026-10-28 11:30", "label": "Recovery approved", "detail": "Option B was approved at 11:05"},
    {"id": "m3", "ts": "2026-10-28 12:15", "label": "Ready to start?", "detail": "T-117 is not at Gate 1 yet"},
    {"id": "m4", "ts": "2026-10-28 13:30", "label": "Work released", "detail": "T-117 checked in, overtime approved"},
    {"id": "m5", "ts": "2026-10-28 16:00", "label": "Finding recorded", "detail": "Blade scratch above limit in zone B"},
    {"id": "m6", "ts": "2026-10-29 10:00", "label": "Plan reassessed", "detail": "Disposition issued, engine back on track"},
]

CLOCK_MIN, CLOCK_MAX = "2026-10-27 16:00", "2026-10-30 12:00"      # the period the shop records cover

AGENT = {"id": "sanad-data-agent", "name": "SANAD_data_agent",
         "description": "Sanad Digital Assistant: engine status, delivery risk, recovery planning, job cards, tools, findings and approvals"}


def persona(key: str | None) -> dict[str, Any]:
    return PERSONAS.get((key or "").lower()) or PERSONAS[DEFAULT_PERSONA]


def clock(ts: str | None):
    """A requested shop time, or the start of the scenario."""
    return ops.parse(ts) or ops.scenario_start()


def public() -> dict[str, Any]:
    """What the chat needs to draw the persona and shop-time controls."""
    return {
        "title": "Sanad MRO Intelligence Hub",
        "personas": [{k: p[k] for k in ("key", "id", "title", "short", "initials", "blurb", "suggestions")} for p in PERSONAS.values()],
        "defaultPersona": DEFAULT_PERSONA,
        "moments": [{**m, "nice": ops.nice(ops.parse(m["ts"]))} for m in MOMENTS],
        "defaultMoment": MOMENTS[0]["ts"],
        "clock": {"min": CLOCK_MIN, "max": CLOCK_MAX, "minNice": ops.nice(ops.parse(CLOCK_MIN), with_year=False), "maxNice": ops.nice(ops.parse(CLOCK_MAX), with_year=False)},
        "note": "Synthetic demonstration data. Not Sanad operational data.",
    }
