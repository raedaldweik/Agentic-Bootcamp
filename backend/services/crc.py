"""Example 2: colorectal cancer screening check.

A person enters a few facts about themselves and gets three things back: a risk
tier, the screening pathway that fits them under the UAE national programme, and
the nearest EHS facilities that can do the test, with distances.

What is real here, and what is not:

* The risk tier is the Asia-Pacific Colorectal Screening (APCS) score (Yeoh et al.,
  Gut 2011), a published score built for exactly this triage: age, sex, first-degree
  family history and smoking, plus the body-mass-index point of the later modified
  score. Its tiers came with measured rates of advanced neoplasia at screening
  colonoscopy (about 1%, 3% and 5%), which is what the "chance of finding something"
  line quotes.
* The pathway rules follow the UAE National Cancer Screening recommendations
  (average-risk screening from 40 to 75, yearly FIT or colonoscopy every ten years)
  and the usual family-history and high-risk surveillance rules. They are a teaching
  simplification, not a clinical protocol.
* The facilities are the 18 EHS hospitals and health centres the rest of the app
  uses, with the same approximate coordinates. Which service each offers is assumed from its
  type: hospitals have endoscopy units, health centres do FIT and GP referral.

It is an educational prototype. It does not diagnose, and the page says so.
"""
from __future__ import annotations

import math
from typing import Any

# The 18 EHS facilities the rest of the app uses (bootcamp/data/ehs_facilities.csv), with the
# same approximate coordinates as services/geo.py. Listed here so this module needs nothing
# heavier than the standard library.
FACILITIES: list[tuple[str, str, str, str, float, float]] = [
    ("F001", "Al Qassimi Hospital", "Hospital", "Sharjah", 25.3327, 55.4021),
    ("F002", "Kuwait Hospital Sharjah", "Hospital", "Sharjah", 25.3603, 55.3892),
    ("F003", "Saqr Hospital", "Hospital", "Ras Al Khaimah", 25.7880, 55.9517),
    ("F004", "Fujairah Hospital", "Hospital", "Fujairah", 25.1276, 56.3370),
    ("F005", "Umm Al Quwain Hospital", "Hospital", "Umm Al Quwain", 25.5498, 55.5657),
    ("F006", "Wasit Health Centre", "Primary Care", "Sharjah", 25.3440, 55.4460),
    ("F007", "Al Hamriyah Health Centre", "Primary Care", "Sharjah", 25.4699, 55.5001),
    ("F008", "Al Dhaid Health Centre", "Primary Care", "Sharjah", 25.2870, 55.8813),
    ("F009", "Al Hamidiya Health Centre", "Primary Care", "Ajman", 25.3945, 55.4996),
    ("F010", "Al Rams Health Centre", "Primary Care", "Ras Al Khaimah", 25.8800, 55.9640),
    ("F011", "Sha'am Health Centre", "Primary Care", "Ras Al Khaimah", 25.9950, 56.0500),
    ("F012", "Falaj Al Mualla Health Centre", "Primary Care", "Umm Al Quwain", 25.3938, 55.8530),
    ("F013", "Qidfa Health Centre", "Primary Care", "Fujairah", 25.3060, 56.3560),
    ("F014", "Al Bidya Health Centre", "Primary Care", "Fujairah", 25.4360, 56.3520),
    ("F015", "Al Nahda Health Centre", "Primary Care", "Sharjah", 25.3072, 55.3810),
    ("F016", "Masafi Health Centre", "Primary Care", "Fujairah", 25.3115, 56.1670),
    ("F017", "Khorfakkan Hospital", "Hospital", "Sharjah", 25.3400, 56.3475),
    ("F018", "Dibba Hospital", "Hospital", "Fujairah", 25.5915, 56.2610),
]

