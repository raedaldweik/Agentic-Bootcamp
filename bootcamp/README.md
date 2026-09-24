# Bootcamp kit: build the population-health agent on SAS RAM

How the two days work, and the material each step needs. The app in this repo is the participants'
workbench (data, documents, a finished agent, and a SAS RAM tab that signs in to their environment);
this folder is what goes into SAS Viya and SAS Retrieval Agent Manager (RAM).

## The flow

```
idea ──► Design Thinking Agent (pre-built, on RAM, drives SAS Viya through MCP)
             │
             ├─ 1. structured data ──► synthetic table in CAS (generated, or the registry CSV loaded from URL)
             ├─ 2. ML model ────────► Model Studio AutoML project, champion registered + published to MAS
             └─ 3. knowledge ───────► the participant creates the RAM collection with the NHA PDFs (manual)
                                            │
                              4. the participant builds their agent in RAM (no code):
                                 system prompt + collection + the team's Bootcamp MCP tool source
                                 (8 tools, scoped to their table and model by ALLOWED_TABLES / ALLOWED_MODELS)
                                            │
                              5. they test it on the app's SAS RAM tab (sign in, pick the agent)
```

| Component | Where | Material |
|---|---|---|
| Design Thinking Agent | RAM, pre-built by the facilitator | `agents/design_thinking_agent.md` (prompt + config), `tools.md` (24 tools) |
| Structured data | SAS Viya CAS | `data/ehs_diabetes_registry.csv` (4,000 patients, 54 columns), `data/ehs_facilities.csv`, `data/DATA_DICTIONARY.md` |
| ML model | Model Studio via MCP | target `deterioration_next_12m`; leakage columns listed in the data dictionary |
| Knowledge (RAG) | RAM collection | `documents/NHA_*.pdf` (4 synthetic guideline PDFs, section-numbered) |
| Bootcamp MCP | RAM tool source, one registration per team | `../bootcamp_mcp/` (container image; `ALLOWED_TABLES`, `ALLOWED_MODELS`), tool list in `tools.md` |
| Population Health Agent | RAM, built by each team | `agents/population_health_agent.md` (prompt template + test questions with expected answers) |

## Facilitator dry-run (do this yourself first)

1. **MCP servers.** In RAM's MCP Tools view, instantiate the SAS Viya MCP container template
   (`ghcr.io/sassoftware/sas-mcp-server:latest`, the official example:
   `sas-retrieval-agent-manager-examples/examples/container_mcp_servers/sas_mcp_server`) with
   `MCP_TIERS=0,1,2,5,6`, `MCP_READ_ONLY=false`, `ALLOW_RAW_BEARER=true`; once for the dry-run,
   four or five times for the day. Add a second template for the Bootcamp MCP image,
   `ghcr.io/raedaldweik/bootcamp-mcp:latest` (built by the repo's GitHub Actions workflow; make
   the package public once), same port, path and OAuth client; you instantiate it in step 6, once
   the table and model exist. `../bootcamp_mcp/README.md` lists every field.
2. **Design Thinking Agent.** In RAM: new agent → name `Design Thinking Agent` → paste the prompt
   from `agents/design_thinking_agent.md` → add the MCP tool source and tick the 24 tools in
   `tools.md` → share with all participant accounts.
3. **Data.** Load the two CSVs into the `Public` caslib as `EHS_DIABETES` and `EHS_FACILITIES`,
   promoted to global scope (already done on the bootcamp Viya). Use `Public` for everything, never
   a personal caslib: Model Studio cannot read `casuser`. If you need to reload, `upload_data` from
   the raw GitHub URLs (if the environment has outbound internet):
   - `https://raw.githubusercontent.com/raedaldweik/Agentic-Bootcamp/claude/ehs-bootcamp-repo-setup-xxxwca/bootcamp/data/ehs_diabetes_registry.csv`
   - `https://raw.githubusercontent.com/raedaldweik/Agentic-Bootcamp/claude/ehs-bootcamp-repo-setup-xxxwca/bootcamp/data/ehs_facilities.csv`
   (replace the branch segment with `main` once merged). Otherwise copy them to a server path and
   hand out paths; `upload_data` accepts either.
4. **Walk the path** with the Design Thinking Agent using suffix `_TEST`:
   - "My idea: an agent that tells a programme lead which diabetic patients will deteriorate and
     what the guideline says to do. Team name TEST."
   - Route A: "Use the registry, Public.EHS_DIABETES, and profile it." Expect 4,000 rows, target
     rate 10.4%, 54 columns, and no table created.
   - "Build the model." Expect a Model Studio project, a gradient boosting or forest champion, the
     champion registered and published to MAS, a module name back, and a `score_data` check.
   - "Design the knowledge base." Expect the four NHA documents and the retrieval settings.
   - "Assemble my agent." Expect a filled-in system prompt, the 6-tool list and test questions.
5. **Collection.** In RAM: new collection `NHA_Guidelines_TEST` → upload the four PDFs from
   `documents/` → chunk 600–800 characters with overlap, top-k 4–6, citations on → test one query:
   "LDL target very high risk" must return NHA-CG-02 §3.
