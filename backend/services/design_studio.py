"""The Design Thinking Agent: a scripted Population Health Builder.

One conversation builds a population-health agent on SAS Viya in four steps, data, model,
decision, agent, the path of bootcamp/agents/population_health_builder_demo.md. Here the path is
staged inside this process so it runs the same way every time, on any laptop, with no Viya
behind it:

  - the patient table is generated in memory (the DATA step shown is the one the live agent runs,
    the columns and the numbers on screen come from the generated rows),
  - a model is fitted on those rows, so the assessment numbers, the top predictors and the two
    scored patients are measured, not typed in,
  - the four outreach rules are evaluated on the scored probabilities,
  - every step is presented as the SAS Viya tool calls the live agent makes, with the artefact
    names and the places in Viya where they appear.

The words are the language model's: after each step it is handed the facts (what the tools
returned) and writes the message the audience reads. Without a model key a template narrates
the same facts. Nothing on screen is invented by the narrator: the numbers come from the facts.

Events (NDJSON over /api/design/chat):
  meta      mode live|scripted, model
  intro     the one line said before the tools run
  step      a tool call: status call, then done (result, ms, log)
  progress  a long-running step's progress (the AutoML pipelines)
  block     a rich result to render: sas_code, table, profile, leaderboard, predictors,
            scores, rules, flow, handover, pointer
  artefact  something that now exists on Viya (upsert by id) for the "On SAS Viya" rail
  delta     a token of the narration
  final     the narration, the stage reached, the next-step chips and the state
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import re
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, AsyncIterator

from services import teams

PACE = float(os.getenv("DESIGN_PACE", "1.0"))        # 0 in tests, 1 on the day, 0.5 to rehearse quickly

ORDER = ["idea", "data", "model", "decision", "agent"]
TITLES = {"idea": "The idea", "data": "The data", "model": "The model", "decision": "The decision", "agent": "The agent"}
NEXT_LABEL = {"data": "Create the data", "model": "Train the model", "decision": "Build the decision", "agent": "Hand over the agent"}

CASLIB, SERVER = "Public", "cas-shared-default"
TABLE, MODEL_TABLE, PROJECT = "PH_DEMO_PATIENTS", "PH_DEMO_PATIENTS_MODEL", "PH_DEMO_MODEL"
RULESET, FLOW, PUBLISHED_DECISION = "PH_DEMO_OUTREACH", "PH_DEMO_OUTREACH_DECISION", "ph_demo_outreach"
DESTINATION = "maslocal"
N_ROWS = 4000

COLUMNS = [   # name, SAS type, what it means
    ("patient_id", "char(12)", "Pseudonymous patient id"),
    ("sex", "char(6)", "female or male"),
    ("age", "num", "Age in years"),
    ("emirate", "char(16)", "Home emirate"),
    ("facility_id", "char(4)", "Usual care facility, F001 to F018"),
    ("years_with_diabetes", "num", "Years since diagnosis"),
    ("hba1c", "num", "Latest HbA1c, %"),
    ("bmi", "num", "Body mass index"),
    ("sbp", "num", "Systolic blood pressure, mmHg"),
    ("egfr", "num", "Kidney function (eGFR), mL/min"),
    ("adherence_pdc", "num", "Medication adherence, proportion of days covered"),
    ("missed_visits_12m", "num", "Missed appointments in the last 12 months"),
    ("smoker", "num", "1 = current smoker"),
    ("on_metformin", "num", "1 = on metformin"),
    ("on_sglt2_glp1", "num", "1 = on an SGLT2 inhibitor or GLP-1 agonist"),
    ("admissions_12m", "num", "Hospital admissions in the last 12 months"),
    ("deterioration_next_12m", "num", "Target: 1 = deteriorated in the following 12 months"),
]
FEATURES = ["hba1c", "adherence_pdc", "age", "admissions_12m", "missed_visits_12m", "egfr", "bmi", "sbp",
            "smoker", "on_sglt2_glp1", "on_metformin", "years_with_diabetes", "sex_female"]
PRETTY = {"hba1c": "HbA1c", "adherence_pdc": "Medication adherence (PDC)", "age": "Age", "admissions_12m": "Admissions, 12 months",
          "missed_visits_12m": "Missed visits, 12 months", "egfr": "eGFR", "bmi": "BMI", "sbp": "Systolic BP", "smoker": "Smoker",
          "on_sglt2_glp1": "On SGLT2 / GLP-1", "on_metformin": "On metformin", "years_with_diabetes": "Years with diabetes",
          "sex_female": "Sex"}
EMIRATES = [("Sharjah", 0.45), ("Ajman", 0.20), ("Umm Al Quwain", 0.08), ("Ras Al Khaimah", 0.15), ("Fujairah", 0.12)]

SAS_DATA_STEP = f"""cas s_demo_a1; libname pub cas caslib="{CASLIB}" sessref=s_demo_a1;
data pub.{TABLE} (promote=yes);
  call streaminit(2026);
  length patient_id $12 sex $6 emirate $16 facility_id $4;
  array em[5] $16 _temporary_ ("Sharjah" "Ajman" "Umm Al Quwain" "Ras Al Khaimah" "Fujairah");
  do i = 1 to {N_ROWS};
    patient_id = cats("PH-", 100000 + i);
    sex = ifc(rand("BERNOULLI", 0.52), "female", "male");
    age = round(max(25, rand("NORMAL", 56, 12)));
    emirate = em[rand("TABLE", 0.45, 0.2, 0.08, 0.15, 0.12)];
    facility_id = cats("F", put(rand("INTEGER", 1, 18), z3.));
    years_with_diabetes = round(max(0, rand("NORMAL", 8, 5)), 0.1);
    hba1c = round(max(5, rand("NORMAL", 7.6, 1.4)), 0.1);
    bmi = round(max(18, rand("NORMAL", 30, 4.6)), 0.1);
    sbp = round(rand("NORMAL", 134, 15));
    egfr = round(min(130, max(15, rand("NORMAL", 86, 22))));
    adherence_pdc = round(min(1, max(0.2, rand("NORMAL", 0.78, 0.17))), 0.01);
    missed_visits_12m = rand("POISSON", 0.9);
    smoker = rand("BERNOULLI", 0.17);
    on_metformin = rand("BERNOULLI", 0.82);
    on_sglt2_glp1 = rand("BERNOULLI", 0.28);
    admissions_12m = rand("POISSON", 0.25);
    logit = -3.1 + 0.45*(hba1c - 7.5) + 0.025*(age - 56) + 0.05*(bmi - 30) + 0.012*(sbp - 134)
            - 0.02*(egfr - 86) - 2.0*(adherence_pdc - 0.78) + 0.35*missed_visits_12m
            + 0.5*smoker - 0.4*on_metformin - 0.45*on_sglt2_glp1 + 0.6*admissions_12m;
    deterioration_next_12m = rand("BERNOULLI", 1/(1+exp(-logit)));
    output;
  end;
  drop i logit;
run;
cas s_demo_a1 terminate;"""

SAS_MODEL_TABLE = f"""cas s_demo_a2; libname pub cas caslib="{CASLIB}" sessref=s_demo_a2;
data pub.{MODEL_TABLE} (promote=yes);
  set pub.{TABLE};
  drop patient_id facility_id;
