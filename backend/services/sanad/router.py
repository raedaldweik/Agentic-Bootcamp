"""Guess which views a question needs, without a language model.

Used twice. Before the model is called, the likely views are fetched (it takes
milliseconds) and handed to it, so most answers need one model call instead of two.
And when no model is connected, the same guess picks the view that answers.

It is a hint, never a gate: the model still has every tool and ignores a wrong guess.
"""
from __future__ import annotations

import re
from typing import Any

from .ops import Shop

_ENG = re.compile(r"\beng(?:ine)?[\s\-]*#?(\d{3})\b", re.I)
_PART = re.compile(r"\bp[\s\-]*(\d{4})\b", re.I)
_TOOL = re.compile(r"\b([tk])[\s\-]*(\d{3})\b", re.I)
_JC = re.compile(r"\bjc[\s\-]*([a-z]{2,4})[\s\-]*(\d{3})\b", re.I)

# (view, pattern, strong). First match per view counts; order is priority.
_RULES: list[tuple[str, str, bool]] = [
    ("approval_authority", r"\b(deviation|concession|waiver)\b", True),
    ("approval_authority", r"\b(who (can|may|is allowed to|approves?|authoris\w+|signs?)|can i (approve|authoris\w+|sign off|release|certif\w+|accept)|am i allowed|allowed to approve|approval authority|authority matrix)\b", True),
    ("tool_location", r"\b(where('s| is| are)?|locate|location of|find|track down|still at|who has|missing)\b.*\b(tool|extractor|t[\s\-]?\d{3}|k[\s\-]?\d{3}|it)\b", True),
    ("tool_location", r"\b(tool|t[\s\-]?\d{3})\b.*\b(where|still|gate 3|location|custody|handover|camera)\b", True),
    ("task_tools", r"\b(which|what|list)\b.*\btools?\b|\btools? (do|does|are|is) .*(need|required)|\btools? (needed|required)\b", True),
    ("task_readiness", r"\b(can i|may i|are we|am i|is it) .*\b(start|begin|go ahead|proceed)\b|\bready (to|for)\b|\breadiness\b|\bgood to go\b|\bok(ay)? to start\b|\bstart .* now\b", True),
    ("job_card", r"\b(guide me|step[\s\-]by[\s\-]step|walk me|how do i|how to|procedure|instructions?|job card|next step|what('s| is) step|steps?)\b|\bneed to start\b|\bplease guide\b", True),
    ("inspection_finding", r"\b(finding|scratch|blade (damage|inspection)|inspection (result|finding|limit)|limits?\b.*(scratch|blade|leading)|zone [abc]\b|leading[\s\-]edge|disposition)", True),
    ("recovery_plan", r"\b(recovery (plan|option)|recover\b|options?\b.*(part|component|late)|generate .*plan|expedite|alternate stock|re-?sequenc)", True),
    ("recovery_plan", r"\b(approved|approval)\b.*\b(recovery|option|plan|expedite)\b|\b(recovery|option|plan|expedite)\b.*\b(approved|approval)\b", True),
    ("protect_delivery", r"\b(protect|safeguard|best way|keep (the )?(date|commitment)|hold (the )?(date|commitment)|back on track|stay on track)\b", True),
    ("forecast_changes", r"\b(changed|what('s| has) changed|since (yesterday|this morning|last)|what happened|moved the (forecast|date)|difference)\b", True),
    ("engine_status", r"\b(recovery progress|updated (engine )?status)\b", True),
    ("delivery_risk", r"\b(primary|main|biggest|top|key|greatest)\b.*\brisks?\b|\brisks? (to|for|on)\b|\bat risk\b|\bwhy (is|are)\b.*\b(late|delayed|at risk|behind)\b", True),
    ("engine_status", r"\bstatus of\b.*\bengines?\b|\ball (the |our )?engines\b|\bengines? status\b|\bhow (is|are) (the )?(engines?|eng[\s\-]?\d{3})\b", True),
    ("delivery_risk", r"\b(risk|at risk|why (is|are).*(late|delayed)|delay(ed)?|late\b|threat|biggest (problem|issue)|critical path|blocker)\b", False),
    ("engine_status", r"\b(status|overview|all (the )?engines|how (is|are) (the )?(engine|shop)|command cent(re|er)|dashboard|engines?\b.*\b(doing|look)|on track|next release|when will)\b", False),
]
_WHAT_IF = re.compile(r"\b(what if|suppose|assuming|if (the |we |it |p[\s\-]?\d|t[\s\-]?\d)|would happen|simulate|scenario where)\b", re.I)
_DOCS = re.compile(r"\b(what (does|do)|according to|per the|as per|in the|under the|where does)\b.*\b(procedure|manual|policy|standard|document|matrix|instructions?|process)\b|\bsay(s)? about\b|\bdefin(e|ition)\b|\bwhat is (a|an|the) (concession|deviation|disposition|watch status)\b", re.I)
_WIDE = re.compile(r"^\s*(how many|how much|count|list)\b|\b(number of|across the shop|in the shop|every (tool|part|engine)|"
                   r"all (the |our )?(tools|parts|purchase orders|orders|approvals|job cards|findings|staff))\b|\bcalibrat", re.I)
