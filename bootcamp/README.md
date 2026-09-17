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
                                 system prompt + collection + SAS Viya MCP tools (chosen by name)
                                            │
                              5. they test it on the app's SAS RAM tab (sign in, pick the agent)
```

| Component | Where | Material |
|---|---|---|
| Design Thinking Agent | RAM, pre-built by the facilitator | `agents/design_thinking_agent.md` (prompt + config), `tools.md` (24 tools) |
| Structured data | SAS Viya CAS | `data/ehs_diabetes_registry.csv` (4,000 patients, 54 columns), `data/ehs_facilities.csv`, `data/DATA_DICTIONARY.md` |
| ML model | Model Studio via MCP | target `deterioration_next_12m`; leakage columns listed in the data dictionary |
| Knowledge (RAG) | RAM collection | `documents/NHA_*.pdf` (4 synthetic guideline PDFs, section-numbered) |
| Population Health Agent | RAM, built by each team | `agents/population_health_agent.md` (prompt template + test questions with expected answers) |

## Facilitator dry-run (do this yourself first)

1. **MCP server.** Deploy the SAS Viya MCP server in HTTP mode with `MCP_TIERS=0,1,2,5,6`,
   `MCP_READ_ONLY=false`, `ALLOW_RAW_BEARER=true`, and register it in RAM as a tool source
   (the official example: `sas-retrieval-agent-manager-examples/examples/container_mcp_servers/sas_mcp_server`).
2. **Design Thinking Agent.** In RAM: new agent → name `Design Thinking Agent` → paste the prompt
   from `agents/design_thinking_agent.md` → add the MCP tool source and tick the 24 tools in
   `tools.md` → share with all participant accounts.
3. **Data.** Host the two CSVs where the Viya server can reach them. The raw GitHub URLs work if the
   environment has outbound internet:
   - `https://raw.githubusercontent.com/raedaldweik/Agentic-Bootcamp/claude/ehs-bootcamp-repo-setup-xxxwca/bootcamp/data/ehs_diabetes_registry.csv`
   - `https://raw.githubusercontent.com/raedaldweik/Agentic-Bootcamp/claude/ehs-bootcamp-repo-setup-xxxwca/bootcamp/data/ehs_facilities.csv`
   (replace the branch segment with `main` once merged). Otherwise copy them to a server path and
   hand out paths; `upload_data` accepts either.
4. **Walk the path** with the Design Thinking Agent using suffix `_TEST`:
   - "My idea: an agent that tells a programme lead which diabetic patients will deteriorate and
     what the guideline says to do. Team name TEST."
   - Route A: "Load the registry from <URL> into CASUSER.REGISTRY_TEST and profile it." Expect
     4,000 rows, target rate 10.4%, 54 columns.
   - "Build the model." Expect a Model Studio project, a gradient boosting or forest champion, the
     champion registered and published to MAS, a module name back, and a `score_data` check.
   - "Design the knowledge base." Expect the four NHA documents and the retrieval settings.
   - "Assemble my agent." Expect a filled-in system prompt, the 6-tool list and test questions.
5. **Collection.** In RAM: new collection `NHA_Guidelines_TEST` → upload the four PDFs from
   `documents/` → chunk 600–800 characters with overlap, top-k 4–6, citations on → test one query:
   "LDL target very high risk" must return NHA-CG-02 §3.
6. **Population Health Agent.** New agent → paste the prompt from
   `agents/population_health_agent.md` with `REGISTRY_TEST` and your module name filled in → attach
   the collection → add the MCP tool source with the 6 tools → publish.
7. **Test on the app.** Set `RAM_API_URL` (and auth) on the deployed app, open the SAS RAM tab, sign
   in, pick `Population Health Agent`, and run the test questions in
   `agents/population_health_agent.md`. The numbers must match the app's Dashboard tab.

Known slow points: the first `execute_sas_code` pays compute-session start-up; AutoML runs take
minutes (stagger teams); RAG ingestion takes a minute or two after upload.

## On the day

Teams of three or four, one RAM login per team (RAM history is per identity; a shared login means
every team sees every conversation, so set `RAM_HIDE_HISTORY=true` on the app if you must share).
Every artefact carries the team suffix (`_TEAM3`). Route A (load the registry) keeps all teams on the
same numbers as the app; route B (generate) is for teams with their own idea.