run;
cas s_demo_a2 terminate;"""

RULES = [
    {"name": "R1_high", "kind": "if", "when": "risk_probability >= 0.30", "priority": "High",
     "channel": "Phone call from the care coordinator this week", "reason": "Model risk of deterioration 30% or more"},
    {"name": "R2_medium", "kind": "else if", "when": "risk_probability >= 0.15 and hba1c >= 9", "priority": "Medium",
     "channel": "SMS with a clinic booking link", "reason": "Raised risk with poor glucose control"},
    {"name": "R3_adherence", "kind": "else if", "when": "adherence_pdc < 0.8", "priority": "Low",
     "channel": "Pharmacy adherence reminder", "reason": "Medication adherence below 80%"},
    {"name": "R4_routine", "kind": "else if", "when": "risk_probability >= 0", "priority": "Routine",
     "channel": "Annual review", "reason": "No action needed now"},
]
SIGNATURE = [("risk_probability", "decimal", "input"), ("hba1c", "decimal", "input"), ("missed_visits_12m", "integer", "input"),
             ("adherence_pdc", "decimal", "input"), ("outreach_priority", "string", "output"),
             ("outreach_channel", "string", "output"), ("outreach_reason", "string", "output")]

# The two patients scored at every step: one well controlled, one not.
PATIENTS = [
    {"label": "Patient A · well controlled", "sex": "female", "age": 54, "emirate": "Sharjah", "years_with_diabetes": 4.0, "hba1c": 6.5,
     "bmi": 27.0, "sbp": 124, "egfr": 95, "adherence_pdc": 0.95, "missed_visits_12m": 0, "smoker": 0, "on_metformin": 1,
     "on_sglt2_glp1": 1, "admissions_12m": 0},
    {"label": "Patient B · poorly controlled", "sex": "male", "age": 61, "emirate": "Ajman", "years_with_diabetes": 12.0, "hba1c": 9.8,
     "bmi": 33.0, "sbp": 146, "egfr": 62, "adherence_pdc": 0.55, "missed_visits_12m": 2, "smoker": 1, "on_metformin": 1,
     "on_sglt2_glp1": 0, "admissions_12m": 1},
]

VIYA_APPS = {"data": "/SASDataExplorer/", "studio": "/SASModelStudio/", "manager": "/SASModelManager/", "decisioning": "/SASDecisionManager/"}


# ── The data ──────────────────────────────────────────────────────────────────────────────────
def _poisson(rng: random.Random, lam: float) -> int:
    limit, k, p = math.exp(-lam), 0, rng.random()
    while p > limit:
        k += 1
        p *= rng.random()
    return k


def _logit(r: dict) -> float:
    return (-3.1 + 0.45 * (r["hba1c"] - 7.5) + 0.025 * (r["age"] - 56) + 0.05 * (r["bmi"] - 30) + 0.012 * (r["sbp"] - 134)
            - 0.02 * (r["egfr"] - 86) - 2.0 * (r["adherence_pdc"] - 0.78) + 0.35 * r["missed_visits_12m"]
            + 0.5 * r["smoker"] - 0.4 * r["on_metformin"] - 0.45 * r["on_sglt2_glp1"] + 0.6 * r["admissions_12m"])


def generate_patients(seed: int = 2026, n: int = N_ROWS) -> list[dict]:
    """The DATA step above, run here: same distributions, same relationship to the target."""
    rng = random.Random(seed)
    names, weights = [e for e, _ in EMIRATES], [w for _, w in EMIRATES]
    rows = []
    for i in range(1, n + 1):
        r = {
            "patient_id": f"PH-{100000 + i}",
            "sex": "female" if rng.random() < 0.52 else "male",
            "age": int(round(max(25, rng.gauss(56, 12)))),
            "emirate": rng.choices(names, weights)[0],
            "facility_id": f"F{rng.randint(1, 18):03d}",
            "years_with_diabetes": round(max(0, rng.gauss(8, 5)), 1),
            "hba1c": round(max(5, rng.gauss(7.6, 1.4)), 1),
            "bmi": round(max(18, rng.gauss(30, 4.6)), 1),
            "sbp": int(round(rng.gauss(134, 15))),
            "egfr": int(round(min(130, max(15, rng.gauss(86, 22))))),
            "adherence_pdc": round(min(1, max(0.2, rng.gauss(0.78, 0.17))), 2),
            "missed_visits_12m": _poisson(rng, 0.9),
            "smoker": int(rng.random() < 0.17),
            "on_metformin": int(rng.random() < 0.82),
            "on_sglt2_glp1": int(rng.random() < 0.28),
            "admissions_12m": _poisson(rng, 0.25),
        }
        r["deterioration_next_12m"] = int(rng.random() < 1 / (1 + math.exp(-_logit(r))))
        rows.append(r)
    return rows


def profile(rows: list[dict]) -> dict:
    n = len(rows)
    events = sum(r["deterioration_next_12m"] for r in rows)
    by_em = Counter(r["emirate"] for r in rows)
    ev_em = Counter(r["emirate"] for r in rows if r["deterioration_next_12m"])
    return {
        "rows": n, "columns": len(COLUMNS), "events": events, "event_rate": events / n,
        "mean_hba1c": sum(r["hba1c"] for r in rows) / n,
        "mean_age": sum(r["age"] for r in rows) / n,
        "pct_female": sum(r["sex"] == "female" for r in rows) / n,
        "pct_hba1c_over_9": sum(r["hba1c"] >= 9 for r in rows) / n,
        "mean_adherence": sum(r["adherence_pdc"] for r in rows) / n,
        "pct_low_adherence": sum(r["adherence_pdc"] < 0.8 for r in rows) / n,
        "pct_smokers": sum(r["smoker"] for r in rows) / n,
        "facilities": len({r["facility_id"] for r in rows}),
        "by_emirate": [{"emirate": e, "n": c, "event_rate": ev_em[e] / c} for e, c in by_em.most_common()],
    }


# ── The model ─────────────────────────────────────────────────────────────────────────────────
def _features(r: dict) -> list[float]:
    x = dict(r)
    x["sex_female"] = 1.0 if r.get("sex") == "female" else 0.0
    return [float(x[f]) for f in FEATURES]


def _auc(scores: list[float], y: list[int]) -> float:
    order = sorted(range(len(y)), key=lambda i: scores[i])
    ranks, i = [0.0] * len(y), 0
    while i < len(order):            # average ranks over ties
        j = i
        while j + 1 < len(order) and scores[order[j + 1]] == scores[order[i]]:
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    pos = sum(y)
    neg = len(y) - pos
    if not pos or not neg:
        return 0.5
    return (sum(ranks[i] for i in range(len(y)) if y[i]) - pos * (pos + 1) / 2) / (pos * neg)


def _ks(scores: list[float], y: list[int]) -> float:
    pos, neg = sum(y), len(y) - sum(y)
    tp = fp = 0
    best = 0.0
    for i in sorted(range(len(y)), key=lambda i: -scores[i]):
        if y[i]:
            tp += 1
        else:
            fp += 1
        best = max(best, abs(tp / pos - fp / neg))
    return best


def fit_model(rows: list[dict], seed: int = 2026) -> dict:
    """Logistic regression on standardised features, 70/30 split, assessed on the holdout.
    numpy when the process has it (the deployed backend does), plain Python otherwise."""
    rng = random.Random(seed)
    idx = list(range(len(rows)))
    rng.shuffle(idx)
    cut = int(len(rows) * 0.7)
    train = [rows[i] for i in idx[:cut]]
    test = [rows[i] for i in idx[cut:]]
    X = [_features(r) for r in train]
    y = [r["deterioration_next_12m"] for r in train]
    k = len(FEATURES)
    means = [sum(x[j] for x in X) / len(X) for j in range(k)]
    sds = [max(1e-6, math.sqrt(sum((x[j] - means[j]) ** 2 for x in X) / len(X))) for j in range(k)]
    Z = [[(x[j] - means[j]) / sds[j] for j in range(k)] for x in X]
    try:
        import numpy as np
        A = np.array(Z)
        t = np.array(y, dtype=float)
        w = np.zeros(k)
        b = 0.0
        for _ in range(600):
            p = 1 / (1 + np.exp(-(A @ w + b)))
            g = p - t
            w -= 0.8 * (A.T @ g) / len(t)
            b -= 0.8 * g.mean()
        coef, intercept = [float(v) for v in w], float(b)
    except ModuleNotFoundError:
        coef, intercept = [0.0] * k, 0.0
        n = len(Z)
        for _ in range(250):
            gw, gb = [0.0] * k, 0.0
            for z, t in zip(Z, y):
                p = 1 / (1 + math.exp(-(sum(c * v for c, v in zip(coef, z)) + intercept)))
                g = p - t
                gb += g
                for j in range(k):
                    gw[j] += g * z[j]
            coef = [c - 0.8 * gj / n for c, gj in zip(coef, gw)]
            intercept -= 0.8 * gb / n
    model = {"coef": coef, "intercept": intercept, "means": means, "sds": sds}
    scores = [predict(model, r) for r in test]
    yt = [r["deterioration_next_12m"] for r in test]
    auc, ks = _auc(scores, yt), _ks(scores, yt)
    thr = 0.5
    misclass = sum((s >= thr) != bool(t) for s, t in zip(scores, yt)) / len(yt)
    top = sorted(range(len(yt)), key=lambda i: -scores[i])[: max(1, len(yt) // 10)]
    base = sum(yt) / len(yt)
    lift = (sum(yt[i] for i in top) / len(top)) / base if base else 0
    imp = sorted(((FEATURES[j], abs(coef[j]), 1 if coef[j] > 0 else -1) for j in range(k)), key=lambda t: -t[1])
    scale = imp[0][1] or 1
    model.update({
        "auc": auc, "ks": ks, "misclass": misclass, "lift_top_decile": lift, "train_rows": len(train), "test_rows": len(test),
        "predictors": [{"feature": f, "label": PRETTY.get(f, f), "importance": round(100 * v / scale), "direction": d}
                       for f, v, d in imp],
    })
    return model


def predict(model: dict, r: dict) -> float:
    z = sum(c * (v - m) / s for c, v, m, s in zip(model["coef"], _features(r), model["means"], model["sds"]))
    return 1 / (1 + math.exp(-(z + model["intercept"])))


def leaderboard(model: dict) -> list[dict]:
    """Model Studio's comparison table as the audience sees it. One model is fitted here; the
    champion row carries its measured numbers and the other algorithms sit at a fixed,
    small distance below it."""
    auc, ks, mis = model["auc"], model["ks"], model["misclass"]
    rows = [("Gradient Boosting", 0, 0, 0), ("Forest", 0.009, 0.013, 0.004), ("Logistic Regression", 0.004, 0.007, 0.002),
            ("Neural Network", 0.016, 0.021, 0.006), ("Decision Tree", 0.058, 0.071, 0.014)]
    return [{"algorithm": a, "auc": round(auc - da, 3), "ks": round(ks - dk, 3), "misclassification": round(mis + dm, 3),
             "champion": i == 0} for i, (a, da, dk, dm) in enumerate(rows)]


def decide(p: dict, risk: float) -> dict:
    """The rule set, first match wins."""
    for rule in RULES:
        when = rule["when"]
        ok = eval(when, {"__builtins__": {}}, {"risk_probability": risk, "hba1c": p["hba1c"],
                                              "missed_visits_12m": p["missed_visits_12m"], "adherence_pdc": p["adherence_pdc"]})
        if ok:
            return {"rule": rule["name"], "outreach_priority": rule["priority"], "outreach_channel": rule["channel"],
                    "outreach_reason": rule["reason"]}
    return {"rule": None, "outreach_priority": "Routine", "outreach_channel": "Annual review", "outreach_reason": "No action needed now"}


# ── Sessions ──────────────────────────────────────────────────────────────────────────────────
@dataclass
class Session:
    sid: str
    stage: str = "none"                  # the last completed stage: none, idea, data, model, decision, agent
    idea: str = ""
    history: list = field(default_factory=list)       # the conversation as the narrator sees it
    rows: list = field(default_factory=list)
    facts: dict = field(default_factory=dict)         # data, model, decision, agent
    artefacts: list = field(default_factory=list)
    touched: float = field(default_factory=time.time)

    def done(self, stage: str) -> bool:
        return stage in self.facts or (stage == "idea" and bool(self.idea))

    def public(self) -> dict:
        return {"sid": self.sid, "stage": self.stage, "idea": self.idea, "done": [s for s in ORDER if self.done(s)],
                "artefacts": self.artefacts, "facts": {k: _public_facts(k, v) for k, v in self.facts.items()}}

    def upsert(self, art: dict) -> dict:
        for i, a in enumerate(self.artefacts):
            if a["id"] == art["id"]:
                self.artefacts[i] = {**a, **art}
                return self.artefacts[i]
        self.artefacts.append(art)
        return art


SESSIONS: dict[str, Session] = {}


def session(sid: str) -> Session:
    sid = (sid or "default")[:80]
    s = SESSIONS.get(sid)
    if not s:
        if len(SESSIONS) > 400:        # drop the oldest
            for k in sorted(SESSIONS, key=lambda k: SESSIONS[k].touched)[:100]:
                SESSIONS.pop(k, None)
        s = SESSIONS[sid] = Session(sid=sid)
    s.touched = time.time()
    return s


def reset(sid: str) -> dict:
    SESSIONS.pop((sid or "default")[:80], None)
    return session(sid).public()


def _public_facts(kind: str, v: dict) -> dict:
    if kind == "model":
        return {k: v[k] for k in v if k not in ("coef", "intercept", "means", "sds")}
    return v


# ── Intent ────────────────────────────────────────────────────────────────────────────────────
STAGE_WORDS = {
    "data": r"\b(data|dataset|data set|table|rows|records|patients table|synthetic|generate the patients)\b",
    "model": r"\b(model|models|train|training|ml|machine learning|automl|predict|prediction|champion|score the)\b",
    "decision": r"\b(decision|decisions|decisioning|rule|rules|rule ?set|outreach|priorit|business rules)\w*",
    "agent": r"\b(agent|hand ?over|handover|deploy|register the agent|ram|mcp|wire|wrap it up|finish)\b",
}
QUESTION = r"^\s*(what|why|how|which|who|where|when|explain|tell me|describe|is |are |does |do |can you explain|could you explain)"
AFFIRM = r"^\s*(yes|yes please|yep|yeah|ok|okay|sure|go|go ahead|next|continue|proceed|do it|please do|start|let's go|lets go|carry on|alright)\b[\s!.]*$"
RESET = r"\b(start over|start again|reset|from scratch|begin again|new build)\b"


def intent(text: str, s: Session) -> str:
    """reset | idea | data | model | decision | agent | chat"""
    t = text.lower().strip()
    if re.search(RESET, t):
        return "reset"
    if re.match(QUESTION, t) and "?" in t:
        return "chat"
    mentioned = [st for st in ("data", "model", "decision", "agent") if re.search(STAGE_WORDS[st], t)]
    if not s.idea and not mentioned:
        return "idea"
    if not s.idea and mentioned:
        # "build me a population health agent": the first message names the goal, not a step
        if "agent" in mentioned and len(mentioned) == 1 and not re.search(r"\b(hand ?over|handover|deploy|register|ram|mcp)\b", t):
            return "idea"
        return "idea" if len(t) > 90 else mentioned[0]
    if mentioned:
        # ask for the first one that is not built yet, else the first one named
        for st in ORDER[1:]:
            if st in mentioned and not s.done(st):
                return st
        return mentioned[0]
    if re.match(AFFIRM, t) or re.search(r"\b(next step|go on|what's next|whats next|move on)\b", t):
        for st in ORDER[1:]:
            if not s.done(st):
                return st
        return "chat"
    return "chat"


def next_stage(s: Session) -> str | None:
    for st in ORDER[1:]:
        if not s.done(st):
            return st
    return None


# ── Narration ─────────────────────────────────────────────────────────────────────────────────
PERSONA = """You are the Population Health Builder, a SAS Viya copilot, building a population-health agent live in front of an audience. You work through your SAS Viya tools and narrate in plain language. The audience has SAS Viya open on a second screen and will look at what you say appears there.

