# Live Demonstration: Real-World Evidence in Action with Agentic AI (SAS)

**Slot:** 45 min · **Facilitator:** SAS · **Audience:** hackathon participants, mixed technical and non-technical

**Deck:** `RWE_in_Action_with_Agentic_AI.pptx` (22 slides, speaker notes with a timing guide on every slide, built on the SAS EXTERNAL template with Anova fonts embedded; same design language as the Session 2 deck, with consulting-deck conventions: action titles, an executive summary, big-number evidence cards with a source line, stat tiles, problem / solution pages). No organisation is named in the examples; the data is synthetic.

## Storyline

| Part | Minutes | Slides | What it says |
|---|---|---|---|
| Executive summary | 3 | 2 | Agentic AI has left the pilot stage; the value is in real-world data you already hold |
| Why now, what it is | 5 | 3 – 5 | The real-world-evidence loop and where the hours go; analytical vs generative vs agentic AI; what surrounds the model |
| The evidence | 7 | 6 – 8 | Six production deployments with measured results; where agentic AI can go to work across the care pathway (six places, two use cases each); why most pilots fail and what the successes share |
| Example 1 · Population health | 5 + 10 live | 9 – 13 | Problem, the solution overview (data, agent, MCP server, tools, CAS table), the four demo questions, the anatomy of one answer (backup) |
| Example 2 · Cancer early warning | 5 + 7 live | 14 – 18 | Problem, the solution overview in the same diagram (inputs, screening agent, MCP server, tools, facilities table), the four demo personas, the programme-scale view with the published evidence |
| What it means | 3 | 19 – 20 | The blueprint both examples share; five tests for an agentic use case worth building |
| Sources, close | | 21 – 22 | Fifteen numbered sources; thank you |

Both live examples run in the hackathon app in this repo: Example 1 is the Assistant tab (Basira, `backend/services/agent.py`, scenario chips C1–C4 in `backend/services/scenarios.py`); Example 2 is the screening check (`backend/services/crc.py`, personas Fatima, Khalid, Mariam, Youssef).

## Evidence cited on the slides

Every number on an evidence slide has a source line on the slide and an entry on slide 21: the JAMA 2026 multisite AI-scribe study, the JAMA Network Open 2025 burnout study, Geisinger's ML-guided screening outreach (M&SOM 2026), the WellSpan / Hippocratic AI multilingual outreach analysis, MUSC Health's prior-authorisation agents, NIH TrialGPT, MIT NANDA's GenAI Divide, Gartner's June 2025 forecast, SAS Innovate 2026, the IDF Diabetes Atlas, the UAE National Cancer Registry, and the APCS score (Gut 2011). Registry figures (4,000 patients, 34.9% well controlled, 760 overdue, AED 64.0M) are from the synthetic registry in `bootcamp/data/`.

## Before the session

Open the app on the second screen: Example 1 warmed up on the morning briefing with the trace panel visible, Example 2 loaded with Fatima's profile. Timing and fallbacks are in the speaker notes of slide 1; slides 13 and 18 are the backups if a live environment misbehaves.

## Rebuilding the deck

```bash
pip install python-pptx lxml
cd Hackathon/Live_Demo_RWE_in_Action_with_Agentic_AI/build
python3 build_rwe_demo.py          # writes ../RWE_in_Action_with_Agentic_AI.pptx
```

* `build/icons/` – line icons (Lucide, via react-icons) pre-rendered as PNG in white / blue / navy / slate. Regenerate with `node icons.js` (needs `react-icons`, `react`, `react-dom`, `sharp`); the folder keeps only the icons the deck uses.
* `build/arc.json` – the light-grey arc band traced from the reference deck (same file as Session 2).
* Environment overrides: `SAS_TEMPLATE=<path>` and `DEMO_OUT=<path>`.

Edit the text directly in PowerPoint for small changes; edit the script and rebuild for structural ones.

## Viewing on a phone

Mobile viewers do not load the fonts embedded in the template, so text reflows in a fallback font. The deck is built with slack for that (cards, not dense tables; minimum 12 pt), and a PDF export from PowerPoint is the safest way to preview it on a phone.
