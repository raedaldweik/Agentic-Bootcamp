"""
Cancer screening, the screening programme's data layer.

Loads the synthetic programme tables once (scripts/generate_screening_data.py) and serves the
population-level views: the programme dashboard with its cross-filter, the facility map, the
navigator worklists the agent works from, one person's full picture, and the raw tables for
the Data page. The same numbers feed the dashboard, the agent and the what-if page.
"""
from __future__ import annotations

import copy
import json
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from services import crc

DATA = Path(__file__).resolve().parent.parent / "data" / "screening"
TODAY = date(2026, 9, 1)
TABLE_NAMES = ["facilities", "population", "invitations", "fit_tests", "colonoscopies"]
ELIGIBLE_STATUSES = ["due", "overdue", "up_to_date"]           # the programme's denominator (40–75, average risk)
FILTER_LABELS = {"tier": "APCS tier", "facility": "Facility", "emirate": "Emirate", "status": "Status",
                 "nationality": "Nationality", "band": "Uptake risk"}
STATUS_LABELS = {"due": "Due now", "overdue": "Overdue", "up_to_date": "Up to date", "surveillance": "Surveillance",
                 "urgent": "Symptoms: urgent", "not_yet": "Not yet 40", "shared_decision": "76 to 85: shared decision",
                 "not_eligible": "Over 85"}
TIER_LABELS = {"average": "Average", "moderate": "Moderate", "high": "Higher"}


@lru_cache(maxsize=1)
def tables() -> dict[str, pd.DataFrame]:
    t = {n: pd.read_csv(DATA / f"{n}.csv.gz") for n in TABLE_NAMES}
    return t


def population() -> pd.DataFrame:
    return tables()["population"]


@lru_cache(maxsize=1)
def data_dictionary() -> dict:
    return json.loads((DATA / "data_dictionary.json").read_text())


# ── Model scores for the whole population, once ──────────────────────────────────────
@lru_cache(maxsize=1)
def scored() -> pd.DataFrame:
    from services import crc_ml
    d = population().copy()
    d["uptake_risk"] = np.nan
    ok = d["consent_status"] != "restricted"
    if crc_ml.available():
        d.loc[ok, "uptake_risk"] = crc_ml.score_rows(d[ok])
        d["uptake_band"] = d["uptake_risk"].apply(lambda p: crc_ml.band(float(p)) if pd.notna(p) else None)
    else:
        d["uptake_band"] = None
    return d


# ── Cross-filter ──────────────────────────────────────────────────────────────────────
def filtered(f: dict | None) -> pd.DataFrame:
    d = scored()
    f = f or {}
    if f.get("tier"):
        key = {v: k for k, v in TIER_LABELS.items()}.get(f["tier"], f["tier"])
        d = d[d["apcs_tier"] == key]
    if f.get("facility"):
        d = d[d["nearest_facility_name"] == f["facility"]]
    if f.get("emirate"):
        d = d[d["emirate"] == f["emirate"]]
    if f.get("status"):
        key = {v: k for k, v in STATUS_LABELS.items()}.get(f["status"], f["status"])
        d = d[d["due_status"] == key]
    if f.get("nationality"):
        d = d[d["nationality_group"] == f["nationality"]]
    if f.get("band"):
        d = d[d["uptake_band"] == f["band"]]
    return d


def describe_filters(f: dict | None) -> list[dict]:
    return [{"key": k, "label": FILTER_LABELS[k], "value": v} for k, v in (f or {}).items() if k in FILTER_LABELS and v]


def _pct(n, d):
    return round(float(n) / float(d) * 100, 1) if d else 0.0


