# Agentic AI Hackathon — SAS × EHS

Material and the demo application for the two-day Agentic AI Hackathon delivered with Emirates
Health Services (facilitators: EHS, BITS Pilani, SAS).

| Path | What it is |
|---|---|
| `backend/`, `frontend/`, `Dockerfile` | **The hackathon app**: the participants' workbench for the two days. The three environment links, the registry dashboard, the raw data and guideline documents, a working population-health assistant (Basira) to learn from, and a **SAS RAM** page that signs in to the participants' own Retrieval Agent Manager environment. Details below. |
| `bootcamp/` | **The hackathon kit**: the flow, the pre-built Design Thinking Agent (prompt + config), the Population Health Agent template and test questions, the CAS-ready registry CSVs with a data dictionary, the NHA guideline PDFs for the RAM collection, and the SAS Viya MCP tool selection for each agent. |
| `bootcamp_mcp/` | **The Bootcamp MCP server**: a pip-installable, containerised MCP server built on the SAS Viya MCP server, with eight tools scoped by `ALLOWED_TABLES` / `ALLOWED_MODELS` so each team's agent sees only its own table and model. Registered in RAM once per team. |
| `Day1/Session2_How_an_AI_Agent_Works/` | Session 2 deck (10:45 – 11:30): *How an AI agent works and makes decisions*. Speaker notes and the build script included. |
| `Day1/Agentic_AI_Overview_and_Live_Demo/` | 45-minute deck: *Agentic AI in action*, an overview of Agentic AI, RAG, MCP and composite AI followed by the live demo of the Population Health Agent and the bridge to the hands-on build. Speaker notes and the build script included. |
| `templates/SAS_External_Template.pptx` | Clean SAS EXTERNAL PowerPoint template (SAS-2023 palette, Anova fonts embedded). Base for every SAS-delivered session. |

---

## Teams and environments

The hackathon runs on a handful of SAS environments, one Viya and one RAM each, listed in
`backend/data/environments.json` (URLs only, nothing secret). Ten teams are spread over them in
order and wrap around: with four environments team 5 is on environment 1 again, so some
environments carry two teams. Add a row when a new environment is ready.

When that file has rows the app opens with a team sign-in that cannot be skipped: username `team3`,
password `TEAM_PASSWORD` (one shared password for every team; `TEAM3_PASSWORD` overrides one team,
`TEAM3_ENV` pins a team to an environment, `TEAM_COUNT` changes the number of teams from 10). The
sign-in is a cookie, so a refresh does not ask again; the team chip in the header switches team. From
then on the home page shows the team's RAM and Viya buttons. The Viya and RAM usernames and passwords
are deliberately not shown in the app, so no browser offers to save or flag them; they go on a slide.
The **Hackathon Agent** tab talks to that team's RAM, and RAM sign-ins are kept per browser per team.

An empty environments file means one environment for everyone, from `VIYA_URL`, `RAM_URL` and
`RAM_API_URL`, and no team sign-in. `ENVIRONMENTS_JSON` (the same list as one string) overrides
the file without a commit.

## The hackathon app

Participants build a population-health agent on SAS Retrieval Agent Manager (RAM) over two days.
This app replaces the slides-only approach: it carries the use case they build, the data and
documents they load, a finished agent to learn from, and a page connected to their own RAM
environment to test what they built. Under the hood it is an agentic assistant (Basira) on a
synthetic health information exchange modelled on the EHS diabetes registry across the Northern
Emirates: a supervisor and five specialist agents on a function-calling model, grounded retrieval
with page-level citations over a clinical guideline corpus, trained ML models, a human-in-the-loop
approval queue, an audit trail and a population-health MCP server.

All patient data is synthetic: 4,000 people living with diabetes across 18 EHS hospitals and
primary healthcare centres in Sharjah, Ajman, Umm Al Quwain, Ras Al Khaimah and Fujairah, with
36 months of coded longitudinal records and a FHIR R4 export sample. The guideline corpus is the
hackathon's synthetic "National Health Authority" set (NHA-CG-01 diabetes, NHA-CG-02 lipids,
NHA-CG-03 hypertension, NHA-PP-01 screening and recall). Not for clinical use.

### The pages

| Tab | What it shows |
|---|---|
| Example 2 | A **bowel cancer screening check**: a person enters age, sex, height and weight, smoking, family history, their own history, last screening, symptoms and where they live, and gets a risk tier (the published APCS score), the pathway that fits under the UAE national programme (FIT or colonoscopy, how often, or the urgent route when there are symptoms), the three nearest EHS facilities with distances on a map, and what they could change. Rules in `backend/services/crc.py`, educational prototype, says so on the page. |
| Home | The **three environment buttons** (SAS Viya, SAS RAM, hackathon materials; each opens in a new tab; URLs come from `VIYA_URL`, `RAM_URL`, `MATERIALS_URL`, greyed out until set) and the live registry summary |
| Dashboards | Three dashboards behind one tab, switched with a second row of pills. **Registry**: the population overview (KPIs, HbA1c trend, demand forecast, facility benchmark, risk tiers, complications). **Geography**: the 18 EHS facilities on a map of the Northern Emirates, coloured by control, gaps, risk or cost, with the flagged ones ranked. **Simulator**: the factors that change a patient's deterioration risk, on five anonymous profiles (no patient records): move a factor, the deployed model re-scores it, the attribution shows what moved, the assistant explains the change |
| Data · Documents | The raw registry tables (browse, search) and the NHA guideline PDFs: what participants load into SAS Viya and index in a RAM collection |
| Assistant | Basira, the finished population-health agent: live agent trace, scenario chips, charts, citations, drafts queued for human approval, EN/AR voice |
| **SAS RAM** | Sign in to the participants' own RAM environment at the top of the page, pick the agent they built, and test it: every tool, LLM and retrieval call is shown. Sign-in flows for standalone RAM (Keycloak device code) and full Viya (SASLogon code). One sign-in per browser, kept alive in the background and persisted across restarts. `RAM_MOCK=true` runs it against a mock without a RAM. |

