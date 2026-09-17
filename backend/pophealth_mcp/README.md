# population-health-mcp

**A population-health MCP server for the SAS × EHS Agentic AI Bootcamp.**

Healthcare MCP servers read patient records (single-patient lookups, FHIR resources) and call
model scoring (the SAS Viya MCP server scores a published model, runs SAS code, loads data).
None of them lets an agent reason about a **population**: quality measures, care gaps, cohorts,
risk stratification, policy what-ifs, or a safe write-back path for interventions. This server
fills exactly that gap, and inside Basira the supervisor's population-health specialist reaches
it over a genuine MCP hop that you can watch in the agent trace.

## Tools

| Tool | What it does |
|---|---|
| `get_population_snapshot` | Headline KPIs for the whole registry: control, complications, gaps, utilisation, annual cost (AED) |
| `build_cohort` | Declarative cohort from clinical criteria (HbA1c, eGFR, therapy, facility, nationality…) |
| `find_care_gaps` | Open guideline-derived gaps, filterable by gap type and facility |
| `compute_quality_measure` | HEDIS-style measures BASIRA-DM-01 … 10 (numerator, denominator, rate, target) |
| `stratify_risk` | Score a cohort through the deployed deterioration-risk model |
| `simulate_policy` | Counterfactual what-if by re-scoring an eligible cohort with an intervention applied |
| `draft_intervention` | DRAFT-ONLY intervention that lands in the human approval queue; never writes to the EMR |

## Run it

```bash
cd backend && python -m pophealth_mcp        # stdio transport
```

Any MCP client can connect. Claude Desktop (`claude_desktop_config.json`):

```json
{ "mcpServers": { "pophealth": { "command": "python", "args": ["-m", "pophealth_mcp"], "cwd": "/path/to/backend" } } }
```

## Under SAS Retrieval Agent Manager

RAM registers MCP servers as tool sources for its agents. Run this server in HTTP mode behind
the same ingress as the SAS Viya MCP server and add it to the population-health agent you build
in Lab 2. On SAS Viya the seven tools keep their contracts: cohorts and measures become CAS /
FedSQL queries over the registry tables, `stratify_risk` calls the model published from SAS
Model Manager, and `draft_intervention` writes a draft task for a human to approve.
