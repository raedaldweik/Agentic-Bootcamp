"""
Cancer screening, synthetic colorectal-cancer screening programme generator.

A population of residents of the Northern Emirates in and around the screening age, the
programme's activity over 36 months (invitations, FIT tests, colonoscopies) and the
outcome the uptake model learns from: whether an invitation led to a completed test
within 90 days. Everything is synthetic and seeded, so the files are reproducible.

Tables written to backend/data/screening/ (csv.gz):

    facilities.csv.gz        the 18 hospitals and health centres, with endoscopy capacity
    population.csv.gz        12,000 people: who they are, where they live, their risk
                             factors, the APCS tier and the pathway the rules give them,
                             their screening history and the latest invitation's outcome
    invitations.csv.gz       every programme invitation over 36 months and what happened
    fit_tests.csv.gz         FIT stool tests (programme and opportunistic) with results
    colonoscopies.csv.gz     colonoscopies: indication, wait, findings

The rules that give each person a pathway are the same ones the app uses live
(services/crc.py), so the programme tables and the screening check never disagree.

Run from backend/:  python -m scripts.generate_screening_data
"""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from services import crc  # noqa: E402

OUT = HERE / "data" / "screening"
SEED = 2026
RNG = np.random.default_rng(SEED)
TODAY = date(2026, 9, 1)
N_PEOPLE = 12_000
MONTHS = 36

# ────────────────────────────── reference data ──────────────────────────────

# Area weights: Sharjah city dense, the East Coast and the far north thinner (the access story)
AREAS = [a for a in crc.AREAS if a["emirate"] in crc.NETWORK_EMIRATES]
AREA_WEIGHT = {
    "Al Nahda": 9, "Al Majaz": 10, "Al Qasimia": 8, "Al Khan": 6, "Muwaileh / University City": 9,
    "Al Hamriyah": 3, "Al Dhaid": 3, "Khor Fakkan": 3, "Kalba": 2.5, "Dibba Al Hisn": 1.5,
    "Ajman city / Al Rashidiya": 7, "Al Nuaimiya": 5, "Al Hamidiya": 4, "Masfout": 0.8,
    "Umm Al Quwain city": 3, "Falaj Al Mualla": 1.2,
    "Al Nakheel": 5, "Al Hamra / Al Jazirah": 3, "Al Rams": 1.8, "Sha'am": 1.2,
    "Fujairah city": 4.5, "Qidfa": 1.2, "Al Bidya": 1.0, "Masafi": 0.8, "Dibba Al Fujairah": 1.8,
}
# Facility capacity (synthetic): endoscopy slots per week for hospitals, FIT kits a month for all
FACILITY_CAPACITY = {
    "F001": (38, 900), "F002": (26, 700), "F003": (22, 500), "F004": (18, 450), "F005": (10, 300),
    "F017": (12, 300), "F018": (8, 220),
}

NATIONALITY_GROUPS = [
    # (group, weight, language, uninsured share, shift-work share)
    ("Emirati",            0.22, "ar", 0.00, 0.08),
    ("South Asian",        0.38, "ur", 0.05, 0.34),
    ("Arab expatriate",    0.20, "ar", 0.02, 0.16),
    ("Filipino",           0.08, "tl", 0.03, 0.30),
    ("East African",       0.04, "en", 0.06, 0.28),
    ("Western / other",    0.08, "en", 0.01, 0.06),
]
LANG_OF = {"South Asian": ["ur", "hi", "ml"], "Filipino": ["tl"], "Emirati": ["ar"],
           "Arab expatriate": ["ar"], "East African": ["en", "sw"], "Western / other": ["en"]}


def haversine(lat1, lon1, lat2, lon2):
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def month_start(d: date) -> date:
    return date(d.year, d.month, 1)