# ── The programme dashboard ───────────────────────────────────────────────────────────
def _dashboard(filters_json: str) -> dict:
    f = json.loads(filters_json) if filters_json else {}
    d = filtered(f)
    ids = set(d["person_id"])
    t = tables()
    inv = t["invitations"][t["invitations"]["person_id"].isin(ids)]
    fit = t["fit_tests"][t["fit_tests"]["person_id"].isin(ids)]
    col = t["colonoscopies"][t["colonoscopies"]["person_id"].isin(ids)]
    y12 = (TODAY - timedelta(days=365)).isoformat()
    elig = d[d["due_status"].isin(ELIGIBLE_STATUSES)]
    due = d[d["due_status"].isin(["due", "overdue"])]
    inv12 = inv[inv["sent_date"] >= y12]
    fit12 = fit[fit["test_date"] >= y12]
    fitpos = col[col["indication"] == "fit_positive"]
    info = {"active": f, "chips": describe_filters(f), "patients": int(len(d)), "total": int(len(scored()))}

    # 36-month trend: invitations sent and completed within 90 days, by month sent
    inv = inv.assign(month=inv["sent_date"].str.slice(0, 7))
    trend = (inv.groupby("month").agg(invited=("invite_id", "size"), completed=("completed_90d", "sum")).reset_index()
             .sort_values("month"))
    trend_rows = [{"month": r.month, "Invited": int(r.invited), "Completed within 90 days": int(r.completed)} for r in trend.itertuples()]
    # FIT positivity by month
    fit = fit.assign(month=fit["test_date"].str.slice(0, 7))
    pos = fit.groupby("month").agg(tests=("test_id", "size"), positive=("result", lambda s: int((s == "positive").sum()))).reset_index().sort_values("month")
    pos_rows = [{"month": r.month, "FIT positivity %": round(r.positive / r.tests * 100, 1) if r.tests else 0.0} for r in pos.itertuples()]

    # facility benchmark: % of the eligible up to date, by nearest facility
    fb = (elig.groupby("nearest_facility_name").agg(people=("person_id", "size"),
                                                   up_to_date=("due_status", lambda s: int((s == "up_to_date").sum())))
          .reset_index())
    fb["pct_up_to_date"] = (fb["up_to_date"] / fb["people"] * 100).round(1)
    fb = fb.sort_values("pct_up_to_date", ascending=False)
    bench = [{"facility": r.nearest_facility_name, "people": int(r.people), "pct_up_to_date": float(r.pct_up_to_date)} for r in fb.itertuples()]

    tiers = [{"tier": TIER_LABELS[k], "people": int((d["apcs_tier"] == k).sum())} for k in ["average", "moderate", "high"]]
    statuses = [{"status": STATUS_LABELS[k], "people": int((d["due_status"] == k).sum())}
                for k in ["due", "overdue", "up_to_date", "surveillance", "urgent", "not_yet", "shared_decision", "not_eligible"]
                if int((d["due_status"] == k).sum())]
    bands = [{"band": b, "people": int((due["uptake_band"] == b).sum())} for b in ["Low", "Moderate", "High", "Very high"]]
    # equity: 90-day completion of the latest invitation by nationality group and by language
    eq = d[d["completed_90d"].notna()]
    equity = (eq.groupby("nationality_group")["completed_90d"].agg(["mean", "size"]).reset_index()
              .sort_values("mean", ascending=False))
    equity_rows = [{"group": r.nationality_group, "completion_pct": round(r["mean"] * 100, 1), "people": int(r["size"])} for _, r in equity.iterrows()]
    lang = eq.groupby("language")["completed_90d"].agg(["mean", "size"]).reset_index().sort_values("mean", ascending=False)
    lang_rows = [{"language": r.language, "completion_pct": round(r["mean"] * 100, 1), "people": int(r["size"])} for _, r in lang.iterrows()]
    # the funnel over 36 months
    completed = inv[inv["completed_90d"] == 1]
    funnel = [
        {"stage": "Invitations sent", "n": int(len(inv))},
        {"stage": "Completed within 90 days", "n": int(len(completed))},
        {"stage": "FIT tests returned", "n": int(len(fit))},
        {"stage": "FIT positive", "n": int((fit["result"] == "positive").sum())},
        {"stage": "Colonoscopy after positive FIT", "n": int(len(fitpos))},
        {"stage": "Colonoscopies, all indications", "n": int(len(col))},
        {"stage": "Advanced adenoma or cancer found", "n": int(col["finding"].isin(["advanced_adenoma", "cancer"]).sum())},
        {"stage": "Cancers found", "n": int((col["finding"] == "cancer").sum())},
    ]
    waits = col[col["indication"] == "fit_positive"]["wait_days"]
    return {
        "filter": info,
        "kpis": [
            {"label": "Eligible, 40 to 75" + (" (in the filter)" if f else ""), "value": f"{len(elig):,}"},
            {"label": "Up to date", "value": _pct((elig["due_status"] == "up_to_date").sum(), len(elig)), "suffix": "%"},
            {"label": "Due or overdue", "value": f"{len(due):,}", "accent": "red"},
            {"label": "Invited, last 12 months", "value": f"{len(inv12):,}"},
            {"label": "Completed within 90 days", "value": _pct(inv12["completed_90d"].sum(), len(inv12)), "suffix": "%"},
            {"label": "FIT positivity, 12 months", "value": _pct((fit12["result"] == "positive").sum(), len(fit12)), "suffix": "%"},
        ],
        "trend": trend_rows, "fit_positivity_trend": pos_rows,
        "facility_benchmark": bench, "tiers": tiers, "statuses": statuses, "uptake_bands": bands,
        "equity": equity_rows, "equity_language": lang_rows, "funnel": funnel,
        "colonoscopy_wait": {"median_days": float(np.median(waits)) if len(waits) else None,
                             "within_8_weeks_pct": _pct((waits <= 56).sum(), len(waits))},
        "fit_positive_no_colonoscopy": int(d["fit_positive_no_colonoscopy"].sum()),
        "urgent_symptoms": int((d["due_status"] == "urgent").sum()),
        "expected_completions_if_invited": round(float((1 - due["uptake_risk"].fillna(0.5)).sum()), 0),
    }


