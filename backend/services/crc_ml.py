"""
Example 2, the predictive layer: screening non-completion risk.

One model, trained in scripts/train_models.py on the programme's own invitations: given what
is known about a person BEFORE anyone contacts them, how likely is it that an invitation
will not lead to a completed test within 90 days? The programme uses it for one thing only,
to decide how much outreach effort each due person gets (a policy rule, NHA-CS-01 §8). It
never changes who is eligible or which test they get: that is the rules' job (crc.py).

This module serves the model: feature building (shared with training), scoring with
per-feature attribution (XGBoost pred_contribs), the anonymous profiles and levers of the
what-if page, the live re-score, and the narrated explanation (a language model when one is
configured, a deterministic narrative otherwise).
"""
from __future__ import annotations

import copy
import json
from functools import lru_cache
from pathlib import Path
from typing import AsyncGenerator

import numpy as np
import pandas as pd
from xgboost import Booster, DMatrix

MODELS = Path(__file__).resolve().parent.parent / "models"
MODEL_ID = "screening_uptake"
MODEL_VERSION = "1.0.0"

FEATURES = ["age", "is_male", "bmi", "distance_km", "hospital_distance_km", "missed_appointments_12m",
            "gp_visits_12m", "language_barrier", "uninsured", "shift_work", "smoker_current", "diabetes",
            "never_screened", "family_history_any", "apcs_points"]
# Clinical and operational priors as monotonic constraints: the estimate of NOT completing
# cannot fall as distance or missed appointments rise, nor rise as GP contact grows.
MONOTONE = {"distance_km": 1, "missed_appointments_12m": 1, "gp_visits_12m": -1, "language_barrier": 1,
            "uninsured": 1, "shift_work": 1, "smoker_current": 1, "never_screened": 1, "family_history_any": -1,
            "is_male": 1}
LABELS = {
    "age": "Age", "is_male": "Male", "bmi": "BMI", "distance_km": "Distance to nearest facility",
    "hospital_distance_km": "Distance to nearest hospital", "missed_appointments_12m": "Missed appointments (12 m)",
    "gp_visits_12m": "GP visits (12 m)", "language_barrier": "Language other than Arabic or English",
    "uninsured": "Uninsured", "shift_work": "Shift worker", "smoker_current": "Current smoker",
    "diabetes": "Diabetes", "never_screened": "Never screened before", "family_history_any": "Family history of bowel cancer",
    "apcs_points": "APCS points",
}
BANDS = [("Low", 0.0), ("Moderate", 0.30), ("High", 0.50), ("Very high", 0.70)]


def band(p: float) -> str:
    out = "Low"
    for name, lo in BANDS:
        if p >= lo:
            out = name
    return out


def features(df: pd.DataFrame) -> pd.DataFrame:
    """The model's feature frame from population rows (also used by the training script)."""
    out = pd.DataFrame(index=df.index)
    out["age"] = df["age"].astype(float)
    out["is_male"] = (df["sex"] == "male").astype(int)
    out["bmi"] = df["bmi"].astype(float)
    out["distance_km"] = df["distance_km"].astype(float)
    out["hospital_distance_km"] = df["hospital_distance_km"].astype(float)
    out["missed_appointments_12m"] = df["missed_appointments_12m"].astype(float)
    out["gp_visits_12m"] = df["gp_visits_12m"].astype(float)
    out["language_barrier"] = (~df["language"].isin(["ar", "en"])).astype(int)
    out["uninsured"] = (df["insurance"] == "Uninsured").astype(int)
    out["shift_work"] = (df["employment"] == "shift").astype(int)
    out["smoker_current"] = (df["smoking"] == "current").astype(int)
    out["diabetes"] = df["diabetes"].astype(int)
    out["never_screened"] = (df["last_screen"] == "never").astype(int)
    out["family_history_any"] = (df["family_history"] != "none").astype(int)
    out["apcs_points"] = df["apcs_points"].astype(float)
    return out[FEATURES]


@lru_cache(maxsize=1)
def _booster() -> Booster:
    b = Booster()
    b.load_model(str(MODELS / f"{MODEL_ID}.xgb.json"))
    b.set_param({"nthread": 1})
    return b


