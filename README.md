# Composite AI in Health Care — SAS

The demonstration application for a session on **Composite AI**: how predictive machine learning,
deterministic business rules and generative AI agents work together in one governed workflow, with
deterministic controls and human-in-the-loop checkpoints keeping the outcome reliable. Two worked
examples, both on synthetic data: **population health** (a diabetes registry) and **colorectal cancer
screening** (a screening programme). A third page signs in to SAS Retrieval Agent Manager (RAM), where
such an agent is built and run on SAS Viya.

| Path | What it is |
|---|---|
| `backend/`, `frontend/`, `Dockerfile` | **The app**: the two stories and the SAS RAM page. Details below. |
| `kit/` | **The agent kit** for building the population-health agent on SAS RAM: the agent prompts, the CAS-ready registry CSVs with a data dictionary, the guideline PDFs for the RAM collection, the SAS Viya MCP tool selection, and the Viya scripts. |
| `scoped_mcp/` | **The scoped MCP server**: a pip-installable, containerised MCP server built on the SAS Viya MCP server, with eight tools scoped by `ALLOWED_TABLES` / `ALLOWED_MODELS`, so an agent sees only its own table and model. Registered in RAM once per agent. |
| `decks/How_an_AI_Agent_Works/` | Session deck: *How an AI agent works and makes decisions*. Speaker notes and the build script included. |
| `decks/RWE_in_Action_with_Agentic_AI/` | 45-minute session deck: *Real-World Evidence in Action with Agentic AI (SAS)*. The evidence, then the two live examples from this app. Speaker notes, sources and the build script included. |
| `templates/SAS_External_Template.pptx` | Clean SAS EXTERNAL PowerPoint template (SAS-2023 palette, Anova fonts embedded). |

---

## The app

Four places to be: **Home**, **Population health**, **Cancer screening** and **SAS RAM**. Each example opens a second row
of pills with the same shape: the dashboards, the data, the documents, the model, and a finished agent.

| Tab | What it shows |
|---|---|
| Home | The composite-AI story: how a decision is made here (predict, validate, reason, act, approve), the two stories with live numbers and their chapters, and the SAS RAM and SAS Viya buttons (from `RAM_URL`, `VIYA_URL`; greyed out until set) |
| **Population health** | **Registry**: the diabetes population (KPIs, HbA1c trend, demand forecast, facility benchmark, risk tiers, complications), with a cross-filter on every panel. **Geography**: the 18 facilities on a map of the Northern Emirates. **Simulator**: the factors that change a patient's deterioration risk, on anonymous profiles, re-scored live by the deployed model. **Data**: the 8 HIE tables. **Documents**: the guideline corpus. **Example agent**: Basira, a supervisor and five specialists on a function-calling model, grounded retrieval with page citations, drafts queued for human approval, audit trail. |
| **Cancer screening** | **Programme**: the screening population at programme level (eligible, up to date, due, invitations, 90-day completion, FIT positivity), trends, facility benchmark, the model's outreach bands, equity, the funnel from invitation to finding, and the facility map, with a cross-filter. **Screening check**: one person enters a few facts and gets a risk tier (the published APCS score), the pathway under the national programme, and the nearest facilities on a map; an assistant answers questions with policy citations. **Model**: the non-completion model on anonymous profiles, re-scored live, with attribution, a narrated explanation and the model card. **Rules**: the 13-rule policy catalogue and a live trace of which rule decided for a chosen person. **Data**: the programme's five tables. **Documents**: the screening pathway and recall policy. **Example agent**: the composite agent, with the navigator worklist, the approval queue and the audit trail beside it. |
| **SAS RAM** | Sign in to a RAM environment, pick an agent published there, and test it: every tool, LLM and retrieval call is shown. Sign-in flows for standalone RAM (Keycloak device code) and full Viya (SASLogon code). `RAM_MOCK=true` runs it against a mock without a RAM. |

All data is synthetic. Population health: 4,000 people living with diabetes across 18 hospitals and primary
healthcare centres in Sharjah, Ajman, Umm Al Quwain, Ras Al Khaimah and Fujairah, 36 months of coded
records. Cancer screening: 12,000 residents aged 36 to 85 of the same emirates, 36 months of invitations, FIT
tests and colonoscopies. The guideline corpus is a synthetic "National Health Authority" set (NHA-CG-01
diabetes, NHA-CG-02 lipids, NHA-CG-03 hypertension, NHA-PP-01 screening and recall, NHA-CS-01 colorectal
screening pathway). Not for clinical use.