_dashboard_cached = lru_cache(maxsize=64)(_dashboard)


def dashboard(filters_json: str = "") -> dict:
    return copy.deepcopy(_dashboard_cached(filters_json or ""))


# ── Map ───────────────────────────────────────────────────────────────────────────────
METRICS = {
    "pct_up_to_date": {"label": "% of eligible up to date", "worse_is_high": False},
    "overdue": {"label": "People due or overdue", "worse_is_high": True},
    "completion_pct": {"label": "90-day completion of invitations", "worse_is_high": False},
    "mean_uptake_risk_pct": {"label": "Mean predicted non-completion (model)", "worse_is_high": True},
    "fit_positivity_pct": {"label": "FIT positivity", "worse_is_high": True},
    "median_wait_days": {"label": "Median wait, positive FIT to colonoscopy (days)", "worse_is_high": True},
}


@lru_cache(maxsize=1)
def _map() -> dict:
    d = scored(); t = tables()
    fac = t["facilities"]; inv = t["invitations"]; fit = t["fit_tests"]; col = t["colonoscopies"]
    out = []
    for f in fac.itertuples():
        g = d[d["nearest_facility_id"] == f.facility_id]
        elig = g[g["due_status"].isin(ELIGIBLE_STATUSES)]
        due = g[g["due_status"].isin(["due", "overdue"])]
        gi = inv[inv["facility_id"] == f.facility_id]
        gf = fit[fit["facility_id"] == f.facility_id]
        gc = col[(col["facility_id"] == f.facility_id) & (col["indication"] == "fit_positive")]
        out.append({
            "facility_id": f.facility_id, "name": f.facility_name, "type": f.facility_type, "region": f.region,
            "lat": float(f.lat), "lon": float(f.lon), "endoscopy_unit": int(f.endoscopy_unit),
            "slots_per_week": int(f.colonoscopy_slots_per_week), "patients": int(len(g)), "eligible": int(len(elig)),
            "pct_up_to_date": _pct((elig["due_status"] == "up_to_date").sum(), len(elig)),
            "overdue": int(len(due)),
            "completion_pct": _pct(gi["completed_90d"].sum(), len(gi)),
            "mean_uptake_risk_pct": round(float(due["uptake_risk"].mean()) * 100, 1) if len(due) and due["uptake_risk"].notna().any() else 0.0,
            "fit_positivity_pct": _pct((gf["result"] == "positive").sum(), len(gf)),
            "median_wait_days": float(np.median(gc["wait_days"])) if len(gc) else None,
        })
    med = float(np.median([o["pct_up_to_date"] for o in out]))
    for o in out:
        o["status"] = "top" if o["pct_up_to_date"] >= med + 4 else "flagged" if o["pct_up_to_date"] <= med - 4 else "on_target"
    regions = {}
    for o in out:
        r = regions.setdefault(o["region"], {"region": o["region"], "patients": 0, "eligible": 0, "overdue": 0, "utd_w": 0.0, "risk_w": 0.0})
        r["patients"] += o["patients"]; r["eligible"] += o["eligible"]; r["overdue"] += o["overdue"]
        r["utd_w"] += o["pct_up_to_date"] * o["eligible"]; r["risk_w"] += o["mean_uptake_risk_pct"] * max(o["overdue"], 1)
    rows = []
    for r in regions.values():
        rows.append({"region": r["region"], "patients": r["patients"], "eligible": r["eligible"], "overdue": r["overdue"],
                     "pct_up_to_date": round(r["utd_w"] / max(r["eligible"], 1), 1),
                     "overdue_per_100": round(r["overdue"] / max(r["eligible"], 1) * 100, 1)})
    return {"facilities": out, "regions": sorted(rows, key=lambda x: x["pct_up_to_date"]),
            "metrics": {k: v["label"] for k, v in METRICS.items()}, "metric_meta": METRICS,
            "popup": [["Eligible", "eligible"], ["Up to date", "pct_up_to_date", "%"], ["Due or overdue", "overdue"],
                      ["90-day completion", "completion_pct", "%"], ["Model risk", "mean_uptake_risk_pct", "%"]]}


