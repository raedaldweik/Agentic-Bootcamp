# Sanad AI — standalone chat on SAS Retrieval Agent Manager

The RAM chat experience on its own, in the Sanad (a Mubadala company) brand: deep navy
surfaces, Sanad primary blue, a cyan "evolution" glow and the geometric **S** mark. Nothing else from the hackathon app is included — this folder is a complete
frontend by itself.

<p align="center"><img src="public/sanad-logo.svg" alt="Sanad" height="56" /></p>

## What is in it

| Piece | Where |
|---|---|
| Welcome screen: turning turbine, headline, four suggested prompts | `src/components/MessageList.jsx` (Hero) |
| Conversation rail: brand lockup, new conversation, history, connection card, collapses to a 74 px strip | `src/components/Sidebar.jsx` |
| Top bar: conversation title, showcase badge, agent / collection picker | `src/components/TopBar.jsx`, `TargetSelector.jsx` |
| Messages, live activity timeline while the agent works (retrieval → tools → model) | `src/components/MessageList.jsx` |
| Answer card: markdown, interactive SVG charts (bar, line, area, pie/donut, scatter), VA report snapshots, source chips, tool-call trace, copy, usage | `src/components/ResponseCard.jsx`, `ChartCard.jsx`, `ReportCard.jsx`, `ToolCallTrace.jsx` |
| Flight recorder: every tool, retrieval and LLM call behind an answer, with inputs and outputs | `src/components/QueryDetails.jsx` |
| Composer: attach a document, dictate, send; scan line while running; `/` focuses it | `src/components/Composer.jsx`, `VoiceInput.jsx` |
| Sign-in for RAM deployments that need it (Keycloak device code, Viya SASLogon code) | `src/components/SignIn.jsx` |
| Every colour, radius, shadow and font as a token | `src/styles/theme.css` (`:root`) |
| Every UI string in one place | `src/lib/strings.js` |

The backend contract is unchanged: the same `/api/ram/*` endpoints the hackathon app uses
(`backend/routers/ram.py`), so anything that works on the hackathon's RAM page works here.

## Run it

```bash
cd sanad-chat
npm install
npm run dev            # http://localhost:5174
```

**Nothing else running?** The app notices that no backend answers `/api/ram/health` and switches
to **Showcase mode**: an in-browser stand-in for RAM with three Sanad-flavoured agents, two
collections, scripted answers with charts, sources and a trace that fills in step by step. Every
figure is synthetic and every answer says so. The status card bottom-left shows the mode.
`VITE_DEMO=true npm run dev` forces it even when a backend is up.

**Against the real backend:** start it as in the root README (`uvicorn main:app --port 8000` in
`backend/`); the dev server proxies `/api` to it. `RAM_MOCK=true` on the backend gives the
backend's own mock; `RAM_API_URL` (+ auth) points it at a live SAS Retrieval Agent Manager.

## Deploy it

`Dockerfile.sanad` at the repo root builds this folder and serves it from the same FastAPI
backend (it sets `FRONTEND_DIST=/app/sanad-chat/dist`). On Railway, create a second service
from the same repo and set its Dockerfile path to `Dockerfile.sanad`; the environment variables
are the same as the hackathon service.

## Brand assets

`public/sanad-mark.svg` (the S, used as favicon) and `public/sanad-logo.svg` (mark + wordmark)
are built-in renderings of the Sanad mark — a geometric uppercase S made of two structured forms
that overlap through the middle band, the overlap in a lighter tone — not the official files. To use the official artwork:

1. Drop the official files over `public/sanad-mark.svg` and `public/sanad-logo.svg`.
2. Set `VITE_LOGO_URL=/sanad-logo.svg` so the rail shows the official lockup instead of the
   built-in mark + wordmark (`src/components/Logo.jsx`).
3. Put the official hex values into the `:root` block of `src/styles/theme.css`
   (`--sanad`, `--sanad-hi`, `--sanad-lo`, `--cyan`, `--sky`).

Fonts: Sora (display), Inter (body), JetBrains Mono (code), loaded from Google Fonts in `index.html`.
