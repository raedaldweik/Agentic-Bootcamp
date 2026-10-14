"""
Cancer screening, the composite agent for the screening programme.

Four kinds of intelligence, each doing the only job it is good at:

  * deterministic rules (crc.py) decide eligibility, the test, the interval and the urgent
    route; they run first and the agent cannot overrule them;
  * the predictive model (crc_ml.py) estimates which invitations will not be acted on, which
    sets outreach intensity through one policy rule (NHA-CS-01 §8.3), and nothing else;
  * grounded retrieval (rag.py over the screening documents) supplies the policy passages
    the answer cites;
  * the language model reasons across the tools and writes the message to the person. Every
    draft passes a deterministic validator (§9.2) and lands in the human approval queue (§9.3);
    a draft that fails the validator twice is replaced by the programme template.

Two ways to run it, same event stream as the population-health story's agent:

  * the scenario chips: deterministic executors that call the same services and stream the
    same step/final events, so the demo works with no model credentials and the numbers are
    always live;
  * free-form chat: a function-calling loop on the configured model with seven tools; falls
    back to the chips' executors or a notice when no model is configured.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import AsyncGenerator

import pandas as pd

from services import audit as audit_svc
from services import crc, crc_ml, queue_service, screening

ACTOR = "screening_agent"
MODEL_LABEL_DIRECT = "direct tool run · live data"

# ─────────────────────────── shared helpers ───────────────────────────

async def _steps(events: list[dict]) -> AsyncGenerator[dict, None]:
    for e in events:
        yield {"type": "step", "status": "call", "agent": e["agent"], "tool": e["tool"], "detail": e.get("args_summary", "")}
        await asyncio.sleep(0.2)
        yield {"type": "step", "status": "done", "agent": e["agent"], "tool": e["tool"],
               "detail": e.get("result_summary", ""), "duration_ms": e.get("duration_ms", 180)}


def _trace(events: list[dict]) -> list[dict]:
    return [{"agent": e["agent"], "tool": e["tool"], "args_summary": e.get("args_summary", ""),
             "result_summary": e.get("result_summary", ""), "duration_ms": e.get("duration_ms", 180)} for e in events]


def _final(answer: str, ev: list[dict], charts=None, citations=None, actions=None, usage=None, model=MODEL_LABEL_DIRECT) -> dict:
    return {"type": "final", "answer": answer, "trace": _trace(ev), "charts": charts or [],
            "citations": citations or [], "actions": actions or [], "usage": usage, "model": model}


def _cite(hits: list[dict]) -> list[dict]:
    return [{"doc": h["doc"], "page": h["page"], "file": h["file"], "snippet": h["snippet"]} for h in hits]


def _fired(assessment: dict) -> list[dict]:
    return [r for r in assessment["rule_trace"] if r["status"] in ("decided", "applied")]


def _rule_summary(assessment: dict) -> str:
    d = next(r for r in assessment["rule_trace"] if r["status"] == "decided")
    mods = [r["id"] for r in assessment["rule_trace"] if r["status"] == "applied"]
    return f"{d['id']} decided ({d['name']}, {d['source']['doc']} {d['source']['section']})" + (f"; {', '.join(mods)} applied" if mods else "")


# ─────────────────────────── the guardrail (NHA-CS-01 §9.2) ───────────────────────────
MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DAYS = "Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday"
FORBIDDEN = [
    (re.compile(r"\b\d{1,2}[:.]\d{2}\s*(am|pm)?\b|\b\d{1,2}\s?(am|pm)\b", re.I), "an appointment time"),
    (re.compile(rf"\b\d{{1,2}}[/.-]\d{{1,2}}([/.-]\d{{2,4}})?\b|\b\d{{1,2}}(st|nd|rd|th)?\s+({MONTHS})\b|\b({MONTHS})\s+\d{{1,2}}\b|\b({DAYS})\b", re.I), "a date"),
    (re.compile(r"\bAED\b|\$|€|dirham|\bprice\b|\bcosts?\b|\bfee\b|\bfree of charge\b", re.I), "a price or cost"),
    (re.compile(r"(\+?\d[\d\s\-]{7,}\d)"), "a phone number"),
    (re.compile(r"waiting time|wait time|waiting list|the wait is", re.I), "a waiting time"),
    (re.compile(r"\byou (have|may have|might have|probably have|likely have|could have) (bowel |colorectal |colon )?cancer\b|\b(chance|risk|likelihood|probability) of (having |getting )?cancer\b|\d+\s?%\s*(chance|risk|likelihood|probability)", re.I), "a statement about the person's likelihood of cancer"),
    (re.compile(r"\bdiagnos(is|ed|e)\b", re.I), "a diagnosis"),
]
TEST_WORDS = {"endoscopy": ["colonoscopy"], "primary": ["fit", "stool test"], "either": ["fit", "stool test", "colonoscopy"]}


def validate_message(message: str, assessment: dict, facility_name: str) -> dict:
    """Deterministic checks on a drafted message. Returns ok plus the list of failures."""
    fails = []
    low = message.lower()
    where = assessment["pathway"]["where"]
    if assessment["pathway"]["id"] == "symptomatic":
        if not any(w in low for w in ("doctor", "assessment", "gp", "physician", "clinic")):
            fails.append("does not tell the person to see a doctor")
    elif not any(w in low for w in TEST_WORDS.get(where, [])):
        fails.append(f"does not name the test ({' or '.join(TEST_WORDS.get(where, []))})")
    if facility_name and facility_name.lower() not in low:
        fails.append(f"does not name the facility ({facility_name})")
    for pat, what in FORBIDDEN:
        if pat.search(message):
            fails.append(f"contains {what}")
    if len(message) > 900:
        fails.append("longer than 900 characters")
    return {"ok": not fails, "failures": fails, "rule": "NHA-CS-01 §9.2"}


def template_message(assessment: dict, facility_name: str, language: str = "en") -> str:
    """The programme's own wording, by pathway: what the validator always accepts."""
    pw = assessment["pathway"]
    lang_note = "" if language in ("ar", "en") else f" (sent in your language by the messaging service: {language})"
    if pw["id"] == "symptomatic":
        return (f"Hello. Thank you for telling us about your symptoms. Please see a doctor this week: book a GP assessment at "
                f"{facility_name}, and say the words 'bleeding' or 'change in bowels' when you book. The doctor will arrange any test you need. "
                f"Most causes turn out to be minor, and getting checked early is the right step.{lang_note}")
    if pw["where"] == "endoscopy":
        return (f"Hello. Our records show you are due for a bowel check by colonoscopy, the test recommended for people in your situation. "
                f"Please book a referral appointment at {facility_name}, which has an endoscopy unit; bring any previous reports with you. "
                f"We can help you book if you reply to this message.{lang_note}")
    return (f"Hello. You are due for bowel cancer screening, a simple stool test (FIT) you do at home in five minutes. "
            f"Collect your kit at {facility_name} or ask for one at your next visit, return it within a day or two, and the result comes back in about a week. "
            f"If you prefer a colonoscopy instead, the same centre can refer you. Reply to this message and we will help you book.{lang_note}")


