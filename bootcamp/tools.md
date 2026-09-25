# Which tools each agent gets

Two MCP servers, one per audience:

| Server | Who uses it | Tools | Scope |
|---|---|---|---|
| **SAS Viya MCP Server** (`sassoftware/sas-mcp-server` v1.15, 92 tools in 10 tiers) | the facilitator's Design Thinking Agent | 24 of the 92, listed below | the whole Viya environment (it creates tables, projects and models) |
| **Bootcamp MCP** (`../bootcamp_mcp/`, built on the SAS server) | every participant agent | 8 | only the team's `ALLOWED_TABLES` and `ALLOWED_MODELS`, set when the facilitator registers it in RAM |

Participants never see the 92-tool list. Their server is registered once per team with the table and
model the Design Thinking Agent produced for them, and every tool on it refuses anything else.

## SAS Viya MCP Server

**Caslib rule for both servers: `Public` only.** Every table lives in `Public` on
`cas-shared-default` at global scope (`Public.EHS_DIABETES`, `Public.EHS_FACILITIES`, and the teams'
`Public.<NAME>_TEAMn`). A personal caslib (`casuser`) breaks the flow: `list_castables` returns
nothing for it and Model Studio cannot resolve its data-table URI (`create_ml_project` fails with
errorCode 119072, "project data table could not be retrieved"). The first dry-run hit both.

Tool names below are the ones the server registers; in RAM, pick them by name when you add the MCP
tool source to an agent. A shorter tool list measurably improves tool selection, so do not connect
all 92 to the Design Thinking Agent.

| Tier | Group | Used by |
|---|---|---|
| 0 | Compute contexts and code execution | Design Thinking |
| 1 | Data discovery (CAS tables, FedSQL, catalog) | both |
| 2 | Data operations and files | Design Thinking |
| 3 | Reports and visualization | optional, Design Thinking (a VA dashboard step) |
| 4 | Batch jobs | no |
| 5 | Automated machine learning (Model Studio) | Design Thinking |
| 6 | Model management and scoring (MAS) | both |
| 7 | Decisioning | optional, Design Thinking (recall rules) |
| 8 | Workbench (execute code only) | no |
| 9 | Business glossary | no |

Server environment for the bootcamp deployment:

```
MCP_TIERS=0,1,2,5,6        # add 3 for the Visual Analytics step, 7 for Intelligent Decisioning rules
MCP_READ_ONLY=false        # participants create tables, projects and models
ALLOW_RAW_BEARER=true      # RAM authenticates with its Viya token
```

**Identity and capacity.** RAM authenticates to a container MCP server with one OAuth client
(client credentials, the RAM template's `ram-client` with its own UID/GID), so every participant
reaches Viya as that one identity. The SAS MCP server keeps one warm compute session per identity
per registration, which means everyone on a registration shares one session and their jobs run one
at a time. Register the SAS MCP server once per team (each registration is its own container and
gets its own session), keep every code call short, and never let a participant agent reset the
session. What actually scales with people is Viya itself: about 0.15 CPU and 550 MB per warm compute
session, plus whatever Model Studio runs need. See the capacity section in `README.md`.

## Design Thinking Agent (22 tools)

| Tool | Why |
|---|---|
| `execute_sas_code` | generate synthetic data with a DATA step, promote tables, any transformation without a dedicated tool |
| `list_compute_contexts` | pick the compute context (`reset_compute_session` stays off the list: with one shared identity it would kill the session under every team; the facilitator resets from a separate MCP client if needed) |
| `list_caslibs`, `list_castables`, `list_source_tables` | see what exists before creating anything |
| `get_castable_info`, `get_castable_columns`, `get_castable_data` | confirm a table, its columns and sample rows |
| `query_data` | profile: counts, target rate, missing values, distinct levels (FedSQL) |
| `upload_data` | load the registry CSV from a URL straight into CAS (route A) |
| `upload_inline_data` | small lookup tables built on the fly |
| `promote_table_to_memory` | global scope, required before AutoML |
| `list_ml_projects`, `create_ml_project`, `run_ml_project` | the Model Studio project |
| `register_ml_champion_model`, `publish_ml_champion_model` | champion into the repository and out to MAS |
| `list_registered_models`, `list_publishing_destinations`, `list_mas_modules` | find the destination and the published module |
| `get_mas_module_step_signature`, `score_data` | verify the published model scores |

Optional: `describe_report_objects`, `create_report`, `apply_report_operations`, `get_report_outline`
(tier 3) if you want the copilot to build a Visual Analytics page; the rule set and decision flow
tools (tier 7) if you want a recall decision flow.

## Population Health Agent: the Bootcamp MCP (8 tools)

Register `bootcamp_mcp` in RAM once per team (see `../bootcamp_mcp/README.md`) with, for team 3:

```
ALLOWED_TABLES=Public.EHS_DIABETES,Public.EHS_FACILITIES     # route A: the shared registry
ALLOWED_TABLES=Public.HOSPITAL_RISK_TEAM1,Public.EHS_FACILITIES   # route B: the team's own table
ALLOWED_MODELS=hospital_risk_team1                            # the published module's name
```

| Tool | Why |
|---|---|
| `list_tables`, `describe_table`, `preview_table` | what the agent can see: its tables, their columns, a few rows |
| `query_data` | every number: cohorts, rates, costs, group-bys, the patient a clinician asks about (FedSQL, scoped to the allowed tables) |
| `list_models`, `describe_model` | the published champion model and its inputs |
| `score`, `score_table_rows` | risk scoring: one record, or rows pulled from the table by a WHERE and scored in one call |

Everything else the agent needs (the guidelines, the citations) comes from its RAM collection, not
from a tool. Authentication is the SAS server's own (`ALLOW_RAW_BEARER=true`, RAM presents the
participant's Viya token), so the registration looks the same as the SAS server's, plus the two
scope variables.

**Fallback on the full SAS Viya MCP server** (6 tools, plus one optional), if the Bootcamp MCP is not
deployed: `query_data`, `get_castable_columns`, `get_castable_info`, `list_castables`,
`get_mas_module_step_signature`, `score_data`, and `execute_sas_code` only if the agent should
forecast visits with PROC ESM. The prompt template notes the name swaps.

## Note on the fork

`raedaldweik/sas-mcp-server` is at v1.9.3 (75 tools, no glossary tier). Everything above also works
on it, since none of the selected tools changed; only the tier table differs (no tier 9).
