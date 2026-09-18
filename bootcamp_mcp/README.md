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

## Register it in SAS Retrieval Agent Manager

One registration per team, each with its own scope:

1. RAM → Tool sources → add an MCP server. Point it at the container image (or at a running
   `http://<host>:8134/mcp`). Follow the SAS example for the transport and token settings:
   [container_mcp_servers/sas_mcp_server](https://github.com/sassoftware/sas-retrieval-agent-manager-examples/tree/main/examples/container_mcp_servers/sas_mcp_server);
   the only differences are the image and the two extra variables.
2. Environment variables: everything in `.env.sample`, with the team's `ALLOWED_TABLES` and
   `ALLOWED_MODELS` (`Public.EHS_DIABETES,Public.EHS_FACILITIES` and the team's published module
   name; a route-B team gets its own `Public.<TABLE>_TEAMn` instead).
   Keep `ALLOW_RAW_BEARER=true`: RAM presents the signed-in participant's Viya token, and the
   server accepts it after validating it against Viya's JWKS, exactly as the SAS server does.
3. In the team's agent, add the tool source. All eight tools, or fewer; the server is already scoped,
   so there is nothing to hide.
4. Ask the agent "which tables can you see?" It should call `list_tables` and name only the team's.

The Design Thinking Agent's last step tells the participant the two values to give the facilitator.

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