def _queue_draft(kind: str, title: str, detail: str, person_id: str = "", person_ids=None, citation: str = "") -> dict:
    item = queue_service.add_draft(kind, title, detail, person_id, person_ids or [], citation, drafted_by=ACTOR)
    audit_svc.log("SCREENING·DRAFT", ACTOR, f"{kind}: {title} queued for approval ({item['id']})", person_id, "action")
    return item


def _facility_for(prs: dict, assessment: dict) -> str:
    if assessment["facilities"]:
        return assessment["facilities"][0]["name"]
    return prs.get("nearest_facility_name") or ""


# ─────────────────────────── scenario chips (deterministic) ───────────────────────────

def _person_bundle(person_id: str) -> dict:
    p = screening.person(person_id)
    if p.get("consent") == "DENIED":
        audit_svc.log("CONSENT·DENIED", ACTOR, "Screening agent blocked on a restricted record", person_id, "warning")
    return p


async def sc_batch(_: str = ""):
    t0 = time.time()
    rows = screening.worklist("batch", 20)
    due_total = int(screening.scored()["due_status"].isin(["due", "overdue"]).sum())
    bands = {b: sum(1 for r in rows if r["uptake_band"] == b) for b in ["Low", "Moderate", "High", "Very high"]}
    bundles = [_person_bundle(r["person_id"]) for r in rows]
    assessments = [b["assessment"] for b in bundles]
    fit_n = sum(1 for a in assessments if a["pathway"]["where"] in ("primary", "either"))
    colo_n = len(assessments) - fit_n
    hits = crc.retrieve("outreach intensity predicted non-completion reminders language navigator", 3)
    drafts = []
    for b, r in zip(bundles, rows):
        a = b["assessment"]; fac = _facility_for(b["person"], a)
        msg = template_message(a, fac, b["person"]["language"])
        v = validate_message(msg, a, fac)
        drafts.append({"person_id": r["person_id"], "channel": b["risk"]["outreach"]["channel"], "band": b["risk"]["band"], "ok": v["ok"], "message": msg})
    ok_n = sum(1 for d in drafts if d["ok"])
    item = _queue_draft("screening_batch", f"Outreach batch: {len(drafts)} invitations",
                        "\n".join(f"{d['person_id']}: {d['channel']} ({d['band']}) · {d['message'][:90]}…" for d in drafts),
                        person_ids=[d["person_id"] for d in drafts], citation="NHA-CS-01 §8.1 to §8.3, §9.3")
    ev = [
        {"agent": "cohort_agent", "tool": "find_due_people", "args_summary": "status in (due, overdue), not invited in 12 months, 20 by clinical priority (APCS points, age)",
         "result_summary": f"{due_total:,} due or overdue in the programme; 20 selected"},
        {"agent": "rules_agent", "tool": "assess_pathway", "args_summary": "20 people through NHA-CS-01 §3 to §7",
         "result_summary": f"20/20 confirmed due: {fit_n} FIT pathway, {colo_n} colonoscopy pathway; 0 overridden by symptoms or history"},
        {"agent": "risk_agent", "tool": "predict_uptake", "args_summary": "screening_uptake v1.0.0, 20 people",
         "result_summary": "bands: " + ", ".join(f"{k} {v}" for k, v in bands.items())},
        {"agent": "guideline_agent", "tool": "search_policy", "args_summary": "outreach intensity, reminders, languages",
         "result_summary": f"{len(hits)} passages, {', '.join(sorted({h['doc'].split(' ')[0] + ' ' + h['doc'].split(' ')[1] for h in hits})) if hits else 'none'}"},
        {"agent": "action_agent", "tool": "draft_outreach", "args_summary": "channel from the §8.3 band, programme template per pathway",
         "result_summary": f"20 drafts: " + ", ".join(f"{c} {sum(1 for d in drafts if d['channel'] == c)}" for c in ["app", "sms", "call"] if any(d["channel"] == c for d in drafts))},
        {"agent": "guardrail_agent", "tool": "validate_messages", "args_summary": "NHA-CS-01 §9.2: test named, facility named, no dates / prices / phone numbers / cancer-likelihood",
         "result_summary": f"{ok_n}/20 passed"},
        {"agent": "action_agent", "tool": "queue_for_approval", "args_summary": item["id"],
         "result_summary": "queued; nothing is sent until a person approves (§9.3)"},
    ]
    async for e in _steps(ev):
        yield e
    lines = "\n".join(f"| {r['person_id']} | {r['age']} {r['sex'][0].upper()} | {r['area']} | {screening.TIER_LABELS[r['apcs_tier']]} | "
                      f"{'FIT' if a['pathway']['where'] != 'endoscopy' else 'Colonoscopy'} | **{r['uptake_band']}** ({r['uptake_risk']*100:.0f}%) | {d['channel']} |"
                      for r, a, d in list(zip(rows, assessments, drafts))[:8])
    avg = float(screening.dashboard("")["kpis"][4]["value"]) / 100
    expected = sum(1 - (r["uptake_risk"] if r["uptake_risk"] is not None else 0.5) for r in rows)
    answer = f"""**Outreach batch drafted and queued.** Of **{due_total:,} people** due or overdue, today's 20 are the ones not yet invited this year with the highest clinical priority (APCS points, then age).

**What each layer did.** The rules confirmed all 20 are due and set the test ({fit_n} FIT, {colo_n} colonoscopy). The model placed them in outreach bands ({', '.join(f'{v} {k.lower()}' for k, v in bands.items())}), which sets the channel under §8.3: {sum(1 for d in drafts if d['channel'] == 'call')} navigator calls, {sum(1 for d in drafts if d['channel'] == 'sms')} SMS, {sum(1 for d in drafts if d['channel'] == 'app')} app notifications. The validator passed {ok_n} of 20 drafts.

| Person | Age | Area | APCS | Test | Non-completion risk | Channel |
|---|---|---|---|---|---|---|
{lines}

Draft **{item['id']}** holds all 20 messages. Approve it in the queue on the right and the messaging service sends them; reject it and nothing goes out. With a standard invitation the model expects **{expected:.0f} of 20** to complete (the programme's average is {avg*100:.0f}%, about {20*avg:.0f} of 20): the gap is why §8.3 puts the navigator on the high bands.
"""
    yield _final(answer, ev,
                 charts=[{"type": "bar", "title": "Predicted non-completion band of the batch",
                          "subtitle": "screening_uptake v1.0.0 · sets outreach intensity only (NHA-CS-01 §8.3)",
                          "data": [{"band": k, "people": v} for k, v in bands.items()], "xKey": "band",
                          "yKeys": [{"key": "people", "label": "People"}]}],
                 citations=_cite(hits), actions=[{"draft_id": item["id"]}])


