"""Patient-level what-if simulator.

The clinician moves a lever (HbA1c, blood pressure, adherence, a therapy flag ...) and the
SAME deployed deterioration-risk model re-scores the patient. Nothing here is canned:

  * baseline and simulated probabilities come from the XGBoost booster in ml.py;
  * the per-feature attribution is the change in the booster's own pred_contribs
    (SHAP-style, log-odds space) allocated proportionally onto the probability change;
  * the registry percentile comes from scoring the whole registry once and caching it;
  * rule-based care gaps that depend on the levers are re-derived, so closing the HbA1c
    recall gap or starting an SGLT2 inhibitor is reflected in the gap list and in
    care_gap_count (which is itself a model feature).

The language model's role is explanation only: it is handed the numbers and asked to
narrate them. Without LLM credentials a deterministic narrative is produced from the same
numbers, so the simulator works in direct tool mode too.
"""
from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import AsyncGenerator

import numpy as np
import pandas as pd
from xgboost import DMatrix

from services import audit as audit_svc
from services import hie, ml

# ── Levers exposed to the UI (order = display order) ─────────────────────────────────
# kind: range | toggle. group: display grouping. Bounds follow the registry's 2nd–98th pct
# with clinical head-room; step is what a clinician would plausibly type.
LEVERS: list[dict] = [
    {"key": "age", "label": "Age", "unit": "y", "kind": "range", "min": 18, "max": 90, "step": 1,
     "group": "Profile", "hint": "Risk rises with age; everything else held equal"},
    {"key": "hba1c_latest", "label": "HbA1c", "unit": "%", "kind": "range", "min": 5.0, "max": 13.0, "step": 0.1,
     "group": "Glycaemic control", "hint": "Target <7% (individualised); ≥9% is poor control"},
    {"key": "hba1c_days_since_test", "label": "Days since last HbA1c", "unit": "d", "kind": "range", "min": 0, "max": 600, "step": 5,
     "group": "Glycaemic control", "hint": "Registry expects a test every 6 months (180 days)"},
    {"key": "sbp_latest", "label": "Systolic BP", "unit": "mmHg", "kind": "range", "min": 95, "max": 195, "step": 1,
     "group": "Cardio-renal", "hint": "Target <140 mmHg in diabetes with hypertension"},
    {"key": "egfr_latest", "label": "eGFR", "unit": "mL/min", "kind": "range", "min": 5, "max": 130, "step": 1,
     "group": "Cardio-renal", "hint": "<60 = CKD stage 3 or worse"},
    {"key": "acr_latest", "label": "Urine ACR", "unit": "mg/mmol", "kind": "range", "min": 0.3, "max": 60, "step": 0.1,
     "group": "Cardio-renal", "hint": "≥3 mg/mmol = albuminuria"},
    {"key": "adherence_pdc", "label": "Medication adherence (PDC)", "unit": "", "kind": "range", "min": 0.2, "max": 1.0, "step": 0.01,
     "group": "Behaviour", "hint": "Proportion of days covered; ≥0.80 counts as adherent", "percent": True},
    {"key": "bmi", "label": "BMI", "unit": "kg/m²", "kind": "range", "min": 17, "max": 47, "step": 0.1,
     "group": "Behaviour", "hint": "≥30 = obesity"},
    {"key": "smoker", "label": "Current smoker", "kind": "toggle", "group": "Behaviour"},
    {"key": "on_metformin", "label": "Metformin", "kind": "toggle", "group": "Therapy"},
    {"key": "on_sglt2_glp1", "label": "SGLT2 inhibitor / GLP-1 RA", "kind": "toggle", "group": "Therapy",
     "hint": "Guideline-recommended intensification for uncontrolled type 2"},
    {"key": "on_raas_inhibitor", "label": "RAAS inhibitor (ACEi / ARB)", "kind": "toggle", "group": "Therapy",
     "hint": "Renal protection when albuminuria or CKD is present"},
    {"key": "admissions_12mo", "label": "Admissions, last 12 months", "unit": "", "kind": "range", "min": 0, "max": 4, "step": 1,
     "group": "Utilisation"},
    {"key": "ed_visits_12mo", "label": "ED visits, last 12 months", "unit": "", "kind": "range", "min": 0, "max": 4, "step": 1,
     "group": "Utilisation"},
]
LEVER_KEYS = {l["key"] for l in LEVERS}
THERAPY_FLAGS = ["on_metformin", "on_sglt2_glp1", "on_insulin", "on_raas_inhibitor"]

