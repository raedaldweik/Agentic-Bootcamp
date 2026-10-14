"""Writes NHA-CS-01, the synthetic colorectal-cancer screening pathway document that Example 2's
rules cite (section numbers match services/crc.RULES). Same look as the other NHA documents.

Run from backend/:  python -m scripts.make_crc_guideline
"""
from __future__ import annotations

import shutil
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer

HERE = Path(__file__).resolve().parent.parent
OUT = HERE / "data" / "guidelines" / "NHA_CS01_Colorectal_Cancer_Screening_Pathway.pdf"
KIT = HERE.parent / "kit" / "documents" / OUT.name
FOOTER = ("Synthetic demonstration document created for the SAS Composite AI demo. The 'National Health Authority' "
          "is fictional. Not for clinical use. No copyrighted guideline text is reproduced.")

SECTIONS = [
    ("§1 Purpose and scope",
     ["This pathway sets out who is offered colorectal (bowel) cancer screening, with which test and how often, "
      "how people with symptoms or a positive test are managed, and the standards the screening programme's "
      "outreach must meet. It applies to the programme's invitations, to opportunistic screening in primary care, "
      "and to any decision-support system acting on the programme's behalf."]),
    ("§2 Definitions",
     ["FIT: the faecal immunochemical test, a home stool test for hidden blood; positive at 20 micrograms of haemoglobin per gram of faeces or above.",
      "Colonoscopy: endoscopic examination of the whole large bowel, performed in a hospital endoscopy unit under sedation.",
      "Average risk: no first-degree relative with colorectal cancer, no personal history in §5 and no symptoms in §6.",
      "First-degree relative: a parent, brother, sister or child.",
      "Red-flag symptoms: rectal bleeding or blood in the stool; a change in bowel habit lasting more than four weeks; unexplained weight loss; iron-deficiency anaemia; persistent abdominal pain or an abdominal mass."]),
    ("§3 Average-risk screening",
     ["3.1 Screening window. People at average risk are offered screening from age 40 to age 75: a FIT every year, or a colonoscopy every ten years. A person whose last FIT was within 12 months, or whose last colonoscopy was within ten years and normal, is up to date and is next due at the end of that interval.",
      "3.2 Ages 76 to 85. Screening is an individual decision made with the person's doctor, weighing overall health and previous screening. People never screened, or last screened more than ten years ago, benefit most.",
      "3.3 Over 85. Routine screening is not offered. New bowel symptoms are still assessed under §6.",
      "3.4 Before 40. No routine screening, unless §4.2 or §5 applies. People are encouraged to learn their family history."]),
    ("§4 Risk stratification",
     ["4.1 APCS score. The programme stratifies with the Asia-Pacific Colorectal Screening score (age, sex, first-degree family history, smoking, with the body-mass-index point of the modified score): 0 to 1 points average risk, 2 to 3 moderately raised, 4 and above higher risk. People in the moderate and higher tiers keep the same screening window but may be offered a colonoscopy directly instead of a FIT. The tier describes a group's rate of advanced neoplasia at screening colonoscopy, about 1%, 3% and 5%; it is not an individual prediction.",
      "4.2 Family history. One first-degree relative diagnosed at 60 or older: average-risk tests, screening to start no later than 40. One first-degree relative diagnosed before 60, or two or more first-degree relatives at any age: colonoscopy every five years, starting at 40 or ten years before the youngest relative's age at diagnosis, whichever is earlier."]),
    ("§5 Surveillance populations",
     ["People with adenomatous polyps removed, a previous colorectal cancer, ulcerative colitis or Crohn's colitis of eight years or more, or a known hereditary syndrome (Lynch syndrome, familial adenomatous polyposis) are managed in a specialist surveillance programme by colonoscopy, on the interval set by a gastroenterologist: three to five years after polyps, one year after cancer treatment then every three to five years, one to three years in long-standing colitis, and one to two years from the early twenties in hereditary syndromes. A FIT is not a substitute for surveillance colonoscopy."]),
    ("§6 Symptoms and the positive test",
     ["6.1 Red-flag symptoms take precedence over every screening rule. A person reporting any symptom in §2 is referred for clinical assessment within 14 days and for colonoscopy by referral; they are not offered a FIT.",
      "6.2 Positive FIT. A positive FIT is followed by a colonoscopy within eight weeks (56 days). A repeat FIT is not an acceptable response to a positive result.",
      "6.3 Safety net. Any positive FIT with no colonoscopy recorded at eight weeks is placed on the navigator worklist and the person is contacted within five working days; the referring facility is notified."]),
    ("§7 Where tests are done",
     ["FIT kits are handed out, returned and reviewed at primary healthcare centres, which also provide GP assessment and referral. Colonoscopy and gastroenterology clinics are provided at hospitals with an endoscopy unit. People on a colonoscopy pathway are directed to the nearest hospital with an endoscopy unit; people on the FIT pathway to the nearest health centre. Residents outside the network's footprint are directed to their own health authority."]),
    ("§8 Programme outreach standards",
     ["8.1 Every person found due is invited within 30 days; a reminder follows at 14 and 28 days if no test is booked.",
      "8.2 Invitations and reminders are available in Arabic, English, Urdu, Hindi, Malayalam and Tagalog, and name the test, the nearest place to do it and how to book.",
      "8.3 Outreach intensity follows the programme's predicted risk that an invitation is not acted on within 90 days. Low: app notification, reminder at 14 days. Moderate: SMS in the person's language with reminders at 14 and 28 days and a booking link. High: a patient-navigator phone call within five working days with booking offered on the call. Very high: navigator call with the booking made on the call, the kit posted or handed over at the nearest centre, and a transport note on the record. The predicted risk changes outreach effort only.",
      "8.4 Programme targets: participation of at least 60% of the eligible population; 90-day completion of at least 65% of invitations; FIT positivity between 5% and 10%; colonoscopy within eight weeks of a positive FIT for at least 90%."]),
    ("§9 Predictive models and generated communication",
     ["9.1 A predictive model may prioritise and shape outreach. It must not alter eligibility, the test offered, the interval, or any clinical decision; those follow §3 to §6 only.",
      "9.2 A message drafted by a language model must be built from the pathway decided under §3 to §6, name the test and the facility, use the person's language, and must not state an appointment date or time, a price, a waiting time, a phone number, or any statement about the person's likelihood of having cancer.",
      "9.3 Every drafted message or referral is reviewed and approved by a member of staff before it is sent; drafts that fail the checks in 9.2 are returned to a template. Every model score, rule outcome, draft and decision is written to the programme's audit trail."]),
    ("§10 Quality indicators",
     ["Participation rate; 90-day completion rate by facility, language and nationality group; FIT positivity; time from positive FIT to colonoscopy; proportion of positive FITs with colonoscopy within eight weeks; adenoma, advanced-adenoma and cancer detection rates; proportion of outreach drafts approved without edit."]),
]