async def sc_person(message: str = "", person_id: str | None = None):
    # a person named in the message (the worklist click), else the batch's highest-risk person
    m = re.search(r"SC-\d{6}", message or "")
    if m:
        person_id = m.group(0)
    if not person_id:
        batch = screening.worklist("batch", 20)
        person_id = max(batch, key=lambda r: r["uptake_risk"] or 0)["person_id"]
    pid = person_id
    b = _person_bundle(pid)
    if b.get("consent") == "DENIED":
        ev = [{"agent": "rules_agent", "tool": "assess_pathway", "args_summary": pid, "result_summary": "blocked: restricted consent"}]
        async for e in _steps(ev):
            yield e
        yield _final(f"**{pid} has restricted consent.** The record cannot be opened or scored; the attempt is on the audit trail.", ev)
        return
    prs, a, risk = b["person"], b["assessment"], b["risk"]
    fac = _facility_for(prs, a)
    hits = crc.retrieve(f"{a['pathway']['title']} {a['pathway']['test']} invitation language facility", 3)
    live = None
    try:
        live = await llm_draft(prs, a, risk, fac)
    except Exception:
        live = None
    attempts = []
    msg = None
    if live:
        v = validate_message(live, a, fac)
        attempts.append({"source": "language model", **v})
        if v["ok"]:
            msg = live
    if msg is None:
        msg = template_message(a, fac, prs["language"])
        attempts.append({"source": "programme template", **validate_message(msg, a, fac)})
    kind = "screening_invite"
    item = _queue_draft(kind, f"Invitation: {pid} · {risk['outreach']['channel']}", msg, person_id=pid,
                        citation=f"{a['decided_by']} · NHA-CS-01 §8.3, §9.2")
    drv = ", ".join(f"{d['label'].lower()} {('yes' if d['value'] else 'no') if d['feature'] in ('is_male','uninsured','language_barrier','shift_work','smoker_current','diabetes','never_screened','family_history_any') else d['value']}"
                    for d in risk["drivers"][:3])
    ev = [
        {"agent": "rules_agent", "tool": "assess_pathway", "args_summary": f"{pid}: age {prs['age']}, {prs['family_history'].replace('_', ' ')}, last screen {prs['last_screen']}",
         "result_summary": _rule_summary(a)},
        {"agent": "risk_agent", "tool": "predict_uptake", "args_summary": f"{pid} through screening_uptake v1.0.0",
         "result_summary": f"{risk['probability']*100:.0f}% non-completion · {risk['band']} band · drivers: {drv}"},
        {"agent": "rules_agent", "tool": "outreach_policy", "args_summary": f"band {risk['band']} → §8.3",
         "result_summary": risk["outreach"]["plan"]},
        {"agent": "guideline_agent", "tool": "search_policy", "args_summary": a["pathway"]["title"],
         "result_summary": f"{len(hits)} passages"},
        {"agent": "action_agent", "tool": "draft_message", "args_summary": "language model" if live else "programme template (no model configured)",
         "result_summary": f"{len(msg)} characters, channel {risk['outreach']['channel']}"},
        {"agent": "guardrail_agent", "tool": "validate_message", "args_summary": "NHA-CS-01 §9.2",
         "result_summary": " → ".join(f"{t['source']}: {'passed' if t['ok'] else 'failed (' + '; '.join(t['failures']) + ')'}" for t in attempts)},
        {"agent": "action_agent", "tool": "queue_for_approval", "args_summary": item["id"], "result_summary": "queued (§9.3); no message sent"},
    ]
    async for e in _steps(ev):
        yield e
    fired = "\n".join(f"- **{r['id']}** {r['name']}: {r['note']} ({r['source']['doc']} {r['source']['section']})" for r in _fired(a))
    guard = "\n".join(f"- {t['source']}: {'passed' if t['ok'] else 'failed: ' + '; '.join(t['failures'])}" for t in attempts)
    answer = f"""**{pid}**, {prs['age']}, {prs['sex']}, {prs['area']} ({prs['emirate']}), {prs['nationality_group']}, speaks {prs['language']}. Never screened: {'yes' if prs['last_screen'] == 'never' else 'no'}. {prs['distance_km']} km from {prs['nearest_facility_name']}.

**1 · Rules decided the pathway.** {a['pathway']['title']}: {a['pathway']['test']}, {a['pathway']['interval'].lower()}.
{fired}

**2 · The model set the effort, not the pathway.** Predicted non-completion **{risk['probability']*100:.0f}%** ({risk['band']}); strongest drivers: {drv}. Under §8.3 that means: {risk['outreach']['plan']}

**3 · The message, written for approval** ({'drafted by the language model' if attempts and attempts[0]['source'] == 'language model' and attempts[0]['ok'] else 'programme template'}):

> {msg}

**4 · Guardrail (§9.2):**
{guard}

Draft **{item['id']}** is in the approval queue. Nothing reaches the person until someone approves it (§9.3).
"""
    yield _final(answer, ev, citations=_cite(hits), actions=[{"draft_id": item["id"]}])