def map_payload() -> dict:
    return copy.deepcopy(_map())


def map_spec(metric: str = "completion_pct", title: str | None = None) -> dict:
    m = _map(); metric = metric if metric in METRICS else "completion_pct"
    return {"type": "map", "title": title or f"{METRICS[metric]['label']} by facility", "metric": metric,
            "metric_label": METRICS[metric]["label"], "worse_is_high": METRICS[metric]["worse_is_high"],
            "facilities": [{**f, "value": f[metric]} for f in m["facilities"]],
            "highlight": [f["name"] for f in m["facilities"] if f["status"] == "flagged"], "popup": m["popup"]}


# ── Worklists and one person ──────────────────────────────────────────────────────────
def worklist(kind: str = "due", limit: int = 25, uninvited_only: bool = False) -> list[dict]:
    d = scored()
    d = d[d["consent_status"] != "restricted"]
    if kind == "due":
        d = d[d["due_status"].isin(["due", "overdue"])]
        if uninvited_only:
            d = d[d["invited_12m"] == 0]
        d = d.sort_values("uptake_risk", ascending=False)
    elif kind == "batch":
        # the day's outreach batch: due or overdue, not invited this year, by clinical priority
        # (APCS points, then age), so the model's bands are what differ between them
        d = d[d["due_status"].isin(["due", "overdue"]) & (d["invited_12m"] == 0)]
        d = d.sort_values(["apcs_points", "age", "person_id"], ascending=[False, False, True])
    elif kind == "fit_positive":
        d = d[d["fit_positive_no_colonoscopy"] == 1].copy()
        d["days_since_fit"] = d["fit_date_latest"].apply(lambda s: (TODAY - date.fromisoformat(s)).days if isinstance(s, str) else None)
        d = d.sort_values("days_since_fit", ascending=False)
    elif kind == "urgent":
        d = d[d["due_status"] == "urgent"].sort_values("apcs_points", ascending=False)
    else:
        raise ValueError(kind)
    cols = ["person_id", "age", "sex", "nationality_group", "language", "emirate", "area", "nearest_facility_name",
            "nearest_hospital_id", "distance_km", "apcs_tier", "apcs_points", "pathway_id", "pathway_test", "due_status",
            "last_screen", "invited_12m", "uptake_risk", "uptake_band", "fit_date_latest", "fit_result_latest",
            "family_history", "missed_appointments_12m", "gp_visits_12m"]
    if "days_since_fit" in d.columns:
        cols.append("days_since_fit")
    rows = d.head(limit)[cols].replace({np.nan: None}).to_dict("records")
    for r in rows:
        if r.get("uptake_risk") is not None:
            r["uptake_risk"] = round(float(r["uptake_risk"]), 3)
    return rows


