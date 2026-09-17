# Agentic AI Bootcamp — SAS × EHS

Material and the demo application for the two-day Agentic AI Bootcamp delivered with Emirates
Health Services (facilitators: EHS, BITS Pilani, SAS).

| Path | What it is |
|---|---|
| `backend/`, `frontend/`, `Dockerfile` | **Basira (بصيرة)**, the bootcamp's population-health intelligence app: an agentic assistant on an EHS-flavoured diabetes registry, plus a **SAS Copilot** page connected to SAS Retrieval Agent Manager. Details below. |
| `Day1/Session2_How_an_AI_Agent_Works/` | Session 2 deck (10:45 – 11:30): *How an AI agent works and makes decisions*. Speaker notes and the build script included. |
| `templates/SAS_External_Template.pptx` | Clean SAS EXTERNAL PowerPoint template (SAS-2023 palette, Anova fonts embedded). Base for every SAS-delivered session. |

---

## Basira: EHS Population Health Intelligence

An agentic AI assistant on top of a synthetic health information exchange modelled on the EHS
diabetes registry across the Northern Emirates: a supervisor and five specialist agents on a
function-calling model, grounded retrieval with page-level citations over a clinical guideline
corpus, four trained ML models with model cards and held-out evaluation, a patient what-if
simulator, a counterfactual programme simulator, a human-in-the-loop approval queue, a full audit
trail, a population-health MCP server, and a SAS Copilot page that talks to SAS Retrieval Agent
Manager (RAM).

All patient data is synthetic: 4,000 people living with diabetes across 18 EHS hospitals and
primary healthcare centres in Sharjah, Ajman, Umm Al Quwain, Ras Al Khaimah and Fujairah, with
36 months of coded longitudinal records and a FHIR R4 export sample. The guideline corpus is the
bootcamp's synthetic "National Health Authority" set (NHA-CG-01 diabetes, NHA-CG-02 lipids,
NHA-CG-03 hypertension, NHA-PP-01 screening and recall). Not for clinical use.

### The pages

| Tab | What it shows |
|---|---|
| Home | The story, the registry summary, and the **three environment buttons**: SAS Viya, SAS RAM, bootcamp materials (each opens in a new tab; URLs come from `VIYA_URL`, `RAM_URL`, `MATERIALS_URL`) |
| Assistant | The multi-agent assistant with a live agent trace, scenario chips, charts, maps, citations, EN/AR voice |
| Dashboards | Registry, clinical quality, deterioration risk, cost and equity, geography (cross-filtered) |
| Simulator | Patient what-if with live re-scoring, attribution and a narrated explanation |
| **SAS Copilot** | The RAM chat page: pick an agent or collection published in SAS Retrieval Agent Manager, ask, and see every tool, LLM and retrieval call. Sign-in flows for standalone RAM (Keycloak device code) and full Viya (SASLogon code). `RAM_MOCK=true` runs it without a RAM. |
| Evaluation | Held-out model metrics, the golden agent evalset, the LLM cost plan, the governance control list |
| Queue · Documents · Data · Audit | Human approvals, the guideline corpus, the HIE browser, the audit trail |

### Quickstart

```bash
# 1) Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m scripts.train_models          # trains the 4 models from the committed registry (~30s)
cp .env.example .env                    # add ANTHROPIC_API_KEY for live chat; RAM_API_URL for the SAS Copilot page
uvicorn main:app --reload --port 8000

# 2) Frontend (second terminal)
cd frontend
npm install
npm run dev                             # http://localhost:5173 (proxies /api → :8000)
```

**No API key?** Everything still works: the scenario chips run the tools directly on live data; only
free-form chat and the simulator's narrated explanation need model credentials. The SAS Copilot page
runs against an in-memory mock until `RAM_API_URL` is set (`RAM_MOCK=true`).

Regenerate the synthetic registry from scratch (deterministic, seeded): `python -m scripts.generate_hie_data`.

### Configuration (Railway Variables tab, or `backend/.env`)

| Variable | Purpose |
|---|---|
| `ANTHROPIC_API_KEY` | The language model behind the assistant and the simulator explanation (`MODEL` pins an id) |
| `VIYA_URL`, `RAM_URL`, `MATERIALS_URL` | The three buttons on the home page (materials defaults to this repo) |
| `EHS_LOGO_URL` | Optional absolute URL to the official EHS logo, used in the header instead of `frontend/public/ehs-logo.svg` |
| `RAM_API_URL` (+ auth) | SAS Retrieval Agent Manager for the SAS Copilot page; see `backend/.env.example` for the sign-in options (`RAM_TOKEN`, OAuth client, or interactive sign-in) |
| `RAM_MOCK` | `true` = SAS Copilot page on an in-memory mock (default in `.env.example`) |
| `RAM_HIDE_HISTORY` | `true` when teams share one RAM identity, so nobody sees another team's conversations |
| `GEMINI_API_KEY` | Optional: builds the semantic guideline index; otherwise retrieval is BM25 |

### Branding

The header uses `frontend/public/ehs-logo.svg` (a placeholder lockup) and `frontend/public/sas-logo.png`.
Drop the official EHS logo in as `frontend/public/ehs-logo.svg` (or `.png`, and update the two `<img>`
tags in `App.jsx`), or point `EHS_LOGO_URL` at a hosted copy. Colours live in the `:root` block of
`frontend/src/index.css` (`--brand` teal-green, `--gold`, `--sas-blue`).

### Deploy to Railway

Push to GitHub → Railway → **New Project → Deploy from GitHub repo**. The `Dockerfile` builds the
frontend, installs the backend, trains the models at image build time, and serves everything on one
`$PORT`. Set the variables above in the service's Variables tab. Health check: `/api/health`.

### Repo layout

```
backend/
  main.py                FastAPI app (serves API + built frontend)
  routers/               chat (NDJSON streaming) · dashboards · evals · simulate · queue/audit/docs/data
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
  src/pages/             landing, assistant, dashboards, simulator, evaluation, queue, documents, data, audit
  src/ram/               the SAS Copilot page (RAM chat, sign-in, traces, charts)
```

## Design language (shared by all SAS decks)

Taken from the *SAS Viya Agentic AI Experience* reference presentation:

* Colours: SAS Blue `#0766D1`, Midnight `#032954`, Sky `#4398F9`, Light `#C4DEFD`, Slate `#7E889A`, panel grey `#E4E7EA`, arc grey `#F0F1F3`.
* Fonts: Anova Bold (titles) / Anova Light (body) — theme fonts of the template.
* Content slides: slate 56 pt title, blue subtitle, light-grey arc band, white rounded cards with soft shadows, icon circles overlapping the card top, navy pill headers with blue chevrons.
* Section dividers on slate, title / closing / takeaways on SAS blue.
