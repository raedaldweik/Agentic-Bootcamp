"""Acceptance run for a deployed Sanad MRO Intelligence Hub.

    python -m scripts.sanad_smoke https://your-app.up.railway.app
    python -m scripts.sanad_smoke http://localhost:8000 --code ACCESS_CODE --only manager

Asks the storyline's questions as each role at the right shop time, then a set of questions
that are not in the storyline, and prints for each one: how it was answered (model or shop
data), time to the first words and to the complete answer, the card shown and the next
questions. Ends with a summary and a non-zero exit code if anything looks wrong.

It talks to the public API exactly as the chat does, so it needs nothing but the address.
Each run uses real model calls when the server has a key.
"""
from __future__ import annotations

import argparse
import statistics
import sys
import time

import httpx

M = {1: "2026-10-28 09:30", 2: "2026-10-28 11:30", 3: "2026-10-28 12:15", 4: "2026-10-28 13:30", 5: "2026-10-28 16:00", 6: "2026-10-29 10:00"}

# (role, shop time, question, card expected or None, what the answer must mention: a word, or any one of a group)
STORY = [
    ("manager", M[1], "Show me the status of all the engines.", "engine_status", ["ENG-204"]),
    ("manager", M[1], "What is the primary risk to ENG-204?", "delivery_risk", ["P-4582"]),
    ("manager", M[1], "What has changed on ENG-204 since yesterday?", "forecast_changes", [("36", "5 Nov")]),
    ("manager", M[1], "Generate a recovery plan for component P-4582.", "recovery_plan", [("2,400", "2400", "Option B", "option B")]),
    ("manager", M[2], "Has the recovery option been approved?", "recovery_plan", ["EXQ-0592"]),
    ("technician", M[3], "I need to start the fan blade removal task. Please guide me.", "job_card", ["JC-FAN-204"]),
    ("technician", M[3], "Can I start fan blade removal now?", "task_readiness", ["T-117"]),
    ("technician", M[3], "Which tools does this step need?", "task_tools", ["T-117"]),
    ("supervisor", M[3], "Where is tool T-117?", "tool_location", ["Gate 3"]),
    ("supervisor", M[3], "Is the tool still at Gate 3?", "tool_location", [("camera", "sighting", "not confirmed", "custody")]),
    ("technician", M[4], "T-117 is checked in at Gate 1 and the supervisor has released the work. Guide me through the fan blade removal step by step.", "job_card", ["step"]),
    ("supervisor", M[5], "Can I approve a deviation so the work can continue?", "approval_authority", [("Engineering", "Quality")]),
    ("supervisor", M[6], "What is now the best way to protect the committed delivery date?", "protect_delivery", []),
    ("manager", M[6], "Show me the updated engine status and recovery progress.", "engine_status", [("16:30", "90 min", "on track")]),
]
# Not in the storyline: these need the model (free-form, what-if, documents, actions, refusals).
OFF_SCRIPT = [
    ("manager", M[1], "Which engine is furthest ahead of its commitment, and by how much?", None, ["ENG-209"]),
    ("supervisor", M[2], "What if P-4582 arrives four hours later than promised?", "simulate_schedule", []),
    ("supervisor", M[1], "What does the tool control procedure say about camera detections?", None, [("TC-003", "Tool Control Procedure")]),
    ("technician", M[5], "What is the scratch limit in zone B and what did we measure?", None, ["0.25", ("0.8", "0.80")]),
    ("manager", M[6], "Which approvals were recorded for ENG-204, and by whom?", None, ["EXQ-0592"]),
    ("manager", M[1], "Draw a chart of hours late or ahead for each engine.", "chart_1", []),
    ("supervisor", M[1], "Raise a handover request for T-117.", None, ["THR-"]),
    ("supervisor", M[5], "Approve the deviation for the blade finding.", None, [("cannot", "can't", "can not", "unable", "not able", "only an authorised")]),
    ("technician", M[3], "Confirm step 1 of the job card.", None, [("released", "release")]),
    ("manager", M[1], "how's 215 looking", None, ["ENG-215"]),
    ("manager", M[1], "What's the weather in Abu Dhabi today?", None, []),
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("url", help="address of the app, such as https://your-app.up.railway.app")
    ap.add_argument("--code", help="access code, if SANAD_ACCESS_CODE is set on the server")
    ap.add_argument("--only", choices=["manager", "technician", "supervisor", "story", "offscript"], help="run a subset")
    ap.add_argument("--slow", type=float, default=15.0, help="seconds after which an answer is reported as slow (default 15)")
    args = ap.parse_args()
    base = args.url.rstrip("/") + "/api/assistant"
    c = httpx.Client(timeout=30, follow_redirects=True)

    health = c.get(f"{base}/health").json()
    if health.get("locked"):
        if not args.code:
            print("The app asks for an access code: pass --code.")
            return 2
        c.post(f"{base}/unlock", json={"code": args.code}).raise_for_status()
        health = c.get(f"{base}/health").json()
    print(f"{args.url}: build {health.get('build')}, model {health.get('model') or 'NOT CONFIGURED'}, effort {health.get('effort')}, "
          f"check {health.get('modelCheck')}\n")
    live = bool(health.get("llm"))

    cases = [("story", *x) for x in STORY] + ([("offscript", *x) for x in OFF_SCRIPT] if live else [])
    if not live:
        print("No model key on the server: running the storyline only (answered from the shop data).\n")
    if args.only:
        cases = [x for x in cases if args.only in (x[0], x[1])]

    problems: list[str] = []
    totals: list[float] = []
    firsts: list[float] = []
    for group, role, ts, question, card, words in cases:
        t0 = time.perf_counter()
        r = c.post(f"{base}/query", json={"content": question, "persona": role, "shopTime": ts})
        if r.status_code == 429:
            time.sleep(8)
            r = c.post(f"{base}/query", json={"content": question, "persona": role, "shopTime": ts})
        r.raise_for_status()
        qid = r.json()["queryId"]
        first = None
        while True:
            st = c.get(f"{base}/query/{qid}").json()
            if st.get("done"):
                break
            if first is None and st.get("text"):
                first = time.perf_counter() - t0
            if time.perf_counter() - t0 > 150:
                st = {"result": {"answer": "", "mode": "timeout", "cards": [], "followups": [], "notice": "no answer in 150 s"}}
                break
            time.sleep(0.15)
        total = time.perf_counter() - t0
        res = st["result"]
        answer = res.get("answer") or res.get("errorText") or ""
        cards = [x.get("id") for x in res.get("cards") or []]
        issues = []
        if live and res.get("mode") != "model":
            issues.append(f"answered from shop data, not the model ({res.get('notice') or res.get('mode')})")
        if card and card not in cards:
            issues.append(f"expected card {card}, got {cards or 'none'}")
        if "[[" in answer:
            issues.append("marker left in the answer")
        low = answer.lower()
        missing = [w for w in words if not any(x.lower() in low for x in ((w,) if isinstance(w, str) else w))]
        if missing:
            issues.append(f"answer does not mention {missing}")
        if total > args.slow:
            issues.append(f"slow: {total:.1f} s")
        if not res.get("followups") and res.get("mode") == "model":
            issues.append("no next questions")
        totals.append(total)
        if first is not None:
            firsts.append(first)
        mark = "!!" if issues else "ok"
        print(f"[{mark}] {role:10s} {ts[5:]}  {question[:78]}")
        print(f"     {res.get('mode')}, first words {f'{first:.1f} s' if first is not None else 'n/a'}, complete {total:.1f} s, card {cards or 'none'}")
        print(f"     {' '.join(answer.split())[:230]}")
        for i in issues:
            print(f"     -> {i}")
            problems.append(f"{question[:50]}: {i}")
        print()

    if totals:
        q = sorted(totals)
        print(f"{len(totals)} questions. Complete answer: median {statistics.median(q):.1f} s, slowest {q[-1]:.1f} s."
              + (f" First words: median {statistics.median(firsts):.1f} s." if firsts else ""))
    print(f"{len(problems)} thing(s) to look at." if problems else "Nothing to look at.")
    for p in problems:
        print(f"  - {p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