FEATURE_LABELS = {
    "age": "Age", "is_male": "Male sex", "bmi": "BMI", "bmi_change_12m": "BMI change (12 m)",
    "years_since_diagnosis": "Years since diagnosis", "smoker": "Smoking",
    "hba1c_latest": "HbA1c", "hba1c_12m_ago": "HbA1c 12 months ago", "hba1c_days_since_test": "Days since HbA1c test",
    "sbp_latest": "Systolic BP", "dbp_latest": "Diastolic BP", "egfr_latest": "eGFR", "acr_latest": "Urine ACR",
    "albuminuria": "Albuminuria", "retinopathy": "Retinopathy", "neuropathy": "Neuropathy",
    "foot_ulcer_history": "Foot ulcer history", "htn": "Hypertension", "on_metformin": "Metformin",
    "on_sglt2_glp1": "SGLT2i / GLP-1 RA", "on_insulin": "Insulin", "on_raas_inhibitor": "RAAS inhibitor",
    "adherence_pdc": "Adherence (PDC)", "admissions_12mo": "Admissions (12 m)", "ed_visits_12mo": "ED visits (12 m)",
    "diabetes_medication_count": "Diabetes medicines", "care_gap_count": "Open care gaps",
}

# Rule-based gaps the simulator can re-derive from the lever state, each with the levers it
# depends on. The rules mirror scripts/generate_hie_data.py exactly, and a gap is only
# re-derived when one of its inputs was moved; otherwise the record's state stands, so a
# simulation with no changes scores exactly the baseline. The remaining gaps (retinal / foot
# screening, ACR screening, therapy inertia) come from the record as-is.
DERIVED_GAPS = {
    "hba1c_overdue": (lambda r: r["hba1c_days_since_test"] > 183, {"hba1c_days_since_test"}),
    "bp_uncontrolled": (lambda r: bool(r["htn"]) and (r["sbp_latest"] >= 140 or r["dbp_latest"] >= 90), {"sbp_latest"}),
    "glp1_sglt2_gap": (lambda r: r["diabetes_type"] == "type2" and r["hba1c_latest"] >= 8.0
                       and (r["bmi"] >= 30 or bool(r["ckd"]) or bool(r["albuminuria"])) and not r["on_sglt2_glp1"],
                       {"hba1c_latest", "bmi", "egfr_latest", "acr_latest", "on_sglt2_glp1"}),
    "low_adherence": (lambda r: r["adherence_pdc"] < 0.6, {"adherence_pdc"}),
    "renal_protection_gap": (lambda r: (bool(r["albuminuria"]) or bool(r["ckd"])) and not r["on_raas_inhibitor"],
                             {"egfr_latest", "acr_latest", "on_raas_inhibitor"}),
}

# One-click presets applied on top of the record
PRESETS = {
    "guideline_targets": {
        "label": "Guideline targets",
        "description": "HbA1c 7.0%, systolic 130 mmHg, HbA1c tested today, adherent (PDC 0.90); no change to therapy.",
        "set": {"hba1c_latest": 7.0, "sbp_latest": 130, "hba1c_days_since_test": 0, "adherence_pdc": 0.90},
    },
    "intensify": {
        "label": "Intensify therapy",
        "description": "Start an SGLT2 inhibitor / GLP-1 RA and a RAAS inhibitor; everything else unchanged.",
        "set": {"on_sglt2_glp1": 1, "on_raas_inhibitor": 1},
    },
    "deteriorate": {
        "label": "Left untreated",
        "description": "HbA1c +1.5 points, systolic +15 mmHg, adherence −0.20, one admission, the trajectory if nothing changes.",
        "delta": {"hba1c_latest": 1.5, "sbp_latest": 15, "adherence_pdc": -0.20, "admissions_12mo": 1},
    },
}