def person_inputs(row: pd.Series) -> dict:
    """A population row as the input the screening check (crc.assess) takes."""
    return {"age": int(row["age"]), "sex": row["sex"], "bmi": float(row["bmi"]), "smoking": row["smoking"],
            "diabetes": bool(row["diabetes"]), "family_history": row["family_history"],
            "youngest_relative_age": None if pd.isna(row["youngest_relative_age"]) else int(row["youngest_relative_age"]),
            "history": [] if row["own_history"] == "none" else [row["own_history"]],
            "symptoms": ["bleeding"] if int(row["red_flag_symptoms"]) else [], "last_screen": row["last_screen"],
            "location": {"lat": float(row["lat"]), "lon": float(row["lon"]), "label": f"{row['area']}, {row['emirate']}"}}


def person(person_id: str) -> dict:
    d = scored()
    r = d[d["person_id"] == person_id]
    if r.empty:
        return {"error": f"{person_id} not found"}
    row = r.iloc[0]
    if row["consent_status"] == "restricted":
        return {"person_id": person_id, "consent": "DENIED",
                "message": "Restricted consent: the record cannot be opened or scored. This attempt has been logged."}
    from services import crc_ml
    assessment = crc.assess(person_inputs(row))
    risk = None
    if crc_ml.available():
        p, c = crc_ml.contribs(row)
        X = crc_ml.features(row.to_frame().T).iloc[0]
        risk = {"probability": round(p, 4), "band": crc_ml.band(p), "drivers": crc_ml.top_drivers(c, X, 5),
                "outreach": crc_ml.outreach_for(p)}
    prof = row[["person_id", "age", "sex", "nationality_group", "language", "insurance", "employment", "emirate", "area",
                "nearest_facility_name", "nearest_hospital_id", "distance_km", "hospital_distance_km", "smoking", "bmi",
                "diabetes", "family_history", "own_history", "red_flag_symptoms", "last_screen", "gp_visits_12m",
                "missed_appointments_12m", "apcs_tier", "due_status", "invited_12m", "last_invite_date", "last_invite_channel",
                "fit_result_latest", "fit_date_latest", "finding_latest", "fit_positive_no_colonoscopy"]].replace({np.nan: None}).to_dict()
    prof = {k: (v.item() if hasattr(v, "item") else v) for k, v in prof.items()}
    return {"person": prof, "assessment": assessment, "risk": risk}


# ── The decision, tested on real records (SAS Intelligent Decisioning's scoring test) ──────────
RULE_NODE = {"R1": "rs_symptoms", "R2": "rs_history", "R3": "rs_family", "R9": "rs_family", "R4": "rs_window", "R5": "rs_window",
             "R6": "rs_window", "R7": "rs_window", "R8": "rs_window", "R10": "rs_routing", "R11": "rs_outreach", "R12": "rs_safety",
             "R13": "rs_guard"}