# ── Places in the UAE a participant can pick, with coordinates (lat, lon) ─────
# Northern Emirates first (the EHS footprint), then Dubai, Abu Dhabi and Al Ain.
AREAS: list[dict] = [
    {"emirate": "Sharjah", "area": "Al Nahda", "lat": 25.3005, "lon": 55.3745},
    {"emirate": "Sharjah", "area": "Al Majaz", "lat": 25.3230, "lon": 55.3840},
    {"emirate": "Sharjah", "area": "Al Qasimia", "lat": 25.3430, "lon": 55.3930},
    {"emirate": "Sharjah", "area": "Al Khan", "lat": 25.3250, "lon": 55.3720},
    {"emirate": "Sharjah", "area": "Muwaileh / University City", "lat": 25.3000, "lon": 55.4700},
    {"emirate": "Sharjah", "area": "Al Hamriyah", "lat": 25.4700, "lon": 55.5000},
    {"emirate": "Sharjah", "area": "Al Dhaid", "lat": 25.2880, "lon": 55.8800},
    {"emirate": "Sharjah", "area": "Khor Fakkan", "lat": 25.3400, "lon": 56.3500},
    {"emirate": "Sharjah", "area": "Kalba", "lat": 25.0700, "lon": 56.3500},
    {"emirate": "Sharjah", "area": "Dibba Al Hisn", "lat": 25.6200, "lon": 56.2700},
    {"emirate": "Ajman", "area": "Ajman city / Al Rashidiya", "lat": 25.4050, "lon": 55.4400},
    {"emirate": "Ajman", "area": "Al Nuaimiya", "lat": 25.3900, "lon": 55.4600},
    {"emirate": "Ajman", "area": "Al Hamidiya", "lat": 25.3920, "lon": 55.5000},
    {"emirate": "Ajman", "area": "Masfout", "lat": 24.8100, "lon": 56.0500},
    {"emirate": "Umm Al Quwain", "area": "Umm Al Quwain city", "lat": 25.5650, "lon": 55.5550},
    {"emirate": "Umm Al Quwain", "area": "Falaj Al Mualla", "lat": 25.3900, "lon": 55.8500},
    {"emirate": "Ras Al Khaimah", "area": "Al Nakheel", "lat": 25.7900, "lon": 55.9500},
    {"emirate": "Ras Al Khaimah", "area": "Al Hamra / Al Jazirah", "lat": 25.6900, "lon": 55.7800},
    {"emirate": "Ras Al Khaimah", "area": "Al Rams", "lat": 25.8800, "lon": 55.9600},
    {"emirate": "Ras Al Khaimah", "area": "Sha'am", "lat": 25.9900, "lon": 56.0500},
    {"emirate": "Fujairah", "area": "Fujairah city", "lat": 25.1300, "lon": 56.3300},
    {"emirate": "Fujairah", "area": "Qidfa", "lat": 25.3100, "lon": 56.3600},
    {"emirate": "Fujairah", "area": "Al Bidya", "lat": 25.4400, "lon": 56.3500},
    {"emirate": "Fujairah", "area": "Masafi", "lat": 25.3100, "lon": 56.1700},
    {"emirate": "Fujairah", "area": "Dibba Al Fujairah", "lat": 25.5900, "lon": 56.2600},
    {"emirate": "Dubai", "area": "Deira", "lat": 25.2700, "lon": 55.3200},
    {"emirate": "Dubai", "area": "Bur Dubai", "lat": 25.2500, "lon": 55.2900},
    {"emirate": "Dubai", "area": "Al Qusais", "lat": 25.2800, "lon": 55.3800},
    {"emirate": "Dubai", "area": "Mirdif", "lat": 25.2200, "lon": 55.4200},
    {"emirate": "Dubai", "area": "International City", "lat": 25.1600, "lon": 55.4100},
    {"emirate": "Dubai", "area": "Al Barsha", "lat": 25.1100, "lon": 55.2000},
    {"emirate": "Dubai", "area": "Dubai Marina / JBR", "lat": 25.0800, "lon": 55.1400},
    {"emirate": "Dubai", "area": "Jebel Ali", "lat": 25.0000, "lon": 55.0600},
    {"emirate": "Abu Dhabi", "area": "Abu Dhabi city", "lat": 24.4500, "lon": 54.3800},
    {"emirate": "Abu Dhabi", "area": "Khalifa City", "lat": 24.4200, "lon": 54.6000},
    {"emirate": "Abu Dhabi", "area": "Mussafah", "lat": 24.3500, "lon": 54.5000},
    {"emirate": "Abu Dhabi", "area": "Al Ain", "lat": 24.2100, "lon": 55.7400},
]
EHS_EMIRATES = {"Sharjah", "Ajman", "Umm Al Quwain", "Ras Al Khaimah", "Fujairah"}

SERVICES = {
    "Hospital": ["Colonoscopy (endoscopy unit)", "Gastroenterology clinic", "FIT kit"],
    "Primary Care": ["FIT kit and result review", "GP assessment", "Referral to endoscopy"],
}

# Average-risk screening window under the UAE national programme.
SCREEN_START, SCREEN_END, SCREEN_SHARED_DECISION_END = 40, 75, 85
PREVALENCE = {"average": 1.3, "moderate": 3.2, "high": 5.2}   # % advanced neoplasia, APCS tiers

RED_FLAGS = {
    "bleeding": "blood in the stool or rectal bleeding",
    "bowel_change": "a change in bowel habit lasting more than four weeks",
    "weight_loss": "unexplained weight loss",
    "anaemia": "iron-deficiency anaemia on a blood test",
    "mass_or_pain": "persistent abdominal pain or a lump",
}
HISTORY = {
    "polyps": "polyps (adenomas) removed before",
    "crc": "colorectal cancer treated before",
    "ibd8": "ulcerative colitis or Crohn's disease for 8 years or more",
    "syndrome": "a known inherited syndrome (Lynch or FAP) in you or your family",
}