# ── Anonymous profiles ───────────────────────────────────────────────────────────────
# The simulator is about the factors, not a person: each profile is a clinical archetype,
# represented by the (synthetic) registry row closest to the centre of its cohort, and shown
# without name, id, facility or nationality. The row gives the model a complete, coherent
# feature vector; the levers are what the user moves.
PROFILES: list[dict] = [
    {"id": "well_controlled", "label": "Well controlled",
     "description": "HbA1c under 7% and no open care gaps",
     "rule": lambda s: (s["hba1c_latest"] < 7.0) & (s["care_gap_count"] == 0)},
    {"id": "typical_t2", "label": "Typical type 2",
     "description": "HbA1c 7 to 8.5% on metformin, not on insulin",
     "rule": lambda s: (s["diabetes_type"] == "type2") & s["hba1c_latest"].between(7.0, 8.5)
                       & (s["on_metformin"] == 1) & (s["on_insulin"] == 0)},
    {"id": "uncontrolled_obese", "label": "Uncontrolled and obese",
     "description": "HbA1c 9% or more, BMI over 30, not yet on an SGLT2i or GLP-1 RA",
     "rule": lambda s: (s["diabetes_type"] == "type2") & (s["hba1c_latest"] >= 9.0) & (s["bmi"] > 30)
                       & (s["on_sglt2_glp1"] == 0)},
    {"id": "kidney_disease", "label": "Kidney disease",
     "description": "eGFR under 60 with albuminuria",
     "rule": lambda s: (s["egfr_latest"] < 60) & (s["albuminuria"] == 1)},
    {"id": "recent_admission", "label": "Recent admission",
     "description": "Admitted in the last 12 months, very high model risk",
     "rule": lambda s: (s["admissions_12mo"] >= 1) & (s["p"] >= 0.25)},
]
PROFILE_IDS = {p["id"] for p in PROFILES}
_PROFILE_FEATURES = ["age", "bmi", "hba1c_latest", "sbp_latest", "egfr_latest", "acr_latest",
                     "adherence_pdc", "admissions_12mo", "ed_visits_12mo", "care_gap_count", "p"]


@lru_cache(maxsize=1)
def _profile_rows() -> dict:
    """profile id -> the registry patient_id that represents it (deterministic)."""
    s = hie.summary()
    s = s[s["consent_status"] != "restricted"].copy()
    s["p"] = ml._score(ml._feature_frame(s))
    out = {}
    for prof in PROFILES:
        g = s[prof["rule"](s)]
        if g.empty:
            g = s
        z = g[_PROFILE_FEATURES].astype(float)
        z = (z - z.median()) / (z.std(ddof=0).replace(0, 1.0))
        out[prof["id"]] = str(g.loc[(z ** 2).sum(axis=1).idxmin(), "patient_id"])
    return out


def resolve_profile(profile_id: str) -> str | None:
    """The patient row behind a profile id, or None for an unknown profile."""
    return _profile_rows().get(profile_id)


def _profile_header(row: pd.Series, prof: dict) -> dict:
    """What the UI may show about a profile: the archetype and its clinical factors, no identity."""
    gaps = [g for g in str(row["open_care_gaps"] or "").split(";") if g]
    return {
        "id": prof["id"], "label": prof["label"], "description": prof["description"],
        "age": int(row["age"]), "gender": row["gender"], "diabetes_type": row["diabetes_type"],
        "years_since_diagnosis": _clean(row["years_since_diagnosis"]), "registry_tier": row["registry_risk_tier"],
        "hba1c_12m_ago": _clean(row["hba1c_12m_ago"]), "open_care_gaps": gaps,
        "gap_labels": [hie.GAP_LABELS.get(g, g) for g in gaps],
        "retinopathy": int(row["retinopathy"]), "neuropathy": int(row["neuropathy"]),
        "foot_ulcer_history": int(row["foot_ulcer_history"]), "htn": int(row["htn"]), "ckd": int(row["ckd"]),
    }


def profiles() -> list[dict]:
    """The profile chips: archetype, one-line description, the model's risk for it."""
    out = []
    for prof in PROFILES:
        row = _row(resolve_profile(prof["id"]))
        prob, _ = _contribs(row)
        out.append({"id": prof["id"], "label": prof["label"], "description": prof["description"],
                    "probability": round(prob, 4), "band": ml._band(prob),
                    "age": int(row["age"]), "diabetes_type": row["diabetes_type"],
                    "hba1c_latest": _clean(row["hba1c_latest"])})
    return out


def profile_baseline(profile_id: str) -> dict:
    """The baseline for a profile: the same as a patient's, with the identity replaced by the archetype."""
    pid = resolve_profile(profile_id)
    if pid is None:
        return {"error": f"unknown profile {profile_id}"}
    b = baseline(pid)
    if b.get("error") or b.get("consent") == "DENIED":
        return b
    prof = next(p for p in PROFILES if p["id"] == profile_id)
    b.pop("patient", None)
    b["profile"] = _profile_header(_row(pid), prof)
    return b


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    return v.item() if hasattr(v, "item") else v