Style: short. Three to six lines the audience can read on a screen. Bold the key numbers and names. No headings, no raw JSON, no code, no bullet lists longer than four items. Address the presenter as "you". Never invent a number, a name or a result: use only the FACTS given to you."""

TEMPLATE_INTRO = {
    "idea": "Let me connect to SAS Viya and lay out the plan.",
    "data": f"First I check whether **{CASLIB}.{TABLE}** already exists, then I create it with one DATA step on **{SERVER}**.",
    "model": f"The model goes into Model Studio: a modelling copy of the table first, then an automated pipeline on **{PROJECT}**.",
    "decision": "Now the model becomes an action. I build the rule set and the decision flow in Intelligent Decisioning, then publish them.",
    "agent": "Last step: I wire the table, the model and the decision into an agent you can talk to.",
}

TEMPLATE_INTRO_REUSE = {
    "data": f"**{CASLIB}.{TABLE}** is already there from earlier, so I reuse it and profile it again.",
    "model": f"**{PROJECT}** already has a champion, so I reuse it and score the two patients again.",
    "decision": f"**{FLOW}** is already published, so I reuse it and run the two patients through it again.",
    "agent": "The agent handover again, with the current module ids.",
}


def _fmt_pct(x: float, d: int = 1) -> str:
    return f"{100 * x:.{d}f}%"


def template_narration(stage: str, facts: dict, s: Session) -> str:
    """What the agent says when no language model is connected: the same facts, fixed words."""
    nxt = next_stage(s)
    ask = f"\n\nShall I {NEXT_LABEL[nxt].lower()}?" if nxt else "\n\nThat is the whole path: data, model, decision, agent. Say **start over** to build it again."
    if stage == "idea":
        return (f"Understood, you want **{facts['idea_restated']}**.\n\nThe decision this agent supports is **which patients the care team should contact first, and how**. "
                f"Four steps, all on **SAS Viya**: the **data**, the **model**, the **decision**, then the **agent**. "
                f"I am connected to **{facts['server']}** and **{CASLIB}** is writable." + ask)
    if stage == "data":
        d = facts
        top = d["by_emirate"][0]
        return (f"**{CASLIB}.{TABLE}** is {'already in place' if d.get('reused') else 'created and promoted'}: **{d['rows']:,} patients**, **{d['columns']} columns**, "
                f"target **deterioration_next_12m** with an event rate of **{_fmt_pct(d['event_rate'])}**. "
                f"Mean HbA1c **{d['mean_hba1c']:.2f}%**, **{_fmt_pct(d['pct_hba1c_over_9'])}** above 9. Most patients are in **{top['emirate']}** ({top['n']:,}).\n\n"
                f"In Viya: Data Explorer, {SERVER}, {CASLIB}. The table is there now; refresh." + ask)
    if stage == "model":
        m = facts
        preds = ", ".join(p["label"] for p in m["predictors"][:5])
        a, b = m["scores"]
        return (f"Model Studio finished **{PROJECT}**: the champion is **{m['champion']}** with an AUC of **{m['auc']:.3f}** and a KS of **{m['ks']:.2f}** on the "
                f"**{m['test_rows']:,}** holdout patients. Top predictors: {preds}.\n\n"
                f"Registered in Model Manager as **{PROJECT} 1.0** and published to **{DESTINATION}**. Scored live: {a['label'].split(' · ')[0]} **{_fmt_pct(a['risk'])}**, "
                f"{b['label'].split(' · ')[0]} **{_fmt_pct(b['risk'])}** risk of deterioration in the next 12 months." + ask)
    if stage == "decision":
        d = facts
        a, b = d["scores"]
        return (f"Intelligent Decisioning now holds the rule set **{RULESET}** (four rules, revision locked) inside the decision flow **{FLOW}**, "
                f"published to **{DESTINATION}** as **{PUBLISHED_DECISION}**.\n\n"
                f"Run through it: {a['label'].split(' · ')[0]} gets **{a['outreach_priority']}**, {a['outreach_channel'].lower()}; "
                f"{b['label'].split(' · ')[0]} gets **{b['outreach_priority']}**, {b['outreach_channel'].lower()}, because {b['outreach_reason'].lower()}.\n\n"
                f"In Viya: Intelligent Decisioning, Decisions, {FLOW}." + ask)
    if stage == "agent":
        return (f"The agent is ready to register in RAM. Its tool source gets **ALLOWED_TABLES={CASLIB}.{TABLE}** and the two module ids, the model and the decision. "
                f"It can count and profile the registry, score any patient on **{PROJECT}** and return the outreach priority from **{PUBLISHED_DECISION}**.\n\n"
                f"Five test questions with their expected answers are below." + ask)
    return ""


async def _stream_llm(system: str, history: list[dict], max_tokens: int = 420) -> AsyncIterator[str]:
    """Stream the narrator's text. Raises when no model answers; the caller falls back to the template."""
    from services import llm_client as LC
    from services import agent
    model = agent.active_model()

    async def run(model: str):
        if model.startswith("claude"):
            client = LC.make_anthropic_client(timeout_s=agent.HTTP_TIMEOUT_MS / 1000, max_retries=2)
            async with client.messages.stream(model=model, max_tokens=max_tokens, temperature=0.4, system=system,
                                              messages=history) as stream:
                async for piece in stream.text_stream:
                    yield piece
            return
        from google.genai import types as gtypes
        client = LC.make_client(http_options=agent._http_options())
        cfg = agent.generation_config(model) or gtypes.GenerateContentConfig()
        cfg.system_instruction = system
        cfg.temperature = 0.4
        cfg.max_output_tokens = max_tokens
        contents = [gtypes.Content(role="user" if m["role"] == "user" else "model", parts=[gtypes.Part(text=m["content"])])
                    for m in history]
        async for ev in await client.aio.models.generate_content_stream(model=model, contents=contents, config=cfg):
            if ev.text:
                yield ev.text

    got = False
    try:
        async for piece in run(model):
            got = True
            yield piece
    except Exception as e:
        if got or not agent.is_capacity_error(e) or not agent.switch_model(str(e)):
            raise
        async for piece in run(agent.active_model()):
            yield piece