6. **Population Health Agent.** Instantiate the Bootcamp MCP template for the test team with
   `ALLOWED_TABLES=Public.EHS_DIABETES,Public.EHS_FACILITIES`, `ALLOWED_MODELS=<your module name>`
   and `MCP_SERVER_NAME=Bootcamp team TEST` (`../bootcamp_mcp/README.md`). New agent → paste the
   prompt from `agents/population_health_agent.md` with `Public.EHS_DIABETES` and your module name
   filled in → attach the collection → add that instance (all 8 tools) → publish. Ask it "which
   tables can you see?": only the two `Public` tables may come back.
7. **Test on the app.** Set `RAM_API_URL` (and auth) on the deployed app, open the SAS RAM tab, sign
   in, pick `Population Health Agent`, and run the test questions in
   `agents/population_health_agent.md`. The numbers must match the app's Dashboard tab.

Known slow points: the first `execute_sas_code` pays compute-session start-up; AutoML runs take
minutes (stagger teams); RAG ingestion takes a minute or two after upload.

## Capacity: what the 15-person test showed

Fifteen people on the Design Thinking Agent broke the SAS MCP server within five minutes with
`errorCode 12207 / 12212: OAuth authentication failed: No user credentials could be found for OS
process launch`, and CAS restarted. Neither is a sign-in problem. Two things combine:

1. **One identity for everyone.** RAM calls the SAS MCP server with a single OAuth client
   (client credentials), so all participants reach Viya as that client. The MCP server keeps one
   warm compute session per identity, so fifteen people's DATA steps queued through one session
   and each `cas mysess` / `terminate` from one person hit the others.
2. **Viya ran out of room.** Fifteen synthetic-data runs plus AutoML projects starting at once
   is far more than a small environment carries. When CAS and the launcher pods restart, every
   session creation fails with exactly that launcher error until they are back. The MCP server's
   own measurements: about 0.15 CPU and 550 MB of Viya per warm compute session (25 people ≈ 3.75
   CPU and 13 GB before any Model Studio run), and the MCP container itself costs almost nothing.

What to do, in order of effect:

- **Build the model once, before the day.** The facilitator runs AutoML on `Public.EHS_DIABETES`,
  publishes the champion, and puts its module name in the Design Thinking Agent prompt
  (`{{SHARED_MODEL}}`). Route A teams then never run AutoML. Route B teams get AutoML only with
  your go-ahead, one at a time across the room. The prompts now enforce this.
- **One SAS MCP registration per team.** Each registration is its own container with its own
  compute session, so ten teams get ten sessions instead of sharing one. Same for the Bootcamp
  MCP, which is already per team.
- **Short, self-contained code calls.** Unique CAS session names ended in the same call, no
  `reset_compute_session`, `query_data` for profiling. The prompt now says so.
- **Ask the Viya administrator for headroom for the day**: CAS memory, compute node capacity,
  and a shorter compute-session idle timeout so abandoned sessions are reaped quickly.
- **Recover** after an outage by restarting the SAS MCP container (its cached session is stale)
  once CAS and the launcher pods are back.
- **Re-run the 15-person test** with these changes before the bootcamp, and watch CAS memory
  while it runs.

### The deployment decision, checked against the SAS docs

The SAS MCP server documents four ways to run it (stdio, HTTP with browser PKCE, Docker, Kubernetes
behind an ingress). Its multi-user mode, Kubernetes with each user signing in through a browser
PKCE flow, is built for people using an MCP client such as VS Code or Claude Code. It does not
apply to RAM: RAM is the MCP client here, and RAM's tool sources support exactly two
authentications, none (the Remote MCP template) or OAuth client credentials (the container
template). So the mode you use, the container template with client credentials and
`ALLOW_RAW_BEARER=true`, is the supported one. Nothing is being missed there.

What the docs do offer, and the kit now uses:

- **One OAuth client per team, not one for the room.** The template's own script creates a client
  with its own UID, GID and Viya group; run it once per team
  (`CLIENT_ID=ram-team01 CUID=2101 CGID=2101 python create_viya_oauth_client.py`, then
  `ram-team02` with `2102`, and so on) and give each team's instances that client. Each team is
  then its own Viya identity: its own compute sessions, its own CASUSER, its own audit trail, and a
  runaway job in one team cannot block or reset another's. If the administrator has an hour,
  a per-team caslib with an authorization rule limiting each client to its own caslib makes the
  isolation platform-enforced as well.
- **One instance per team, single replica each.** The server's compute-session cache is
  in-process and its Kubernetes guide says to stay at one replica; RAM's container instances are
  exactly that.
- **The MCP container is not the cost.** Measured at 113m CPU and 23 MB for 40 concurrent
  clients; the cost is Viya, about 0.15 CPU and 550 MB per warm compute session plus whatever
  Model Studio runs need. That is why the runbook removes the heavy work from the day rather than
  adding servers.

### How many of what, for 20 RAM users