### Cancer screening, composite AI end to end

Each kind of intelligence does the one job it is good at, and the app shows the seams:

| Layer | What it decides | Where |
|---|---|---|
| **Deterministic rules** | Eligibility, the test, the interval, the urgent route. Thirteen rules implementing NHA-CS-01, evaluated in order; the first pathway rule that fires decides. The agent cannot overrule them. | `backend/services/crc.py` (`RULES`, `assess()` returns a `rule_trace`), the **Rules** tab |
| **Predictive model** | The chance that an invitation is *not* acted on within 90 days (XGBoost, monotonic constraints, held-out AUC on the model card). It feeds exactly one rule: outreach intensity (§8.3: app, SMS, navigator call, call plus booking help). Never eligibility, never the test. | `backend/services/crc_ml.py`, trained by `scripts/train_models.py`, the **Model** tab |
| **Grounded retrieval** | The policy passages the answers cite, with page numbers, from the screening documents only. | `backend/services/rag.py`, `crc.retrieve()`, the **Documents** tab |
| **Generative agent** | Reasons across the tools and writes the message to the person. Scenario chips are deterministic executors that call the same services and stream the same events, so the demo works with no model credentials; free-form chat is a function-calling loop with seven tools when Anthropic credentials are present. | `backend/services/crc_agent.py`, the **Example agent** tab |
| **Deterministic guardrail** | Every drafted message is checked against §9.2: it must name the decided test and the facility, and may not contain a date, a time, a price, a phone number, a waiting time or a statement about the person's likelihood of cancer. Two failures and the programme template is used instead. | `crc_agent.validate_message()` |
| **Human in the loop** | Nothing is sent. Every draft and referral lands in the approval queue; a person approves or rejects it there, and the decision is on the audit trail with every rule outcome, model score and what-if. | `queue_service.py`, `audit.py`, the right rail of the **Example agent** tab |

The five chips tell the story in order: **S1** the morning outreach batch (rules confirm who is due,
the model sets the channel, the validator passes the drafts, one batch item queued); **S2** one person end
to end (the rule trace, the drivers, the message, the guardrail result); **S3** symptoms reported in the
app (rule R1 overrides everything and the model is not consulted); **S4** positive FITs with no colonoscopy
(the §6.3 safety net, with an endoscopy capacity check); **S5** where uptake is lowest (the map and the
equity view). Clicking a person on the worklist runs S2 for them.

### Quickstart

```bash
# 1) Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.train_models          # trains the 5 models from the committed data (~1 min)
cp .env.example .env                    # add ANTHROPIC_API_KEY for live chat; RAM_API_URL for the SAS RAM page
uvicorn main:app --reload --port 8000

# 2) Frontend (second terminal)
cd frontend
npm install
npm run dev                             # http://localhost:5173 (proxies /api → :8000)
```

**No API key?** Everything still works: the scenario chips in both examples run the tools directly on
live data; only free-form chat and the narrated explanations need model credentials. The SAS RAM page
runs against an in-memory mock until `RAM_API_URL` is set (`RAM_MOCK=true`).

Regenerate the synthetic data from scratch (deterministic, seeded): `python -m scripts.generate_hie_data`
(Population health) and `python -m scripts.generate_screening_data` (Cancer screening). `python -m scripts.make_crc_guideline`
rewrites the NHA-CS-01 PDF.

### Configuration (Railway Variables tab, or `backend/.env`)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | The language model behind the agents (`MODEL` pins an id). Free-form chat in Cancer screening needs an Anthropic key specifically |
| `VIYA_URL`, `RAM_URL` | The two environment buttons on the home page. `ENV1_VIYA_URL` / `ENV1_RAM_URL` stand in when these are empty |
| `LOGO_URL` | Optional absolute URL to a hosted logo, used top left instead of the bundled SAS logo (`frontend/src/assets/sas-logo.png`) |
| `RAM_API_URL` (+ auth) | SAS Retrieval Agent Manager for the SAS RAM page; see `backend/.env.example` for the sign-in options |
| `RAM_MOCK` | `true` = SAS RAM page on an in-memory mock (default in `.env.example`) |
| `RAM_HIDE_HISTORY`, `RAM_SESSION_FILE`, `RAM_BROWSER_RESTORE` | Shared-login and session-persistence options for the RAM page, as before |
| `TEAMS_ENABLED`, `TEAM_PASSWORD`, `ENV2_…` | Optional workshop mode: several environments with a team sign-in (see below). Off by default |
| `GEMINI_API_KEY` | Optional: builds the semantic guideline index; otherwise retrieval is BM25 |

