"""Business rules: who is eligible for diabetes outreach, who is excluded, and at what
priority and channel. The third box of the composite-AI triad.

The model (box 2) ranks risk; it never decides. These rules decide, the way a rule set in
SAS Intelligent Decisioning would: deterministic, readable, auditable, first match wins.
Nothing here sends anything: the output is a *staged* plan (box 5) that waits at the human
checkpoint (box 6) before it becomes the approved list (box 7).
"""
from __future__ import annotations

from typing import Any

RULE_SET = {
    "id": "OUTREACH_ELIGIBILITY_v1",
    "name": "Diabetes outreach: eligibility, exclusions and thresholds",
    "inputs": ["consent_status", "age", "hba1c_latest", "hba1c_days_since_test", "care_gap_count",
               "admissions_12mo", "adherence_pdc", "risk (model probability, 12 months)"],
    "outputs": ["eligible", "excluded_by", "priority", "channel", "rule_fired", "reason"],
    "rules": [
        {"id": "X1", "kind": "exclusion", "when": "consent_status = 'restricted'",
         "then": "exclude, RESTRICTED_CONSENT: no outreach without general consent"},
        {"id": "X2", "kind": "exclusion", "when": "age > 85",
         "then": "exclude, AGE_OVER_85: individual decision with the treating doctor, not a campaign"},
        {"id": "X3", "kind": "exclusion", "when": "admissions_12mo >= 1 and hba1c_days_since_test <= 14",
         "then": "exclude, UNDER_ACTIVE_CARE: admitted this year and tested in the last two weeks"},
        {"id": "E1", "kind": "eligibility", "when": "care_gap_count >= 1 or hba1c_latest >= 7.5 or risk >= 0.15",
         "then": "eligible; anyone else is NO_ACTIONABLE_NEED"},
        {"id": "P1", "kind": "threshold", "when": "risk >= 0.30 or hba1c_latest >= 9.5 or admissions_12mo >= 1",
         "then": "priority Urgent, phone call from the care coordinator this week"},
        {"id": "P2", "kind": "threshold", "when": "risk >= 0.20 or hba1c_latest >= 9.0 or care_gap_count >= 3",
         "then": "priority High, phone call within two weeks"},
        {"id": "P3", "kind": "threshold", "when": "hba1c_latest >= 7.5 or care_gap_count >= 2",
         "then": "priority Medium, SMS with a clinic booking link"},
        {"id": "P4", "kind": "threshold", "when": "adherence_pdc < 0.8",
         "then": "priority Low, pharmacy adherence reminder"},
        {"id": "P5", "kind": "threshold", "when": "otherwise",
         "then": "priority Routine, annual review letter"},
    ],
}
PRIORITY_RANK = {"Urgent": 0, "High": 1, "Medium": 2, "Low": 3, "Routine": 4}
CHANNEL = {"Urgent": "Phone call from the care coordinator this week", "High": "Phone call within two weeks",
           "Medium": "SMS with a clinic booking link", "Low": "Pharmacy adherence reminder",
           "Routine": "Annual review letter"}


def _f(row: dict, key: str, default: float = 0.0) -> float:
    v = row.get(key)
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    return default if v != v else v   # NaN


def evaluate(row: dict, risk: float) -> dict:
    """One patient through the rule set. First match wins within each block."""
    consent = str(row.get("consent_status") or "general")
    age = _f(row, "age"); hba1c = _f(row, "hba1c_latest"); days = _f(row, "hba1c_days_since_test", 999)
    gaps = _f(row, "care_gap_count"); adm = _f(row, "admissions_12mo"); pdc = _f(row, "adherence_pdc", 1.0)
    out = {"patient_id": row.get("patient_id"), "risk": round(float(risk), 4), "hba1c": hba1c,
           "care_gaps": int(gaps), "eligible": False, "excluded_by": None, "priority": None,
           "channel": None, "rule_fired": None, "reason": None}
    if consent == "restricted":
        return {**out, "excluded_by": "RESTRICTED_CONSENT", "rule_fired": "X1", "reason": "No outreach without general consent"}
    if age > 85:
        return {**out, "excluded_by": "AGE_OVER_85", "rule_fired": "X2", "reason": "Individual decision with the treating doctor"}
    if adm >= 1 and days <= 14:
        return {**out, "excluded_by": "UNDER_ACTIVE_CARE", "rule_fired": "X3", "reason": "Admitted this year and tested in the last two weeks"}
    if not (gaps >= 1 or hba1c >= 7.5 or risk >= 0.15):
        return {**out, "excluded_by": "NO_ACTIONABLE_NEED", "rule_fired": "E1", "reason": "Controlled, no open care gap, low model risk"}
    out["eligible"] = True
    if risk >= 0.30 or hba1c >= 9.5 or adm >= 1:
        pr, rule, why = "Urgent", "P1", (f"model risk {risk*100:.0f}%" if risk >= 0.30 else f"HbA1c {hba1c}" if hba1c >= 9.5 else "an admission this year")
    elif risk >= 0.20 or hba1c >= 9.0 or gaps >= 3:
        pr, rule, why = "High", "P2", (f"model risk {risk*100:.0f}%" if risk >= 0.20 else f"HbA1c {hba1c}" if hba1c >= 9.0 else f"{int(gaps)} open care gaps")
    elif hba1c >= 7.5 or gaps >= 2:
        pr, rule, why = "Medium", "P3", (f"HbA1c {hba1c}" if hba1c >= 7.5 else f"{int(gaps)} open care gaps")
    elif pdc < 0.8:
        pr, rule, why = "Low", "P4", f"adherence {pdc*100:.0f}%"
    else:
        pr, rule, why = "Routine", "P5", "no threshold crossed"
    return {**out, "priority": pr, "channel": CHANNEL[pr], "rule_fired": rule, "reason": why}


def apply(rows: list[dict], risks: list[float], top_n: int = 25) -> dict[str, Any]:
    """The staged plan for a list of patients: per-patient decisions, ordered by priority
    then risk, plus the counts the agent and the page report."""
    decided = [evaluate(r, p) for r, p in zip(rows, risks)]
    eligible = [d for d in decided if d["eligible"]]
    eligible.sort(key=lambda d: (PRIORITY_RANK[d["priority"]], -d["risk"]))
    by_priority = {k: sum(1 for d in eligible if d["priority"] == k) for k in PRIORITY_RANK}
    by_exclusion: dict[str, int] = {}
    for d in decided:
        if d["excluded_by"]:
            by_exclusion[d["excluded_by"]] = by_exclusion.get(d["excluded_by"], 0) + 1
    by_channel = {CHANNEL[k]: v for k, v in by_priority.items() if v}
    return {
        "rule_set": RULE_SET["id"],
        "evaluated": len(decided), "eligible": len(eligible),
        "excluded": len(decided) - len(eligible),
        "by_priority": by_priority, "by_exclusion": by_exclusion, "by_channel": by_channel,
        "plan": eligible[:top_n],
        "status": "staged, nothing sent; waits at the human checkpoint",
    }