async def sc_symptoms(_: str = ""):
    rows = screening.worklist("urgent", 1)
    pid = rows[0]["person_id"]
    b = _person_bundle(pid); prs, a = b["person"], b["assessment"]
    fac = _facility_for(prs, a)
    hosp = next((f for f in a["facilities"] if f["endoscopy"]), None)
    hits = crc.retrieve("red-flag symptoms assessment within 14 days colonoscopy by referral not FIT", 3)
    msg = template_message(a, fac, prs["language"])
    v = validate_message(msg, a, fac)
    item = _queue_draft("urgent_referral", f"Urgent assessment: {pid}",
                        f"GP assessment at {fac} within 14 days; colonoscopy by referral at {hosp['name'] if hosp else 'the nearest endoscopy unit'}.\n\nMessage to the person: {msg}",
                        person_id=pid, citation="R1 · NHA-CS-01 §6.1")
    audit_svc.log("SCREENING·RULE", ACTOR, f"R1 red-flag override for {pid}: model not consulted (§9.1)", pid, "warning")
    ev = [
        {"agent": "rules_agent", "tool": "assess_pathway", "args_summary": f"{pid}: symptoms reported in the app",
         "result_summary": "R1 decided: red-flag symptoms override every screening rule (NHA-CS-01 §6.1); R8 overridden"},
        {"agent": "risk_agent", "tool": "predict_uptake", "args_summary": "skipped",
         "result_summary": "not consulted: a deterministic rule takes precedence and the model may not alter the pathway (§9.1)"},
        {"agent": "guideline_agent", "tool": "search_policy", "args_summary": "red-flag symptoms, 14 days, referral", "result_summary": f"{len(hits)} passages"},
        {"agent": "rules_agent", "tool": "route_facility", "args_summary": f"from {prs['area']}",
         "result_summary": f"GP this week at {fac}; endoscopy unit {hosp['name'] if hosp else 'n/a'} ({hosp['km'] if hosp else '?'} km)"},
        {"agent": "guardrail_agent", "tool": "validate_message", "args_summary": "NHA-CS-01 §9.2", "result_summary": "passed" if v["ok"] else "failed: " + "; ".join(v["failures"])},
        {"agent": "action_agent", "tool": "queue_for_approval", "args_summary": item["id"], "result_summary": "urgent item queued for the duty nurse (§9.3)"},
    ]
    async for e in _steps(ev):
        yield e
    answer = f"""**Symptoms change everything, and no model is asked.** {pid}, {prs['age']}, reported {', '.join(a['inputs']['symptoms'])} in the app.

**Rule R1 fired** (NHA-CS-01 §6.1): red-flag symptoms override every screening rule. The person is not offered a FIT; they need a clinical assessment within 14 days and a colonoscopy by referral. Rule R8 (due for screening) would have applied and is shown as overridden in the trace. The predictive model was **not consulted**: §9.1 forbids a model from altering the pathway, and there is nothing for it to decide here.

**Routing (R10, §7):** GP assessment at **{fac}** this week; colonoscopy at **{hosp['name'] if hosp else 'the nearest endoscopy unit'}**, {hosp['km'] if hosp else '?'} km away.

**The message** (programme wording, passed the §9.2 check):

> {msg}

Urgent item **{item['id']}** is at the top of the approval queue for the duty nurse. The override and the fact that the model was skipped are both on the audit trail.
"""
    yield _final(answer, ev, citations=_cite(hits), actions=[{"draft_id": item["id"]}])