_ACTION = re.compile(r"^\s*(please\s+)?(raise|record|log|prepare|submit|create|save|file|open|draft|route|send|request|confirm)\b", re.I)


def entities(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    m = _ENG.search(text)
    if m:
        out["engine_id"] = f"ENG-{m.group(1)}"
    m = _PART.search(text)
    if m:
        out["part_id"] = f"P-{m.group(1)}"
    m = _TOOL.search(text)
    if m:
        out["tool_id"] = f"{m.group(1).upper()}-{m.group(2)}"
    m = _JC.search(text)
    if m:
        out["job_card"] = f"JC-{m.group(1).upper()}-{m.group(2)}"
    return out


def match(question: str, shop: Shop, persona: dict[str, Any], history: list[str] | None = None, limit: int = 2) -> list[dict[str, Any]]:
    """[{view, args, strong}] for the views this question most likely needs, best first."""
    q = (question or "").lower()
    if not q.strip() or _ACTION.match(q):
        return []                       # an instruction to do something: let the model use its action tools
    found = entities(question)
    # carry the subject over from earlier turns ("is it still at Gate 3?")
    for earlier in reversed(history or []):
        for k, v in entities(earlier).items():
            if _known(k, v, shop):      # a subject is carried over only if it exists: "ENG-999" must not follow the person around
                found.setdefault(k, v)
    if _WHAT_IF.search(q):
        return []                       # needs parameters only the model can read out of the sentence
    if _DOCS.search(q):
        return []                       # a question about what a document says: search, do not guess a view
    if _WIDE.search(q):
        return []                       # a count or a list across the shop: a single view would narrow it
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for view, pattern, strong in _RULES:
        if view in seen or not re.search(pattern, q):
            continue
        seen.add(view)
        picked.append({"view": view, "args": _args(view, found, question, shop), "strong": strong})
    picked.sort(key=lambda p: not p["strong"])
    return picked[:limit]


def _args(view: str, found: dict[str, str], question: str, shop: Shop) -> dict[str, Any]:
    eng = found.get("engine_id")
    if not eng and found.get("part_id"):
        eng = next((p["engine_id"] for p in shop.t["purchase_orders"] if p["part_id"] == found["part_id"]), None)
    if view in ("engine_status",):
        # "all the engines" is the overview even when an engine was discussed earlier
        return {"engine_id": eng} if eng and not re.search(r"\ball\b|\bengines\b|overview", question.lower()) else {}
    if view in ("delivery_risk", "forecast_changes", "recovery_plan", "protect_delivery"):
        return {"engine_id": eng} if eng else {}
    if view in ("job_card", "task_readiness", "task_tools"):
        return {"job_card": found["job_card"]} if found.get("job_card") else {}
    if view == "tool_location":
        return {"tool_id": found.get("tool_id") or _missing_tool(shop) or "T-117"}
    if view == "inspection_finding":
        return {"engine_id": eng} if eng else {}
    if view == "approval_authority":
        return {"action": question}
    return {}


def _known(kind: str, value: str, shop: Shop) -> bool:
    table, column = {"engine_id": ("engines", "engine_id"), "tool_id": ("tools", "tool_id"), "job_card": ("job_cards", "job_card"),
                     "part_id": ("parts", "part_id")}[kind]
    return any(row[column] == value for row in shop.t[table])


def _missing_tool(shop: Shop) -> str | None:
    for row in shop.t["job_card_tools"]:
        st = shop.tool_state(row["tool_id"])
        if st and not st["checked_in"]:
            return row["tool_id"]
    return None