@lru_cache(maxsize=1)
def _monotone() -> dict:
    spec = json.loads((ml.MODELS / "complication_risk.features.json").read_text())
    return spec.get("monotone", {})


def _model_version() -> str:
    spec = json.loads((ml.MODELS / "complication_risk.features.json").read_text())
    return spec.get("version", "2.1.0")


def _facility_name(fid: str) -> str:
    f = hie.tables()["facilities"]
    row = f[f["facility_id"] == fid]
    return str(row.iloc[0]["facility_name"]) if not row.empty else str(fid)


@lru_cache(maxsize=1)
def _registry_probs() -> np.ndarray:
    """Every consenting patient scored once, gives the percentile context."""
    s = hie.summary()
    s = s[s["consent_status"] != "restricted"]
    return np.sort(ml._score(ml._feature_frame(s)))


def _percentile(p: float) -> float:
    probs = _registry_probs()
    return float(np.searchsorted(probs, p, side="right") / len(probs) * 100)


def _row(patient_id: str) -> pd.Series | None:
    s = hie.summary()
    row = s[s["patient_id"] == patient_id]
    return None if row.empty else row.iloc[0].copy()


def _apply(row: pd.Series, overrides: dict) -> pd.Series:
    """Apply lever overrides and keep the dependent columns coherent."""
    r = row.copy()
    for k, v in (overrides or {}).items():
        if k not in LEVER_KEYS or v is None:
            continue
        spec = next(l for l in LEVERS if l["key"] == k)
        if spec["kind"] == "toggle":
            r[k] = 1 if bool(v) else 0
        else:
            val = min(max(float(v), spec["min"]), spec["max"])
            r[k] = int(round(val)) if float(spec["step"]).is_integer() else float(val)
    # Diastolic tracks systolic when only systolic was moved (keeps the record plausible)
    if "sbp_latest" in (overrides or {}) and "dbp_latest" not in (overrides or {}):
        r["dbp_latest"] = float(row["dbp_latest"] + 0.5 * (r["sbp_latest"] - row["sbp_latest"]))
    # Therapy flags drive the medicine count
    r["diabetes_medication_count"] = max(0, int(row["diabetes_medication_count"]) + sum(
        int(r[f]) - int(row[f]) for f in ["on_metformin", "on_sglt2_glp1", "on_insulin"]))
    r["albuminuria"] = 1 if float(r["acr_latest"]) >= 3.0 else 0
    r["ckd"] = 1 if float(r["egfr_latest"]) < 60 else int(row["ckd"])
    # Re-derive only the rule-based gaps whose inputs moved; keep the record's state for the rest
    moved = {k for k, v in (overrides or {}).items() if k in LEVER_KEYS and v is not None}
    record_gaps = [g for g in str(row["open_care_gaps"] or "").split(";") if g]
    gaps = list(record_gaps)
    for g, (rule, inputs) in DERIVED_GAPS.items():
        if not (moved & inputs):
            continue
        if rule(r) and g not in gaps:
            gaps.append(g)
        elif not rule(r) and g in gaps:
            gaps.remove(g)
    r["open_care_gaps"] = ";".join(gaps)
    r["care_gap_count"] = len(gaps)
    return r


def _contribs(row: pd.Series) -> tuple[float, dict]:
    booster, features, _ = ml._risk()
    X = ml._feature_frame(row.to_frame().T)
    X = X.astype(float)
    prob = float(booster.predict(DMatrix(X))[0])
    c = booster.predict(DMatrix(X), pred_contribs=True)[0]
    return prob, dict(zip(features + ["baseline"], [float(v) for v in c]))


def _lever_values(row: pd.Series) -> dict:
    out = {}
    for l in LEVERS:
        v = _clean(row.get(l["key"]))
        out[l["key"]] = (int(v) if l["kind"] == "toggle" else v)
    return out


def _header(row: pd.Series) -> dict:
    gaps = [g for g in str(row["open_care_gaps"] or "").split(";") if g]
    return {
        "patient_id": row["patient_id"], "name": row["full_name"], "age": int(row["age"]),
        "gender": row["gender"], "nationality": row["nationality"], "diabetes_type": row["diabetes_type"],
        "years_since_diagnosis": _clean(row["years_since_diagnosis"]),
        "facility": _facility_name(row["primary_facility_id"]), "registry_tier": row["registry_risk_tier"],
        "hba1c_12m_ago": _clean(row["hba1c_12m_ago"]), "open_care_gaps": gaps,
        "gap_labels": [hie.GAP_LABELS.get(g, g) for g in gaps],
        "annual_cost_aed": _clean(row["annual_cost_aed"]),
        "retinopathy": int(row["retinopathy"]), "neuropathy": int(row["neuropathy"]),
        "foot_ulcer_history": int(row["foot_ulcer_history"]), "htn": int(row["htn"]), "ckd": int(row["ckd"]),
    }