def available() -> bool:
    return (MODELS / f"{MODEL_ID}.xgb.json").exists()


@lru_cache(maxsize=1)
def spec() -> dict:
    return json.loads((MODELS / f"{MODEL_ID}.features.json").read_text())


@lru_cache(maxsize=1)
def card() -> dict:
    cards = json.loads((MODELS / "model_cards.json").read_text())
    return next((c for c in cards if c["model_id"] == MODEL_ID), {})


def score_frame(X: pd.DataFrame) -> np.ndarray:
    return _booster().predict(DMatrix(X[FEATURES].astype(float)))


def score_rows(df: pd.DataFrame) -> np.ndarray:
    """P(invitation not completed within 90 days) for population rows."""
    if df.empty:
        return np.array([])
    return score_frame(features(df))


def contribs(row: pd.Series) -> tuple[float, dict]:
    X = features(row.to_frame().T).astype(float)
    p = float(_booster().predict(DMatrix(X))[0])
    c = _booster().predict(DMatrix(X), pred_contribs=True)[0]
    return p, dict(zip(FEATURES + ["baseline"], [float(v) for v in c]))


def top_drivers(c: dict, X: pd.Series, n: int = 8) -> list[dict]:
    pairs = sorted(((k, v) for k, v in c.items() if k != "baseline"), key=lambda t: -abs(t[1]))[:n]
    return [{"feature": k, "label": LABELS.get(k, k), "value": _clean(X.get(k)), "contribution": round(v, 4)} for k, v in pairs]


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    return v.item() if hasattr(v, "item") else v


# ── Outreach policy (NHA-CS-01 §8): what the predicted band changes, and only that ──
OUTREACH = {
    "Low":       {"channel": "app", "plan": "App notification with the FIT kit collection point; reminder at 14 days if no booking.", "navigator": False, "effort": 1},
    "Moderate":  {"channel": "sms", "plan": "SMS in the person's language, reminder at 14 and 28 days, link to book.", "navigator": False, "effort": 2},
    "High":      {"channel": "call", "plan": "Phone call from a patient navigator within 5 working days, booking offered on the call.", "navigator": True, "effort": 3},
    "Very high": {"channel": "call", "plan": "Navigator call plus booking made on the call, kit posted or handed over at the nearest centre, transport note on the record.", "navigator": True, "effort": 4},
}


def outreach_for(p: float) -> dict:
    b = band(p)
    return {"band": b, **OUTREACH[b], "rule": "NHA-CS-01 §8.3"}


# ── What-if: anonymous profiles and levers ──────────────────────────────────────────
LEVERS: list[dict] = [
    {"key": "distance_km", "label": "Distance to nearest facility", "unit": "km", "kind": "range", "min": 0.5, "max": 45, "step": 0.5,
     "group": "Access", "hint": "Door to door; the East Coast and the far north sit at 10 km and more"},
    {"key": "hospital_distance_km", "label": "Distance to nearest hospital", "unit": "km", "kind": "range", "min": 0.5, "max": 60, "step": 0.5,
     "group": "Access", "hint": "Where a colonoscopy would be done"},
    {"key": "uninsured", "label": "Uninsured", "kind": "toggle", "group": "Access"},
    {"key": "language_barrier", "label": "Language other than Arabic or English", "kind": "toggle", "group": "Access",
     "hint": "Invitations exist in six languages; the call centre in two"},
    {"key": "missed_appointments_12m", "label": "Missed appointments, last 12 months", "unit": "", "kind": "range", "min": 0, "max": 6, "step": 1,
     "group": "Engagement"},
    {"key": "gp_visits_12m", "label": "GP visits, last 12 months", "unit": "", "kind": "range", "min": 0, "max": 12, "step": 1,
     "group": "Engagement", "hint": "A relationship with a GP is the strongest protective factor"},
    {"key": "never_screened", "label": "Never screened before", "kind": "toggle", "group": "Engagement"},
    {"key": "shift_work", "label": "Shift worker", "kind": "toggle", "group": "Engagement"},
    {"key": "smoker_current", "label": "Current smoker", "kind": "toggle", "group": "Profile"},
    {"key": "diabetes", "label": "Diabetes", "kind": "toggle", "group": "Profile"},
    {"key": "family_history_any", "label": "Family history of bowel cancer", "kind": "toggle", "group": "Profile"},
    {"key": "age", "label": "Age", "unit": "y", "kind": "range", "min": 36, "max": 85, "step": 1, "group": "Profile"},
    {"key": "is_male", "label": "Male", "kind": "toggle", "group": "Profile"},
    {"key": "bmi", "label": "BMI", "unit": "kg/m²", "kind": "range", "min": 17.5, "max": 48, "step": 0.1, "group": "Profile"},
]
LEVER_KEYS = {l["key"] for l in LEVERS}