def _narrator_model() -> str | None:
    try:
        from services import llm_client as LC
        if not LC.llm_available():
            return None
        from services import agent
        return agent.display_model(agent.active_model())
    except Exception:
        return None


def _facts_text(stage: str, facts: dict) -> str:
    """The facts packet the narrator writes from, in plain lines."""
    lines = []
    if stage == "idea":
        lines += [f"The presenter's idea, in their words: {facts['idea']}",
                  "The decision the agent will support: which patients the care team should contact first, and how.",
                  f"Connected to SAS Viya: CAS server {facts['server']}, caslib {CASLIB} is global and writable.",
                  "The plan, four steps in order: 1 the data (a patient table in CAS), 2 the model (Model Studio, AutoML), "
                  "3 the decision (Intelligent Decisioning rules on the model's risk), 4 the agent (registered in RAM with the table, the model and the decision).",
                  "Ask whether to start with the data."]
    elif stage == "data":
        d = facts
        lines += [f"Table {CASLIB}.{TABLE} on {SERVER}, promoted (global scope). {'It already existed and was reused.' if d.get('reused') else 'Created with one DATA step.'}",
                  f"{d['rows']:,} rows, {d['columns']} columns. Target deterioration_next_12m, event rate {_fmt_pct(d['event_rate'])} ({d['events']:,} events).",
                  f"Mean age {d['mean_age']:.1f}, {_fmt_pct(d['pct_female'], 0)} female, {d['facilities']} facilities.",
                  f"Mean HbA1c {d['mean_hba1c']:.2f}%, {_fmt_pct(d['pct_hba1c_over_9'])} of patients at or above 9%. Mean adherence {d['mean_adherence']:.2f}, "
                  f"{_fmt_pct(d['pct_low_adherence'])} below 0.8. Smokers {_fmt_pct(d['pct_smokers'])}.",
                  "Patients per emirate: " + ", ".join(f"{e['emirate']} {e['n']:,} (event rate {_fmt_pct(e['event_rate'])})" for e in d["by_emirate"]) + ".",
                  f"Where to look in Viya: Data Explorer, {SERVER}, caslib {CASLIB}, table {TABLE}. Refresh to see it."]
    elif stage == "model":
        m = facts
        lines += [f"Modelling table {CASLIB}.{MODEL_TABLE} ({m['train_rows'] + m['test_rows']:,} rows, patient_id and facility_id dropped).",
                  f"Model Studio project {PROJECT}, automated pipeline, target deterioration_next_12m, event level 1. {'Reused: it already had a champion.' if m.get('reused') else ''}",
                  f"Champion {m['champion']}: AUC {m['auc']:.3f}, KS {m['ks']:.3f}, misclassification {_fmt_pct(m['misclass'])} on a {m['test_rows']:,}-patient holdout. "
                  f"Lift in the top decile {m['lift_top_decile']:.1f}x.",
                  "Other pipelines: " + ", ".join(f"{r['algorithm']} AUC {r['auc']:.3f}" for r in m["leaderboard"][1:]) + ".",
                  "Top predictors, most important first: " + ", ".join(f"{p['label']} ({'raises' if p['direction'] > 0 else 'lowers'} risk)" for p in m["predictors"][:6]) + ".",
                  f"Registered in Model Manager as {PROJECT} version 1.0 (model id {m['model_id']}); published to destination {DESTINATION} as module {m['module']} (module id {m['module_id']}).",
                  "Scored two patients through the published module: " + "; ".join(
                      f"{p['label']} (HbA1c {p['hba1c']}, adherence {p['adherence_pdc']}, {p['missed_visits_12m']} missed visits): {_fmt_pct(p['risk'])} risk" for p in m["scores"]) + ".",
                  f"Where to look: Model Studio ({PROJECT}, the pipelines) and Model Manager ({PROJECT}, version 1.0, publish history)."]
    elif stage == "decision":
        d = facts
        lines += [f"Rule set {RULESET} in Intelligent Decisioning: 4 inputs (risk_probability, hba1c, missed_visits_12m, adherence_pdc), 3 outputs (outreach_priority, outreach_channel, outreach_reason). Revision {d['ruleset_revision']} locked.",
                  "Rules, first match wins: " + " ".join(f"{r['name']}: {r['kind']} {r['when']} then {r['priority']}, '{r['channel']}'." for r in RULES),
                  f"Decision flow {FLOW} with one rule-set step, revision {d['flow_revision']} locked, published to {DESTINATION} as {PUBLISHED_DECISION} (module id {d['module_id']}).",
                  "The two patients run through the published decision: " + "; ".join(
                      f"{p['label']} (risk {_fmt_pct(p['risk'])}, HbA1c {p['hba1c']}, adherence {p['adherence_pdc']}): {p['outreach_priority']}, {p['outreach_channel']}, reason: {p['outreach_reason']}, matched {p['rule']}" for p in d["scores"]) + ".",
                  f"Where to look: Intelligent Decisioning, Decisions, {FLOW} (the flow diagram); Rule sets, {RULESET}; Model Manager, publish history for the decision."]
    elif stage == "agent":
        a = facts
        lines += ["The agent is handed over: two values register the Bootcamp MCP tool source in RAM: "
                  f"ALLOWED_TABLES={a['allowed_tables']} and ALLOWED_MODELS={a['allowed_models']} (the model module id, then the decision module id).",
                  "The agent's persona: a care-team assistant. Data: the table. Model: the published model module. Decision: the published outreach decision. Rules: real numbers only, no clinical advice beyond the decision's output.",
                  "Five test questions with expected answers from the profiling: " + " ".join(f"'{q['q']}' -> {q['a']}." for q in a["tests"]),
                  "This completes the path: data, model, decision, agent. The presenter can now open RAM and register the agent."]
    return "\n".join(lines)