def baseline(patient_id: str) -> dict:
    row = _row(patient_id)
    if row is None:
        return {"error": f"patient {patient_id} not found"}
    if row["consent_status"] == "restricted":
        return {"consent": "DENIED", "patient_id": patient_id,
                "message": "Restricted consent, the record cannot be opened or scored. This attempt has been logged."}
    prob, contribs = _contribs(row)
    mono = _monotone()
    levers = [{**l, "direction": mono.get(l["key"], 0)} for l in LEVERS]
    return {
        "patient": _header(row), "levers": levers, "values": _lever_values(row),
        "presets": [{"id": k, **{kk: vv for kk, vv in v.items() if kk in ("label", "description")}} for k, v in PRESETS.items()],
        "risk": {"probability": round(prob, 4), "band": ml._band(prob), "percentile": round(_percentile(prob), 1)},
        "drivers": _top_drivers(contribs, row),
        "event_cost_aed": ml.EVENT_COST_AED, "model_version": _model_version(),
    }


def _top_drivers(contribs: dict, row: pd.Series, n: int = 8) -> list[dict]:
    pairs = sorted(((k, v) for k, v in contribs.items() if k != "baseline"), key=lambda t: -abs(t[1]))[:n]
    return [{"feature": k, "label": FEATURE_LABELS.get(k, k), "value": _clean(row.get(k)),
             "contribution": round(v, 4)} for k, v in pairs]


def preset_overrides(preset_id: str, patient_id: str) -> dict:
    row = _row(patient_id)
    spec = PRESETS.get(preset_id)
    if row is None or not spec:
        return {}
    out = dict(spec.get("set", {}))
    for k, d in spec.get("delta", {}).items():
        out[k] = round(float(row[k]) + d, 2)
    return out


def simulate(patient_id: str, overrides: dict | None) -> dict:
    row = _row(patient_id)
    if row is None:
        return {"error": f"patient {patient_id} not found"}
    if row["consent_status"] == "restricted":
        return {"consent": "DENIED", "patient_id": patient_id}
    overrides = {k: v for k, v in (overrides or {}).items() if k in LEVER_KEYS}
    sim = _apply(row, overrides)
    p0, c0 = _contribs(row)
    p1, c1 = _contribs(sim)
    dp = p1 - p0

    # Attribution: change in log-odds contribution per feature, allocated onto Δp
    deltas = {k: c1[k] - c0[k] for k in c0 if k != "baseline"}
    total = sum(deltas.values())
    attribution = []
    for k, d in sorted(deltas.items(), key=lambda t: -abs(t[1])):
        if abs(d) < 1e-4:
            continue
        share = (d / total * dp) if abs(total) > 1e-9 else 0.0
        attribution.append({"feature": k, "label": FEATURE_LABELS.get(k, k),
                            "from": _clean(row.get(k)), "to": _clean(sim.get(k)),
                            "delta_logodds": round(d, 4), "delta_probability": round(share, 4)})
    attribution = attribution[:10]

    gaps0 = set(g for g in str(row["open_care_gaps"] or "").split(";") if g)
    gaps1 = set(g for g in str(sim["open_care_gaps"] or "").split(";") if g)
    changed = {k: {"from": _clean(row.get(k)), "to": _clean(sim.get(k))}
               for k in overrides if _clean(row.get(k)) != _clean(sim.get(k))}

    return {
        "patient_id": patient_id,
        "baseline": {"probability": round(p0, 4), "band": ml._band(p0), "percentile": round(_percentile(p0), 1)},
        "simulated": {"probability": round(p1, 4), "band": ml._band(p1), "percentile": round(_percentile(p1), 1)},
        "delta": {"absolute": round(dp, 4), "relative_pct": round((dp / p0 * 100) if p0 > 0 else 0.0, 1)},
        "expected_cost_delta_aed": int(round(dp * ml.EVENT_COST_AED)),
        "event_cost_aed": ml.EVENT_COST_AED,
        "changed": changed,
        "attribution": attribution,
        "gaps": {"closed": [hie.GAP_LABELS.get(g, g) for g in sorted(gaps0 - gaps1)],
                 "opened": [hie.GAP_LABELS.get(g, g) for g in sorted(gaps1 - gaps0)],
                 "open_after": len(gaps1)},
        "values": _lever_values(sim),
        "method": ("The patient is re-scored through the deployed deterioration-risk model (XGBoost, "
                   "v2.1.0, monotonic clinical constraints). Attribution is the change in each feature's SHAP-style contribution "
                   f"(pred_contribs), allocated onto the probability change. Cost uses AED {ml.EVENT_COST_AED:,} "
                   "per deterioration episode. Association, not a causal treatment effect."),
    }