| Thing | How many | Why |
|---|---|---|
| Viya users | **0 new** | RAM never uses a RAM user's identity towards Viya. Every tool-source registration authenticates with one OAuth client (the template's `ram-client`, with its own UID/GID), and that client is the only identity Viya sees. Your RAM users matter inside RAM only: who sees which agent and conversations |
| OAuth clients | **1 per team** (or 1 for the room) | created with the template's script, each with its own UID/GID and group, so each team is its own Viya identity; one shared client also works but then every team is one identity |
| SAS MCP server registrations (Design Thinking) | **4 to 5** | each registration is its own container with its own warm compute session (about 550 MB on Viya each). Make that many copies of the Design Thinking Agent (`Design Thinking A` … `E`), attach one registration to each, and give each RAM user one copy. Four or five people per session keeps the queueing invisible; twenty registrations would work too but cost 11 GB of Viya for nothing |
| Bootcamp MCP registrations | **one per team** | this is where `ALLOWED_TABLES` / `ALLOWED_MODELS` live, so it is per team by design; 20 RAM users as 20 teams means 20, five teams sharing logins means 5 |
| Model Studio runs | **1 before the day** | the shared model; Route B teams only with your go-ahead, one at a time |

Known failure, already handled in the prompts: a table in a personal caslib (`casuser`). The
Design Thinking Agent's first dry-run created `casuser.HOSPITAL_RISK_TEAM1`, then `create_ml_project`
failed twice with Analytics Gateway errors 92423 / 67017 / 119072 ("project data table could not be
retrieved"), and `list_castables` on `casuser` came back empty. Everything now goes to `Public`.

## The plan after the 15-person test: runbook

**Principle: on the day Viya does no heavy work.** Every participant flow is a few FedSQL queries
and scoring calls; the synthetic data and the model exist before anyone walks in.

**This week (T-7)**
1. Build the model once: run the Design Thinking Agent's Route B path yourself on
   `Public.EHS_DIABETES` (or AutoML in Model Studio), register and publish the champion, and put
   the module name in the Design Thinking prompt as `{{SHARED_MODEL}}`. Route A is now the only
   path the room takes; Route B is an extension you unlock for one team at a time.
2. Create one OAuth client per team with the template's script (`ram-team01`…, own UID/GID and
   group). Make the `bootcamp-mcp` package public on GitHub. In RAM: instantiate the SAS MCP
   template 4 or 5 times (`sas-viya-A`…`E`), duplicate the Design Thinking Agent per instance,
   assign each RAM user one copy; create the Bootcamp MCP template and one instance per team,
   each instance with its team's client.
3. Ask the Viya administrator, with the timestamps of the test: were the CAS and launcher pods
   OOM-killed or restarted? Ask for CAS memory and compute headroom for the day, a compute-session
   idle timeout of about 15 minutes, and a look at any per-user session limit.

**Rehearsal (T-3), with a go/no-go**
4. Repeat the 15-person test on the new setup: shared model, Route A only, 4 SAS instances, one
   driver per team. The admin watches CAS memory and pod restarts while it runs. Pass means no
   launcher or CAS errors and every agent turn under 30 seconds. If it passes at 15, it passes
   at 20 RAM users, because the load is per team and staggered, not per person.
5. If it fails, drop to five teams live on Viya at a time (the others build their collection and
   prompt meanwhile), and re-test. If it still fails, run the day on Plan B below.

**The day**
6. Pre-warm: before the room starts, open each Design Thinking copy and ask it one question, so
   its compute session exists and the first team does not pay the spin-up.
7. Waves: teams start the Design Thinking flow five at a time, ten minutes apart. One person per
   team drives the agent; the rest watch the screen. That is 5 concurrent sessions, never 50.
8. The AutoML "moment" happens once, live, on your screen, not twenty times in the room.
9. Recovery: a launcher error (12207/12212) or a CAS error means wait a minute and retry once;
   if it persists, the admin checks the pods, and you restart the affected SAS MCP instance in
   RAM once CAS is back (its cached session is stale). The prompts already tell the agent not to
   send anyone to sign in again.

**Plan B, if Viya cannot hold even the light load**
The bootcamp still runs. The app's Dashboards and Simulator carry the data story without Viya;
the Assistant tab is a finished agent with no Viya behind it; and every team can still build a
real agent in RAM with the NHA collection and the system prompt, tested on the app's SAS RAM
tab, with the Viya tools attached only for the teams you let through one at a time.

## On the day

Teams of three or four, one RAM login per team (RAM history is per identity; a shared login means
every team sees every conversation, so set `RAM_HIDE_HISTORY=true` on the app if you must share).
Every artefact carries the team suffix (`_TEAM3`). Route A (load the registry) keeps all teams on the
same numbers as the app; route B (generate) is for teams with their own idea. When a team's table and
model are ready, register their Bootcamp MCP (one registration per team, `ALLOWED_TABLES` and
`ALLOWED_MODELS` set to theirs); the Design Thinking Agent's last message gives them the two values
to hand over.