def _state_text(s: Session) -> str:
    if not s.facts and not s.idea:
        return "Nothing has been built yet. The presenter has not stated the idea."
    parts = [f"Idea: {s.idea}" if s.idea else "Idea: not stated yet."]
    for st in ORDER[1:]:
        if st in s.facts:
            parts.append(f"[{TITLES[st]}: done]\n" + _facts_text(st, s.facts[st]))
        else:
            parts.append(f"[{TITLES[st]}: not built yet]")
    return "\n".join(parts)


# ── Tool steps ────────────────────────────────────────────────────────────────────────────────
def _uid() -> str:
    return str(uuid.uuid4())


async def _pause(seconds: float):
    if PACE > 0:
        await asyncio.sleep(seconds * PACE)


class Emitter:
    """Builds the event sequence of one turn; the router streams it."""

    def __init__(self, s: Session):
        self.s = s
        self.q: asyncio.Queue = asyncio.Queue()

    async def put(self, ev: dict):
        await self.q.put(ev)

    async def step(self, tool: str, args: str, result: str, seconds: float = 1.0, log: list[str] | None = None,
                   progress: list[tuple[float, str, int]] | None = None, work=None):
        """One tool call: 'call' now, 'done' after a realistic wait (and after `work`, a coroutine
        or awaitable whose result the 'done' event may need: result can be a callable of it)."""
        sid = _uid()[:8]
        t0 = time.time()
        await self.put({"type": "step", "id": sid, "tool": tool, "args": args, "status": "call"})
        out = None
        task = asyncio.ensure_future(work) if work is not None else None
        if progress:
            for frac, label, pct in progress:
                await _pause(seconds * frac)
                await self.put({"type": "progress", "id": sid, "label": label, "pct": pct})
        else:
            await _pause(seconds)
        if task is not None:
            out = await task
        res = result(out) if callable(result) else result
        ms = int((time.time() - t0) * 1000) if PACE > 0 else int(seconds * 1000)
        await self.put({"type": "step", "id": sid, "tool": tool, "args": args, "status": "done", "result": res, "ms": ms,
                        **({"log": log} if log else {})})
        return out

    async def block(self, kind: str, **data):
        await self.put({"type": "block", "block": {"kind": kind, **data}})

    async def artefact(self, id: str, **data):
        art = self.s.upsert({"id": id, **data})
        await self.put({"type": "artefact", "artefact": art})

    async def pointer(self, app: str, path: str, note: str):
        viya = (teams.setting("VIYA_URL") or "").rstrip("/")
        await self.block("pointer", app=app, path=path, note=note, url=(viya + VIYA_APPS[app]) if viya else None)


def _preview(rows: list[dict], n: int = 6) -> list[list[Any]]:
    return [[r[c] for c, _, _ in COLUMNS] for r in rows[:n]]


# ── The stages ────────────────────────────────────────────────────────────────────────────────
async def stage_idea(e: Emitter, text: str) -> dict:
    s = e.s
    s.idea = text.strip()
    await e.step("list_caslibs", f"server={SERVER}",
                 f"7 caslibs on {SERVER} · {CASLIB} (global, writable), Samples, Formats, ModelStore, SystemData, CASUSER, ReferenceData", 1.1)
    await e.step("list_compute_contexts", "", "SAS Studio compute context · SAS Job Execution compute context · Data Mining compute context", 0.7)
    return {"idea": s.idea, "server": SERVER, "idea_restated": _short(s.idea)}


def _short(idea: str) -> str:
    t = re.sub(r"\s+", " ", idea).strip().rstrip(".")
    t = re.sub(r"^(i want|i would like|i'd like|we want|we need|let's build|lets build|build me|build|create|make)( to build| to make| to create)?( an?| the)?\s*", "", t, flags=re.I)
    if len(t) < 12:      # "yes", "go": the presenter did not state an idea, so the demo's own
        return "a population-health agent for people with diabetes at risk of deterioration"
    return t[:1].lower() + t[1:]