PROFILES: list[dict] = [
    {"id": "engaged_nearby", "label": "Engaged and nearby",
     "description": "Sees a GP, lives within 3 km of a health centre, screened before",
     "rule": lambda d: (d["gp_visits_12m"] >= 2) & (d["distance_km"] <= 3) & (d["last_screen"] != "never")},
    {"id": "far_from_care", "label": "Far from a facility",
     "description": "More than 12 km from the nearest centre, never screened",
     "rule": lambda d: (d["distance_km"] >= 12) & (d["last_screen"] == "never")},
    {"id": "shift_worker", "label": "Shift worker, never screened",
     "description": "Works shifts, speaks neither Arabic nor English at home, never screened",
     "rule": lambda d: (d["employment"] == "shift") & (~d["language"].isin(["ar", "en"])) & (d["last_screen"] == "never")},
    {"id": "diabetes_misses", "label": "Diabetes, misses appointments",
     "description": "Living with diabetes, two or more missed appointments this year",
     "rule": lambda d: (d["diabetes"] == 1) & (d["missed_appointments_12m"] >= 2)},
    {"id": "family_history", "label": "Family history, due early",
     "description": "A parent or sibling had bowel cancer; on the colonoscopy pathway",
     "rule": lambda d: (d["family_history"].isin(["one_under60", "two_plus"])) & (d["age"] < 50)},
]
PRESETS = {
    "navigator": {"label": "Navigator support", "description": "A GP visit this month, one missed appointment forgiven, kit handed over at the centre (distance to 1 km).",
                  "set": {"gp_visits_12m": 3, "missed_appointments_12m": 0, "distance_km": 1.0}},
    "mobile_unit": {"label": "Mobile FIT unit", "description": "A mobile unit at the workplace: distance 0.5 km, no appointment to miss.",
                    "set": {"distance_km": 0.5, "missed_appointments_12m": 0}},
    "disengage": {"label": "Left alone", "description": "No GP contact, two more missed appointments: the trajectory if nothing is done.",
                  "set": {"gp_visits_12m": 0}, "delta": {"missed_appointments_12m": 2}},
}
_CENTRE_FEATURES = ["age", "bmi", "distance_km", "missed_appointments_12m", "gp_visits_12m", "apcs_points", "p"]


def _population() -> pd.DataFrame:
    from services import screening
    return screening.population()


@lru_cache(maxsize=1)
def _profile_rows() -> dict:
    d = _population()
    d = d[(d["consent_status"] != "restricted") & d["due_status"].isin(["due", "overdue", "surveillance", "not_yet"])].copy()
    d["p"] = score_rows(d)
    out = {}
    for prof in PROFILES:
        g = d[prof["rule"](d)]
        if g.empty:
            g = d
        z = g[_CENTRE_FEATURES].astype(float)
        z = (z - z.median()) / z.std(ddof=0).replace(0, 1.0)
        out[prof["id"]] = str(g.loc[(z ** 2).sum(axis=1).idxmin(), "person_id"])
    return out


def _row(person_id: str) -> pd.Series | None:
    d = _population()
    r = d[d["person_id"] == person_id]
    return None if r.empty else r.iloc[0].copy()


def _lever_values(X: pd.Series) -> dict:
    return {l["key"]: (int(X[l["key"]]) if l["kind"] == "toggle" else _clean(X[l["key"]])) for l in LEVERS}


