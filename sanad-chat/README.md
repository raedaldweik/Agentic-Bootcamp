# Sanad AI — standalone chat on SAS Retrieval Agent Manager

The Agentic AI Hackathon's chatbot (the **Hackathon Agent** tab, `frontend/src/ram/`) on its own,
in the Sanad (a Mubadala company) brand. Same warm-pearl glass design, same layout and the same
features; the EHS logo is replaced by the Sanad mark and wordmark, the SAS logo is removed, and
the brand blue is Sanad's. English only. Nothing else from the hackathon app is included.

## What is in it

| Piece | Where |
|---|---|
| Header: Sanad lockup top left, eyebrow, title, accent line (no partner logo) | `src/App.jsx`, `src/ram/Logo.jsx` |
| The chat page: recent conversations, agent / collection dropdown, connection status and sign-in, messages with the live agent activity, attach, voice, send | `src/ram/RamPage.jsx` |
| Answer card: markdown, interactive SVG charts, VA report snapshots, source chips, tool-call trace, usage, the details popup | `src/ram/ResponseCard.jsx`, `ChartCard.jsx`, `ReportCard.jsx`, `ToolCallTrace.jsx`, `QueryDetails.jsx`, `SourceViewer.jsx` |
| Sign-in for RAM deployments that need it (Keycloak device code, Viya SASLogon code) | `src/ram/SignIn.jsx` |
| The hackathon glass stylesheet with the Sanad tokens | `src/index.css` (`:root`) |
| Every UI string, and the suggestion chips | `src/lib/strings.js` |

The backend contract is unchanged: the same `/api/ram/*` endpoints as the hackathon app
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
figure is synthetic and every answer says so. The status pill in the chat card shows the mode.
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

`public/sanad-mark.svg` (the S, also the favicon) and `public/sanad-logo.svg` (mark + wordmark)
are built-in renderings of the Sanad mark — a geometric uppercase S made of two structured forms
that overlap through the middle band — not the official files. To use the official artwork:

1. Drop the official files over `public/sanad-mark.svg` and `public/sanad-logo.svg`.
2. Set `VITE_LOGO_URL=/sanad-logo.svg` so the header shows the official lockup instead of the
   built-in mark + wordmark (`src/ram/Logo.jsx`).
3. Put the official hex values into the `:root` block of `src/index.css` (`--brand`,
   `--brand-hi`, `--brand-lo`, `--brand-grad`).