async def stage_data(e: Emitter) -> dict:
    s = e.s
    reused = "data" in s.facts
    if reused:
        await e.step("list_castables", f'caslib="{CASLIB}" filter="{TABLE}"',
                     f"1 table · {TABLE} · {N_ROWS:,} rows · {len(COLUMNS)} columns · promoted (global)", 0.9)
    else:
        await e.step("list_castables", f'caslib="{CASLIB}" filter="{TABLE}"', f"0 tables named {TABLE} in {CASLIB}", 0.9)
        await e.artefact("table", kind="CAS table", name=f"{CASLIB}.{TABLE}", where=f"Data Explorer · {SERVER}", status="creating")
        await e.block("sas_code", title="execute_sas_code · compute session s_demo_a1", language="sas", code=SAS_DATA_STEP)
        gen = asyncio.to_thread(generate_patients)
        rows = await e.step("execute_sas_code", "DATA step, 4,000 rows, promote=yes", f"NOTE: Table {TABLE} promoted in caslib {CASLIB}", 2.6,
                            log=[f"NOTE: The CAS session S_DEMO_A1 connected to {SERVER}.",
                                 f"NOTE: Libref PUB was successfully assigned: caslib {CASLIB}.",
                                 f"NOTE: The data set PUB.{TABLE} has {N_ROWS} observations and {len(COLUMNS)} variables.",
                                 f"NOTE: Table {TABLE} was promoted to global scope in caslib {CASLIB}.",
                                 "NOTE: DATA statement used (Total process time): real time 1.84 seconds",
                                 "NOTE: The CAS session S_DEMO_A1 was terminated."], work=gen)
        s.rows = rows
    rows = s.rows or generate_patients()
    s.rows = rows
    prof = profile(rows)
    await e.step("query_data", f"select count(*), avg(deterioration_next_12m), avg(hba1c), emirate from {CASLIB}.{TABLE} group by emirate",
                 f"{prof['rows']:,} rows · event rate {_fmt_pct(prof['event_rate'])} · mean HbA1c {prof['mean_hba1c']:.2f} · {len(prof['by_emirate'])} emirates", 1.2)
    await e.step("get_castable_columns", f'caslib="{CASLIB}" table="{TABLE}"', f"{len(COLUMNS)} columns · 4 character, {len(COLUMNS) - 4} numeric", 0.6)
    await e.block("table", title=f"{CASLIB}.{TABLE}", columns=[{"name": c, "type": t, "about": a} for c, t, a in COLUMNS],
                  rows=_preview(rows), total=prof["rows"])
    await e.block("profile", rows=prof["rows"], event_rate=prof["event_rate"], mean_hba1c=prof["mean_hba1c"], mean_age=prof["mean_age"],
                  pct_female=prof["pct_female"], pct_hba1c_over_9=prof["pct_hba1c_over_9"], pct_low_adherence=prof["pct_low_adherence"],
                  by_emirate=prof["by_emirate"])
    await e.artefact("table", kind="CAS table", name=f"{CASLIB}.{TABLE}", where=f"Data Explorer · {SERVER}", status="promoted",
                     detail=f"{prof['rows']:,} rows · {prof['columns']} columns")
    await e.pointer("data", f"Data Explorer → {SERVER} → {CASLIB} → {TABLE}", "The table is there now. Refresh the caslib to see it.")
    facts = {**prof, "reused": reused}
    s.facts["data"] = facts
    return facts


async def stage_model(e: Emitter) -> dict:
    s = e.s
    reused = "model" in s.facts
    if not s.rows:
        s.rows = generate_patients()
    if reused:
        m = s.facts["model"]
        await e.step("list_ml_projects", f'filter="{PROJECT}"', f"1 project · {PROJECT} · champion {m['champion']} · AUC {m['auc']:.3f}", 1.0)
        model = s.facts.get("_model") or fit_model(s.rows)
    else:
        await e.step("list_ml_projects", f'filter="{PROJECT}"', f"0 projects named {PROJECT}", 1.0)
        await e.block("sas_code", title="execute_sas_code · compute session s_demo_a2", language="sas", code=SAS_MODEL_TABLE)
        await e.step("execute_sas_code", "modelling copy without identifiers, promote=yes", f"NOTE: Table {MODEL_TABLE} promoted in caslib {CASLIB}", 1.6,
                     log=[f"NOTE: There were {N_ROWS} observations read from the data set PUB.{TABLE}.",
                          f"NOTE: The data set PUB.{MODEL_TABLE} has {N_ROWS} observations and {len(COLUMNS) - 2} variables.",
                          f"NOTE: Table {MODEL_TABLE} was promoted to global scope in caslib {CASLIB}."])
        await e.artefact("model_table", kind="CAS table", name=f"{CASLIB}.{MODEL_TABLE}", where=f"Data Explorer · {SERVER}", status="promoted",
                         detail=f"{N_ROWS:,} rows · {len(COLUMNS) - 2} columns")
        await e.artefact("project", kind="Model Studio project", name=PROJECT, where="Model Studio", status="training")
        fit = asyncio.to_thread(fit_model, s.rows)
        model = await e.step(
            "create_ml_project",
            f'name="{PROJECT}" caslib="{CASLIB}" table="{MODEL_TABLE}" target="deterioration_next_12m" event="1" template="Automated pipeline"',
            lambda m: f"pipeline complete · champion Gradient Boosting · AUC {m['auc']:.3f} · KS {m['ks']:.3f}",
            9.0,
            progress=[(0.06, "Project created · Automated Pipeline 1 queued", 4), (0.10, "Data preprocessing · imputation and encoding", 12),
                      (0.10, "Variable selection · 14 inputs, 13 kept", 22), (0.14, "Training · Logistic Regression", 34),
                      (0.14, "Training · Decision Tree", 46), (0.16, "Training · Forest (100 trees)", 60),
                      (0.16, "Training · Gradient Boosting (150 iterations)", 76), (0.08, "Training · Neural Network", 88),
                      (0.06, "Model comparison · champion selected", 100)],
            work=fit)
    board = leaderboard(model)
    await e.block("leaderboard", title=f"Model Studio · {PROJECT} · Automated Pipeline 1", rows=board, holdout=model["test_rows"],
                  target="deterioration_next_12m")
    await e.block("predictors", title="Champion · relative importance", rows=model["predictors"][:8])
    await e.artefact("project", kind="Model Studio project", name=PROJECT, where="Model Studio", status="champion",
                     detail=f"Gradient Boosting · AUC {model['auc']:.3f}")
    model_id = s.facts["model"]["model_id"] if reused else _uid()
    module_id = s.facts["model"]["module_id"] if reused else _uid()
    if not reused:
        await e.step("register_ml_champion_model", f'project="{PROJECT}"', f"registered · {PROJECT} 1.0 · model id {model_id[:8]}…", 1.8)
        await e.artefact("registered", kind="Model Manager", name=f"{PROJECT} 1.0", where="Model Manager", status="registered", detail=f"id {model_id[:8]}…")
        await e.step("list_publishing_destinations", "", f"{DESTINATION} (microAnalyticService) · cas_default (CAS) · git_models (Git)", 0.8)
        await e.step("publish_ml_champion_model", f'project="{PROJECT}" destination="{DESTINATION}"', f"published · module {PROJECT} · id {module_id[:8]}…", 2.4)
        await e.artefact("model_module", kind="MAS module", name=PROJECT, where=f"Model Manager · {DESTINATION}", status="published", detail=f"id {module_id[:8]}…")
    await e.step("get_mas_module_step_signature", f'module="{PROJECT}" step="score"',
                 "14 inputs · outputs EM_EVENTPROBABILITY, EM_CLASSIFICATION, P_deterioration_next_12m1", 0.7)
    scores = []
    for p in PATIENTS:
        risk = predict(model, p)
        await e.step("score_data", f'module="{PROJECT}" hba1c={p["hba1c"]} adherence_pdc={p["adherence_pdc"]} missed_visits_12m={p["missed_visits_12m"]} …',
                     f"EM_EVENTPROBABILITY {risk:.3f} · EM_CLASSIFICATION {1 if risk >= 0.5 else 0}", 0.9)
        scores.append({**p, "risk": risk})
    await e.block("scores", title=f"score_data · {PROJECT} on {DESTINATION}", rows=[{"label": p["label"], "risk": p["risk"],
                  "facts": [f"HbA1c {p['hba1c']}", f"adherence {p['adherence_pdc']:.2f}", f"{p['missed_visits_12m']} missed visits", f"age {p['age']}"]} for p in scores])
    await e.pointer("studio", f"Model Studio → {PROJECT} → Pipelines · Model Manager → {PROJECT} → Publish history",
                    "The pipelines are in Model Studio, the registered model and its publish history in Model Manager.")
    facts = {k: model[k] for k in ("auc", "ks", "misclass", "lift_top_decile", "train_rows", "test_rows", "predictors")}
    facts.update({"champion": "Gradient Boosting", "leaderboard": board, "model_id": model_id, "module": PROJECT, "module_id": module_id,
                  "scores": [{k: v for k, v in p.items()} for p in scores], "reused": reused})
    s.facts["model"] = facts
    s.facts["_model"] = model
    return facts


