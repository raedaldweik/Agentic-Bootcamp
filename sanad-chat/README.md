# Sanad AI — standalone chat on SAS Retrieval Agent Manager

The Agentic AI Hackathon's chatbot (the **Hackathon Agent** tab, `frontend/src/ram/`) on its own,
in the Sanad (a Mubadala company) brand. Same glass design, same layout and the same features;
the EHS logo is replaced by the official Sanad logo, the SAS logo is removed, and the colours are
Sanad's. English only. Nothing else from the hackathon app is included.

## What is in it

| Piece | Where |
|---|---|
| Header: Sanad lockup top left, eyebrow, title, accent line (no partner logo) | `src/App.jsx`, `src/ram/Logo.jsx` |
| The chat page: recent conversations, agent / collection dropdown, connection status and sign-in, messages with the live agent activity, attach, voice, send | `src/ram/RamPage.jsx` |
| Answer card: markdown, interactive SVG charts, VA report snapshots, source chips, tool-call trace, usage, the details popup | `src/ram/ResponseCard.jsx`, `ChartCard.jsx`, `ReportCard.jsx`, `ToolCallTrace.jsx`, `QueryDetails.jsx`, `SourceViewer.jsx` |
| Sign-in for RAM deployments that need it (Keycloak device code, Viya SASLogon code) | `src/ram/SignIn.jsx` |
| The hackathon glass stylesheet in the Sanad palette | `src/index.css` (`:root`) |
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

## Brand

The official logo is `public/brand/SANAD_M_E_RGB_TRIANGLE.svg`, kept as issued (mark, wordmark and
"A Mubadala Company" on Sanad's white corner triangle).

| File | What it is |
|---|---|
| `public/sanad-logo.svg` | The official artwork with the corner triangle removed and cropped to the lockup, in navy for light backgrounds |
| `public/sanad-logo-white.svg` | The same artwork in white, for the dark frame. The header shows it top left |
| `public/sanad-mark.svg` | The favicon: the official S in white facets on Sanad's deep indigo, as on the dark version of the mark |
| `src/ram/Logo.jsx` | The official S geometry as a component, navy on light (avatars, watermark, sign-in) or white on dark |

`VITE_LOGO_URL` points the header at a hosted copy instead of `public/sanad-logo-white.svg`.

The page and header are dark: the hackathon's glass recipe (gradients, lit edges, soft bokeh) on
the petrol navy of Sanad's event livery (the MRO Asia Pacific 2026 artwork), lit with the sky of
its window view. The chat itself is light so it reads easily: the conversation list, the chat card,
bubbles, input and menus are pale frosted glass with a soft sky gradient and dark navy ink.

Page and header tokens live in the `:root` block of `src/index.css`:

| Token | Colour | Use |
|---|---|---|
| `--frame` | `#051E2E` | the page: petrol navy, a sky glow from the top and a sea-teal glow below |
| `--sky`, `--sky-lt` | `#5F93C4`, `#9DC5E0` | the header eyebrow and accent line, background glow |
| `--sea` | `#226984` | background glow and bokeh |

The chat area's tokens are scoped to `.ram-page .ram-chat` at the end of the same file:

| Token | Colour | Use |
|---|---|---|
| `--panel-top`, `--panel-bottom` | pale sky glass | the conversation list and chat cards |
| `--brand`, `--brand-hi`, `--brand-lo` | `#2F6FA8`, `#1D5A93`, `#0B2F55` | steel-blue accents and accent text |
| `--teal` | `#5A5772` | trace panels: the slate violet of the official mark |
| `--text` … `--text-faint` | `#0B1433` … `#8193A8` | dark navy ink |

The official navy `#071D49` is kept in `public/sanad-logo.svg` and in the mark component's
`tone="navy"`, for use on light backgrounds.

There is no "Connected" indicator: the chat card shows a status message only when something is
wrong (backend offline, not configured), and the Sign in button when the deployment needs one.