def add_months(d: date, k: int) -> date:
    m = d.month - 1 + k
    return date(d.year + m // 12, m % 12 + 1, 1)


# ────────────────────────────── facilities ──────────────────────────────

def gen_facilities() -> pd.DataFrame:
    rows = []
    for fid, name, typ, region, lat, lon in crc.FACILITIES:
        slots, kits = FACILITY_CAPACITY.get(fid, (0, 180 if typ == "Primary Care" else 300))
        rows.append({"facility_id": fid, "facility_name": name, "facility_type": typ, "region": region,
                     "lat": lat, "lon": lon, "endoscopy_unit": int(typ == "Hospital"),
                     "colonoscopy_slots_per_week": slots, "fit_kits_per_month": kits})
    return pd.DataFrame(rows)


# ────────────────────────────── population ──────────────────────────────

def gen_population(fac: pd.DataFrame) -> pd.DataFrame:
    area_names = [a["area"] for a in AREAS]
    w = np.array([AREA_WEIGHT[a] for a in area_names], dtype=float); w /= w.sum()
    nat_w = np.array([g[1] for g in NATIONALITY_GROUPS]); nat_w /= nat_w.sum()
    # age bands: the programme window 40–75 dominates; a few younger (family history) and older
    bands = [(36, 39, 0.05), (40, 49, 0.37), (50, 59, 0.29), (60, 69, 0.18), (70, 75, 0.07), (76, 85, 0.04)]
    band_w = np.array([b[2] for b in bands]); band_w /= band_w.sum()
    fac_rows = fac.to_dict("records")

    rows = []
    for i in range(N_PEOPLE):
        pid = f"SC-{200001 + i}"
        area = AREAS[int(RNG.choice(len(AREAS), p=w))]
        # a little scatter around the area centre (the outskirts are further from everything)
        lat = area["lat"] + RNG.normal(0, 0.018); lon = area["lon"] + RNG.normal(0, 0.018)
        dists = [(haversine(lat, lon, f["lat"], f["lon"]), f) for f in fac_rows]
        dists.sort(key=lambda t: t[0])
        d_any, f_any = dists[0]
        d_hosp, f_hosp = next((d, f) for d, f in dists if f["endoscopy_unit"])
        g = NATIONALITY_GROUPS[int(RNG.choice(len(NATIONALITY_GROUPS), p=nat_w))]
        nat, _, _, unins, shift_share = g
        lang = str(RNG.choice(LANG_OF[nat]))
        lo, hi, _ = bands[int(RNG.choice(len(bands), p=band_w))]
        age = int(RNG.integers(lo, hi + 1))
        male = RNG.random() < (0.52 if nat == "Emirati" else 0.66 if nat in ("South Asian", "East African") else 0.50)
        sex = "male" if male else "female"
        smoking = str(RNG.choice(["never", "former", "current"], p=[0.60, 0.13, 0.27] if male else [0.92, 0.04, 0.04]))
        bmi = float(np.clip(RNG.normal(28.2 if nat != "Western / other" else 26.5, 4.6), 17.5, 48))
        diabetes = RNG.random() < min(0.45, 0.06 + 0.0045 * (age - 36) + (0.08 if bmi >= 30 else 0))
        family = str(RNG.choice(["none", "one_60plus", "one_under60", "two_plus"], p=[0.885, 0.07, 0.035, 0.01]))
        youngest = int(RNG.integers(62, 80)) if family == "one_60plus" else int(RNG.integers(38, 59)) if family == "one_under60" else int(RNG.integers(42, 70)) if family == "two_plus" else None
        hist = str(RNG.choice(["none", "polyps", "ibd8", "crc", "syndrome"], p=[0.946, 0.035, 0.010, 0.006, 0.003]))
        symptoms = RNG.random() < 0.014
        residency = "Citizen" if nat == "Emirati" else "Resident"
        uninsured = RNG.random() < unins
        insurance = "Government" if nat == "Emirati" else ("Uninsured" if uninsured else str(RNG.choice(["Employer-Private", "Basic"], p=[0.62, 0.38])))
        employment = str(RNG.choice(["shift", "day", "not working"], p=[shift_share, 0.72 - shift_share if age < 65 else 0.25, 0.28 if age < 65 else 0.75 - shift_share] if age < 65 else [shift_share * 0.4, 0.25, 0.75 - shift_share * 0.4]))
        gp_visits = int(RNG.poisson(1.3 + 1.6 * diabetes + 0.012 * max(age - 50, 0) + (0.6 if nat == "Emirati" else 0)))
        missed = int(RNG.poisson(0.35 + 0.25 * (employment == "shift") + 0.15 * (lang not in ("ar", "en")) + 0.2 * uninsured))
        # screening history: engagement raises the chance of being screened before
        engage = 0.25 + 0.06 * min(gp_visits, 6) + 0.12 * (family != "none") - 0.05 * missed - 0.004 * d_any
        engage += 0.10 if nat == "Emirati" else 0
        if age < 40:
            last = "never" if RNG.random() > 0.08 or family == "none" else str(RNG.choice(["colo_10y", "fit_old"]))
        else:
            p_never = float(np.clip(0.72 - engage, 0.12, 0.80))
            rest = 1 - p_never
            last = str(RNG.choice(["never", "fit_1y", "fit_old", "colo_10y", "colo_old"],
                                  p=[p_never, rest * 0.38, rest * 0.30, rest * 0.26, rest * 0.06]))
        months_since = (None if last == "never" else int(RNG.integers(1, 12)) if last == "fit_1y"
                        else int(RNG.integers(13, 60)) if last == "fit_old" else int(RNG.integers(6, 118)) if last == "colo_10y"
                        else int(RNG.integers(121, 220)))
        consent = "restricted" if RNG.random() < 0.015 else "general"
        rows.append({
            "person_id": pid, "age": age, "sex": sex, "nationality_group": nat, "language": lang,
            "residency": residency, "insurance": insurance, "employment": employment,
            "emirate": area["emirate"], "area": area["area"], "lat": round(lat, 4), "lon": round(lon, 4),
            "nearest_facility_id": f_any["facility_id"], "nearest_facility_name": f_any["facility_name"],
            "distance_km": round(d_any, 1), "nearest_hospital_id": f_hosp["facility_id"], "hospital_distance_km": round(d_hosp, 1),
            "smoking": smoking, "bmi": round(bmi, 1), "diabetes": int(diabetes),
            "family_history": family, "youngest_relative_age": youngest, "own_history": hist,
            "red_flag_symptoms": int(symptoms), "last_screen": last, "months_since_last_screen": months_since,
            "gp_visits_12m": gp_visits, "missed_appointments_12m": missed, "consent_status": consent,
        })
    df = pd.DataFrame(rows)

    # ── the deterministic rules give every person a tier and a pathway (services/crc.py) ──
    tiers, points, pathway, test, urgency, due = [], [], [], [], [], []
    for r in df.itertuples():
        person = {"age": r.age, "sex": r.sex, "bmi": r.bmi, "smoking": r.smoking, "diabetes": bool(r.diabetes),
                  "family_history": r.family_history, "youngest_relative_age": r.youngest_relative_age,
                  "history": [] if r.own_history == "none" else [r.own_history],
                  "symptoms": ["bleeding"] if r.red_flag_symptoms else [], "last_screen": r.last_screen,
                  "location": {}}
        a = crc.assess(person)
        tiers.append(a["score"]["tier"]); points.append(a["score"]["points"])
        pathway.append(a["pathway"]["id"]); test.append(a["pathway"]["test"]); urgency.append(a["pathway"]["urgency"])
        pid_ = a["pathway"]["id"]
        if pid_ == "screen_now":
            due.append("overdue" if r.last_screen in ("fit_old", "colo_old") or r.age >= 42 else "due")
        elif pid_ == "family_high":
            due.append("due" if a["pathway"]["urgency"] == "soon" else "not_yet")
        elif pid_ == "surveillance":
            due.append("surveillance")
        elif pid_ == "symptomatic":
            due.append("urgent")
        elif pid_ == "up_to_date":
            due.append("up_to_date")
        elif pid_ == "shared":
            due.append("shared_decision")
        elif pid_ == "stop":
            due.append("not_eligible")
        else:
            due.append("not_yet")
    df["apcs_points"] = points; df["apcs_tier"] = tiers
    df["pathway_id"] = pathway; df["pathway_test"] = test; df["urgency"] = urgency; df["due_status"] = due
    return df


# ────────────────────────────── programme activity ──────────────────────────────

def completion_logit(r, channel: str, reminders: int, fac_factor: float) -> float:
    """The data-generating process behind uptake. The model has to rediscover it."""
    z = 0.30
    z -= 0.105 * r.distance_km
    z -= 0.55 * r.missed_appointments_12m
    z += 0.24 * min(r.gp_visits_12m, 8)
    z -= 0.75 * (r.language not in ("ar", "en"))
    z -= 0.95 * (r.insurance == "Uninsured")
    z -= 0.60 * (r.employment == "shift")
    z -= 0.50 * (r.smoking == "current")
    z += 0.80 * (r.last_screen != "never")
    z += 0.60 * (r.family_history != "none")
    z += 0.25 * r.diabetes
    z += 0.30 * (r.sex == "female")
    z -= 0.018 * abs(r.age - 58)
    z += {"app": 0.25, "call": 0.40, "sms": 0.0, "letter": -0.25}[channel]
    z += 0.20 * reminders
    z += fac_factor
    return z


def gen_activity(pop: pd.DataFrame, fac: pd.DataFrame):
    first_month = add_months(month_start(TODAY), -MONTHS)
    months = [add_months(first_month, k) for k in range(MONTHS)]
    # a facility-level organisational factor (east coast and far north weaker outreach)
    fac_factor = {f.facility_id: (-0.35 if f.region in ("Fujairah",) else -0.25 if f.region == "Ras Al Khaimah"
                                  else -0.15 if f.region == "Umm Al Quwain" else 0.05 if f.region == "Sharjah" else 0.0)
                  for f in fac.itertuples()}
    invitations, fits, colos = [], [], []
    latest = {}   # person_id -> latest invitation outcome
    inv_n = fit_n = colo_n = 0

    def fit_test(pid, fid, d, tier, source):
        nonlocal fit_n
        fit_n += 1
        p_pos = {"average": 0.045, "moderate": 0.075, "high": 0.11}[tier]
        pos = RNG.random() < p_pos
        hb = float(np.clip(RNG.lognormal(3.9 if pos else 1.2, 0.5), 0.5, 900))
        fits.append({"test_id": f"FIT-{fit_n:06d}", "person_id": pid, "facility_id": fid, "test_date": d.isoformat(),
                     "result": "positive" if pos else "negative", "f_hb_ug_g": round(hb, 1), "source": source})
        return pos

    def colonoscopy(pid, hosp, d, indication, tier):
        nonlocal colo_n
        colo_n += 1
        wait = int(np.clip(RNG.normal(26 if indication == "fit_positive" else 44, 10), 5, 120))
        if indication == "fit_positive":
            p = [0.44, 0.31, 0.18, 0.07]
        elif indication == "symptoms":
            p = [0.52, 0.22, 0.14, 0.12]
        elif indication in ("surveillance", "family_history"):
            p = [0.62, 0.24, 0.11, 0.03]
        else:
            p = [0.72, 0.19, 0.07, 0.02]
        if tier == "high":
            p = [p[0] - 0.08, p[1], p[2] + 0.05, p[3] + 0.03]
        finding = str(RNG.choice(["normal", "polyp", "advanced_adenoma", "cancer"], p=np.array(p) / sum(p)))
        colos.append({"procedure_id": f"COL-{colo_n:06d}", "person_id": pid, "facility_id": hosp,
                      "procedure_date": (d + timedelta(days=wait)).isoformat(), "indication": indication,
                      "wait_days": wait, "bowel_prep_adequate": int(RNG.random() < 0.91), "finding": finding,
                      "polyps_removed": int(RNG.poisson(1.6)) if finding in ("polyp", "advanced_adenoma") else 0})
        return finding

    for r in pop.itertuples():
        if r.consent_status == "restricted":
            continue
        # how many invitations this person received over 36 months
        if r.due_status in ("due", "overdue", "up_to_date", "surveillance"):
            k = int(RNG.choice([0, 1, 2, 3], p=[0.18, 0.42, 0.28, 0.12]))
        elif r.due_status in ("shared_decision",):
            k = int(RNG.choice([0, 1], p=[0.6, 0.4]))
        else:
            k = 0
        sent_months = sorted(RNG.choice(MONTHS, size=k, replace=False)) if k else []
        for mi in sent_months:
            inv_n += 1
            d = months[int(mi)] + timedelta(days=int(RNG.integers(0, 28)))
            channel = str(RNG.choice(["sms", "app", "call", "letter"], p=[0.46, 0.30, 0.14, 0.10]))
            reminders = int(RNG.choice([0, 1, 2], p=[0.5, 0.35, 0.15]))
            z = completion_logit(r, channel, reminders, fac_factor[r.nearest_facility_id]) + RNG.normal(0, 0.40)
            done = RNG.random() < 1 / (1 + math.exp(-z))
            days = int(np.clip(RNG.gamma(2.2, 14), 2, 90)) if done else None
            outcome = "completed" if done else str(RNG.choice(["no_response", "declined", "booked_not_attended"], p=[0.66, 0.14, 0.20]))
            invitations.append({"invite_id": f"INV-{inv_n:06d}", "person_id": r.person_id, "sent_date": d.isoformat(),
                                "channel": channel, "reminders": reminders, "facility_id": r.nearest_facility_id,
                                "pathway_id": r.pathway_id, "completed_90d": int(done), "days_to_completion": days,
                                "outcome": outcome})
            latest[r.person_id] = (d, channel, int(done), days)
            if done:
                td = d + timedelta(days=days)
                if r.pathway_id in ("screen_now", "up_to_date") and not (r.apcs_tier != "average" and RNG.random() < 0.25):
                    pos = fit_test(r.person_id, r.nearest_facility_id, td, r.apcs_tier, "programme")
                    if pos and RNG.random() < 0.86:
                        colonoscopy(r.person_id, r.nearest_hospital_id, td + timedelta(days=int(RNG.integers(3, 14))), "fit_positive", r.apcs_tier)
                else:
                    ind = ("surveillance" if r.pathway_id == "surveillance" else "family_history" if r.pathway_id == "family_high"
                           else "primary_screening")
                    colonoscopy(r.person_id, r.nearest_hospital_id, td, ind, r.apcs_tier)
        # symptomatic people: a referral colonoscopy in the last months, most of them
        if r.due_status == "urgent" and RNG.random() < 0.7:
            d = TODAY - timedelta(days=int(RNG.integers(10, 150)))
            colonoscopy(r.person_id, r.nearest_hospital_id, d, "symptoms", r.apcs_tier)
        # opportunistic FIT outside the programme
        if r.last_screen == "fit_1y" and r.person_id not in latest and RNG.random() < 0.5:
            d = TODAY - timedelta(days=int(RNG.integers(20, 360)))
            pos = fit_test(r.person_id, r.nearest_facility_id, d, r.apcs_tier, "opportunistic")
            if pos and RNG.random() < 0.8:
                colonoscopy(r.person_id, r.nearest_hospital_id, d + timedelta(days=7), "fit_positive", r.apcs_tier)

    inv = pd.DataFrame(invitations); ft = pd.DataFrame(fits); co = pd.DataFrame(colos)
    # fold the latest invitation back onto the population
    pop = pop.copy()
    pop["invitations_36m"] = pop["person_id"].map(inv.groupby("person_id").size()).fillna(0).astype(int)
    cutoff = (TODAY - timedelta(days=365)).isoformat()
    pop["invited_12m"] = pop["person_id"].map(inv[inv["sent_date"] >= cutoff].groupby("person_id").size()).fillna(0).astype(int).clip(upper=1)
    pop["last_invite_date"] = pop["person_id"].map({k: v[0].isoformat() for k, v in latest.items()})
    pop["last_invite_channel"] = pop["person_id"].map({k: v[1] for k, v in latest.items()})
    pop["completed_90d"] = pop["person_id"].map({k: v[2] for k, v in latest.items()})
    pop["days_to_completion"] = pop["person_id"].map({k: v[3] for k, v in latest.items()})
    lastfit = ft.sort_values("test_date").groupby("person_id").last()
    pop["fit_result_latest"] = pop["person_id"].map(lastfit["result"])
    pop["fit_date_latest"] = pop["person_id"].map(lastfit["test_date"])
    lastco = co.sort_values("procedure_date").groupby("person_id").last()
    pop["colonoscopy_done"] = pop["person_id"].isin(co["person_id"]).astype(int)
    pop["finding_latest"] = pop["person_id"].map(lastco["finding"])
    pop["colonoscopy_date_latest"] = pop["person_id"].map(lastco["procedure_date"])
    # programme flag: a positive FIT with no colonoscopy afterwards (the safety-net rule)
    pop["fit_positive_no_colonoscopy"] = ((pop["fit_result_latest"] == "positive")
                                         & (pop["colonoscopy_date_latest"].isna() | (pop["colonoscopy_date_latest"] < pop["fit_date_latest"]))).astype(int)
    return pop, inv, ft, co


DATA_DICTIONARY = {
    "facilities": "The 18 hospitals and health centres of the network: coordinates, whether there is an endoscopy unit, colonoscopy slots per week and FIT kits per month (synthetic capacity).",
    "population": "12,000 residents aged 36 to 85: demographics, language, insurance, employment, where they live and the distance to the nearest facility, risk factors (smoking, BMI, diabetes, family history, own history, symptoms), the APCS points and tier, the pathway the rules give them (pathway_id, due_status), screening history, engagement (GP visits, missed appointments), the latest invitation and its 90-day outcome (completed_90d: the uptake model's label), latest FIT and colonoscopy.",
    "invitations": "Every programme invitation over 36 months: date, channel (sms/app/call/letter), reminders, the facility it came from, the person's pathway, whether a test was completed within 90 days, days to completion and the outcome.",
    "fit_tests": "FIT stool tests: date, facility, result, faecal haemoglobin (ug/g) and whether it was a programme or an opportunistic test.",
    "colonoscopies": "Colonoscopies: indication (fit_positive, family_history, surveillance, symptoms, primary_screening), wait in days, bowel preparation adequacy, finding (normal, polyp, advanced_adenoma, cancer) and polyps removed.",
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    fac = gen_facilities()
    print("Generating population…", flush=True)
    pop = gen_population(fac)
    print("Generating programme activity…", flush=True)
    pop, inv, ft, co = gen_activity(pop, fac)
    for name, df in [("facilities", fac), ("population", pop), ("invitations", inv), ("fit_tests", ft), ("colonoscopies", co)]:
        df.to_csv(OUT / f"{name}.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
        print(f"  {name}: {len(df):,} rows")
    (OUT / "data_dictionary.json").write_text(json.dumps(DATA_DICTIONARY, indent=2))
    inv12 = inv[inv["sent_date"] >= (TODAY - timedelta(days=365)).isoformat()]
    print(f"  due/overdue: {(pop['due_status'].isin(['due', 'overdue'])).sum():,} · up to date: {(pop['due_status'] == 'up_to_date').sum():,} "
          f"· 90-day completion (12 m): {inv12['completed_90d'].mean()*100:.1f}% · FIT positivity: {(ft['result'] == 'positive').mean()*100:.1f}% "
          f"· cancers: {(co['finding'] == 'cancer').sum()}")
    print(f"✓ written to {OUT}")


if __name__ == "__main__":
    main()