async def sc_fit_positive(_: str = ""):
    rows = screening.worklist("fit_positive", 60)
    overdue = [r for r in rows if (r.get("days_since_fit") or 0) > 56]
    fac = screening.tables()["facilities"]
    by_hosp = {}
    for r in rows:
        h = fac[fac["facility_id"] == r["nearest_hospital_id"]].iloc[0]
        by_hosp.setdefault(h["facility_name"], {"hospital": h["facility_name"], "people": 0, "slots_per_week": int(h["colonoscopy_slots_per_week"])})
        by_hosp[h["facility_name"]]["people"] += 1
    hits = crc.retrieve("positive FIT colonoscopy within eight weeks safety net navigator repeat FIT not acceptable", 3)
    item = _queue_draft("colonoscopy_referral", f"Positive FIT without colonoscopy: {len(rows)} referrals ({len(overdue)} past 8 weeks)",
                        "\n".join(f"{r['person_id']}: FIT positive {r['fit_date_latest']} ({r['days_since_fit']} days) → {next(h for h in by_hosp if True)}" for r in rows[:30]),
                        person_ids=[r["person_id"] for r in rows], citation="R12 · NHA-CS-01 §6.2, §6.3")
    ev = [
        {"agent": "cohort_agent", "tool": "fit_positive_backlog", "args_summary": "positive FIT, no colonoscopy recorded since",
         "result_summary": f"{len(rows)} people; {len(overdue)} past the 56-day standard"},
        {"agent": "rules_agent", "tool": "apply_rule", "args_summary": "R12 (§6.2, §6.3)",
         "result_summary": "colonoscopy within 8 weeks; navigator contact within 5 working days when breached; a repeat FIT is not acceptable"},
        {"agent": "risk_agent", "tool": "predict_uptake", "args_summary": f"{len(rows)} people",
         "result_summary": "navigator call for all: the §6.3 safety net is a rule, the model only orders the call list"},
        {"agent": "cohort_agent", "tool": "endoscopy_capacity", "args_summary": "slots per week at the nearest hospitals",
         "result_summary": "; ".join(f"{v['hospital'].replace(' Hospital', '')}: {v['people']} vs {v['slots_per_week']}/wk" for v in by_hosp.values())},
        {"agent": "guideline_agent", "tool": "search_policy", "args_summary": "positive FIT follow-up", "result_summary": f"{len(hits)} passages"},
        {"agent": "action_agent", "tool": "queue_for_approval", "args_summary": item["id"], "result_summary": "referral batch queued for the endoscopy coordinator (§9.3)"},
    ]
    async for e in _steps(ev):
        yield e
    worst = "\n".join(f"| {r['person_id']} | {r['age']} | {r['fit_date_latest']} | **{r['days_since_fit']}** | {r['nearest_facility_name']} |" for r in rows[:8])
    answer = f"""**{len(rows)} positive FITs have no colonoscopy on record**, and **{len(overdue)}** are already past the eight-week standard (NHA-CS-01 §6.2). A positive FIT means blood was found; nine in ten are not cancer, but every one must be looked at, and a repeat FIT is not an acceptable answer.

| Person | Age | FIT positive | Days since | Facility |
|---|---|---|---|---|
{worst}

**Rule R12 (§6.3)** puts each of them on the navigator worklist: a call within five working days and a notified referral to the endoscopy unit. The model does not decide any of this; it only orders the call list so the people least likely to self-book are called first.

**Capacity check:** {'; '.join(f"{v['hospital']} has {v['people']} to absorb against {v['slots_per_week']} slots a week" for v in by_hosp.values())}. The backlog clears within a week of slots everywhere.

Referral batch **{item['id']}** is queued for the endoscopy coordinator.
"""
    yield _final(answer, ev,
                 charts=[{"type": "bar", "title": "Positive FITs awaiting colonoscopy, by endoscopy unit",
                          "subtitle": "against the unit's weekly colonoscopy slots",
                          "data": [{"hospital": v["hospital"].replace(" Hospital", ""), "waiting": v["people"], "slots a week": v["slots_per_week"]} for v in by_hosp.values()],
                          "xKey": "hospital", "yKeys": [{"key": "waiting", "label": "Waiting"}, {"key": "slots a week", "label": "Slots a week"}]}],
                 citations=_cite(hits), actions=[{"draft_id": item["id"]}])


async def sc_programme(_: str = ""):
    d = screening.dashboard("")
    m = screening.map_payload()
    worst = sorted(m["facilities"], key=lambda f: f["completion_pct"])[:4]
    eq = d["equity"]; lang = d["equity_language"]
    hits = crc.retrieve("programme targets participation completion positivity quality indicators", 3)
    ev = [
        {"agent": "cohort_agent", "tool": "programme_snapshot", "args_summary": "whole programme", "result_summary": f"{d['kpis'][0]['value']} eligible · {d['kpis'][1]['value']}% up to date · {d['kpis'][2]['value']} due or overdue"},
        {"agent": "risk_agent", "tool": "predict_uptake", "args_summary": "everyone due", "result_summary": "bands: " + ", ".join(f"{b['band']} {b['people']}" for b in d["uptake_bands"])},
        {"agent": "cohort_agent", "tool": "render_map", "args_summary": "90-day completion by facility", "result_summary": f"lowest: {', '.join(f['name'].replace(' Health Centre', ' HC') for f in worst)}"},
        {"agent": "guideline_agent", "tool": "search_policy", "args_summary": "programme targets", "result_summary": f"{len(hits)} passages"},
    ]
    async for e in _steps(ev):
        yield e
    k = {x["label"].split(" (")[0]: x for x in d["kpis"]}
    answer = f"""**The programme at a glance.** {k['Eligible, 40 to 75']['value']} people aged 40 to 75 are eligible; **{k['Up to date']['value']}%** are up to date against the §8.4 target of 60%, and **{k['Due or overdue']['value']}** are due or overdue. Of the invitations sent in the last 12 months, **{k['Completed within 90 days']['value']}%** led to a test within 90 days (target 65%). FIT positivity is {k['FIT positivity, 12 months']['value']}% (target range 5 to 10%); {d['colonoscopy_wait']['within_8_weeks_pct']}% of positive FITs reached colonoscopy within eight weeks.

**Where uptake is lowest.** The map shows the East Coast and the far north: {', '.join(f"{f['name']} ({f['completion_pct']}%)" for f in worst)}. Distance is the first driver the model finds; outreach effort there is where the §8.3 rule puts the navigator calls.

**Who is being left behind.** Completion by nationality group runs from {eq[0]['group']} at {eq[0]['completion_pct']}% to {eq[-1]['group']} at {eq[-1]['completion_pct']}%; by language from {lang[0]['language']} {lang[0]['completion_pct']}% to {lang[-1]['language']} {lang[-1]['completion_pct']}%. Invitations exist in six languages (§8.2); the call centre in two.

**Open safety issues:** {d['fit_positive_no_colonoscopy']} positive FITs without a colonoscopy, {d['urgent_symptoms']} people with red-flag symptoms on the pathway. Both have their own chip.
"""
    yield _final(answer, ev,
                 charts=[screening.map_spec("completion_pct", "90-day completion of invitations, by facility"),
                         {"type": "bar", "title": "90-day completion by nationality group", "subtitle": "latest invitation per person",
                          "data": [{"group": e["group"], "completion %": e["completion_pct"]} for e in eq], "xKey": "group",
                          "yKeys": [{"key": "completion %", "label": "Completion %"}]}],
                 citations=_cite(hits))


