# SAS Viya MCP server: which tools to give each agent

The bootcamp runs the current **SAS Viya MCP Server** (`sassoftware/sas-mcp-server` v1.15, 92 tools
in 10 tiers). Tool names below are the ones the server registers; in RAM, pick them by name when you
add the MCP tool source to an agent. A shorter tool list measurably improves tool selection, so do
not connect all 92 to either agent.

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

## Design Thinking Agent (24 tools)

| Tool | Why |
|---|---|
| `execute_sas_code` | generate synthetic data with a DATA step, promote tables, any transformation without a dedicated tool |
| `list_compute_contexts`, `reset_compute_session` | pick the compute context; recover from a wedged session |
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

## Population Health Agent (6 tools, plus one optional)

| Tool | Why |
|---|---|
| `query_data` | every number: cohorts, rates, costs, group-bys, the patient a clinician asks about |
| `get_castable_columns` | inspect columns before claiming data is missing |
| `get_castable_info`, `list_castables` | confirm the table and its row count |
| `get_mas_module_step_signature`, `score_data` | risk scoring through the published champion model |
| `execute_sas_code` (optional) | only if the agent should forecast visits with PROC ESM |

Everything else the agent needs (the guidelines, the citations) comes from its RAM collection, not
from a tool.

## Note on the fork

`raedaldweik/sas-mcp-server` is at v1.9.3 (75 tools, no glossary tier). Everything above also works
on it, since none of the selected tools changed; only the tier table differs (no tier 9).
