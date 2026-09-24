#!/usr/bin/env python3
"""Prove that a team's OAuth client can do, on Viya, everything the bootcamp needs.

For each client: mint a token with client credentials (what RAM does), then walk the
exact calls the MCP servers make, in the order they fail on an under-authorised client:

  1. token          client_credentials grant against SASLogon
  2. context        the compute context is visible
  3. session        a compute session starts (the launcher runs SAS as the client's UID/GID;
                    this is the step that says "No user credentials could be found for OS
                    process launch" when the identity cannot launch)
  4. sas            a DATA step runs and the log names the identity SAS runs as
  5. cas read       Public.<table> is visible through casManagement (row count)
  6. fedsql         a FedSQL count through a CAS session inside the compute session, the
                    way query_data works
  7. cas write      (--write) a tiny table is created in Public with promote=yes and dropped
  8. mas            published models are listed; (--model) the step signature is readable
  9. model studio   (--automl) the Analytics Gateway project list is readable

    export VIYA_URL=https://viya.example.com
    python verify_team_client.py --csv clients.csv --write --model deterioration_ehs
    python verify_team_client.py --client-id ram-team01 --client-secret ... --write

Requires: Python 3.10+, ``pip install httpx``.
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
import time

import httpx

VIYA_URL = os.getenv("VIYA_URL", "").rstrip("/")
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() not in ("false", "0", "no")
HINTS = {
    "context": "grant the parent group access to the compute context (Environment Manager → Contexts → the context → Authorization)",
    "session": "the launcher cannot start SAS as this identity: check the client's uid/gid, then ask the administrator to read the launcher and identities logs for this client id",
    "sas": "the session started but the job failed: see the log lines above",
    "cas read": "grant the parent group Read on the Public caslib (Environment Manager → Data → Public → Authorization)",
    "fedsql": "the CAS session could not run FedSQL: CAS authorization on Public, or CAS itself is down",
    "cas write": "grant the parent group Write/Manage on Public, or use a per-team caslib",
    "mas": "grant the parent group access to SAS Micro Analytic Service (/microanalyticScore/**)",
    "model studio": "grant the parent group access to Model Studio (/analyticsGateway/** and /mlPipelineAutomation/**)",
}


def jwt_claims(token: str) -> dict:
    try:
        payload = token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except Exception:
        return {}


class Check:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []

    def ok(self, step: str, detail: str = "") -> None:
        self.rows.append((step, "PASS", detail)); print(f"  PASS  {step:13s} {detail}")

    def fail(self, step: str, detail: str) -> None:
        self.rows.append((step, "FAIL", detail)); print(f"  FAIL  {step:13s} {detail[:300]}\n        → {HINTS.get(step, '')}")


def run_job(client: httpx.Client, sid: str, code: str, timeout: float = 180) -> tuple[str, str, str]:
    r = client.post(f"{VIYA_URL}/compute/sessions/{sid}/jobs", json={"code": code.splitlines()})
    r.raise_for_status()
    jid = r.json()["id"]
    t0 = time.time()
    while True:
        st = client.get(f"{VIYA_URL}/compute/sessions/{sid}/jobs/{jid}/state").text.strip()
        if st in ("completed", "error", "warning", "canceled"):
            break
        if time.time() - t0 > timeout:
            return "timeout", "", ""
        time.sleep(1)
    log = "\n".join(i.get("line", "") for i in client.get(
        f"{VIYA_URL}/compute/sessions/{sid}/jobs/{jid}/log", params={"limit": 1000}).json().get("items", []))
    listing = "\n".join(i.get("line", "") for i in client.get(
        f"{VIYA_URL}/compute/sessions/{sid}/jobs/{jid}/listing", params={"limit": 1000}).json().get("items", []))
    return st, log, listing


def errors_in(log: str) -> str:
    return " | ".join(l.strip() for l in log.splitlines() if l.startswith("ERROR"))[:300]


def verify(client_id: str, secret: str, a: argparse.Namespace) -> Check:
    c = Check()
    print(f"\n{client_id} on {VIYA_URL}")
    with httpx.Client(verify=SSL_VERIFY, timeout=httpx.Timeout(30, read=180)) as anon:
        r = anon.post(f"{VIYA_URL}/SASLogon/oauth/token", auth=(client_id, secret),
                      data={"grant_type": "client_credentials"})
    if r.status_code != 200:
        c.fail("token", f"{r.status_code} {r.text[:200]}"); return c
    token = r.json()["access_token"]
    claims = jwt_claims(token)
    c.ok("token", f"sub={claims.get('sub')} client_id={claims.get('client_id')} expires_in={r.json().get('expires_in')}s")

    with httpx.Client(verify=SSL_VERIFY, timeout=httpx.Timeout(30, read=180),
                      headers={"Authorization": f"Bearer {token}"}) as v:
        # 2. context
        r = v.get(f"{VIYA_URL}/compute/contexts", params={"filter": f"eq(name,'{a.context}')"})
        items = r.json().get("items", []) if r.status_code == 200 else []
        if not items:
            c.fail("context", f"{r.status_code} no context named {a.context!r} visible to this client"); return c
        ctx_id = items[0]["id"]; c.ok("context", f"{a.context} ({ctx_id})")
        # 3. session
        r = v.post(f"{VIYA_URL}/compute/contexts/{ctx_id}/sessions", json={"name": "bootcamp-verify"})
        if r.status_code not in (200, 201):
            c.fail("session", f"{r.status_code} {r.text[:300]}"); return c
        sid = r.json()["id"]; c.ok("session", sid)
        try:
            # 4. sas
            st, log, listing = run_job(v, sid, 'data _null_; put "identity=&SYSUSERID"; run;')
            who = next((l for l in log.splitlines() if "identity=" in l), "")
            if st == "completed" and not errors_in(log):
                c.ok("sas", who.strip())
            else:
                c.fail("sas", f"state={st} {errors_in(log)}")
            # 5. cas read
            caslib, table = a.table.split(".", 1)
            r = v.get(f"{VIYA_URL}/casManagement/servers/{a.cas_server}/caslibs/{caslib}/tables/{table}")
            if r.status_code == 200:
                c.ok("cas read", f"{a.table}: {r.json().get('rowCount')} rows, {r.json().get('columnCount')} columns")
            else:
                c.fail("cas read", f"{r.status_code} {r.text[:200]}")
            # 6. fedsql through compute, like query_data
            code = (f"cas v; proc fedsql sessref=v; select count(*) as n from {a.table}; quit; cas v terminate;")
            st, log, listing = run_job(v, sid, code)
            if st == "completed" and not errors_in(log):
                c.ok("fedsql", " ".join(listing.split())[:80])
            else:
                c.fail("fedsql", f"state={st} {errors_in(log)}")
            # 7. cas write
            if a.write:
                name = f"ZZ_VERIFY_{client_id.replace('-', '_').upper()}"
                code = (f'cas w; libname wl cas caslib="{caslib}" sessref=w;\n'
                        f"data wl.{name} (promote=yes); x=1; run;\n"
                        f'proc casutil sessref=w; droptable casdata="{name}" incaslib="{caslib}" quiet; run;\n'
                        f"cas w terminate;")
                st, log, listing = run_job(v, sid, code)
                if st == "completed" and not errors_in(log):
                    c.ok("cas write", f"created and dropped {caslib}.{name}")
                else:
                    c.fail("cas write", f"state={st} {errors_in(log)}")
            # 8. mas
            r = v.get(f"{VIYA_URL}/microanalyticScore/modules", params={"limit": 5})
            if r.status_code == 200:
                names = [m.get("id") for m in r.json().get("items", [])]
                c.ok("mas", f"{r.json().get('count', len(names))} modules visible, e.g. {names[:3]}")
                if a.model:
                    r = v.get(f"{VIYA_URL}/microanalyticScore/modules/{a.model}/steps/score")
                    if r.status_code == 200:
                        c.ok("mas", f"{a.model}: {len(r.json().get('inputs', []))} inputs")
                    else:
                        c.fail("mas", f"{a.model}: {r.status_code} {r.text[:200]}")
            else:
                c.fail("mas", f"{r.status_code} {r.text[:200]}")
            # 9. model studio
            if a.automl:
                r = v.get(f"{VIYA_URL}/mlPipelineAutomation/projects", params={"limit": 1})
                if r.status_code == 200:
                    c.ok("model studio", "project list readable")
                else:
                    c.fail("model studio", f"{r.status_code} {r.text[:200]}")
        finally:
            v.delete(f"{VIYA_URL}/compute/sessions/{sid}")
    return c


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="clients.csv from create_team_clients.py (verifies every row)")
    ap.add_argument("--client-id"); ap.add_argument("--client-secret")
    ap.add_argument("--context", default=os.getenv("COMPUTE_CONTEXT_NAME", "SAS Job Execution compute context"))
    ap.add_argument("--cas-server", default="cas-shared-default")
    ap.add_argument("--table", default="Public.EHS_DIABETES")
    ap.add_argument("--write", action="store_true", help="also create and drop a table in the caslib")
    ap.add_argument("--model", default="", help="a published MAS module id to read the signature of")
    ap.add_argument("--automl", action="store_true", help="also check Model Studio access")
    a = ap.parse_args()
    if not VIYA_URL:
        print("error: VIYA_URL is not set", file=sys.stderr); sys.exit(1)
    clients: list[tuple[str, str]] = []
    if a.csv:
        with open(a.csv) as f:
            clients = [(r["client_id"], r["client_secret"]) for r in csv.DictReader(f)]
    elif a.client_id and a.client_secret:
        clients = [(a.client_id, a.client_secret)]
    else:
        print("error: give --csv or --client-id and --client-secret", file=sys.stderr); sys.exit(1)
    failed = 0
    for cid, secret in clients:
        c = verify(cid, secret, a)
        failed += any(s == "FAIL" for _, s, _ in c.rows)
    print(f"\n{len(clients) - failed}/{len(clients)} client(s) passed every check.")
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