def search_patients(q: str, limit: int = 8) -> list[dict]:
    s = hie.summary()
    s = s[s["consent_status"] != "restricted"]
    q = (q or "").strip()
    if q:
        mask = s["patient_id"].str.contains(q, case=False, na=False) | s["full_name"].str.contains(q, case=False, na=False)
        s = s[mask]
    s = s.head(limit)
    return [{"patient_id": r.patient_id, "name": r.full_name, "age": int(r.age), "gender": r.gender,
             "diabetes_type": r.diabetes_type, "hba1c_latest": _clean(r.hba1c_latest),
             "registry_tier": r.registry_risk_tier} for r in s.itertuples()]


@lru_cache(maxsize=1)
def presets_patients() -> list[dict]:
    """Three entry points: the demo's hero, a very-high-risk patient, a well-controlled one."""
    from services import scenarios
    s = hie.summary()
    s = s[s["consent_status"] != "restricted"].copy()
    s["p"] = ml._score(ml._feature_frame(s))
    hero = scenarios._pick_deepdive_patient()
    hi = s[(s["p"] >= 0.45) & (s["admissions_12mo"] >= 1)].sort_values("p", ascending=False)
    hi = hi.iloc[0] if not hi.empty else s.sort_values("p", ascending=False).iloc[0]
    lo = s[(s["hba1c_latest"] < 7.0) & (s["care_gap_count"] == 0)].sort_values("p")
    lo = lo.iloc[0] if not lo.empty else s.sort_values("p").iloc[0]
    out = []
    for pid, tag in [(hero, "Flagged by the model, not by the registry tier"),
                     (hi["patient_id"], "Very high risk, recent admission"),
                     (lo["patient_id"], "Well controlled, no open gaps")]:
        r = s[s["patient_id"] == pid].iloc[0]
        out.append({"patient_id": pid, "name": r["full_name"], "tag": tag, "age": int(r["age"]),
                    "hba1c_latest": _clean(r["hba1c_latest"]), "registry_tier": r["registry_risk_tier"],
                    "probability": round(float(r["p"]), 4)})
    return out


# ── Explanation ───────────────────────────────────────────────────────────────────────
SYSTEM_INSTRUCTION = (
    "You are the explanation layer of Basira, a population-health decision-support system used by "
    "clinicians in the Emirates Health Services (EHS) diabetes registry. You receive the output of a deployed "
    "deterioration-risk model before and after a clinician changed some inputs in a what-if "
    "simulator. Explain, in plain clinical English, why the model's 12-month deterioration risk "
    "moved. Rules: use only the numbers provided; attribute the change to the levers listed; "
    "mention the largest one or two drivers with their values; note any care gaps closed; give "
    "one sentence on what this means for the patient's management; finish with one short caveat "
    "that this is a statistical association from a decision-support model, not a guaranteed "
    "treatment effect, and that decisions rest with the clinician. 90 to 130 words, two short "
    "paragraphs, no headings, no bullet lists, no emojis, no marketing tone."
)


def _fmt(k: str, v) -> str:
    if v is None:
        return "n/a"
    if k in THERAPY_FLAGS or k == "smoker":
        return "yes" if int(v) else "no"
    if k == "adherence_pdc":
        return f"{float(v):.2f}"
    if isinstance(v, float):
        return f"{v:.1f}"
    return str(v)