# ── Free text: what a person writes in the "tell us more" boxes ───────────────
# The score and the pathway only count what is ticked, so the notes are scanned for
# things the person wrote but did not tick, and the page offers to tick them.
NOTE_PATTERNS = [
    ("symptoms", "bleeding", r"\b(blood|bleed|bleeding|bloody|red stool|black stool|melaena|melena)\b",
     "You mentioned blood. Tick 'blood in the stool' so it counts: it changes the advice."),
    ("symptoms", "bowel_change", r"\b(constipat\w*|diarrh\w*|loose stool|bowel habit|stools? (changed|change)|going more|going less|urgency)\b",
     "You described a change in bowel habit. If it has lasted more than four weeks, tick it."),
    ("symptoms", "weight_loss", r"\b(lost|losing) (some )?weight|weight loss|kilos? (down|lost)\b",
     "You mentioned losing weight. If it was not on purpose, tick 'unexplained weight loss'."),
    ("symptoms", "anaemia", r"\b(an(a)?emi\w*|low (iron|haemoglobin|hemoglobin)|iron deficien\w*|ferritin)\b",
     "You mentioned anaemia or low iron. Tick it: it is one of the warning signs doctors look for."),
    ("symptoms", "mass_or_pain", r"\b(abdominal pain|stomach pain|tummy pain|belly pain|cramps?|lump|mass|bloat\w*)\b",
     "You mentioned pain or a lump. If it is persistent, tick 'persistent abdominal pain or a lump'."),
    ("family_history", None, r"\b(father|mother|dad|mum|mom|brother|sister|son|daughter|parent|sibling)s?\b[^.]{0,60}\b(cancer|tumou?r|polyps?)\b",
     "You wrote about a relative with cancer or polyps. If it was a parent, brother, sister or child with bowel cancer, pick it under 'bowel cancer in the family' and give their age at diagnosis."),
    ("history", "polyps", r"\bpolyps?\b(?![^.]{0,60}\b(father|mother|brother|sister|son|daughter|parent|sibling))",
     "You mentioned polyps. If they were removed from your own bowel, tick it under your own history."),
    ("history", "ibd8", r"\b(crohn|colitis|ulcerative|ibd|inflammatory bowel)\b",
     "You mentioned colitis or Crohn's. If you have had it for 8 years or more, tick it: it moves you to a surveillance programme."),
    ("history", "syndrome", r"\b(lynch|fap|familial adenomatous|hnpcc|genetic test|brca)\b",
     "You mentioned an inherited syndrome or a genetic test. Tick 'a known inherited syndrome' if that is you or your family."),
    ("smoking", None, r"\b(smok\w*|cigarette|shisha|vap\w*|hookah|medwakh)\b",
     "You mentioned smoking or shisha. Set 'Smoking' to 'Yes' or 'Used to' so the score counts it."),
    ("last_screen", None, r"\b(colonoscop\w*|fit test|stool test|screened|screening|sigmoidoscop\w*)\b",
     "You mentioned a previous test. Pick it under 'Last screening' so the timing is right."),
    ("diabetes", None, r"\b(diabet\w*|metformin|insulin|hba1c|sugar)\b",
     "You mentioned diabetes or diabetes medicines. Set 'Diabetes' to 'Yes'."),
]
NOTE_FIELDS = ("health", "family", "screening", "symptoms", "lifestyle", "other")


def note_hints(p: dict) -> list[dict]:
    import re as _re
    text = " ".join(str((p.get("notes") or {}).get(k) or "") for k in NOTE_FIELDS).lower()
    if not text.strip():
        return []
    flags = set(p.get("symptoms") or []); history = set(p.get("history") or [])
    hints = []
    for field, value, pattern, message in NOTE_PATTERNS:
        if not _re.search(pattern, text):
            continue
        already = ((field == "symptoms" and value in flags) or (field == "history" and value in history)
                   or (field == "family_history" and (p.get("family_history") or "none") != "none")
                   or (field == "smoking" and (p.get("smoking") or "never") != "never")
                   or (field == "last_screen" and (p.get("last_screen") or "never") != "never")
                   or (field == "diabetes" and bool(p.get("diabetes"))))
        if not already:
            hints.append({"field": field, "value": value, "text": message})
    return hints


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def facilities() -> list[dict]:
    return [{"facility_id": fid, "name": name, "type": typ, "region": region, "lat": lat, "lon": lon,
             "services": SERVICES[typ], "endoscopy": typ == "Hospital"}
            for fid, name, typ, region, lat, lon in FACILITIES]


def options() -> dict:
    return {
        "areas": AREAS,
        "facilities": facilities(),
        "red_flags": [{"id": k, "label": v} for k, v in RED_FLAGS.items()],
        "history": [{"id": k, "label": v} for k, v in HISTORY.items()],
        "family_history": [
            {"id": "none", "label": "No parent, brother, sister or child with bowel cancer"},
            {"id": "one_60plus", "label": "One of them, diagnosed at 60 or older"},
            {"id": "one_under60", "label": "One of them, diagnosed before 60"},
            {"id": "two_plus", "label": "Two or more of them, at any age"},
        ],
        "last_screen": [
            {"id": "never", "label": "Never screened"},
            {"id": "fit_1y", "label": "Stool test (FIT) in the last 12 months, normal"},
            {"id": "fit_old", "label": "Stool test (FIT) more than a year ago"},
            {"id": "colo_10y", "label": "Colonoscopy in the last 10 years, normal"},
            {"id": "colo_old", "label": "Colonoscopy more than 10 years ago"},
        ],
        "examples": EXAMPLES,
    }


def _bmi(height_cm: float | None, weight_kg: float | None) -> float | None:
    if not height_cm or not weight_kg or height_cm < 100 or weight_kg < 25:
        return None
    return round(weight_kg / (height_cm / 100) ** 2, 1)


def apcs_score(age: int, sex: str, family: str, smoking: str, bmi: float | None) -> dict:
    """Asia-Pacific Colorectal Screening score with the BMI point."""
    factors = []
    pts = 0
    if age >= 70:
        pts += 3; factors.append({"factor": "Age 70 or over", "points": 3})
    elif age >= 50:
        pts += 2; factors.append({"factor": "Age 50 to 69", "points": 2})
    else:
        factors.append({"factor": "Age under 50", "points": 0})
    if sex == "male":
        pts += 1; factors.append({"factor": "Male", "points": 1})
    else:
        factors.append({"factor": "Female", "points": 0})
    if family != "none":
        pts += 2; factors.append({"factor": "A first-degree relative with bowel cancer", "points": 2})
    else:
        factors.append({"factor": "No first-degree relative with bowel cancer", "points": 0})
    if smoking in ("current", "former"):
        pts += 1; factors.append({"factor": "Smoker or ex-smoker", "points": 1})
    else:
        factors.append({"factor": "Never smoked", "points": 0})
    if bmi is not None and bmi >= 25:
        pts += 1; factors.append({"factor": f"BMI {bmi} (25 or over)", "points": 1})
    elif bmi is not None:
        factors.append({"factor": f"BMI {bmi}", "points": 0})
    tier = "average" if pts <= 1 else "moderate" if pts <= 3 else "high"
    return {"points": pts, "max_points": 8, "tier": tier, "factors": factors,
            "prevalence_pct": PREVALENCE[tier]}