### Teams and environments (optional)

The app runs one environment with no sign-in: `VIYA_URL` and `RAM_URL`, or `ENV1_VIYA_URL` and
`ENV1_RAM_URL`, which stand in for them. For a workshop with several SAS environments, set
`TEAMS_ENABLED=true`, number the environments (`ENV1_…`, `ENV2_…`) and set `TEAM_PASSWORD`: the app then
opens with a team sign-in (`team3` / `TEAM_PASSWORD`; `TEAM_COUNT`, `TEAM3_PASSWORD`, `TEAM3_ENV` adjust it),
teams are spread over the environments in order, and the SAS RAM tab talks to that team's RAM.

### Branding

The header carries the SAS logo top left (`frontend/src/assets/sas-logo.png`, bundled under a hashed URL so
caches never serve a stale copy; `frontend/public/sas-logo.png` is the same file for the favicon, avatars
and watermarks). `LOGO_URL` can point the header at a hosted copy instead. Colours live in the `:root`
block of `frontend/src/index.css`.

### Deploy to Railway

Push to GitHub → Railway → **New Project → Deploy from GitHub repo**. The `Dockerfile` builds the
frontend, installs the backend, trains the models at image build time, and serves everything on one
`$PORT`. Set the variables above in the service's Variables tab. Health check: `/api/health`.

### Repo layout

```
backend/
  main.py                FastAPI app (serves API + built frontend)
  routers/               chat · dashboards · queue/audit/docs/data · simulate · evals · links · ram · teams
                         screening (Cancer screening: check, rules, programme, model, agent, queue and audit views)
  services/
    hie.py               the registry query engine (Population health)
    ml.py                model scoring, SHAP drivers, similarity, segments, counterfactual simulator
    rag.py               hybrid retrieval over the guideline PDFs (BM25 + optional embedding cache)
    agent.py             the population-health story's supervisor + specialists (ADK) with NDJSON event streaming
    scenarios.py         the population-health story's direct tool runner for the chips
    crc.py               the cancer-screening story's deterministic rules: APCS score, pathway, rule trace, the screening assistant
    crc_ml.py            the cancer-screening story's non-completion model: features, scoring, profiles, what-if, explanation
    crc_agent.py         the cancer-screening story's composite agent: scenario chips, validator, templates, the tool loop
    screening.py         the cancer-screening story's programme data: dashboard, map, worklists, one person, tables
    ram_client.py        SAS RAM REST client: auth flows, async query + poll, traces, mock mode
    queue_service.py · audit.py · evals.py · geo.py · whatif.py · teams.py
  pophealth_mcp/         the population-health MCP server (FastMCP, stdio)
  scripts/               generate_hie_data.py · generate_screening_data.py · make_crc_guideline.py · train_models.py
  data/hie/              the committed synthetic exchange (8 tables, csv.gz)
  data/screening/        the committed synthetic screening programme (5 tables, csv.gz)
  data/guidelines/       the NHA documents (RAG corpus)
  data/evals/            golden agent evalset (10 cases)
frontend/                React + Vite + Tailwind + Recharts + MapLibre glass UI
  src/pages/             landing · Population health (dashboards, simulator, data, documents, assistant)
                         Cancer screening (ScreeningProgrammePage, ScreeningPage, ScreeningModelPage, ScreeningRulesPage, ScreeningAgentPage)
  src/ram/               the SAS RAM page (RAM chat, sign-in, traces, charts)
```

## Design language (shared by all SAS decks)

Taken from the *SAS Viya Agentic AI Experience* reference presentation:

* Colours: SAS Blue `#0766D1`, Midnight `#032954`, Sky `#4398F9`, Light `#C4DEFD`, Slate `#7E889A`, panel grey `#E4E7EA`, arc grey `#F0F1F3`.
* Fonts: Anova Bold (titles) / Anova Light (body) — theme fonts of the template.
* Content slides: slate 56 pt title, blue subtitle, light-grey arc band, white rounded cards with soft shadows, icon circles overlapping the card top, navy pill headers with blue chevrons.
* Section dividers on slate, title / closing / takeaways on SAS blue.
