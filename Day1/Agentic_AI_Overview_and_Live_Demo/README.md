# Day 1 · Agentic AI in action — overview and live demo

**Slot:** 45 min · **Facilitator:** SAS · **Audience:** EHS staff, mixed technical and non-technical

**Deck:** `Agentic_AI_Overview_and_Live_Demo.pptx` (23 slides, speaker notes on every slide, built on the SAS EXTERNAL template with Anova fonts embedded, same design language as Session 2).

## What the session covers

| Part | Minutes | Slides |
|---|---|---|
| What is an agent: predict → generate → act, the loop, where agents fit in healthcare | 8 | 3 – 6 |
| The parts you need: the LLM, RAG, MCP, your own models, and one question flowing through all of them | 10 | 7 – 12 |
| Live demo: the Population Health Agent (scenario, solution overview, demo plan, backup walk-through, the rules) | 18 | 13 – 18 |
| Now you build one: the five build steps and the component table | 4 | 19 – 21 |
| Takeaways, questions | 5 | 22 – 23 |

The demo agent and the agent the participants build are the same agent: the synthetic EHS diabetes registry
(`bootcamp/data/`), the four NHA guideline PDFs (`bootcamp/documents/`), the deterioration model, and the
Bootcamp MCP tools. The five demo questions and their expected answers come from
`bootcamp/agents/population_health_agent.md` (questions 1, 2, 11, 15 and 18; question 20 is the optional
policy what-if).

## Slide outline

| # | Slide | Layout |
|---|---|---|
| 1 | Title | SAS – Title |
| 2 | In the next 45 minutes (agenda + outcomes) | content |
| 3 | Section: What is Agentic AI? | SAS – Section |
| 4 | Predict, generate, act (three generations of AI) | cards |
| 5 | What makes it an agent (the loop) | diagram |
| 6 | Where agents fit in healthcare (six patterns; skippable) | grid |
| 7 | Section: The building blocks | SAS – Section |
| 8 | The LLM is only the middle (map of the four parts) | diagram |
| 9 | Why the LLM alone is not enough | two cards |
| 10 | RAG in one picture (build-time and question-time rows) | flow |
| 11 | MCP: how the agent reaches your systems (agent → MCP server → tools) | diagram |
| 12 | One question, four engines (composite AI) | flow |
| 13 | Section: Live demo | SAS – Section |
| 14 | The scenario: diabetes across five emirates (data, documents, model, headline numbers) | cards + stats |
| 15 | Solution overview (unstructured + structured data, agent, MCP server, tools, CAS table) | diagram |
| 16 | The demo: five questions (what is asked, what happens underneath, what to watch for) | table |
| 17 | One answer, step by step (question 4 in six beats; the backup if the live demo fails) | flow |
| 18 | The rules it was playing by | grid |
| 19 | Section: Now you build one | SAS – Section |
| 20 | Five steps to your own agent | steps |
| 21 | The agent on one page (component table; skippable) | table |
| 22 | Takeaways + Up next | blue |
| 23 | Thank you | SAS – Closing |

## Before the session

Sign in to SAS Retrieval Agent Manager, open the Population Health Agent, run question 1 once so the compute
session is warm, and keep the app's SAS RAM tab open on the second screen for the trace. The timing guide and
the fallback plan are in the speaker notes of slide 1.

## Rebuilding the deck

The deck is generated from `build/build_overview_demo.py` (python-pptx) on top of
`../../templates/SAS_External_Template.pptx`, with the same helpers and palette as the Session 2 build.

```bash
pip install python-pptx lxml
cd Day1/Agentic_AI_Overview_and_Live_Demo/build
python3 build_overview_demo.py        # writes ../Agentic_AI_Overview_and_Live_Demo.pptx
```

* `build/icons/` – line icons (Lucide, via react-icons) pre-rendered as PNG in white / blue / navy / slate.
  Regenerate with `node icons.js` (needs `react-icons`, `react`, `react-dom`, `sharp`); the folder keeps
  only the icons the deck uses.
* `build/arc.json` – the light-grey arc band traced from the reference deck (same file as Session 2).
* Environment overrides: `SAS_TEMPLATE=<path>` and `DEMO_OUT=<path>`.

Edit the text directly in PowerPoint for small changes; edit the script and rebuild for structural ones.