def assess(p: dict) -> dict:
    age = int(p.get("age") or 0)
    sex = p.get("sex") or "female"
    smoking = p.get("smoking") or "never"
    family = p.get("family_history") or "none"
    youngest = p.get("youngest_relative_age")
    history = set(p.get("history") or [])
    flags = set(p.get("symptoms") or [])
    last = p.get("last_screen") or "never"
    bmi = p.get("bmi") or _bmi(p.get("height_cm"), p.get("weight_kg"))
    diabetes = bool(p.get("diabetes"))
    duration = p.get("symptom_duration") or ""    # under_2w | 2_6w | over_6w
    activity = p.get("activity") or "some"        # low | some | regular
    diet = p.get("diet") or "mixed"               # mixed | high_processed | high_fibre
    alcohol = p.get("alcohol") or "none"          # none | moderate | heavy

    score = apcs_score(age, sex, family, smoking, bmi)
    flagged = [RED_FLAGS[f] for f in RED_FLAGS if f in flags]
    hist = [HISTORY[h] for h in HISTORY if h in history]

    # ── Pathway ───────────────────────────────────────────────────────────────
    if flagged:
        pathway = {
            "id": "symptomatic", "urgency": "urgent", "title": "See a doctor within two weeks",
            "test": "Urgent GP assessment, then colonoscopy by referral",
            "interval": "Now. Do not wait for a screening appointment.",
            "where": "endoscopy",
            "why": ("You reported " + ", ".join(flagged)
                    + (" for more than six weeks" if duration == "over_6w" else " for a few weeks" if duration == "2_6w" else "")
                    + ". These need a doctor to look into them properly. Most turn out to be something minor, "
                    "but a stool screening test is not the right test once there are symptoms."
                    + (" Symptoms that have lasted this long should not wait any longer." if duration == "over_6w" else "")),
            "next_steps": [
                "Book a GP or family-medicine appointment this week and say the words 'change in bowels' or 'bleeding'.",
                "Expect a blood test and a referral for a colonoscopy; in the UAE this is usually arranged within two weeks.",
                "Bring a list of your medicines and the dates the symptoms started.",
            ],
        }
    elif "syndrome" in history or "crc" in history or "ibd8" in history or "polyps" in history:
        if "syndrome" in history:
            interval, why = ("Colonoscopy every 1 to 2 years from your early twenties, under a genetics and gastroenterology team",
                             "An inherited syndrome such as Lynch or FAP raises lifetime risk sharply, so surveillance starts young and is frequent.")
        elif "crc" in history:
            interval, why = ("Colonoscopy one year after treatment, then every 3 to 5 years as your specialist advises",
                             "After a bowel cancer, the rest of the bowel is checked on a fixed schedule.")
        elif "ibd8" in history:
            interval, why = ("Colonoscopy every 1 to 3 years, starting 8 years after the colitis began",
                             "Long-standing inflammation of the colon raises the risk, so it is checked directly rather than with a stool test.")
        else:
            interval, why = ("Colonoscopy every 3 to 5 years, depending on the number and size of the polyps removed",
                             "Polyps can come back; the surveillance interval depends on what was found last time.")
        pathway = {
            "id": "surveillance", "urgency": "soon", "title": "You belong in a specialist surveillance programme",
            "test": "Colonoscopy, on a schedule set by a gastroenterologist", "interval": interval, "where": "endoscopy",
            "why": why + " A stool test (FIT) is not enough for you.",
            "next_steps": [
                "Ask your GP for a referral to the gastroenterology clinic at the nearest EHS hospital, or go to the one you already attend.",
                "Take your previous colonoscopy or pathology report with you if you have it.",
                "If you are overdue by more than a year, say so when booking.",
            ],
        }
    elif family in ("one_under60", "two_plus"):
        start = SCREEN_START
        if youngest:
            start = min(SCREEN_START, int(youngest) - 10)
        due = age >= start
        pathway = {
            "id": "family_high", "urgency": "soon" if due else "later",
            "title": "Colonoscopy every five years" if due else f"Colonoscopy every five years, starting at {start}",
            "test": "Colonoscopy (not a stool test)", "where": "endoscopy",
            "interval": f"Every 5 years, from age {start}" + (", so you are due now" if due and last not in ("colo_10y",) else ""),
            "why": ("A close relative diagnosed young, or more than one relative, roughly doubles your risk. "
                    "Guidelines move you from the stool test to colonoscopy and start ten years before your "
                    "relative's diagnosis, or at 40, whichever is earlier."),
            "next_steps": [
                "Book a GP visit and ask for a colonoscopy referral on the grounds of family history.",
                "Find out, if you can, the age at which your relative was diagnosed. It sets your start age.",
                "Tell your brothers, sisters and children: the same rule applies to them.",
            ] if due else [
                f"Nothing to book yet. Put a reminder in for your {start}th birthday.",
                "Find out the age at which your relative was diagnosed; if it was younger than you think, your start age moves earlier.",
            ],
        }
    else:
        # average risk, or one relative diagnosed at 60+ (same tests, from 40)
        up_to_date = last in ("fit_1y", "colo_10y")
        if age < SCREEN_START:
            pathway = {
                "id": "not_yet", "urgency": "later", "title": f"No screening needed yet. It starts at {SCREEN_START}.",
                "test": "None for now", "interval": f"From age {SCREEN_START}: a yearly stool test (FIT) or a colonoscopy every 10 years",
                "where": "primary",
                "why": ("In the UAE routine screening starts at 40, earlier than in Europe or the US, because bowel cancer "
                        "here is diagnosed younger. Before then the best protection is knowing your family history and "
                        "acting on any symptoms."),
                "next_steps": [
                    f"Put screening on your list for your {SCREEN_START}th birthday.",
                    "Ask your parents and siblings whether anyone had bowel cancer or polyps; it changes your start age.",
                    "See a doctor straight away if you ever notice blood in the stool or a lasting change in bowel habit.",
                ],
            }
        elif age > SCREEN_SHARED_DECISION_END:
            pathway = {
                "id": "stop", "urgency": "later", "title": "Routine screening is no longer recommended",
                "test": "None routinely", "interval": "Not routinely after 85", "where": "primary",
                "why": "Above 85 the test is more likely to cause harm than to help, so it is not offered routinely.",
                "next_steps": ["Mention any new bowel symptoms to your doctor promptly; that is still worth acting on."],
            }
        elif age > SCREEN_END:
            pathway = {
                "id": "shared", "urgency": "later", "title": "Between 76 and 85: a decision to make with your doctor",
                "test": "Yearly stool test (FIT) or colonoscopy, if you and your doctor decide to continue",
                "interval": "Individual decision", "where": "primary",
                "why": "After 75 the benefit depends on your overall health and whether you were screened before.",
                "next_steps": ["Raise it at your next GP visit, especially if you were never screened or it was more than 10 years ago."],
            }
        elif up_to_date:
            nxt = "in 12 months" if last == "fit_1y" else "10 years after your last colonoscopy"
            pathway = {
                "id": "up_to_date", "urgency": "later", "title": "You are up to date",
                "test": "Yearly stool test (FIT) or colonoscopy every 10 years", "interval": f"Next one {nxt}", "where": "primary",
                "why": "Your last test was within the recommended interval. Keep the rhythm: it is the regularity that catches cancer early.",
                "next_steps": [f"Book the next test {nxt}.", "See a doctor in between if symptoms appear; screening does not replace that."],
            }
        else:
            pathway = {
                "id": "screen_now", "urgency": "now", "title": "You are due for screening",
                "test": "A stool test (FIT) you do at home, or a colonoscopy",
                "interval": "FIT every year, or colonoscopy every 10 years",
                "where": "primary" if score["tier"] == "average" else "either",
                "why": ("You are in the 40 to 75 window and " + ("have never been screened" if last == "never" else "your last test is out of date")
                        + ". FIT takes five minutes at home and is free at EHS health centres; a positive result leads to a colonoscopy. "
                        + ("Your risk tier is above average, so some people in your position choose colonoscopy directly." if score["tier"] != "average" else "")),
                "next_steps": [
                    "Collect a FIT kit from the nearest EHS health centre or ask for one at any EHS visit. No preparation, no fasting.",
                    "Return it within a day or two; the result comes in about a week.",
                    "If it is positive you will be called for a colonoscopy. Nine out of ten positive tests are not cancer, but all need checking.",
                ],
            }
    if family == "one_60plus" and pathway["id"] in ("screen_now", "up_to_date", "not_yet"):
        pathway["why"] += " One relative diagnosed at 60 or older does not change the tests, only that you start at 40 at the latest."

    # ── Lifestyle advice, from what was entered ───────────────────────────────
    advice = []
    if smoking == "current":
        advice.append({"title": "Stop smoking", "text": "Smoking is one of the APCS points you can remove. EHS runs free quit-smoking clinics; ask at any health centre."})
    if bmi is not None and bmi >= 25:
        advice.append({"title": "Weight", "text": f"A BMI of {bmi} adds a point. Losing 5% of body weight measurably lowers bowel-cancer risk and helps blood sugar too."})
    if activity == "low":
        advice.append({"title": "Move more", "text": "150 minutes a week of brisk walking is linked to roughly a quarter lower risk of colon cancer."})
    if diet == "high_processed":
        advice.append({"title": "Processed and red meat", "text": "Daily processed meat raises risk by about a fifth. Swapping some of it for fish, pulses and vegetables helps."})
    elif diet != "high_fibre":
        advice.append({"title": "Fibre", "text": "Whole grains, fruit, vegetables and pulses lower risk. Aim for 30 g of fibre a day."})
    if alcohol == "heavy":
        advice.append({"title": "Alcohol", "text": "More than two drinks a day raises risk. Cutting down helps within a few years."})
    if diabetes:
        advice.append({"title": "Diabetes", "text": "Type 2 diabetes is linked to a somewhat higher bowel-cancer risk. Good glucose control and the screening above cover it; no extra test is needed."})
    if not advice:
        advice.append({"title": "Keep it up", "text": "Nothing in what you entered points to a lifestyle change. Screening on time is the one thing left to do."})

    # ── Where to go ───────────────────────────────────────────────────────────
    loc = p.get("location") or {}
    lat, lon = loc.get("lat"), loc.get("lon")
    place = loc.get("label") or ""
    if (lat is None or lon is None) and loc.get("area"):
        a = next((x for x in AREAS if x["area"] == loc["area"]), None)
        if a:
            lat, lon, place = a["lat"], a["lon"], f"{a['area']}, {a['emirate']}"
    nearby: list[dict] = []
    outside = False
    if lat is not None and lon is not None:
        allf = facilities()
        for f in allf:
            f = dict(f)
            f["km"] = round(haversine_km(lat, lon, f["lat"], f["lon"]), 1)
            f["minutes"] = int(round(f["km"] / 55 * 60 + 6))   # door to door at suburban speeds
            nearby.append(f)
        nearby.sort(key=lambda f: f["km"])
        if pathway["where"] == "either":
            # due, and risk tier above average: FIT at a health centre or colonoscopy at a
            # hospital are both reasonable, so simply the three nearest places, by distance
            nearby = nearby[:3]
            for f in nearby:
                f["role"] = "Colonoscopy here, if you choose it directly" if f["endoscopy"] else "FIT kit here"
        elif pathway["id"] == "symptomatic":
            # the first step is a doctor this week, wherever is nearest; the colonoscopy follows
            # by referral, so the nearest hospital with an endoscopy unit is always in the list
            picked = nearby[:2]
            if not any(f["endoscopy"] for f in picked):
                picked.append(next(f for f in nearby if f["endoscopy"]))
            nearby = picked
            for f in nearby:
                f["role"] = ("Doctor and colonoscopy under one roof" if f["endoscopy"]
                             else "See a doctor here this week; they refer you on")
        else:
            want_endoscopy = pathway["where"] == "endoscopy"
            primary = [f for f in nearby if f["endoscopy"] == want_endoscopy][:2]
            other = [f for f in nearby if f["endoscopy"] != want_endoscopy][:1]
            for f in primary:
                f["role"] = "Colonoscopy and gastroenterology are here" if want_endoscopy else "FIT kit here; this is where to start"
            for f in other:
                f["role"] = "Nearest health centre, for the GP referral" if want_endoscopy else "Nearest hospital, if you choose colonoscopy"
            nearby = primary + other
        outside = min(x["km"] for x in nearby) > 35 if nearby else False
        if loc.get("area"):
            em = next((x["emirate"] for x in AREAS if x["area"] == loc["area"]), "")
            outside = outside or (em and em not in EHS_EMIRATES)

    tier_label = {"average": "Average risk", "moderate": "Moderately raised risk", "high": "Higher risk"}[score["tier"]]
    summary = (f"{tier_label} on the APCS score ({score['points']} of {score['max_points']} points). "
               f"{pathway['title']}. " +
               (f"Nearest place to go: {nearby[0]['name']}, about {nearby[0]['km']} km away." if nearby else "Pick your area to see where to go."))
    return {
        "inputs": {"age": age, "sex": sex, "bmi": bmi, "smoking": smoking, "family_history": family,
                   "history": sorted(history), "symptoms": sorted(flags), "last_screen": last},
        "note_hints": note_hints(p),
        "score": {**score, "tier_label": tier_label},
        "pathway": pathway,
        "advice": advice,
        "location": {"lat": lat, "lon": lon, "label": place, "outside_ehs_footprint": bool(outside)},
        "facilities": nearby,
        "summary": summary,
        "sources": [
            "APCS score: Yeoh KG et al., Gut 2011;60:1236-41, and the modified score with BMI",
            "UAE National Cancer Screening recommendations: colorectal screening from 40 to 75, yearly FIT or colonoscopy every 10 years",
            "Family-history and surveillance intervals: US Multi-Society Task Force 2017 and BSG 2020, simplified",
        ],
        "disclaimer": ("Educational prototype for the hackathon. The rules are simplified, the facility services are assumed "
                       "from facility type, and nothing here is a diagnosis or a substitute for a doctor's advice."),
    }


