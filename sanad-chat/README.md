# Sanad MRO Intelligence Hub

The Sanad chat (the Agentic AI Hackathon chatbot design, in the Sanad brand) with a working
assistant behind it: the **Sanad Digital Assistant** for the engine shop. It answers questions
about engine status, delivery risk, recovery options, job cards, tools, inspection findings and
approvals from shop data and approved documents, for three roles, by typing or by voice.

It is not a script. Every answer is worked out from the data at the moment it is asked, so
questions outside the demonstration storyline work too. The data itself is synthetic.

## What it does

| | |
|---|---|
| **Three roles** | Engine Shop Manager, Technician, Supervisor, chosen from the "Asking as" dropdown. The role sets the suggested questions and what the assistant may do on that person's behalf. |
| **Shop time** | A demonstration clock with six moments of the story (the delivery slips, the recovery is approved, the tool arrives, the finding is recorded, the plan is reassessed) and any other time between 27 Oct 16:00 and 30 Oct 12:00, the period the records cover. The data is shown as it stood at that time, so the same question changes its answer through the day. |
| **Visual answers** | A short answer plus a card: status tables, the critical path, option comparisons, readiness checklists, tool custody, job card steps, and a blade inspection view with each zone against its limit. Charts on request. |
| **Next questions** | Two or three one-tap follow-ups docked above the input after every answer. |
| **Voice** | Tap the microphone and speak. Words appear as they are heard, shop ids are tidied ("t one one seven" becomes T-117), and the question sends itself after a short pause that can be cancelled. "Read aloud" speaks the answers. Chrome, Edge and Safari. |
| **Actions, with limits** | The assistant can raise a tool handover request, draft a finding, route a deviation evidence package, submit a recovery option and confirm job card steps. Each creates a *pending* record in the Notebook. It cannot approve, certify, accept or release anything, and the role rules are enforced in code. |
| **Grounding** | Each answer lists the documents it rests on, and the details panel shows every lookup, model call and timing. |
| **Any question** | Beyond the standard views the assistant can query the shop tables (read-only SQL), search the documents, and run what-if schedules. |

## How it stays fast

1. A small router recognises the common questions and fetches the matching view in a few
   milliseconds, before the model is called. The card is on screen in under half a second.
2. The model receives that view with the question, so most answers take **one** model call.
3. The answer streams as it is written, and answers are short by instruction: the card carries
   the table, the text says what it means.
4. The instructions, data schema and tool definitions never change between questions, so they
   are served from the prompt cache.
5. If the model is slow, rate limited or down, the question is answered straight from the shop
   data and the answer says so. After repeated failures the model is skipped for 30 seconds so
   nobody waits on a timeout.
6. A dropped connection while an answer is on its way is ridden out for about 25 seconds, and a
   server that is restarting shows "The assistant can't be reached" and reconnects by itself.

Without a model key the standard questions still work (answered in milliseconds from the data);
free-form questions, what-ifs and actions need the key.

## Run it

```bash
# backend (Python 3.11 or later; tested on 3.13)
cd backend
pip install -r requirements-sanad.txt
export ANTHROPIC_API_KEY=...            # optional for a first look, needed for free-form questions
uvicorn sanad_app:app --port 8000

# chat, in another terminal
cd sanad-chat
npm install
npm run dev                             # http://localhost:5174, proxies /api to :8000
```

`npm run build` writes `sanad-chat/dist`, which `sanad_app` serves itself, so in production
there is one process and one port.

## Settings

All are environment variables on the backend. Only the first matters to start.

| Variable | Default | What it does |
|---|---|---|
| `ANTHROPIC_API_KEY` | none | The model key, from the Claude Console (it starts with `sk-ant-api`). Without it only the standard questions are answered. If the key is rejected, the chat shows "Model unavailable": tap it, or open `/api/assistant/health`, to see what the API replied and what kind of key is configured. The key itself is never shown. |
| `SANAD_MODEL` | `claude-opus-5-5` | The model. A smaller model such as `claude-haiku-5-5` answers sooner at some cost in judgement on unusual questions. |
| `SANAD_EFFORT` | `low` | How much the model deliberates: `low`, `medium` or `high`. Lower is faster. |
| `SANAD_FAST_MODE` | off | `true` requests fast output on models that offer it. A premium-priced option; if the API rejects it the service carries on without it. |
| `SANAD_FAST_PATH` | off | `true` answers an exact standard question straight from its view, with no model call. Instant, but the wording is fixed. |
| `SANAD_ACCESS_CODE` | none | If set, the chat asks for this code before it can be used. Recommended on a public address, because every question spends the model key. |
| `SANAD_RATE_PER_MIN` | `30` | Questions per browser per minute. |
| `SANAD_GLOBAL_RATE_PER_MIN` | `240` | Questions per minute across everyone. This bounds what a public address can spend; raise it for a large group. |
| `SANAD_MAX_CONCURRENCY` | `24` | Model calls in flight at once. More than this queue briefly. |
| `SANAD_STATE_FILE` | `backend/data/runtime/sanad_state.json` | Where conversations and notebooks are saved. Point it at a mounted volume to keep them across deploys. `SANAD_PERSIST=false` keeps them in memory only. |
| `SANAD_FALLBACKS` | on | `false` switches off the server-side fallback model for declined requests. |
| `SANAD_AGENT` | `true` | `false` serves the chat on SAS Retrieval Agent Manager instead (see below). |

## Deploy on Railway

