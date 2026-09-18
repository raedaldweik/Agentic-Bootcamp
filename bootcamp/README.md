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

1. **MCP servers.** Deploy the SAS Viya MCP server in HTTP mode with `MCP_TIERS=0,1,2,5,6`,
   `MCP_READ_ONLY=false`, `ALLOW_RAW_BEARER=true`, and register it in RAM as a tool source
   (the official example: `sas-retrieval-agent-manager-examples/examples/container_mcp_servers/sas_mcp_server`).
   Build the Bootcamp MCP image from `../bootcamp_mcp/` (`docker build -t bootcamp-mcp:0.1.0 .`);
   you register it in step 6, once the table and model exist.
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
6. **Population Health Agent.** Register the Bootcamp MCP in RAM as a tool source with the same
   auth settings as the SAS server plus `ALLOWED_TABLES=Public.EHS_DIABETES,Public.EHS_FACILITIES`
   and `ALLOWED_MODELS=<your module name>` (`../bootcamp_mcp/README.md`). New agent → paste the
   prompt from `agents/population_health_agent.md` with `Public.EHS_DIABETES` and your module name
   filled in → attach the collection → add the Bootcamp MCP tool source (all 8 tools) → publish. Ask
   it "which tables can you see?": only the two `Public` tables may come back.
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

Known failure, already handled in the prompts: a table in a personal caslib (`casuser`). The
Design Thinking Agent's first dry-run created `casuser.HOSPITAL_RISK_TEAM1`, then `create_ml_project`
failed twice with Analytics Gateway errors 92423 / 67017 / 119072 ("project data table could not be
retrieved"), and `list_castables` on `casuser` came back empty. Everything now goes to `Public`.

## On the day

Teams of three or four, one RAM login per team (RAM history is per identity; a shared login means
every team sees every conversation, so set `RAM_HIDE_HISTORY=true` on the app if you must share).
Every artefact carries the team suffix (`_TEAM3`). Route A (load the registry) keeps all teams on the
same numbers as the app; route B (generate) is for teams with their own idea. When a team's table and
model are ready, register their Bootcamp MCP (one registration per team, `ALLOWED_TABLES` and
`ALLOWED_MODELS` set to theirs); the Design Thinking Agent's last message gives them the two values
to hand over.