EXAMPLES = [
    {"id": "fatima", "label": "Fatima, 44, never screened",
     "sub": "Average risk, due for her first FIT",
     "inputs": {"age": 44, "sex": "female", "height_cm": 160, "weight_kg": 62, "smoking": "never", "diabetes": False,
                "family_history": "none", "history": [], "symptoms": [], "last_screen": "never",
                "activity": "some", "diet": "mixed", "alcohol": "none", "location": {"area": "Al Majaz"}}},
    {"id": "khalid", "label": "Khalid, 56, smoker, father had bowel cancer at 71",
     "sub": "Higher APCS tier, due now, colonoscopy worth considering",
     "inputs": {"age": 56, "sex": "male", "height_cm": 175, "weight_kg": 92, "smoking": "current", "diabetes": True,
                "family_history": "one_60plus", "youngest_relative_age": 71, "history": [], "symptoms": [], "last_screen": "never",
                "activity": "low", "diet": "high_processed", "alcohol": "none", "location": {"area": "Al Nakheel"}}},
    {"id": "mariam", "label": "Mariam, 38, sister diagnosed at 46",
     "sub": "Family history: colonoscopy from 36, so due now",
     "inputs": {"age": 38, "sex": "female", "height_cm": 165, "weight_kg": 60, "smoking": "never", "diabetes": False,
                "family_history": "one_under60", "youngest_relative_age": 46, "history": [], "symptoms": [], "last_screen": "never",
                "activity": "regular", "diet": "high_fibre", "alcohol": "none", "location": {"area": "Fujairah city"}}},
    {"id": "youssef", "label": "Youssef, 61, bleeding for three weeks",
     "sub": "Red flag: urgent pathway, not screening",
     "inputs": {"age": 61, "sex": "male", "height_cm": 172, "weight_kg": 80, "smoking": "former", "diabetes": False,
                "family_history": "none", "history": [], "symptoms": ["bleeding", "bowel_change"], "last_screen": "colo_old",
                "activity": "some", "diet": "mixed", "alcohol": "none", "location": {"area": "Al Hamidiya"}}},
]