SCENARIOS = [
    {"id": "s_batch", "tag": "S1", "label": "Morning outreach batch", "runner": sc_batch,
     "question": "Run the morning outreach batch: who is due, how hard should we reach out to each of them, and draft the invitations for approval."},
    {"id": "s_person", "tag": "S2", "label": "One person, end to end", "runner": sc_person,
     "question": "Take the batch's highest-risk person through the rules, the model and a drafted invitation."},
    {"id": "s_symptoms", "tag": "S3", "label": "Symptoms reported in the app", "runner": sc_symptoms,
     "question": "Someone has just reported bleeding in the app. What happens?"},
    {"id": "s_fit_positive", "tag": "S4", "label": "Positive FIT, no colonoscopy", "runner": sc_fit_positive,
     "question": "Which positive FIT results have no colonoscopy yet, and what should happen to them?"},
    {"id": "s_programme", "tag": "S5", "label": "Where is uptake lowest?", "runner": sc_programme,
     "question": "Show me the programme: where is uptake lowest, and who is being left behind?"},
]


def list_scenarios() -> list[dict]:
    return [{k: v for k, v in s.items() if k != "runner"} for s in SCENARIOS]


def get_runner(scenario_id: str):
    return next((s["runner"] for s in SCENARIOS if s["id"] == scenario_id), None)


# ─────────────────────────── the language model: drafting and the tool loop ───────────────────────────

def llm_enabled() -> bool:
    from services import agent
    return agent.llm_enabled()


def _anthropic_model() -> str | None:
    from services import agent
    if not agent.llm_enabled():
        return None
    m = agent.active_model()
    return m if m.startswith("claude") else None


DRAFT_SYSTEM = (
    "You write short invitation messages for a colorectal-cancer screening programme. You are given the pathway the "
    "rules decided, the facility, the person's language and the outreach channel. Write ONE message of 60 to 110 words, "
    "warm and plain, in English, that: names the test exactly as decided (FIT stool test, or colonoscopy, or a doctor's "
    "assessment for symptoms), names the facility, says how to book (reply to this message), and nothing else. Never "
    "state a date, a day of the week, a time, a price, a waiting time, a phone number, or anything about the person's "
    "likelihood of having cancer. No greeting with a name (you do not know it). Output only the message."
)


async def llm_draft(prs: dict, a: dict, risk: dict, facility: str) -> str | None:
    """One personalised draft from the model, or None when no model is configured."""
    model = _anthropic_model()
    from services import llm_client as LC
    if not model:
        from services import agent
        if not agent.llm_enabled():
            return None
        # Gemini provider: a single generate call
        from google.genai import types as gtypes
        from services import agent as ag
        client = LC.make_client(http_options=ag._http_options())
        cfg = ag.generation_config(ag.active_model()) or gtypes.GenerateContentConfig()
        cfg.system_instruction = DRAFT_SYSTEM; cfg.temperature = 0.4; cfg.max_output_tokens = 300
        r = await client.aio.models.generate_content(model=ag.active_model(), contents=_draft_prompt(prs, a, risk, facility), config=cfg)
        return (r.text or "").strip() or None
    from services import agent as ag
    client = LC.make_anthropic_client(timeout_s=ag.HTTP_TIMEOUT_MS / 1000, max_retries=1)
    r = await client.messages.create(model=model, max_tokens=300, temperature=0.4, system=DRAFT_SYSTEM,
                                     messages=[{"role": "user", "content": _draft_prompt(prs, a, risk, facility)}])
    return "".join(b.text for b in r.content if getattr(b, "type", "") == "text").strip() or None


def _draft_prompt(prs, a, risk, facility) -> str:
    return (f"Pathway decided by the rules: {a['pathway']['title']}. Test: {a['pathway']['test']}. Interval: {a['pathway']['interval']}. "
            f"Facility: {facility}. Channel: {risk['outreach']['channel']}. Person's language: {prs['language']}, age {prs['age']}, "
            f"never screened: {'yes' if prs['last_screen'] == 'never' else 'no'}. Write the message.")


SUPERVISOR = """You are the screening programme's composite AI assistant, demonstrating how deterministic rules, a predictive model, grounded retrieval and a language model work together under human oversight.

Division of labour, which you must respect:
- The RULES (tool assess / get_person) decide eligibility, the test, the interval and the urgent route. You never decide these yourself and never contradict them.
- The MODEL (tool predict_uptake) estimates the chance an invitation is not acted on within 90 days. It sets outreach intensity only (NHA-CS-01 §8.3): Low → app, Moderate → SMS, High → navigator call, Very high → call plus booking help.
- POLICY passages come from search_policy; cite the document and section when you rely on one.
- You WRITE the message to the person and submit it with draft_message, which runs the §9.2 validator and puts it in the human approval queue. Nothing is sent by you.
- Numbers come from tools only; never invent a figure. Keep answers compact, in markdown, with a short table where it helps. If a tool reports restricted consent, stop for that person and say so.
"""

