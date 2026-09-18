"""What-if simulator APIs: baseline, live re-scoring, presets, and a streamed language-model
explanation of why the deployed model's estimate moved.

Two subjects: an anonymous *profile* (the Simulator dashboard: a clinical archetype, no
identity) or a registry *patient* (the assistant's simulate tool). A request names one of
the two; a profile resolves to the registry row that represents it server-side."""
from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from services import audit as audit_svc
from services import whatif

router = APIRouter()


class SimRequest(BaseModel):
    patient_id: str | None = None
    profile_id: str | None = None
    overrides: dict = {}
    actor: str = "clinician"


def _subject(req: SimRequest) -> str:
    """The registry row to score: the profile's representative row, or the patient itself."""
    if req.profile_id:
        pid = whatif.resolve_profile(req.profile_id)
        if pid is None:
            raise HTTPException(404, f"unknown profile {req.profile_id}")
        return pid
    if not req.patient_id:
        raise HTTPException(422, "patient_id or profile_id is required")
    return req.patient_id


@router.get("/api/simulate/profiles")
def simulate_profiles():
    return {"profiles": whatif.profiles()}


@router.get("/api/simulate/profile/{profile_id}")
def simulate_profile(profile_id: str):
    res = whatif.profile_baseline(profile_id)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    return res


@router.get("/api/simulate/profile/{profile_id}/preset/{preset_id}")
def simulate_profile_preset(profile_id: str, preset_id: str):
    pid = whatif.resolve_profile(profile_id)
    ov = whatif.preset_overrides(preset_id, pid) if pid else {}
    if not ov:
        raise HTTPException(404, "unknown preset or profile")
    return {"overrides": ov}


@router.get("/api/simulate/patients")
def simulate_patients(q: str = "", limit: int = 8):
    return {"presets": whatif.presets_patients(), "matches": whatif.search_patients(q, min(limit, 20))}


@router.get("/api/simulate/baseline/{patient_id}")
def simulate_baseline(patient_id: str):
    res = whatif.baseline(patient_id)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    if res.get("consent") == "DENIED":
        audit_svc.log("CONSENT·DENIED", "clinician", "What-if simulator blocked on a restricted record",
                      patient_id, "warning")
    return res


@router.get("/api/simulate/preset/{patient_id}/{preset_id}")
def simulate_preset(patient_id: str, preset_id: str):
    ov = whatif.preset_overrides(preset_id, patient_id)
    if not ov:
        raise HTTPException(404, "unknown preset or patient")
    return {"overrides": ov}


@router.post("/api/simulate")
def simulate(req: SimRequest):
    res = whatif.simulate(_subject(req), req.overrides)
    if res.get("error"):
        raise HTTPException(404, res["error"])
    if req.profile_id:
        res.pop("patient_id", None)
        res["profile_id"] = req.profile_id
    return res


@router.post("/api/simulate/explain")
async def simulate_explain(req: SimRequest):
    subject = _subject(req)

    async def stream():
        async for ev in whatif.explain(subject, req.overrides, req.actor, profile_id=req.profile_id):
            yield json.dumps(ev, default=str) + "\n"
    return StreamingResponse(stream(), media_type="application/x-ndjson")