1. Create a service from this repository and choose the branch `sanad-mro-hub`.
2. Add the variables: `ANTHROPIC_API_KEY`, and `SANAD_ACCESS_CODE` if the address is public.
3. Keep it at **one replica**. Questions in flight are held in memory by the process that
   took them.
4. Optional: mount a volume and set `SANAD_STATE_FILE` to a path on it, so conversations
   survive a redeploy.

There is nothing else to set. On this branch the default `Dockerfile` and `railway.toml` build
the Sanad app, so a deploy of the branch cannot produce anything else. To confirm what is
running, open `/api/health` on the deployed address: it answers `"app": "sanad"` with the
commit it was built from.

The image is slim (the chat, `sanad_app.py`, the assistant, its data and documents) and starts
in about a second. `/api/health` reports whether a model key is present; the start-up log says
whether the model answered a test call.

**After the first deploy, run the acceptance check.** Open the app with `?check` on the end of
the address:

```
https://your-app.up.railway.app/?check
```

Press "Run the check". It asks the storyline's 14 questions as each role at the right shop
time, then 11 questions that are not in the storyline (free-form, a what-if, a document
question, a chart, actions that must succeed and actions that must be refused). For each one
it shows how it was answered (the model or the shop data), the time to the first words and to
the complete answer, the card shown, and anything that looks wrong: an answer that fell back
to the shop data, a missing card, a slow answer. "Copy report" gives the whole thing as text.
It makes real model calls and takes a few minutes. The same check runs from a terminal with
`python -m scripts.sanad_smoke https://your-app.up.railway.app` in `backend/`.

## Each browser is its own user

There is no sign-in. A browser gets an HttpOnly cookie on first contact, and its conversations
and notebook are visible to no one else. "Reset demo" in the Notebook forgets them.

## Where things are

| Piece | Where |
|---|---|
| Shop data: 24 tables as CSV, with their descriptions | `backend/data/sanad/`, built by `backend/scripts/build_sanad_scenario.py` |
| Approved documents: job card, maintenance instructions, inspection standards, procedures | `backend/data/sanad/docs/*.md` |
| The shop as of a moment, and the schedule that forecasts each engine | `backend/services/sanad/ops.py` |
| The twelve standard views, each with its card | `backend/services/sanad/views.py` |
| Tools: views, read-only SQL, document search, charts, role-gated actions | `backend/services/sanad/tools.py` |
| The model loop, the instructions, streaming | `backend/services/sanad/agent.py` |
| Question router (pre-fetch) and the no-model answers | `router.py`, `direct.py` |
| Conversations, limits, fallback, persistence | `backend/services/sanad/engine.py` |
| Roles, suggested questions and the story moments | `backend/services/sanad/scenario.py` |
| HTTP API (`/api/assistant/*`) and the standalone app | `backend/routers/sanad.py`, `backend/sanad_app.py` |
| The chat page, cards, menus, voice | `sanad-chat/src/hub/` |

To change the story, edit `build_sanad_scenario.py` and run
`python -m scripts.build_sanad_scenario` from `backend/`. Forecasts, statuses and option
finish dates are computed from the events by the schedule, not typed in, so they follow.

## Tests

```bash
cd backend
pip install pytest
python -m pytest tests/sanad -q
```

195 tests: the read-only SQL guard, the schedule against the storyline, every view at every
moment, the wording of every answer across the allowed period, the router, the role rules, the HTTP API, limits and the access code. The model path
runs against a local stand-in for the Anthropic API that speaks the real streaming format, so
the real SDK, the tool loop, streaming, retries, the outage fallback and stop are exercised
without a key.

## Running on SAS Retrieval Agent Manager instead

Set `SANAD_AGENT=false` and the `RAM_*` variables from the root README. The same chat then
talks to RAM through `/api/ram/*` and shows RAM's agents and collections
(`src/ram/RamPage.jsx`). The chat decides which page to show by asking the server what it
serves, so the label on screen always matches what is behind it. With no backend at all
(`npm run dev` alone) it falls back to the RAM showcase with scripted answers.

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

The app is dark throughout, the hackathon's glass recipe (gradient panels, lit edges, soft
bokeh) on the petrol navy of Sanad's event livery (the MRO Asia Pacific 2026 artwork), with the
sky of its window view as the accent. Tokens live in the `:root` block of `src/index.css`:

| Token | Colour | Use |
|---|---|---|
| `--frame` | `#051E2E` | the page: petrol navy, lit from the top with a sky glow and a sea-teal glow below |
| `--brand` | `#5F93C4` | sky: accents, active states, chips, the send button gradient |
| `--brand-hi`, `--brand-lo` | `#9DC5E0`, `#B6DEF2` | light and pale sky: focus rings, accent text |
| `--accent` | `#B9B7CC` | lavender from the official mark's facets: the trace panels |
| `--sea` | `#226984` | sea teal: background glow and bokeh |
| `--text`, `--text-md`, `--text-dim`, `--text-faint` | `#F1F5FA` … `#5E7690` | light ink on dark |
| `--glass`, `--glass-strong`, `--surface` | dark navy glass | panels, bubbles, menus and modals |

The chat elements themselves are light so they read easily: the message bubbles, the input
box, the recent conversation items and "New conversation" are pale frosted glass with dark navy
ink and steel-blue (`#2F6FA8`) accents, on the dark panels. Their tokens are the block at the end
of `src/index.css`.

The official navy `#071D49` is kept in `public/sanad-logo.svg` and in the mark component's
`tone="navy"`, for use on light backgrounds.

There is no "Connected" indicator: the chat card shows a status message only when something is
wrong (backend offline, not configured), and the Sign in button when the deployment needs one.