TOOLS = [
    {"name": "find_due_people", "description": "People the rules found due or overdue for screening, ordered by predicted non-completion risk (highest first).",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 10}, "uninvited_only": {"type": "boolean", "default": True}}}},
    {"name": "get_person", "description": "One person's record, the rules' decision (pathway, which rules fired) and the model's prediction and outreach plan.",
     "input_schema": {"type": "object", "properties": {"person_id": {"type": "string"}}, "required": ["person_id"]}},
    {"name": "predict_uptake", "description": "Predicted non-completion probability, band and the §8.3 outreach plan for a list of people.",
     "input_schema": {"type": "object", "properties": {"person_ids": {"type": "array", "items": {"type": "string"}}}, "required": ["person_ids"]}},
    {"name": "search_policy", "description": "Passages from the screening policy documents (NHA-CS-01, NHA-PP-01) for a query; cite doc and page.",
     "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}},
    {"name": "programme_snapshot", "description": "Programme KPIs: eligible, up to date, due, invitations, 90-day completion, FIT positivity, waits, safety issues, uptake bands, lowest facilities.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "fit_positive_backlog", "description": "People with a positive FIT and no colonoscopy recorded, with days since the test.",
     "input_schema": {"type": "object", "properties": {"limit": {"type": "integer", "default": 20}}}},
    {"name": "draft_message", "description": "Submit a message you wrote for one person. It is checked against §9.2 (names the decided test and the facility; no dates, times, prices, phone numbers, waiting times or cancer-likelihood) and, if it passes, queued for human approval. Returns the failures if it does not pass; after two failures the programme template is queued instead.",
     "input_schema": {"type": "object", "properties": {"person_id": {"type": "string"}, "message": {"type": "string"},
                                                       "kind": {"type": "string", "enum": ["screening_invite", "urgent_referral", "colonoscopy_referral"], "default": "screening_invite"}},
                      "required": ["person_id", "message"]}},
]
TOOL_AGENT = {"find_due_people": "cohort_agent", "get_person": "rules_agent", "predict_uptake": "risk_agent", "search_policy": "guideline_agent",
              "programme_snapshot": "cohort_agent", "fit_positive_backlog": "cohort_agent", "draft_message": "action_agent"}
_SESSIONS: dict[str, list] = {}


def _compact_person(b: dict) -> dict:
    if b.get("consent") == "DENIED":
        return {"person_id": b["person_id"], "consent": "DENIED", "message": b["message"]}
    p, a, r = b["person"], b["assessment"], b["risk"]
    return {"person_id": p["person_id"], "age": p["age"], "sex": p["sex"], "language": p["language"], "area": p["area"], "emirate": p["emirate"],
            "nearest_facility": p["nearest_facility_name"], "distance_km": p["distance_km"], "last_screen": p["last_screen"],
            "family_history": p["family_history"], "symptoms": a["inputs"]["symptoms"], "apcs_tier": a["score"]["tier"],
            "pathway": {"id": a["pathway"]["id"], "title": a["pathway"]["title"], "test": a["pathway"]["test"], "interval": a["pathway"]["interval"], "urgency": a["pathway"]["urgency"]},
            "rules_fired": [f"{x['id']} {x['name']} ({x['source']['doc']} {x['source']['section']}): {x['note']}" for x in _fired(a)],
            "recommended_facility": _facility_for(p, a),
            "model": None if not r else {"non_completion_probability": r["probability"], "band": r["band"], "outreach": r["outreach"]["plan"], "channel": r["outreach"]["channel"],
                                        "drivers": [f"{d['label']}={d['value']}" for d in r["drivers"][:3]]}}


class _State:
    def __init__(self):
        self.trace: list[dict] = []; self.citations: list[dict] = []; self.actions: list[dict] = []
        self.charts: list[dict] = []; self.fails: dict[str, int] = {}; self.steps: list[dict] = []


def _run_tool(name: str, args: dict, st: _State) -> dict:
    if name == "find_due_people":
        rows = screening.worklist("due", int(args.get("limit", 10) or 10), bool(args.get("uninvited_only", True)))
        return {"count_due_or_overdue": int(screening.scored()["due_status"].isin(["due", "overdue"]).sum()),
                "people": [{k: r[k] for k in ("person_id", "age", "sex", "language", "area", "nearest_facility_name", "distance_km", "apcs_tier", "pathway_test", "last_screen", "uptake_risk", "uptake_band")} for r in rows]}
    if name == "get_person":
        return _compact_person(_person_bundle(args["person_id"]))
    if name == "predict_uptake":
        out = []
        for pid in (args.get("person_ids") or [])[:40]:
            b = _person_bundle(pid)
            if b.get("consent") == "DENIED" or not b.get("risk"):
                out.append({"person_id": pid, "consent": "DENIED"}); continue
            r = b["risk"]; out.append({"person_id": pid, "non_completion_probability": r["probability"], "band": r["band"], "channel": r["outreach"]["channel"], "plan": r["outreach"]["plan"]})
        return {"model": "screening_uptake v1.0.0", "rule": "NHA-CS-01 §8.3", "results": out}
    if name == "search_policy":
        hits = crc.retrieve(args.get("query", ""), 4)
        for h in hits:
            if not any(c["doc"] == h["doc"] and c["page"] == h["page"] for c in st.citations):
                st.citations.append({"doc": h["doc"], "page": h["page"], "file": h["file"], "snippet": h["snippet"]})
        return {"passages": [{"doc": h["doc"], "page": h["page"], "text": h["snippet"][:600]} for h in hits]}
    if name == "programme_snapshot":
        d = screening.dashboard(""); m = screening.map_payload()
        st.charts.append(screening.map_spec("completion_pct", "90-day completion of invitations, by facility"))
        return {"kpis": {k["label"]: f"{k['value']}{k.get('suffix', '')}" for k in d["kpis"]}, "uptake_bands_among_due": d["uptake_bands"],
                "colonoscopy_wait": d["colonoscopy_wait"], "fit_positive_no_colonoscopy": d["fit_positive_no_colonoscopy"], "urgent_symptoms": d["urgent_symptoms"],
                "lowest_completion_facilities": [{"name": f["name"], "completion_pct": f["completion_pct"], "region": f["region"]} for f in sorted(m["facilities"], key=lambda f: f["completion_pct"])[:5]],
                "equity_by_nationality": d["equity"], "equity_by_language": d["equity_language"]}
    if name == "fit_positive_backlog":
        rows = screening.worklist("fit_positive", int(args.get("limit", 20) or 20))
        return {"count": len(rows), "past_56_days": sum(1 for r in rows if (r.get("days_since_fit") or 0) > 56),
                "people": [{k: r[k] for k in ("person_id", "age", "fit_date_latest", "days_since_fit", "nearest_facility_name", "nearest_hospital_id")} for r in rows]}
    if name == "draft_message":
        pid = args["person_id"]; b = _person_bundle(pid)
        if b.get("consent") == "DENIED":
            return {"queued": False, "reason": "restricted consent"}
        a = b["assessment"]; fac = _facility_for(b["person"], a)
        v = validate_message(args.get("message", ""), a, fac)
        st.steps.append({"agent": "guardrail_agent", "tool": "validate_message", "args_summary": f"{pid} · NHA-CS-01 §9.2",
                         "result_summary": "passed" if v["ok"] else "failed: " + "; ".join(v["failures"])})
        msg = args.get("message", "")
        if not v["ok"]:
            st.fails[pid] = st.fails.get(pid, 0) + 1
            if st.fails[pid] < 2:
                return {"queued": False, "validator": v, "hint": "Rewrite once more without the failing elements, then resubmit."}
            msg = template_message(a, fac, b["person"]["language"])
            v = {"ok": True, "failures": [], "fallback": "programme template used after two failed drafts"}
        item = _queue_draft(args.get("kind") or "screening_invite", f"Invitation: {pid} · {b['risk']['outreach']['channel'] if b.get('risk') else 'sms'}", msg,
                            person_id=pid, citation=f"{a['decided_by']} · NHA-CS-01 §9.2")
        st.actions.append({"draft_id": item["id"]})
        return {"queued": True, "draft_id": item["id"], "validator": v, "message_queued": msg}
    return {"error": f"unknown tool {name}"}


