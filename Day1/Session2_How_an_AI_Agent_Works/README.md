# Day 1 · Session 2 — How an AI agent works and makes decisions

**Slot:** 10:45 – 11:30 (45 min, can stretch to ~55 min) · **Facilitator:** SAS · **Audience:** non-technical EHS staff

**Deck:** `Session2_How_an_AI_Agent_Works_and_Makes_Decisions.pptx` (32 slides, speaker notes on every slide, built on the SAS EXTERNAL template with Anova fonts embedded).

## What the session covers (from the agenda)

| Agenda item | Slides |
|---|---|
| Anatomy of an AI agent: Goal, Planning, Knowledge, Tools, Actions, Human Oversight | 5 – 13 |
| The agent decision-making and execution cycle | 14 – 18 |
| How agents interact with enterprise systems, data and external tools | 19 – 21 |
| Human-in-the-loop vs. autonomous execution | 22 – 25 |
| Agent autonomy, boundaries and escalation points | 26 – 29 |
| Practical exercise (feeds the use-case assessment session at 11:30) | 30 |

One running example is used on every slide: the **No-Show Agent**, a fictional outpatient appointment agent (spot likely no-shows, confirm or reschedule, refill the slot, never make a clinical decision).

## Slide outline

| # | Slide | Layout |
|---|---|---|
| 1 | Title | SAS – Title |
| 2 | In the next 45 minutes (agenda + outcomes) | content |
| 3 | From Session 1: an agent in one sentence (skippable) | content |
| 4 | Our running example: the No-Show Agent | content |
| 5 | Section: Anatomy of an AI agent | SAS – Section |
| 6 | Anatomy overview: six building blocks | diagram |
| 7 | 1 · Goal (weak vs strong goal) | content |
| 8 | 2 · Planning (the plan, and re-planning) | content |
| 9 | 3 · Knowledge (training, documents/RAG, live data, memory) | cards |
| 10 | 4 · Tools (data, models, rules, apps, other agents; MCP) | cards |
| 11 | 5 · Actions (read → suggest → reversible → irreversible ladder) | cards |
| 12 | 6 · Human oversight (before / during / after) | cards |
| 13 | The No-Show Agent on one page (agent canvas) | grid |
| 14 | Section: How an agent decides and executes | SAS – Section |
| 15 | The agent loop: perceive, reason & plan, act, observe | diagram |
| 16 | The loop in practice: one patient, one afternoon | flow |
| 17 | Inside one reasoning step (what goes in / what comes out) | diagram |
| 18 | When does the loop stop? (four designed exits) | cards |
| 19 | Section: Connecting to the enterprise | SAS – Section |
| 20 | Reaching enterprise systems, data and tools (governed tool layer) | diagram |
| 21 | What good integration looks like (four habits) | cards |
| 22 | Section: Human-in-the-loop vs autonomous | SAS – Section |
| 23 | The autonomy spectrum (Assist / Approve / Supervise / Autonomous) | columns |
| 24 | Choosing the level for each action (impact × reversibility) | matrix |
| 25 | Autonomy is earned, not granted (trust ladder) | stairs |
| 26 | Section: Boundaries and escalation | SAS – Section |
| 27 | Boundaries: scope, permissions, limits, hard rules | cards |
| 28 | Escalation: triggers and a good hand-over | two cards |
| 29 | The No-Show Agent's operating agreement | table |
| 30 | Exercise: where would you put the human? (3 EHS scenarios) | cards |
| 31 | Takeaways + Up next | blue |
| 32 | Thank you | SAS – Closing |

## Suggested timing (≈ 52 min)

Intro 3 · Anatomy 14 · Decision loop 9 · Enterprise integration 5 · Human-in-the-loop 7 · Boundaries & escalation 7 · Exercise 5 · Wrap-up 2.
For a strict 45 minutes: skip slides 3 and 21 and run the exercise in 3 minutes. Timing notes are in the speaker notes of slide 1.

## Rebuilding the deck

The deck is generated from `build/build_session2.py` (python-pptx) on top of `../../templates/SAS_External_Template.pptx`.

```bash
pip install python-pptx lxml
cd Day1/Session2_How_an_AI_Agent_Works/build
python3 build_session2.py            # writes ../Session2_How_an_AI_Agent_Works_and_Makes_Decisions.pptx
```

* `build/icons/` – line icons (Lucide, via react-icons) pre-rendered as PNG in white / blue / navy / slate. Regenerate with `node icons.js` (needs `react-icons`, `react`, `react-dom`, `sharp`).
* `build/arc.json` – the light-grey arc band traced from the reference deck, so content slides match the SAS Viya Agentic AI Experience look exactly.
* Environment overrides: `SAS_TEMPLATE=<path>` and `SESSION2_OUT=<path>`.

Edit the text directly in PowerPoint for small changes; edit the script and rebuild for structural ones.