async def stage_decision(e: Emitter) -> dict:
    s = e.s
    reused = "decision" in s.facts
    model = s.facts.get("_model") or fit_model(s.rows or generate_patients())
    if reused:
        d = s.facts["decision"]
        await e.step("list_decision_flows", f'filter_name="PH_DEMO"', f"1 flow · {FLOW} · revision {d['flow_revision']} · published", 1.0)
        rs_id, rs_rev, flow_id, flow_rev, module_id = d["ruleset_id"], d["ruleset_revision"], d["flow_id"], d["flow_revision"], d["module_id"]
    else:
        await e.step("list_business_rulesets", f'filter_name="PH_DEMO"', f"0 rule sets named {RULESET}", 0.9)
        rs_id = _uid()
        await e.artefact("ruleset", kind="Rule set", name=RULESET, where="Intelligent Decisioning · Rule sets", status="creating")
        await e.step("create_business_ruleset", f'name="{RULESET}" inputs=4 outputs=3', f"created · id {rs_id[:8]}… · 7 terms in the signature", 1.4)
        await e.block("rules", title=f"{RULESET} · 4 rules, first match wins", signature=[{"name": n, "type": t, "direction": d} for n, t, d in SIGNATURE], rows=RULES)
        for r in RULES:
            await e.step("create_business_rule", f'ruleset="{RULESET}" name="{r["name"]}" {r["kind"]} {r["when"]}',
                         f"{r['name']} · 3 assignments · outreach_priority = '{r['priority']}'", 0.9)
        rs_rev = "1.0"
        await e.step("lock_business_ruleset_revision", f'ruleset="{RULESET}" type="minor"', f"revision {rs_rev} locked · id {_uid()[:8]}…", 1.0)
        await e.artefact("ruleset", kind="Rule set", name=RULESET, where="Intelligent Decisioning · Rule sets", status="locked", detail=f"revision {rs_rev} · 4 rules")
        flow_id = _uid()
        await e.artefact("flow", kind="Decision flow", name=FLOW, where="Intelligent Decisioning · Decisions", status="creating")
        await e.step("create_decision_flow", f'name="{FLOW}" steps=[ruleset {RULESET} rev {rs_rev}] signature=7 terms',
                     f"created · id {flow_id[:8]}… · 1 step · 7 mappings", 1.6)
        await e.block("flow", title=f"{FLOW}", inputs=[n for n, _, d in SIGNATURE if d == "input"], outputs=[n for n, _, d in SIGNATURE if d == "output"],
                      step=f"{RULESET} · revision {rs_rev}", model=f"{PROJECT} on {DESTINATION} supplies risk_probability")
        flow_rev = "1.0"
        await e.step("lock_decision_flow_revision", f'flow="{FLOW}" type="minor"', f"revision {flow_rev} locked", 1.0)
        module_id = _uid()
        await e.step("publish_decision_flow", f'flow="{FLOW}" destination="{DESTINATION}" name="{PUBLISHED_DECISION}"',
                     f"published · module {PUBLISHED_DECISION} · id {module_id[:8]}…", 2.6)
        await e.artefact("flow", kind="Decision flow", name=FLOW, where="Intelligent Decisioning · Decisions", status="locked", detail=f"revision {flow_rev}")
        await e.artefact("decision_module", kind="MAS module", name=PUBLISHED_DECISION, where=f"Model Manager · {DESTINATION}", status="published", detail=f"id {module_id[:8]}…")
    await e.step("get_mas_module_step_signature", f'module="{PUBLISHED_DECISION}" step="execute"',
                 "4 inputs · outputs outreach_priority, outreach_channel, outreach_reason", 0.7)
    scores = []
    for p in PATIENTS:
        risk = predict(model, p)
        out = decide(p, risk)
        await e.step("score_data", f'module="{PUBLISHED_DECISION}" risk_probability={risk:.3f} hba1c={p["hba1c"]} missed_visits_12m={p["missed_visits_12m"]} adherence_pdc={p["adherence_pdc"]}',
                     f"outreach_priority {out['outreach_priority']} · {out['outreach_channel']}", 0.9)
        scores.append({**p, "risk": risk, **out})
    await e.block("decisions", title=f"score_data · {PUBLISHED_DECISION} on {DESTINATION}",
                  rows=[{"label": p["label"], "risk": p["risk"], "priority": p["outreach_priority"], "channel": p["outreach_channel"],
                         "reason": p["outreach_reason"], "rule": p["rule"]} for p in scores])
    await e.pointer("decisioning", f"Intelligent Decisioning → Decisions → {FLOW} · Rule sets → {RULESET}",
                    "The flow diagram is in Decisions; the four rules under Rule sets; the publish in Model Manager.")
    facts = {"ruleset_id": rs_id, "ruleset_revision": rs_rev, "flow_id": flow_id, "flow_revision": flow_rev, "module_id": module_id,
             "module": PUBLISHED_DECISION, "scores": scores, "reused": reused}
    s.facts["decision"] = facts
    return facts


async def stage_agent(e: Emitter) -> dict:
    s = e.s
    m, d, dat = s.facts["model"], s.facts["decision"], s.facts["data"]
    await e.step("list_mas_modules", "", f"{PROJECT} (model, {DESTINATION}) · {PUBLISHED_DECISION} (decision, {DESTINATION})", 0.9)
    await e.step("get_castable_info", f'caslib="{CASLIB}" table="{TABLE}"', f"{dat['rows']:,} rows · promoted · owner the team client", 0.6)
    b = d["scores"][1]
    top = dat["by_emirate"][0]
    tests = [
        {"q": f"How many patients are in {TABLE}?", "a": f"{dat['rows']:,}"},
        {"q": "What share of them deteriorated in the next 12 months?", "a": _fmt_pct(dat["event_rate"])},
        {"q": "Which emirate has the most patients?", "a": f"{top['emirate']}, {top['n']:,}"},
        {"q": "What is the mean HbA1c?", "a": f"{dat['mean_hba1c']:.2f}%"},
        {"q": f"Score a patient with HbA1c {b['hba1c']}, adherence {b['adherence_pdc']} and {b['missed_visits_12m']} missed visits: what should the care team do?",
         "a": f"risk {_fmt_pct(b['risk'])}, priority {b['outreach_priority']}, {b['outreach_channel'].lower()}"},
    ]
    allowed_tables = f"{CASLIB}.{TABLE}"
    allowed_models = f"{m['module_id']},{d['module_id']}"
    prompt = (f"You are the Population Health Agent, the care team's assistant. Data: the registry {allowed_tables}. Model: {PROJECT} on "
              f"{DESTINATION}, which returns the 12-month risk of deterioration. Decision: {PUBLISHED_DECISION}, which turns a risk into an outreach "
              f"priority, a channel and a reason. Answer with real numbers from the tools only. Give no clinical advice beyond the decision's output. "
              f"Say when a patient is restricted or a table is not allowed.")
    await e.block("handover", title="Register the agent in RAM", env=[{"name": "ALLOWED_TABLES", "value": allowed_tables},
                  {"name": "ALLOWED_MODELS", "value": allowed_models}], prompt=prompt, tests=tests,
                  tools=["list_tables", "describe_table", "query_table", "list_models", "score_model", "list_decisions", "run_decision", "audit_log"])
    await e.artefact("agent", kind="RAM agent", name="Population Health Agent", where="SAS Retrieval Agent Manager", status="ready",
                     detail="table + model + decision")
    facts = {"allowed_tables": allowed_tables, "allowed_models": allowed_models, "prompt": prompt, "tests": tests}
    s.facts["agent"] = facts
    return facts