def _header(row: pd.Series, prof: dict) -> dict:
    return {"id": prof["id"], "label": prof["label"], "description": prof["description"],
            "age": int(row["age"]), "sex": row["sex"], "emirate": row["emirate"], "apcs_tier": row["apcs_tier"],
            "pathway_id": row["pathway_id"], "pathway_test": row["pathway_test"], "due_status": row["due_status"],
            "last_screen": row["last_screen"], "nearest_facility": row["nearest_facility_name"]}


def profiles() -> list[dict]:
    return copy.deepcopy(_profiles_cached())


@lru_cache(maxsize=1)
def _profiles_cached() -> list[dict]:
    out = []
    for prof in PROFILES:
        row = _row(_profile_rows()[prof["id"]])
        p, _ = contribs(row)
        out.append({"id": prof["id"], "label": prof["label"], "description": prof["description"],
                    "probability": round(p, 4), "band": band(p), "age": int(row["age"]), "due_status": row["due_status"]})
    return out


def profile_baseline(profile_id: str) -> dict:
    prof = next((p for p in PROFILES if p["id"] == profile_id), None)
    if not prof:
        return {"error": f"unknown profile {profile_id}"}
    row = _row(_profile_rows()[profile_id])
    p, c = contribs(row)
    X = features(row.to_frame().T).iloc[0]
    mono = spec().get("monotone", {})
    return {"profile": _header(row, prof),
            "levers": [{**l, "direction": mono.get(l["key"], 0)} for l in LEVERS],
            "values": _lever_values(X),
            "presets": [{"id": k, "label": v["label"], "description": v["description"]} for k, v in PRESETS.items()],
            "risk": {"probability": round(p, 4), "band": band(p), "percentile": round(_percentile(p), 1)},
            "outreach": outreach_for(p), "drivers": top_drivers(c, X),
            "model_version": spec().get("version", MODEL_VERSION)}


@lru_cache(maxsize=1)
def _due_probs() -> np.ndarray:
    d = _population()
    d = d[(d["consent_status"] != "restricted") & d["due_status"].isin(["due", "overdue"])]
    return np.sort(score_rows(d))


def _percentile(p: float) -> float:
    probs = _due_probs()
    return float(np.searchsorted(probs, p, side="right") / max(len(probs), 1) * 100)


def preset_overrides(profile_id: str, preset_id: str) -> dict:
    spec_ = PRESETS.get(preset_id)
    if not spec_ or profile_id not in _profile_rows():
        return {}
    X = features(_row(_profile_rows()[profile_id]).to_frame().T).iloc[0]
    out = dict(spec_.get("set", {}))
    for k, dlt in spec_.get("delta", {}).items():
        out[k] = float(np.clip(float(X[k]) + dlt, 0, 99))
    return out


def _apply(X: pd.Series, overrides: dict) -> pd.Series:
    Y = X.copy().astype(float)
    for k, v in (overrides or {}).items():
        if k not in LEVER_KEYS or v is None:
            continue
        l = next(l for l in LEVERS if l["key"] == k)
        if l["kind"] == "toggle":
            Y[k] = 1.0 if bool(v) else 0.0
        else:
            Y[k] = float(min(max(float(v), l["min"]), l["max"]))
    # the nearest hospital can never be nearer than the nearest facility
    Y["hospital_distance_km"] = max(Y["hospital_distance_km"], Y["distance_km"])
    return Y