@lru_cache(maxsize=1)
def decision_test_cases() -> list[dict]:
    """Eight records that walk every branch of the decision, picked deterministically from the population."""
    d = scored(); d = d[d["consent_status"] != "restricted"]
    due = d[d["due_status"].isin(["due", "overdue"]) & (d["invited_12m"] == 0)].sort_values(["apcs_points", "age", "person_id"], ascending=[False, False, True])
    picks = []
    def take(frame, label, sub):
        if len(frame):
            r = frame.iloc[0]; picks.append({"id": r["person_id"], "label": label, "sub": sub})
    take(due[due["uptake_band"].isin(["High", "Very high"])], "Due, unlikely to act", "the model sends a navigator")
    take(due[due["uptake_band"] == "Low"], "Due, likely to act", "an app notification is enough")
    take(d[d["due_status"] == "urgent"], "Symptoms reported", "rule R1, no model")
    take(d[d["fit_positive_no_colonoscopy"] == 1], "Positive FIT, no colonoscopy", "the safety net fires")
    take(d[d["own_history"] == "polyps"], "Polyps removed before", "surveillance, FIT not enough")
    take(d[d["family_history"].isin(["one_under60", "two_plus"]) & (d["age"] < 40)], "Family history, under 40", "colonoscopy pathway starts early")
    take(d[d["due_status"] == "up_to_date"], "Up to date", "nothing due")
    take(d[d["due_status"] == "shared_decision"], "Aged 76 to 85", "a shared decision")
    return picks


