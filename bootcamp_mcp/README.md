# bootcamp-mcp

A scoped SAS Viya MCP server for the EHS × SAS Agentic AI Bootcamp.

The full [SAS Viya MCP Server](https://github.com/sassoftware/sas-mcp-server) exposes 92 tools over an
entire Viya environment. Participants building an agent in SAS Retrieval Agent Manager (RAM) need
eight, and only on their own data. This server is those eight tools, built **on top of** the SAS
server (it is a dependency, not a copy), and every tool refuses to touch anything outside the two
environment variables you set when you register it in RAM:

```
ALLOWED_TABLES=Public.EHS_DIABETES,Public.EHS_FACILITIES
ALLOWED_MODELS=deterioration_team1
```

Authentication is the SAS server's own: the same `PermissiveOAuthProxy`, the same
`ALLOW_RAW_BEARER` handling for RAM's Viya token, the same middleware that swaps the request bearer
for the upstream access token. Queries run through the same compute-session pool and the same FedSQL
code generator as the upstream `query_data`. What changes is the surface and the scope.

## The tools

| Tool | What it does | Scope check |
|---|---|---|
| `list_tables` | The allowed tables with row and column counts; `not_loaded` when one is allowed but not in CAS yet | lists only `ALLOWED_TABLES` |
| `describe_table` | Columns (name, type, label, format) and row count of one table | table must be allowed |
| `preview_table` | The first few rows of one table | table must be allowed |
| `query_data` | One FedSQL SELECT: counts, rates, group-bys, joins, one patient's row | every table after FROM/JOIN must be allowed; bare names are qualified for the model; writes refused |
| `list_models` | The allowed published models with their inputs and outputs | lists only `ALLOWED_MODELS` |
| `describe_model` | Full input/output signature of one model | model must be allowed |
| `score` | Score one record (`{"column": value}`), names matched case-insensitively, values cast to the model's types | model must be allowed |
| `score_table_rows` | Pull rows from an allowed table with a WHERE, score each with an allowed model, in one call | both must be allowed; the WHERE may not contain a second statement or subquery |

Table tools register only when `ALLOWED_TABLES` is set, model tools only when `ALLOWED_MODELS` is,
so a team without a published model yet sees no scoring tools at all. All eight carry MCP tool
annotations: the five list/describe/preview tools are read-only; `query_data` and the two scoring
tools start work on Viya (a compute job, a MAS execution) but destroy nothing.

A refusal is a structured result, not an exception, so the agent can correct itself:

```json
{"status": "out_of_scope", "message": "PUBLIC.HMEQ is outside this server's scope. Allowed tables: PUBLIC.EHS_DIABETES, PUBLIC.EHS_FACILITIES."}
```

## Configuration

| Variable | Meaning | Default |
|---|---|---|
| `ALLOWED_TABLES` | Comma-separated `caslib.table`. Case-insensitive; `*` is a wildcard (`Public.*_TEAM1`). Use global caslibs such as `Public`: a personal caslib (`casuser`) is not resolvable by the Viya data services the tools call | required (or `ALLOWED_MODELS`) |
| `ALLOWED_MODELS` | Comma-separated SAS Micro Analytic Service module ids (the published model's name); `*` allowed | required (or `ALLOWED_TABLES`) |
| `CAS_SERVER` | CAS server the tables live on | `cas-shared-default` |
| `BOOTCAMP_MAX_ROWS` | Cap on rows one query or preview returns (1–10000) | `500` |
| `BOOTCAMP_SCORE_STEP` | MAS step to score with; `auto` prefers `score`, then `execute` | `auto` |
| `MCP_SERVER_NAME` | Name advertised to MCP clients | `Bootcamp MCP Server` |
| `VIYA_ENDPOINT`, `CLIENT_ID`, `ALLOW_RAW_BEARER`, `SSL_VERIFY`, `MCP_SIGNING_KEY`, `MCP_BASE_URL`, `HOST_PORT`, `COMPUTE_CONTEXT_NAME`, `VIYA_AUTH` | Exactly as in the SAS Viya MCP server ([its README](https://github.com/sassoftware/sas-mcp-server#readme)) | upstream defaults |

`.env.sample` has a complete example. One `.env` can drive both servers.

## Run it

**Docker** (what RAM runs):

```bash
cd bootcamp_mcp
docker build -t bootcamp-mcp:0.1.0 .
docker run -d -p 8134:8134 --env-file .env --name bootcamp-mcp bootcamp-mcp:0.1.0
curl http://localhost:8134/health
curl http://localhost:8134/          # the scope this container carries (no data, no tokens)
```

The MCP endpoint is `http://<host>:8134/mcp`.

**pip, from GitHub** (Python 3.12+; `git` needed for the upstream dependency):

```bash
pip install "bootcamp-mcp @ git+https://github.com/raedaldweik/Agentic-Bootcamp.git@main#subdirectory=bootcamp_mcp"
bootcamp-mcp            # HTTP on $HOST_PORT
bootcamp-mcp-stdio      # stdio, for a desktop MCP client; signs in like the SAS server does
```

## The image

RAM runs container MCP servers from an image, the way it runs
`ghcr.io/sassoftware/sas-mcp-server:latest`. This one is published the same way:

```
ghcr.io/raedaldweik/bootcamp-mcp:latest          rebuilt on every push that touches bootcamp_mcp/
ghcr.io/raedaldweik/bootcamp-mcp:sha-<commit>    the same build, pinned
ghcr.io/raedaldweik/bootcamp-mcp:<version>       from a git tag bootcamp-mcp-v<version>
```

The GitHub Actions workflow `.github/workflows/bootcamp-mcp-image.yml` builds it (Actions tab shows
the run). Once, after the first build: GitHub → your profile → Packages → `bootcamp-mcp` → Package
settings → Change visibility → **Public**, or RAM cannot pull it. To build locally instead:
`cd bootcamp_mcp && docker build -t bootcamp-mcp:0.1.0 .` and push to any registry RAM can reach.

## Register it in SAS Retrieval Agent Manager

RAM's container MCP servers are a **template** (the image and its fixed settings, defined once) that
you **instantiate** (one running container per instance, each with its own environment variables).
The Bootcamp MCP is one template and one instance per team.

**The template**, the same fields as the SAS one
([container_mcp_servers/sas_mcp_server](https://github.com/sassoftware/sas-retrieval-agent-manager-examples/tree/main/examples/container_mcp_servers/sas_mcp_server)):

| Field | Value |
|---|---|
| Container image | `ghcr.io/raedaldweik/bootcamp-mcp:latest` |
| Transport · Port · Base path | HTTP · `8134` · `/mcp` |
| Authentication | OAuth client credentials, token URL `<Viya URL>/SASLogon/oauth/token`, scope empty. Best: one client per team (`ram-team01`…, created with the SAS template's `create_viya_oauth_client.py`, each with its own UID/GID and group), so each team is its own Viya identity; the single shared client works too |
| Environment variables | `VIYA_ENDPOINT`, `ALLOW_RAW_BEARER=true`, `ALLOWED_TABLES`, `ALLOWED_MODELS`, `MCP_SERVER_NAME` (values set per instance) |

RAM obtains a Viya token for that client and sends it as the bearer on every call; `ALLOW_RAW_BEARER`
makes the server accept it after validating it against Viya's JWKS, exactly as the SAS server does.
So every instance reaches Viya as that one client: the scope variables are what keep teams apart.

**One instance per team:**

| Variable | Team 1, route A | Team 2, route B |
|---|---|---|
| `MCP_SERVER_NAME` | `Bootcamp team 01` | `Bootcamp team 02` |
| `ALLOWED_TABLES` | `Public.EHS_DIABETES,Public.EHS_FACILITIES` | `Public.HOSPITAL_RISK_TEAM2,Public.EHS_FACILITIES` |
| `ALLOWED_MODELS` | the shared model's module name | `hospital_risk_team2` |
| `VIYA_ENDPOINT`, `ALLOW_RAW_BEARER` | as on the SAS server | as on the SAS server |

Then, per team: the participants create their agent (no code), attach their team's instance with all
eight tools, and ask it "which tables can you see?". Only the team's tables may come back.

**The SAS MCP server, for the Design Thinking Agent**, is the existing template instantiated four
or five times (`sas-viya-A` … `E`, same image, same client, `MCP_TIERS=0,1,2,5,6`,
`MCP_READ_ONLY=false`, `ALLOW_RAW_BEARER=true`). Each instance is its own container with its own
warm compute session; make one copy of the Design Thinking Agent per instance and give each RAM user
one copy, four or five users per instance. `bootcamp/README.md` has the counts.

## Development

```bash
uv venv --python 3.12 && source .venv/bin/activate
uv pip install -e . pytest pytest-asyncio ruff   # pulls sas-mcp-server from its GitHub tag
pytest -q                                # 44 tests, no Viya needed (fake Viya behind httpx.MockTransport)
ruff check src tests
```

`src/bootcamp_mcp/scope.py` is the part to review: the allow-lists, the FedSQL table scan, the
rewrite of bare names, and the WHERE-fragment check, all pure functions with tests in
`tests/test_scope.py`. `tools.py` holds the eight tools; `server.py` the HTTP transport and auth
(reproduced from the upstream `mcp_server.py`, Apache-2.0); `stdio_server.py` the stdio transport.

## What it does not do

No SAS code execution, no uploads, no AutoML, no publishing: those belong to the Design Thinking
Agent on the full server. A participant's agent gets the data and the model it was given, read and
scored, nothing else.

## License

Apache-2.0, like the SAS Viya MCP server it is built on.