def simulate(profile_id: str, overrides: dict | None) -> dict:
    if profile_id not in _profile_rows():
        return {"error": f"unknown profile {profile_id}"}
    row = _row(_profile_rows()[profile_id])
    X0 = features(row.to_frame().T).iloc[0].astype(float)
    X1 = _apply(X0, overrides)
    b = _booster()
    p0 = float(b.predict(DMatrix(X0.to_frame().T[FEATURES]))[0]); c0 = b.predict(DMatrix(X0.to_frame().T[FEATURES]), pred_contribs=True)[0]
    p1 = float(b.predict(DMatrix(X1.to_frame().T[FEATURES]))[0]); c1 = b.predict(DMatrix(X1.to_frame().T[FEATURES]), pred_contribs=True)[0]
    dp = p1 - p0
    deltas = {k: float(c1[i] - c0[i]) for i, k in enumerate(FEATURES)}
    total = sum(deltas.values())
    attribution = []
    for k, d in sorted(deltas.items(), key=lambda t: -abs(t[1])):
        if abs(d) < 1e-4:
            continue
        share = (d / total * dp) if abs(total) > 1e-9 else 0.0
        attribution.append({"feature": k, "label": LABELS.get(k, k), "from": _clean(X0[k]), "to": _clean(X1[k]),
                            "delta_logodds": round(d, 4), "delta_probability": round(share, 4)})
    changed = {k: {"from": _clean(X0[k]), "to": _clean(X1[k])} for k in (overrides or {}) if k in LEVER_KEYS and _clean(X0[k]) != _clean(X1[k])}
    return {
        "profile_id": profile_id,
        "baseline": {"probability": round(p0, 4), "band": band(p0), "percentile": round(_percentile(p0), 1)},
        "simulated": {"probability": round(p1, 4), "band": band(p1), "percentile": round(_percentile(p1), 1)},
        "delta": {"absolute": round(dp, 4), "relative_pct": round((dp / p0 * 100) if p0 > 0 else 0.0, 1)},
        "outreach_before": outreach_for(p0), "outreach_after": outreach_for(p1),
        "changed": changed, "attribution": attribution[:10], "values": _lever_values(X1),
        "method": ("The profile is re-scored through the deployed non-completion model (XGBoost, monotonic constraints). "
                   "Attribution is the change in each feature's SHAP-style contribution (pred_contribs) allocated onto the "
                   "probability change. The band feeds one policy rule, outreach intensity (NHA-CS-01 §8.3); eligibility and the "
                   "test never depend on the model."),
    }


# ── Explanation: the language model narrates the numbers, it never produces them ──
SYSTEM = (
    "You are the explanation layer of a colorectal-cancer screening programme's decision support. You receive the "
    "output of a deployed model that estimates the probability that an invitation will NOT lead to a completed "
    "screening test within 90 days, before and after a programme lead changed some inputs in a what-if simulator. "
    "Explain in plain English why the estimate moved. Rules: use only the numbers provided; attribute the change to "
    "the levers listed; name the one or two largest drivers with their values; say what the outreach rule now "
    "prescribes (it is given to you); one sentence on what it means for the programme; end with one short caveat "
    "that this is a statistical association from a decision-support model and that the model changes outreach "
    "effort only, never eligibility or the test. 80 to 120 words, two short paragraphs, no headings, no lists."
)


def _fmt(k, v):
    if v is None:
        return "n/a"
    if k in ("is_male", "uninsured", "language_barrier", "shift_work", "smoker_current", "diabetes", "never_screened", "family_history_any"):
        return "yes" if int(v) else "no"
    return f"{float(v):.1f}" if isinstance(v, float) and not float(v).is_integer() else str(int(v)) if isinstance(v, (int, float)) else str(v)


def deterministic_explanation(result: dict) -> str:
    b, s, d = result["baseline"], result["simulated"], result["delta"]
    if not result["changed"]:
        return (f"No lever has been changed. The model estimates a {b['probability']*100:.0f}% chance that an invitation to this "
                f"profile is not acted on within 90 days ({b['band']} band), higher than {b['percentile']:.0f}% of the people currently due. "
                f"The outreach rule therefore prescribes: {result['outreach_before']['plan']} Move a lever to see how the estimate responds.")
    direction = "fell" if d["absolute"] < 0 else "rose"
    attr = [a for a in result["attribution"] if abs(a["delta_probability"]) >= 0.005][:3]
    parts = [f"{a['label'].lower()} ({_fmt(a['feature'], a['from'])} to {_fmt(a['feature'], a['to'])}, {a['delta_probability']*100:+.0f} points)"
             if a["from"] != a["to"] else f"{a['label'].lower()} ({a['delta_probability']*100:+.0f} points, through interactions)" for a in attr]
    txt = (f"The estimated chance of not completing {direction} from {b['probability']*100:.0f}% to {s['probability']*100:.0f}% "
           f"({d['absolute']*100:+.0f} points, {d['relative_pct']:+.0f}% relative), moving the profile from the {b['band']} to the "
           f"{s['band']} band" if b["band"] != s["band"] else
           f"The estimated chance of not completing {direction} from {b['probability']*100:.0f}% to {s['probability']*100:.0f}% "
           f"({d['absolute']*100:+.0f} points, {d['relative_pct']:+.0f}% relative), staying in the {s['band']} band")
    txt += ". The change comes mainly from " + (", ".join(parts) if parts else "small movements across several inputs") + "."
    oa = result["outreach_after"]
    txt += (f"\n\nUnder the outreach rule (NHA-CS-01 §8.3) the programme would now {oa['plan'][0].lower() + oa['plan'][1:]} "
            f"The model changes only how hard the programme reaches out; who is eligible and which test they get are set by the pathway rules, "
            f"and the estimate is a statistical association, not a prediction about one person.")
    return txt


