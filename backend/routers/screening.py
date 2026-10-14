"""Cancer screening: colorectal cancer screening, the composite AI example.

  /api/screening/crc/options · assess · chat          the screening check (services/crc.py)
  /api/screening/crc/rules                             the policy catalogue the rules implement
  /api/screening/crc/dashboard · map · worklist · person · data   the programme (services/screening.py)
  /api/screening/crc/documents                         the screening documents in the corpus
  /api/screening/crc/model/...                         the non-completion model and its what-if (services/crc_ml.py)
  /api/screening/crc/agent/...                         the composite agent, its queue and audit view (services/crc_agent.py)
"""
from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from services import crc, crc_agent, crc_ml, screening

router = APIRouter(prefix="/api/screening/crc", tags=["screening"])


class Location(BaseModel):
    area: str | None = None
    lat: float | None = None
    lon: float | None = None
    label: str | None = None


class Person(BaseModel):
    age: int = Field(ge=18, le=100)
    sex: str = "female"
    height_cm: float | None = None
    weight_kg: float | None = None
    bmi: float | None = None
    smoking: str = "never"
    diabetes: bool = False
    family_history: str = "none"
    youngest_relative_age: int | None = None
    history: list[str] = []
    symptoms: list[str] = []
    symptom_duration: str | None = None
    notes: dict[str, str] = {}
    last_screen: str = "never"
    activity: str = "some"
    diet: str = "mixed"
    alcohol: str = "none"
    location: Location | None = None


def _ndjson(gen):
    async def stream():
        async for ev in gen:
            yield json.dumps(ev, default=str) + "\n"
    return StreamingResponse(stream(), media_type="application/x-ndjson")


# ── the screening check ──
@router.get("/options")
def options() -> dict[str, Any]:
    return crc.options()


@router.post("/assess")
def assess(p: Person) -> dict[str, Any]:
    return crc.assess(p.model_dump())


class ChatRequest(BaseModel):
    person: Person
    messages: list[dict[str, Any]]


@router.post("/chat")
async def chat(req: ChatRequest):
    return _ndjson(crc.chat(req.person.model_dump(), req.messages))


# ── the rules ──
@router.get("/rules")
def rules():
    return {"rules": crc.rules_catalogue(), "guide": crc.GUIDE, "examples": crc.EXAMPLES, "decision": crc.decision_flow()}


@router.get("/rules/test_cases")
def rules_test_cases():
    return {"cases": screening.decision_test_cases()}


@router.get("/rules/run/{person_id}")
def rules_run(person_id: str):
    r = screening.decision_run(person_id)
    if r.get("error"):
        raise HTTPException(404, r["error"])
    return r


# ── the programme ──
@router.get("/dashboard")
def dashboard(filters: str = ""):
    try:
        f = json.loads(filters) if filters else {}
    except json.JSONDecodeError:
        raise HTTPException(400, "filters must be a JSON object")
    f = {k: v for k, v in (f or {}).items() if k in screening.FILTER_LABELS and v}
    return screening.dashboard(json.dumps(f, sort_keys=True) if f else "")


@router.get("/map")
def map_():
    return screening.map_payload()


@router.get("/worklist")
def worklist(kind: str = "due", limit: int = 25, uninvited_only: bool = False):
    try:
        return {"kind": kind, "items": screening.worklist(kind, min(limit, 200), uninvited_only)}
    except ValueError:
        raise HTTPException(400, "kind must be due | batch | fit_positive | urgent")


@router.get("/person/{person_id}")
def person(person_id: str):
    p = screening.person(person_id)
    if p.get("error"):
        raise HTTPException(404, p["error"])
    return p


@router.get("/data/tables")
def data_tables():
    return {"tables": screening.table_list(), "source": {"loaded_from": "local-csv", "backend": "local"}}


@router.get("/data/{table}")
def data_rows(table: str, offset: int = 0, limit: int = 50, search: str = ""):
    try:
        return screening.table_rows(table, offset, limit, search)
    except KeyError:
        raise HTTPException(404, f"unknown table '{table}'")


@router.get("/documents")
def documents():
    from services import rag
    docs = [d for d in rag.list_documents() if d["file"].startswith(crc.SCREENING_DOCS)]
    return {"documents": docs, "status": rag.status()}


# ── the model ──
@router.get("/model")
def model():
    if not crc_ml.available():
        raise HTTPException(503, "screening_uptake model not trained: run python -m scripts.train_models")
    card = crc_ml.card()
    fairness = []
    try:
        from sklearn.metrics import roc_auc_score
        ev = pd.read_csv(crc_ml.MODELS / "screening_eval_predictions.csv.gz")
        for col in ("language", "nationality_group", "sex"):
            for g, part in ev.groupby(col):
                if len(part) < 60 or part["y_true"].nunique() < 2:
                    continue
                fairness.append({"dimension": col, "group": str(g), "n": int(len(part)),
                                 "auc": round(float(roc_auc_score(part["y_true"], part["p"])), 3),
                                 "event_rate": round(float(part["y_true"].mean()), 3),
                                 "high_band_rate": round(float((part["p"] >= 0.5).mean()), 3)})
    except Exception:
        pass
    return {"card": card, "spec": crc_ml.spec(), "bands": [{"band": b, "from": lo} for b, lo in crc_ml.BANDS],
            "outreach": crc_ml.OUTREACH, "fairness": fairness}


@router.get("/model/profiles")
def model_profiles():
    return {"profiles": crc_ml.profiles()}


@router.get("/model/profile/{profile_id}")
def model_profile(profile_id: str):
    r = crc_ml.profile_baseline(profile_id)
    if r.get("error"):
        raise HTTPException(404, r["error"])
    return r


@router.get("/model/profile/{profile_id}/preset/{preset_id}")
def model_preset(profile_id: str, preset_id: str):
    ov = crc_ml.preset_overrides(profile_id, preset_id)
    if not ov:
        raise HTTPException(404, "unknown preset or profile")
    return {"overrides": ov}


class SimRequest(BaseModel):
    profile_id: str
    overrides: dict = {}
    actor: str = "programme lead"


@router.post("/model/simulate")
def model_simulate(req: SimRequest):
    r = crc_ml.simulate(req.profile_id, req.overrides)
    if r.get("error"):
        raise HTTPException(404, r["error"])
    return r


@router.post("/model/explain")
async def model_explain(req: SimRequest):
    return _ndjson(crc_ml.explain(req.profile_id, req.overrides, req.actor))


# ── the agent ──
@router.get("/agent/scenarios")
def agent_scenarios():
    return {"scenarios": crc_agent.list_scenarios(), "llm_enabled": crc_agent.llm_enabled(),
            "live_chat": crc_agent._anthropic_model() is not None,
            "agents": ["screening_supervisor", "rules_agent", "risk_agent", "guideline_agent", "action_agent", "guardrail_agent", "cohort_agent"]}


class AgentRequest(BaseModel):
    message: str = ""
    session_id: str = "default"
    scenario_id: str | None = None


@router.post("/agent/chat")
async def agent_chat(req: AgentRequest):
    if req.scenario_id:
        runner = crc_agent.get_runner(req.scenario_id)
        if not runner:
            raise HTTPException(404, "unknown scenario")
        return _ndjson(runner(req.message))
    return _ndjson(crc_agent.stream_chat(req.message, req.session_id))


@router.get("/agent/queue")
def agent_queue(status: str | None = None):
    return {"items": crc_agent.queue_items(status)}


@router.get("/agent/audit")
def agent_audit(limit: int = 80):
    return {"entries": crc_agent.audit_entries(limit)}