def decision_run(person_id: str) -> dict:
    """Run CRC_Screening_Pathway on one record: inputs, the path through the nodes, every rule's
    outcome, the model node's score, and the output variables."""
    b = person(person_id)
    if b.get("error") or b.get("consent") == "DENIED":
        return b
    from services import crc_ml
    prs, a, risk = b["person"], b["assessment"], b["risk"]
    flow = crc.decision_flow()
    decided = a["decided_by"]
    by_rule = {r["id"]: r for r in a["rule_trace"]}
    due = a["pathway"]["id"] in ("screen_now", "family_high") and a["pathway"]["urgency"] in ("now", "soon")
    days_since_fit = ((TODAY - date.fromisoformat(prs["fit_date_latest"])).days if prs.get("fit_date_latest") else None)
    safety = bool(prs.get("fit_positive_no_colonoscopy")) and (days_since_fit or 0) > 56
    chain = ["rs_symptoms", "rs_history", "rs_family", "rs_window"]
    stop_at = RULE_NODE[decided]
    path = ["start"]
    for n in chain:
        path.append(n)
        if n == stop_at:
            break
    if due:
        path += ["model_uptake", "rs_outreach", "rs_guard"]
    path += ["rs_routing", "rs_safety", "end"]

    nodes = {}
    for n in flow["nodes"]:
        nid = n["id"]; reached = nid in path
        rules = []
        for r in n.get("rules", []):
            tr = by_rule.get(r["id"])
            if r["id"] == "R11":
                fired = due and risk is not None
                note = (f"band {risk['band']} ({risk['probability']*100:.0f}%) → {risk['outreach']['channel']}" if fired else "not on a due pathway")
            elif r["id"] == "R12":
                fired = safety
                note = (f"positive FIT {days_since_fit} days ago, no colonoscopy" if safety else
                        ("positive FIT, colonoscopy done" if prs.get("fit_result_latest") == "positive" else "no positive FIT outstanding"))
            elif r["id"] == "R13":
                fired = False; note = "runs when the agent drafts a message (Agent tab)"
            else:
                fired = bool(tr and tr["status"] in ("decided", "applied")); note = tr["note"] if tr else ""
            rules.append({"id": r["id"], "name": r["name"], "fired": fired, "evaluated": reached and r["id"] != "R13",
                          "note": note, "condition": r["condition"], "actions": r["actions"], "source": r["source"]})
        if n["kind"] == "model":
            status = "scored" if (reached and risk) else "skipped"
            note = (f"{risk['probability']*100:.0f}% · {risk['band']}" if status == "scored" else
                    ("deterministic rule precedence (§9.1)" if decided == "R1" else "no outreach decision needed"))
        elif n["kind"] in ("start", "end"):
            status = "reached"; note = ""
        elif nid == "rs_guard":
            status = "deferred" if reached else "skipped"; note = "on the agent's draft" if reached else "no message on this path"
        elif not reached:
            status = "skipped"; note = "not reached: decided upstream" if nid in chain else "not on this path"
        else:
            status = "fired" if any(r["fired"] for r in rules) else "evaluated"
            note = "; ".join(f"{r['id']} {r['note']}" for r in rules if r["fired"]) or "no rule fired"
        nodes[nid] = {"status": status, "note": note, "rules": rules}

    fac = a["facilities"][0]["name"] if a["facilities"] else prs.get("nearest_facility_name")
    outputs = {
        "apcs_points": a["score"]["points"], "apcs_tier": a["score"]["tier"], "pathway_id": a["pathway"]["id"],
        "test": a["pathway"]["test"], "interval": a["pathway"]["interval"], "urgency": a["pathway"]["urgency"], "where": a["pathway"]["where"],
        "facility": fac, "uptake_p": (round(risk["probability"], 3) if (due and risk) else None),
        "outreach_band": (risk["band"] if (due and risk) else None), "outreach_channel": (risk["outreach"]["channel"] if (due and risk) else None),
        "navigator": (risk["outreach"]["navigator"] if (due and risk) else None), "safety_net": safety, "model_consulted": bool(due and risk),
    }
    inputs = {
        "age": prs["age"], "sex": prs["sex"], "bmi": prs["bmi"], "smoking": prs["smoking"], "diabetes": bool(prs["diabetes"]),
        "family_history": prs["family_history"], "youngest_relative_age": None, "personal_history": a["inputs"]["history"],
        "symptoms": a["inputs"]["symptoms"], "last_screen": prs["last_screen"], "distance_km": prs["distance_km"], "language": prs["language"],
        "insurance": prs["insurance"], "employment": prs["employment"], "gp_visits_12m": prs["gp_visits_12m"],
        "missed_appointments_12m": prs["missed_appointments_12m"], "fit_result_latest": prs.get("fit_result_latest"), "days_since_fit": days_since_fit,
    }
    fired = [{"ruleset": nid, "rule": r["id"], "name": r["name"], "fired": r["fired"]} for nid in path for r in nodes.get(nid, {}).get("rules", [])]
    return {"decision": {"id": flow["id"], "version": flow["version"]}, "person_id": person_id, "inputs": inputs, "path": path,
            "nodes": nodes, "outputs": outputs, "rule_fired": fired, "decided_by": decided}


def facility(facility_id: str) -> dict | None:
    f = tables()["facilities"]
    r = f[f["facility_id"] == facility_id]
    return None if r.empty else r.iloc[0].to_dict()


# ── Data page ─────────────────────────────────────────────────────────────────────────
def table_list() -> list[dict]:
    dd = data_dictionary()
    return [{"name": k, "rows": int(len(v)), "columns": list(v.columns), "description": dd.get(k, "")} for k, v in tables().items()]


def table_rows(name: str, offset: int = 0, limit: int = 50, search: str = "") -> dict:
    t = tables()
    if name not in t:
        raise KeyError(name)
    df = t[name]
    if search:
        mask = df.astype(str).apply(lambda col: col.str.contains(search, case=False, na=False)).any(axis=1)
        df = df[mask]
    page = df.iloc[offset:offset + min(limit, 200)].replace({np.nan: None})
    return {"table": name, "total": int(len(df)), "offset": offset, "rows": page.to_dict("records")}