# ── Chat: questions about the result ──────────────────────────────────────────
CHAT_SYSTEM = """You are the screening assistant inside Example 2 of the EHS x SAS Agentic AI Hackathon app,
an educational prototype about bowel (colorectal) cancer screening in the UAE.

You are given the person's form and the assessment the app computed from it. Answer their questions
about that result, about the tests (FIT stool test, colonoscopy, preparation, sedation, what results
mean), about the UAE screening programme (average-risk screening from 40 to 75, yearly FIT or
colonoscopy every 10 years, family-history and surveillance rules), and about the EHS facilities listed.

Rules:
- Plain language, short answers, for someone who is not medical. Two to five sentences, or a short list.
- Never diagnose, never estimate an individual's chance of having cancer, never change the pathway the
  app shows; if they ask whether they have cancer, say a test is the only way to know and point them to
  the next step in their result.
- Anyone with the warning symptoms (bleeding, a changed bowel habit for weeks, unexplained weight loss,
  anaemia, persistent pain or a lump) should see a doctor within two weeks. Say so when relevant, calmly.
- No medicine doses, no interpreting their lab results, nothing beyond bowel cancer screening; for other
  topics say it is outside what this assistant covers and suggest their GP.
- If asked how reliable this is: the risk tier is a published score (APCS), the rules are a simplified
  teaching version of the national programme, and nothing here replaces a doctor.
- Do not invent phone numbers, prices, opening hours or waiting times. Booking is through the EHS app
  or call centre, with an Emirates ID.
- Match the person's language (English or Arabic).
"""

