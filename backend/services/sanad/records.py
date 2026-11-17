"""What the assistant has raised on a person's behalf: requests, drafts and notes.

Everything here is pending. Raising a handover request does not move a tool; a draft
finding is not an accepted finding; an evidence package is not an approval. The shop
state changes only through the records of the authorised roles (see ops), which is
the point: decisions remain with authorised personnel.

Records are kept per browser, so one tester's requests do not appear in another's
notebook. The store is held by the engine and persisted with the conversations.
"""
from __future__ import annotations

import time
from typing import Any

PREFIX = {"tool_request": "THR", "finding_draft": "FDR", "deviation_package": "DEP",
          "recovery_submission": "RSB", "step_confirmation": "JCS", "note": "NOTE", "answer": "ANS"}
LABEL = {"tool_request": "Tool handover request", "finding_draft": "Draft inspection finding",
         "deviation_package": "Deviation evidence package", "recovery_submission": "Recovery option submission",
         "step_confirmation": "Job card step confirmation", "note": "Note", "answer": "Saved answer"}
MAX_PER_OWNER = 200


class Notebook:
    """One owner's records. `items` is the list persisted by the engine."""

    def __init__(self, items: list[dict] | None = None):
        self.items: list[dict] = items if items is not None else []

    def add(self, kind: str, title: str, detail: dict[str, Any], *, by: str, shop_time: str, status: str) -> dict:
        n = 1 + sum(1 for r in self.items if r["kind"] == kind)
        rec = {"id": f"{PREFIX.get(kind, 'REC')}-{n:04d}", "kind": kind, "label": LABEL.get(kind, kind), "title": title,
               "detail": detail, "by": by, "shop_time": shop_time, "status": status,
               "created": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
        self.items.append(rec)
        del self.items[:-MAX_PER_OWNER]
        return rec

    def find(self, kind: str, **match: Any) -> dict | None:
        for r in reversed(self.items):
            if r["kind"] == kind and all(r["detail"].get(k) == v for k, v in match.items()):
                return r
        return None

    def of(self, kind: str) -> list[dict]:
        return [r for r in self.items if r["kind"] == kind]

    def remove(self, record_id: str) -> bool:
        before = len(self.items)
        self.items[:] = [r for r in self.items if r["id"] != record_id]
        return len(self.items) != before

    def clear(self) -> None:
        self.items.clear()


def since(record: dict, shop: Any) -> str:
    """What the shop records show has happened, since a record was raised, to the thing it asked for.
    The record itself stays as it was raised; this is said beside it so the two are never read as a contradiction."""
    d = record.get("detail") or {}
    try:
        if record["kind"] == "tool_request":
            st = shop.tool_state(d.get("tool_id", ""))
            if st and st["checked_in"] and st.get("custody_ts", "") > record["shop_time"]:
                return f"Since then the shop records show the tool checked in at {st['location']} ({st['custody_ts']})."
        elif record["kind"] == "recovery_submission":
            kind = {"A": "stock_transfer", "B": "expedite", "C": "resequence"}.get(d.get("option"))
            done = [a for a in shop.approvals(d.get("engine_id"), kind) if a["ts"] > record["shop_time"]] if kind else []
            if done:
                a = done[-1]
                return f"Since then the shop records show a decision: {a['decision'].lower()} by {a['decided_by']} at {a['ts']} ({a['ref']})."
        elif record["kind"] in ("deviation_package", "finding_draft"):
            done = [a for a in shop.approvals(d.get("engine_id"), "disposition") if a["ts"] > record["shop_time"]]
            if done and record["kind"] == "deviation_package":
                a = done[-1]
                return f"Since then the shop records show a disposition: {a['ref']} by {a['decided_by']} at {a['ts']}."
    except Exception:                                    # a note beside a record must never break an answer
        return ""
    return "Still pending."