def _explanation_context(patient_id: str, overrides: dict, result: dict, profile: dict | None = None) -> str:
    b = baseline(patient_id)
    pt = b["patient"]
    if profile:
        subject = (f"Profile: {profile['label']} ({profile['description']}): {pt['age']}-year-old {pt['gender']}, "
                   f"{pt['diabetes_type'].replace('type', 'type ')} diabetes, {pt['years_since_diagnosis']} years since "
                   f"diagnosis. Registry rule-based tier: {pt['registry_tier']}. Do not refer to a named patient.")
    else:
        subject = (f"Patient: {pt['name']} ({patient_id}), {pt['age']}-year-old {pt['gender']}, "
                   f"{pt['diabetes_type'].replace('type', 'type ')} diabetes, {pt['years_since_diagnosis']} years since "
                   f"diagnosis, facility {pt['facility']}. Registry rule-based tier: {pt['registry_tier']}.")
    lines = [
        subject,
        f"Baseline model risk of deterioration in 12 months: {result['baseline']['probability']*100:.1f}% "
        f"(band {result['baseline']['band']}, higher than {result['baseline']['percentile']:.0f}% of the registry).",
        f"Simulated risk: {result['simulated']['probability']*100:.1f}% (band {result['simulated']['band']}, "
        f"higher than {result['simulated']['percentile']:.0f}% of the registry). "
        f"Change: {result['delta']['absolute']*100:+.1f} points ({result['delta']['relative_pct']:+.0f}% relative).",
        "Levers changed by the clinician: " + ("; ".join(
            f"{FEATURE_LABELS.get(k, k)} {_fmt(k, v['from'])} -> {_fmt(k, v['to'])}" for k, v in result["changed"].items())
            or "none"),
        "Attribution of the change (probability points, model contributions): " + ("; ".join(
            f"{a['label']} {a['delta_probability']*100:+.1f}" for a in result["attribution"][:6]) or "none"),
        "Care gaps closed: " + (", ".join(result["gaps"]["closed"]) or "none") +
        ". Care gaps opened: " + (", ".join(result["gaps"]["opened"]) or "none") + ".",
        f"Expected 12-month cost change at AED {ml.EVENT_COST_AED:,} per episode: AED {result['expected_cost_delta_aed']:+,}.",
        "Baseline top drivers: " + "; ".join(f"{d['label']} = {_fmt(d['feature'], d['value'])} ({d['contribution']:+.2f} log-odds)" for d in b["drivers"][:5]),
    ]
    return "\n".join(lines)


def deterministic_explanation(result: dict) -> str:
    """Deterministic narrative from the numbers, used when no LLM is configured."""
    b, s, d = result["baseline"], result["simulated"], result["delta"]
    if not result["changed"]:
        return (f"No lever has been changed. The model's baseline estimate is a {b['probability']*100:.1f}% "
                f"probability of deterioration in the next 12 months ({b['band']}), higher than "
                f"{b['percentile']:.0f}% of the registry. Move a lever to see how the estimate responds.")
    direction = "fell" if d["absolute"] < 0 else "rose"
    attr = [a for a in result["attribution"] if abs(a["delta_probability"]) >= 0.002][:3]
    parts = []
    for a in attr:
        chg = ""
        if a["feature"] in result["changed"]:
            c = result["changed"][a["feature"]]
            chg = f" ({_fmt(a['feature'], c['from'])} to {_fmt(a['feature'], c['to'])})"
        parts.append(f"{a['label']}{chg} accounted for {a['delta_probability']*100:+.1f} points")
    gaps = result["gaps"]["closed"]
    txt = (f"The model's 12-month deterioration risk {direction} from {b['probability']*100:.1f}% to "
           f"{s['probability']*100:.1f}% ({d['absolute']*100:+.1f} points, {d['relative_pct']:+.0f}% relative), "
           f"moving the patient from the {b['band']} to the {s['band']} band" if b["band"] != s["band"] else
           f"The model's 12-month deterioration risk {direction} from {b['probability']*100:.1f}% to "
           f"{s['probability']*100:.1f}% ({d['absolute']*100:+.1f} points, {d['relative_pct']:+.0f}% relative), "
           f"staying in the {s['band']} band")
    txt += ". " + ("; ".join(parts) + "." if parts else "The change is spread across several small contributions.")
    if gaps:
        txt += f" The change also closes {len(gaps)} care gap{'s' if len(gaps) > 1 else ''}: {', '.join(gaps)}."
    txt += (f"\n\nAt AED {result['event_cost_aed']:,} per deterioration episode this is an expected "
            f"12-month cost change of AED {result['expected_cost_delta_aed']:+,}. The estimate is a statistical "
            "association learned from the registry, not a guaranteed treatment effect; the management "
            "decision rests with the clinician.")
    return txt