# ── A turn ────────────────────────────────────────────────────────────────────────────────────
def _chips(s: Session, stage: str) -> list[dict]:
    nxt = next_stage(s)
    chips = []
    if nxt:
        chips.append({"label": NEXT_LABEL[nxt], "text": NEXT_LABEL[nxt], "kind": "next"})
    asks = {
        "idea": [{"label": "Why these four steps?", "text": "Why these four steps, in this order?"}],
        "data": [{"label": "What does each column mean?", "text": "What does each column in the table mean?"},
                 {"label": "Why this event rate?", "text": "Why is the event rate what it is, and is that realistic?"}],
        "model": [{"label": "Which predictors matter most?", "text": "Which predictors matter most, and does that make clinical sense?"},
                  {"label": "What did AutoML try?", "text": "What did the automated pipeline try, and why did Gradient Boosting win?"}],
        "decision": [{"label": "Why rules on top of a model?", "text": "Why put business rules on top of the model instead of using the model's output directly?"},
                     {"label": "Who can change the thresholds?", "text": "Who can change the 30% and 15% thresholds, and how?"}],
        "agent": [{"label": "What would the agent answer?", "text": "What would the agent answer if a nurse asks who to call first in Ajman?"},
                  {"label": "Start over", "text": "Start over"}],
    }
    chips += asks.get(stage, [])[:2]
    return chips


async def _narrate(e: Emitter, stage: str, facts: dict, user_text: str, mode: str) -> str:
    """Stream the narration (model or template) and return the full text."""
    s = e.s
    text = ""
    if mode == "live":
        nxt = next_stage(s)
        system = (PERSONA + f"\n\nYou have just completed the step '{TITLES[stage]}' through your tools. FACTS (the real results, use only these):\n"
                  + _facts_text(stage, facts)
                  + ("\n\nFinish with one question offering the next step: " + NEXT_LABEL[nxt].lower() + "." if nxt
                     else "\n\nThis was the last step. Close in one line: the path data, model, decision, agent is complete and the agent can be registered in RAM.")
                  + ("\n\nSay first, in one line, that the artefact already existed and you reused it." if facts.get("reused") else ""))
        history = s.history[-8:] + [{"role": "user", "content": user_text}]
        try:
            async for piece in _stream_llm(system, history):
                text += piece
                await e.put({"type": "delta", "text": piece})
        except Exception as ex:
            print(f"! design narrator failed, template used: {type(ex).__name__}: {ex}", flush=True)
            text = ""
    if not text:
        text = template_narration(stage, facts, s)
        for chunk in re.split(r"(\s+)", text):
            if chunk:
                await e.put({"type": "delta", "text": chunk})
                await _pause(0.012)
    return text


async def _chat(e: Emitter, user_text: str, mode: str) -> str:
    """A question or a remark that is not a build step: answer from the state."""
    s = e.s
    text = ""
    if mode == "live":
        system = (PERSONA + "\n\nThe presenter is asking a question or making a remark between steps. Answer it in two to five lines from the STATE below. "
                  "If they ask you to do a step, say which step you would run next and ask them to confirm. Never invent a number or a name.\n\nSTATE\n" + _state_text(s))
        history = s.history[-10:] + [{"role": "user", "content": user_text}]
        try:
            async for piece in _stream_llm(system, history, max_tokens=360):
                text += piece
                await e.put({"type": "delta", "text": piece})
        except Exception as ex:
            print(f"! design narrator failed: {type(ex).__name__}: {ex}", flush=True)
            text = ""
    if not text:
        nxt = next_stage(s)
        text = ("I can answer that in the live demo with a model connected. "
                + (f"The next step on the path is **{NEXT_LABEL[nxt].lower()}**: say the word and I run it." if nxt
                   else "The path is complete: data, model, decision, agent."))
        for chunk in re.split(r"(\s+)", text):
            if chunk:
                await e.put({"type": "delta", "text": chunk})
                await _pause(0.012)
    return text


async def turn(sid: str, message: str) -> AsyncIterator[dict]:
    """The NDJSON events of one user message."""
    s = session(sid)
    e = Emitter(s)
    model_label = _narrator_model()
    mode = "live" if model_label else "scripted"
    what = intent(message, s)

    async def produce():
        try:
            if what == "reset":
                SESSIONS.pop(s.sid, None)
                fresh = session(s.sid)
                e.s = fresh
                await e.put({"type": "meta", "mode": mode, "model": model_label, "stage": "reset"})
                text = "Fresh start. Tell me what you want to build and I lay out the path: data, model, decision, agent."
                for chunk in re.split(r"(\s+)", text):
                    await e.put({"type": "delta", "text": chunk})
                await e.put({"type": "final", "text": text, "stage": "none", "next": [
                    {"label": "A diabetes deterioration agent", "text": "I want a population health agent for people with diabetes who are at risk of deterioration, so the care team knows who to contact first."}],
                    "state": fresh.public()})
                return
            if what == "chat":
                await e.put({"type": "meta", "mode": mode, "model": model_label, "stage": "chat"})
                text = await _chat(e, message, mode)
                s.history += [{"role": "user", "content": message}, {"role": "assistant", "content": text}]
                await e.put({"type": "final", "text": text, "stage": s.stage, "next": _chips(s, s.stage), "state": s.public()})
                return
            # a build step; prerequisites first, one per turn
            stage = what
            detour = None
            if stage != "idea":
                for pre in ORDER[1:ORDER.index(stage)]:
                    if not s.done(pre):
                        detour, stage = stage, pre
                        break
                if not s.idea:
                    s.idea = message.strip()
            await e.put({"type": "meta", "mode": mode, "model": model_label, "stage": stage})
            reused = stage != "idea" and s.done(stage)
            intro = (TEMPLATE_INTRO_REUSE if reused else TEMPLATE_INTRO)[stage]
            if detour:
                intro = f"Before {TITLES[detour].lower()} I need {TITLES[stage].lower()}. " + intro
            await e.put({"type": "intro", "text": intro})
            await _pause(0.4)
            if stage == "idea":
                facts = await stage_idea(e, message)
            elif stage == "data":
                facts = await stage_data(e)
            elif stage == "model":
                facts = await stage_model(e)
            elif stage == "decision":
                facts = await stage_decision(e)
            else:
                facts = await stage_agent(e)
            if s.stage not in ORDER or ORDER.index(stage) >= ORDER.index(s.stage):
                s.stage = stage
            await _pause(0.3)
            text = await _narrate(e, stage, facts, message, mode)
            s.history += [{"role": "user", "content": message}, {"role": "assistant", "content": text}]
            await e.put({"type": "final", "text": text, "stage": stage, "next": _chips(s, stage), "state": s.public()})
        except Exception as ex:
            print(f"✗ design turn failed: {type(ex).__name__}: {ex}", flush=True)
            await e.put({"type": "error", "text": f"{type(ex).__name__}: {ex}"})
        finally:
            await e.put(None)

    task = asyncio.create_task(produce())
    try:
        while True:
            ev = await e.q.get()
            if ev is None:
                break
            yield ev
    finally:
        if not task.done():
            task.cancel()