### Quickstart

```bash
# 1) Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.train_models          # trains the 4 models from the committed registry (~30s)
cp .env.example .env                    # add ANTHROPIC_API_KEY for live chat; RAM_API_URL for the SAS RAM page
uvicorn main:app --reload --port 8000

# 2) Frontend (second terminal)
cd frontend
npm install
npm run dev                             # http://localhost:5173 (proxies /api → :8000)
```

**No API key?** Everything still works: the scenario chips run the tools directly on live data; only
free-form chat needs model credentials. The SAS RAM page
runs against an in-memory mock until `RAM_API_URL` is set (`RAM_MOCK=true`).

Regenerate the synthetic registry from scratch (deterministic, seeded): `python -m scripts.generate_hie_data`.

### Configuration (Railway Variables tab, or `backend/.env`)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | The language model behind the assistant (`MODEL` pins an id) |
| `VIYA_URL`, `RAM_URL`, `MATERIALS_URL` | The three buttons on the home page (materials defaults to this repo) |
| `EHS_LOGO_URL`, `SAS_LOGO_URL` | Optional absolute URLs to hosted logos, used in the header instead of the bundled `frontend/public/ehs-logo.png` (top left) and `frontend/src/assets/sas-logo.png` (top right). Leave unset to get the official transparent logos in the repo |
| `RAM_API_URL` (+ auth) | SAS Retrieval Agent Manager for the SAS RAM page; see `backend/.env.example` for the sign-in options (`RAM_TOKEN`, OAuth client, or interactive sign-in) |
| `RAM_MOCK` | `true` = SAS RAM page on an in-memory mock (default in `.env.example`) |
| `RAM_HIDE_HISTORY` | `true` when several people share one RAM login, so nobody sees another team's conversations (each browser otherwise has its own RAM identity) |
| `RAM_SESSION_FILE` | Where signed-in RAM sessions are kept so a restart does not sign anyone out (default `backend/data/runtime/ram_sessions.json`). On Railway, mount a volume and point this at it to survive redeploys too |
| `RAM_BROWSER_RESTORE` | `false` to stop the browser keeping a copy of its own RAM session; by default it hands the copy back after a redeploy so nobody signs in twice |
| `GEMINI_API_KEY` | Optional: builds the semantic guideline index; otherwise retrieval is BM25 |

### Branding

The header carries the official EHS logo top left (`frontend/public/ehs-logo.png`, cropped with a
transparent background; `ehs-mark.png` is the EHS wordmark alone, used for avatars and watermarks)
and the SAS logo top right (`frontend/src/assets/sas-logo.png`, the navy wordmark on a transparent background, bundled under a hashed URL so caches never serve a stale copy).
`EHS_LOGO_URL` and `SAS_LOGO_URL` can point the header at hosted copies instead. Colours live in the `:root` block of
`frontend/src/index.css`: `--brand` is the EHS blue sampled from the logo (#2B5378), `--gold` the accent.

### Deploy to Railway

Push to GitHub → Railway → **New Project → Deploy from GitHub repo**. The `Dockerfile` builds the
frontend, installs the backend, trains the models at image build time, and serves everything on one
`$PORT`. Set the variables above in the service's Variables tab. Health check: `/api/health`.

### Repo layout

```
backend/
  main.py                FastAPI app (serves API + built frontend)
  routers/               chat (NDJSON streaming) · dashboards · queue/audit/docs/data (evals and simulate stay as APIs)
                         links (the environment buttons) · ram (proxy to SAS Retrieval Agent Manager)
  services/
    hie.py               the registry query engine (single source of truth for chat + dashboards)
    ml.py                model scoring, SHAP drivers, similarity, segments, counterfactual simulator
    rag.py               hybrid retrieval over the guideline PDFs (BM25 + optional embedding cache)
    agent.py             supervisor + specialists (ADK) with NDJSON event streaming
    scenarios.py         direct tool runner for the chips (same services, real numbers, demo-day failover)
    ram_client.py        SAS RAM REST client: auth flows, async query + poll, traces, mock mode
    queue_service.py · audit.py · evals.py · geo.py · whatif.py
  pophealth_mcp/         the population-health MCP server (FastMCP, stdio)
  scripts/               generate_hie_data.py (EHS-flavoured synthetic registry) · train_models.py
  data/hie/              the committed synthetic exchange (8 tables, csv.gz)
  data/guidelines/       the NHA guideline PDFs (RAG corpus)
  data/evals/            golden agent evalset (10 cases)
frontend/                React + Vite + Tailwind + Recharts + MapLibre glass UI
  src/pages/             landing, dashboards (registry, geography, simulator), data, documents, assistant
  src/ram/               the SAS RAM page (RAM chat, sign-in, traces, charts)
```

## Design language (shared by all SAS decks)

Taken from the *SAS Viya Agentic AI Experience* reference presentation:

* Colours: SAS Blue `#0766D1`, Midnight `#032954`, Sky `#4398F9`, Light `#C4DEFD`, Slate `#7E889A`, panel grey `#E4E7EA`, arc grey `#F0F1F3`.
* Fonts: Anova Bold (titles) / Anova Light (body) — theme fonts of the template.
* Content slides: slate 56 pt title, blue subtitle, light-grey arc band, white rounded cards with soft shadows, icon circles overlapping the card top, navy pill headers with blue chevrons.
* Section dividers on slate, title / closing / takeaways on SAS blue.