FAQ = [
    (r"\b(do i have|have i got|is it cancer|cancer\?|am i going to|will i die|dying)\b",
     "Nothing on this page can tell whether you have cancer; only a test can, and most people who are checked do not have it. "
     "What the page can tell you is the right next step for you, which is shown at the top of your result. If you have any of the warning symptoms, that step is a doctor within two weeks."),
    (r"\b(fit|stool test|poo test|poop|sample|kit)\b",
     "FIT is a stool test you do at home. You collect a tiny sample with the stick in the kit, close it and hand it back. "
     "It looks for blood you cannot see. No fasting, no preparation. The result takes about a week. A positive result does not mean cancer: about nine in ten positives are polyps or something harmless, but every positive is followed by a colonoscopy to check."),
    (r"\b(colonoscop\w*|camera|scope|prep\w*|laxative|sedat\w*|anaesth\w*|hurt|painful)\b",
     "A colonoscopy is a camera test of the whole large bowel, done in a hospital endoscopy unit. The day before you drink a bowel-cleansing solution and stay on clear fluids. "
     "On the day you are given sedation, so most people remember little and feel no pain; it takes 20 to 40 minutes and you go home the same day with someone to drive you. If polyps are found they are usually removed there and then."),
    (r"\b(40|forty|start|young|early|age)\b",
     "In the UAE routine screening starts at 40 for people at average risk, earlier than the 45 or 50 used in many countries, because bowel cancer here is diagnosed younger on average. "
     "From 40 to 75 the choice is a yearly FIT or a colonoscopy every ten years. With a close relative diagnosed young, it starts ten years before their age at diagnosis."),
    (r"\b(tier|score|points|apcs|average risk|higher risk|moderate|percent|%|chance|likely|odds)\b",
     "The tier comes from the APCS score, a published score using age, sex, family history, smoking and weight. Each tier was measured in large screening studies: of 100 people in the average tier who have a colonoscopy about 1 is found to have an advanced polyp or early cancer, about 3 in the moderate tier and about 5 in the higher tier. "
     "It describes the group, not you personally. Open 'How the points add up' on your result to see which facts gave points."),
    (r"\b(famil\w*|father|mother|brother|sister|parent|relative|hereditary|genetic|lynch)\b",
     "One parent, brother, sister or child with bowel cancer roughly doubles your own risk. Diagnosed at 60 or older, you keep the normal tests but start at 40 at the latest. Diagnosed younger, or two relatives, you move to colonoscopy every five years, starting ten years before their diagnosis age. "
     "Lynch syndrome and FAP are rarer inherited conditions handled by a genetics team."),
    (r"\b(symptom\w*|bleed\w*|blood|constipat\w*|diarrh\w*|weight loss|pain|lump|anaemi\w*|anemi\w*|urgent|worried|scared)\b",
     "Blood in the stool, a change in bowel habit lasting more than four weeks, unexplained weight loss, anaemia, or persistent pain or a lump all need a doctor within two weeks, whatever your age or tier. "
     "Most turn out to be something minor, but they are checked with a colonoscopy, not a stool test. Book a GP appointment this week and say what you have noticed."),
    (r"\b(where|book\w*|appointment|hospital|centre|center|clinic|near\w*|how do i|go)\b",
     "Your result lists the nearest EHS places and what each does: health centres hand out FIT kits and see you as a GP, hospitals have the endoscopy units for colonoscopy. "
     "Book through the EHS app or the EHS call centre and bring your Emirates ID. If you have symptoms, say so when booking so you are seen sooner."),
    (r"\b(cost|price|free|pay|insurance|fee)\b",
     "Under the national screening programme the stool test and the follow-up colonoscopy are provided through the public system; for insured residents the screening benefit is usually covered. "
     "I cannot quote prices; the facility or your insurer can confirm."),
    (r"\b(result\w*|positive|negative|normal|how long|wait)\b",
     "A FIT result normally comes back within about a week. Negative means no blood was found and you repeat the test in a year. Positive means blood was found and you are invited for a colonoscopy, usually within a few weeks; nine in ten positives are not cancer, but all are checked."),
    (r"\b(polyp\w*|adenoma\w*)\b",
     "Polyps are small growths on the bowel lining. Most are harmless, some can slowly turn into cancer over years, which is exactly why screening works: finding and removing them prevents cancer. "
     "After polyps are removed you get a follow-up colonoscopy in three to five years, depending on how many and how large."),
    (r"\b(diet|food|meat|fibre|fiber|exercise|weight|smok\w*|alcohol|prevent\w*|reduce|lower)\b",
     "The things that measurably lower bowel-cancer risk: not smoking, keeping a healthy weight, 150 minutes a week of brisk activity, more fibre from whole grains, fruit, vegetables and pulses, less processed and red meat, and little or no alcohol. "
     "None of them replaces screening on time; they work alongside it."),
    (r"\b(reliable|accurate|trust|real|ai|doctor|sure|prototype|demo)\b",
     "This is an educational prototype built for the hackathon. The risk tier is a published, validated score and the pathway follows the national programme in simplified form, but it does not replace a doctor. "
     "Use it to understand what applies to you and to know what to ask for; the decision is made with your GP."),
]
FAQ_DEFAULT = ("I can help with what your result means, the tests (the FIT stool test and colonoscopy), when screening starts in the UAE, "
               "family history, warning symptoms, and where to go. Ask me about any of those. For anything else, your GP is the right person.")