async def explain(patient_id: str, overrides: dict | None, actor: str = "clinician",
                  profile_id: str | None = None) -> AsyncGenerator[dict, None]:
    """NDJSON events: {type:'meta'} then {type:'token'} ... then {type:'final'}.

    With *profile_id* the subject is an anonymous archetype: the narrative and the audit
    trail carry the profile, never the registry row behind it.
    """
    from services import agent, llm_client as LC

    profile = next((p for p in PROFILES if p["id"] == profile_id), None) if profile_id else None
    subject_id = profile_id if profile else patient_id
    result = simulate(patient_id, overrides)
    if result.get("error") or result.get("consent") == "DENIED":
        yield {"type": "final", "text": result.get("message") or result.get("error") or "Unavailable", "mode": "error"}
        return

    if not LC.llm_available():
        text = deterministic_explanation(result)
        audit_svc.log("SIM·EXPLAIN", actor, f"What-if explanation (deterministic), risk {result['baseline']['probability']*100:.1f}% → "
                      f"{result['simulated']['probability']*100:.1f}%", subject_id, "info")
        yield {"type": "meta", "mode": "deterministic", "model": None}
        for chunk in text.split(" "):
            yield {"type": "token", "text": chunk + " "}
        yield {"type": "final", "text": text, "mode": "deterministic", "model": None}
        return

    context = _explanation_context(patient_id, overrides or {}, result, profile)
    prompt = ("Explain the change in the model's estimate to the treating clinician.\n\n" + context)

    async def run(model: str):
        if model.startswith("claude"):
            # Anthropic SDK streaming helper: text deltas as they arrive, the SDK retries
            # 429/5xx and connection drops before we ever see an exception.
            client = LC.make_anthropic_client(timeout_s=agent.HTTP_TIMEOUT_MS / 1000, max_retries=2)
            async with client.messages.stream(
                model=model, max_tokens=700, temperature=0.3, system=SYSTEM_INSTRUCTION,
                messages=[{"role": "user", "content": prompt}],
            ) as stream:
                async for piece in stream.text_stream:
                    yield piece
            return
        from google.genai import types as gtypes
        client = LC.make_client(http_options=agent._http_options())
        cfg = agent.generation_config(model) or gtypes.GenerateContentConfig()
        cfg.system_instruction = SYSTEM_INSTRUCTION
        cfg.temperature = 0.3
        cfg.max_output_tokens = 600
        async for ev in await client.aio.models.generate_content_stream(model=model, contents=prompt, config=cfg):
            if ev.text:
                yield ev.text

    model = agent.active_model()
    label = agent.display_model(model)
    text, started = "", time.time()
    yield {"type": "meta", "mode": "live", "model": label}
    try:
        async for piece in run(model):
            text += piece
            yield {"type": "token", "text": piece}
    except Exception as e:  # capacity incident: one hop down the preference list, then give up gracefully
        if agent.is_capacity_error(e) and not text:
            nxt = agent.switch_model(str(e))
            if nxt:
                yield {"type": "meta", "mode": "live", "model": label, "switched": True}
                model = nxt
                try:
                    async for piece in run(model):
                        text += piece
                        yield {"type": "token", "text": piece}
                except Exception as e2:
                    text = text or deterministic_explanation(result)
                    yield {"type": "final", "text": text, "mode": "fallback", "model": label, "error": type(e2).__name__}
                    return
        else:
            text = text or deterministic_explanation(result)
            yield {"type": "final", "text": text, "mode": "fallback", "model": label, "error": type(e).__name__}
            return
    audit_svc.log("SIM·EXPLAIN", actor,
                  f"What-if explanation by {model} in {time.time()-started:.1f}s, risk "
                  f"{result['baseline']['probability']*100:.1f}% → {result['simulated']['probability']*100:.1f}%; "
                  f"levers: {', '.join(FEATURE_LABELS.get(k, k) for k in result['changed']) or 'none'}",
                  subject_id, "info")
    yield {"type": "final", "text": text, "mode": "live", "model": label}


def tool_simulate(patient_id: str, overrides_json: str = "") -> dict:
    """Agent-facing wrapper: overrides as a JSON object of lever -> value."""
    try:
        overrides = json.loads(overrides_json) if overrides_json else {}
    except json.JSONDecodeError as e:
        return {"error": f"overrides_json is not valid JSON: {e}", "levers": sorted(LEVER_KEYS)}
    res = simulate(patient_id, overrides)
    if res.get("error"):
        return res
    res.pop("values", None)
    return res