def _summ(obj, n=140) -> str:
    s = json.dumps(obj, default=str)
    return s if len(s) <= n else s[:n] + "…"


async def stream_chat(message: str, session_id: str = "default") -> AsyncGenerator[dict, None]:
    """Free-form question through the function-calling loop (Anthropic), same event stream as the chips."""
    from services import agent as ag
    from services import llm_client as LC
    model = _anthropic_model()
    if not model:
        yield {"type": "final", "answer": ("**Free-form questions need Anthropic model credentials on the server.** The scenario chips run "
                                           "every layer, rules, model, retrieval, validator and approval queue, on live data without them."),
               "trace": [], "charts": [], "citations": [], "actions": [], "usage": None, "model": None}
        return
    client = LC.make_anthropic_client(timeout_s=ag.HTTP_TIMEOUT_MS / 1000, max_retries=2)
    history = _SESSIONS.setdefault(session_id, [])
    history.append({"role": "user", "content": message})
    msgs = history[-12:]
    st = _State(); t0 = time.time(); calls = 0; tin = tout = 0; text = ""
    for _ in range(8):
        resp = await client.messages.create(model=model, max_tokens=1400, temperature=0.2, system=SUPERVISOR, tools=TOOLS, messages=msgs)
        calls += 1; tin += resp.usage.input_tokens; tout += resp.usage.output_tokens
        blocks = resp.content
        text = "".join(b.text for b in blocks if getattr(b, "type", "") == "text") or text
        tool_uses = [b for b in blocks if getattr(b, "type", "") == "tool_use"]
        if not tool_uses:
            msgs.append({"role": "assistant", "content": text}); break
        msgs.append({"role": "assistant", "content": [b.model_dump() for b in blocks]})
        results = []
        for tu in tool_uses:
            agent_name = TOOL_AGENT.get(tu.name, "system")
            yield {"type": "step", "status": "call", "agent": agent_name, "tool": tu.name, "detail": _summ(tu.input, 90)}
            t1 = time.time()
            try:
                out = await asyncio.to_thread(_run_tool, tu.name, tu.input or {}, st)
            except Exception as e:
                out = {"error": f"{type(e).__name__}: {str(e)[:160]}"}
            ms = int((time.time() - t1) * 1000)
            ev = {"agent": agent_name, "tool": tu.name, "args_summary": _summ(tu.input, 120), "result_summary": _summ(out, 160), "duration_ms": ms}
            st.trace.append(ev)
            while st.steps:
                s = st.steps.pop(0); st.trace.append({**s, "duration_ms": 2})
                yield {"type": "step", "status": "done", **{k: s[k] for k in ("agent", "tool")}, "detail": s["result_summary"], "duration_ms": 2}
            yield {"type": "step", "status": "done", "agent": agent_name, "tool": tu.name, "detail": ev["result_summary"], "duration_ms": ms}
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": json.dumps(out, default=str)[:12000]})
        msgs.append({"role": "user", "content": results})
    _SESSIONS[session_id] = msgs[-12:]
    audit_svc.log("SCREENING·CHAT", ACTOR, f"{calls} model calls, {len(st.trace)} tool steps: {message[:80]}", "", "info")
    yield {"type": "final", "answer": text or "_(no answer)_", "trace": st.trace, "charts": st.charts, "citations": st.citations,
           "actions": st.actions, "model": ag.display_model(model),
           "usage": {"total_tokens": tin + tout, "prompt_tokens": tin, "completion_tokens": tout, "llm_calls": calls, "wall_ms": int((time.time() - t0) * 1000)}}


# ─────────────────────────── queue and audit views for Cancer screening ───────────────────────────
SCREENING_TYPES = {"screening_invite", "screening_batch", "urgent_referral", "colonoscopy_referral"}


def queue_items(status: str | None = None) -> list[dict]:
    return [i for i in queue_service.list_items(status) if i.get("type") in SCREENING_TYPES]


def audit_entries(limit: int = 80) -> list[dict]:
    out = []
    for e in audit_svc.list_entries(600):
        if (e.get("event_type", "").startswith("SCREENING") or str(e.get("patient_id", "")).startswith("SC-")
                or (e.get("event_type", "").startswith("HITL") and any(t in e.get("detail", "") for t in SCREENING_TYPES))
                or e.get("actor") == ACTOR):
            out.append(e)
        if len(out) >= limit:
            break
    return out