def faq_answer(question: str, assessment: dict) -> str:
    import re as _re
    q = (question or "").lower()
    answer = next((a for pat, a in FAQ if _re.search(pat, q)), FAQ_DEFAULT)
    if assessment.get("inputs", {}).get("symptoms") and "two weeks" not in answer:
        answer += " Because you ticked warning symptoms, the first step for you is a doctor within two weeks."
    return answer


def chat_context(person: dict, assessment: dict) -> str:
    notes = {k: v for k, v in (person.get("notes") or {}).items() if v}
    f = assessment["facilities"]
    return "\n".join([
        "PERSON (from the form): " + ", ".join(f"{k}={v}" for k, v in assessment["inputs"].items()),
        "NOTES THEY WROTE: " + (" | ".join(f"{k}: {v}" for k, v in notes.items()) if notes else "none"),
        f"RISK TIER: {assessment['score']['tier_label']}, {assessment['score']['points']}/{assessment['score']['max_points']} APCS points; "
        f"factors: " + ", ".join(f"{x['factor']} (+{x['points']})" for x in assessment["score"]["factors"]),
        f"PATHWAY: {assessment['pathway']['title']} | test: {assessment['pathway']['test']} | timing: {assessment['pathway']['interval']} | urgency: {assessment['pathway']['urgency']}",
        "WHY: " + assessment["pathway"]["why"],
        "NEXT STEPS: " + " / ".join(assessment["pathway"]["next_steps"]),
        "NEAREST PLACES: " + ("; ".join(f"{x['name']} ({x['type']}, {x['km']} km, {x['role']})" for x in f) if f else "no location given"),
        "ADVICE SHOWN: " + "; ".join(f"{a['title']}: {a['text']}" for a in assessment["advice"]),
        "DISCLAIMER SHOWN: " + assessment["disclaimer"],
    ])


async def chat(person: dict, messages: list[dict]):
    """NDJSON events, same shape as the simulator's explanation: meta, token..., final."""
    from services import llm_client as LC
    assessment = assess(person)
    history = [{"role": m["role"], "content": str(m.get("content") or "")[:4000]}
               for m in messages if m.get("role") in ("user", "assistant") and m.get("content")][-12:]
    question = history[-1]["content"] if history and history[-1]["role"] == "user" else ""
    if not LC.llm_available():
        text = faq_answer(question, assessment)
        yield {"type": "meta", "mode": "deterministic", "model": None}
        for chunk in text.split(" "):
            yield {"type": "token", "text": chunk + " "}
        yield {"type": "final", "text": text, "mode": "deterministic", "model": None}
        return
    from services import agent   # the agent graph's model choice; heavy, so only when a model is configured
    system = CHAT_SYSTEM + "\n\nCONTEXT\n" + chat_context(person, assessment)

    async def run(model: str):
        if model.startswith("claude"):
            client = LC.make_anthropic_client(timeout_s=agent.HTTP_TIMEOUT_MS / 1000, max_retries=2)
            async with client.messages.stream(model=model, max_tokens=500, temperature=0.3, system=system,
                                              messages=history) as stream:
                async for piece in stream.text_stream:
                    yield piece
            return
        from google.genai import types as gtypes
        client = LC.make_client(http_options=agent._http_options())
        cfg = agent.generation_config(model) or gtypes.GenerateContentConfig()
        cfg.system_instruction = system; cfg.temperature = 0.3; cfg.max_output_tokens = 500
        contents = [gtypes.Content(role="user" if m["role"] == "user" else "model", parts=[gtypes.Part(text=m["content"])]) for m in history]
        async for ev in await client.aio.models.generate_content_stream(model=model, contents=contents, config=cfg):
            if ev.text:
                yield ev.text

    model = agent.active_model()
    label = agent.display_model(model)
    text = ""
    yield {"type": "meta", "mode": "live", "model": label}
    try:
        async for piece in run(model):
            text += piece
            yield {"type": "token", "text": piece}
    except Exception as e:
        if agent.is_capacity_error(e) and not text and agent.switch_model(str(e)):
            try:
                async for piece in run(agent.active_model()):
                    text += piece
                    yield {"type": "token", "text": piece}
            except Exception:
                pass
        if not text:   # the model is unavailable: the FAQ still answers
            text = faq_answer(question, assessment)
            for chunk in text.split(" "):
                yield {"type": "token", "text": chunk + " "}
            yield {"type": "final", "text": text, "mode": "deterministic", "model": None}
            return
    yield {"type": "final", "text": text, "mode": "live", "model": label}