def build(path: Path):
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["Normal"], fontName="Helvetica", fontSize=10, leading=14, alignment=TA_LEFT)
    h = ParagraphStyle("h", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12.5, spaceBefore=10, spaceAfter=4, textColor="#1B3650")
    title = ParagraphStyle("t", parent=styles["Title"], fontName="Helvetica-Bold", fontSize=17, leading=21, alignment=TA_LEFT, spaceAfter=4)
    meta = ParagraphStyle("m", parent=body, fontSize=9, textColor="#475569", spaceAfter=10)

    def footer(canvas, doc):
        canvas.saveState(); canvas.setFont("Helvetica", 7); canvas.setFillGray(0.45)
        canvas.drawString(20 * mm, 11 * mm, FOOTER); canvas.drawRightString(190 * mm, 11 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=20 * mm,
                            title="NHA-CS-01 Colorectal Cancer Screening Pathway", author="National Health Authority (Fictional)")
    story = [Paragraph("Colorectal Cancer Screening Pathway: Eligibility, Risk Stratification, Symptoms and Programme Outreach", title),
             Paragraph("National Health Authority (Fictional) · Document NHA-CS-01 · Version 1.0 · Issued September 2026 · Synthetic Demonstration Edition", meta)]
    for head, paras in SECTIONS:
        story.append(Paragraph(head, h))
        if len(paras) == 1:
            story.append(Paragraph(paras[0], body))
        else:
            story.append(ListFlowable([ListItem(Paragraph(p, body), leftIndent=10) for p in paras], bulletType="bullet", start="•", leftIndent=12, bulletFontSize=8))
        story.append(Spacer(1, 3))
    doc.build(story, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    build(OUT)
    KIT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT, KIT)
    print(f"✓ {OUT} ({OUT.stat().st_size} bytes) and {KIT}")
