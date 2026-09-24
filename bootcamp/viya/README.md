# Track A on Viya: the SAS-documented way, made runnable

RAM's container MCP template authenticates with **OAuth client credentials**: RAM mints a Viya
token for a client and sends it to the MCP server, which accepts it with `ALLOW_RAW_BEARER=true`.
No person is behind it, nothing expires, and each team can be its own client. This folder turns
that into three scripts you run against Viya, in this order, before anyone is in the room.

```
pip install httpx
export VIYA_URL=https://your-viya.example.com     # add SSL_VERIFY=false only for a self-signed certificate
```

## 1. Create the team clients (you, as Viya administrator, once)

```
export ACCESS_TOKEN=<administrator token>     # or CODE=<authorization code>, see below
python create_team_clients.py --teams 10 --members raed.aldweik@sas.com --out clients.csv
```

Creates, exactly as the SAS example does: one client per team (`ram-team01` … `ram-team10`,
client-credentials grant, its own UID/GID from 2101 up), one Viya group per client with the same
id, and one parent group **`bootcamp-clients`** that every team group belongs to. `clients.csv`
holds the ids and secrets (mode 600; it is git-ignored; the secrets are shown nowhere else).

Getting an administrator token when Viya sign-in is through Microsoft: open
`$VIYA_URL/SASLogon/oauth/authorize?client_id=sas.cli&response_type=code` in a browser that is
signed in as an administrator, copy the code it shows, `export CODE=<code>` (ten minutes, one use).

## 2. Grant the rights (you, once, to the parent group)

In SAS Environment Manager, give **`bootcamp-clients`** what a participant needs. The verify
script in step 3 tells you exactly which of these is still missing.

| Right | Where | Why |
|---|---|---|
| Use the compute context | Contexts → *SAS Job Execution compute context* → Authorization → add the group | every DATA step and FedSQL query |
| Read and Write on `Public` | Data → caslib `Public` → Authorization | read the registry, create team tables |
| SAS Micro Analytic Service | Rules → `/microanalyticScore/**` → add the group (Read) | score the published model |
| Model Studio, Route B teams only | Rules → `/analyticsGateway/**`, `/mlPipelineAutomation/**`, `/modelRepository/**`, `/modelPublish/**` | AutoML, register, publish |

A client identity is not a member of SASUSERS, so it inherits none of the defaults a person gets.
That is why the parent group exists: grant once, every team has it.

## 3. Verify every client (you, five minutes)

```
python verify_team_client.py --csv clients.csv --write --model <shared module id> --automl
```

Walks the exact calls the MCP servers make: token, compute context, **session start** (the
launcher running SAS as the client's UID/GID, which is the step that failed in the 15-person
test), a DATA step, a CAS read of `Public.EHS_DIABETES`, a FedSQL count through a CAS session the
way `query_data` does it, a table created and dropped in `Public`, the MAS module list and the
shared model's signature, and Model Studio's project list. Every FAIL comes with the Viya message
and the grant that fixes it. All PASS on all clients is the go for step 4.

## 4. Load-test Viya with the day's pattern (you, ten minutes, with CAS memory on a second screen)

```
python load_test.py --csv clients.csv --workers-per-team 5 --iterations 4 --model <shared module id>
```

Ten teams, one warm compute session each, five participants per team asking four questions each
through that session (one job at a time per session, which is how a shared compute session
behaves), scoring the model on every question, with think time between questions. No LLM, so it
is the Viya half of the day in isolation. Pass is zero errors and a query p95 under 30 seconds.
The administrator watches CAS memory and the compute pods while it runs. Push it harder
(`--workers-per-team 8 --think 1`) once it passes; that is your safety margin.

## 5. Switch the RAM templates to Track A

Both templates use the same Authentication tab settings: OAuth client credentials, the team's
client id and secret from `clients.csv`, token URL `$VIYA_URL/SASLogon/oauth/token`, scope empty.

**SAS MCP template** (`ghcr.io/raedaldweik/sas-mcp-server:ram`, or `ghcr.io/sassoftware/sas-mcp-server:latest`):

| Field | Value |
|---|---|
| Requested CPU · Memory | **1** · 1G (the server needs a quarter of a core; a 10-core request can keep a second instance from scheduling) |
| `MCP_MODE` | `http` (the browser-OAuth server; RAM's client token is accepted through the next line) |
| `ALLOW_RAW_BEARER` | `true` |
| `VIYA_ENDPOINT`, `SSL_VERIFY`, `COMPUTE_CONTEXT_NAME` | as today |
| `MCP_TIERS` · `MCP_READ_ONLY` | `0,1,2,5,6` · `false` |
| `MCP_SERVER_NAME` | `sas-viya-A` … per instance |
| `VIYA_REFRESH_TOKEN`, `CLIENT_ID`, `SCOPE_ENFORCE` | remove |

Instantiate it four or five times, one Design Thinking Agent copy per instance.

**Bootcamp MCP template** (`ghcr.io/raedaldweik/bootcamp-mcp:latest`): same Authentication tab,
`VIYA_ENDPOINT`, `ALLOW_RAW_BEARER=true`, `ALLOWED_TABLES`, `ALLOWED_MODELS`, `MCP_SERVER_NAME`, CPU 1,
memory 1G; one instance per team, each with its own client.

## 6. Tear down after the bootcamp

```
python create_team_clients.py --teams 10 --delete
```