async def explain(profile_id: str, overrides: dict | None, actor: str = "programme lead") -> AsyncGenerator[dict, None]:
    from services import llm_client as LC
    from services import audit as audit_svc
    result = simulate(profile_id, overrides or {})
    if result.get("error"):
        yield {"type": "final", "text": result["error"], "mode": "error"}
        return
    audit_svc.log("SCREENING·WHATIF", actor, f"Uptake what-if on profile {profile_id}: "
                  f"{result['baseline']['probability']*100:.0f}% → {result['simulated']['probability']*100:.0f}%", "", "info")
    if not LC.llm_available():
        text = deterministic_explanation(result)
        yield {"type": "meta", "mode": "deterministic", "model": None}
        for w in text.split(" "):
            yield {"type": "token", "text": w + " "}
        yield {"type": "final", "text": text, "mode": "deterministic", "model": None}
        return
    from services import agent
    ctx = "\n".join([
        f"Profile: {profile_baseline(profile_id)['profile']['label']}.",
        f"Baseline: {result['baseline']['probability']*100:.1f}% chance of not completing within 90 days ({result['baseline']['band']} band, "
        f"higher than {result['baseline']['percentile']:.0f}% of people currently due).",
        f"Simulated: {result['simulated']['probability']*100:.1f}% ({result['simulated']['band']} band). Change {result['delta']['absolute']*100:+.1f} points.",
        "Levers changed: " + ("; ".join(f"{LABELS.get(k, k)} {_fmt(k, v['from'])} -> {_fmt(k, v['to'])}" for k, v in result["changed"].items()) or "none"),
        "Attribution (probability points): " + ("; ".join(f"{a['label']} {a['delta_probability']*100:+.1f}" for a in result["attribution"][:6]) or "none"),
        f"Outreach rule before: {result['outreach_before']['plan']} Outreach rule after: {result['outreach_after']['plan']}",
    ])
    system = SYSTEM + "\n\nCONTEXT\n" + ctx
    model = agent.active_model(); label = agent.display_model(model); text = ""
    yield {"type": "meta", "mode": "live", "model": label}
    try:
        if model.startswith("claude"):
            client = LC.make_anthropic_client(timeout_s=agent.HTTP_TIMEOUT_MS / 1000, max_retries=2)
            async with client.messages.stream(model=model, max_tokens=400, temperature=0.3, system=system,
                                              messages=[{"role": "user", "content": "Explain the change."}]) as stream:
                async for piece in stream.text_stream:
                    text += piece
                    yield {"type": "token", "text": piece}
        else:
            from google.genai import types as gtypes
            client = LC.make_client(http_options=agent._http_options())
            cfg = agent.generation_config(model) or gtypes.GenerateContentConfig()
            cfg.system_instruction = system; cfg.temperature = 0.3; cfg.max_output_tokens = 400
            async for ev in await client.aio.models.generate_content_stream(model=model, contents="Explain the change.", config=cfg):
                if ev.text:
                    text += ev.text
                    yield {"type": "token", "text": ev.text}
    except Exception as e:  # the deterministic narrative still answers
        if not text:
            text = deterministic_explanation(result)
            for w in text.split(" "):
                yield {"type": "token", "text": w + " "}
            yield {"type": "final", "text": text, "mode": "deterministic", "model": None, "error": str(e)[:120]}
            return
    yield {"type": "final", "text": text, "mode": "live", "model": label}
