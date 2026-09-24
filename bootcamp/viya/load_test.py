#!/usr/bin/env python3
"""Put the bootcamp day's Viya load on Viya before the day, without the room.

Models what the MCP servers do on Track A: one warm compute session per team (one
client identity each), participants' questions as FedSQL queries through that
session (query_data's pattern: a CAS session inside the compute session, created and
terminated per query), and model scoring calls against SAS Micro Analytic Service.
No LLM is involved, so this is the Viya half of the day in isolation.

    export VIYA_URL=https://viya.example.com
    python load_test.py --csv clients.csv --workers-per-team 5 --iterations 4 --model deterioration_ehs

Defaults: 10 teams × 5 workers = 50 participants asking 4 questions each, one query
at a time per team session (that is how a shared compute session behaves), scoring in
parallel. Read the summary: p95 under 30 s and zero errors is a pass; a burst of
"session" or "launch" errors means Viya, not the app.

Requires: Python 3.10+, ``pip install httpx``.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import os
import random
import statistics
import sys
import time
import uuid

import httpx

VIYA_URL = os.getenv("VIYA_URL", "").rstrip("/")
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() not in ("false", "0", "no")

QUERIES = [
    "select region, count(*) as n from {t} group by region",
    "select count(*) as n from {t} where hba1c_latest >= 9",
    "select facility_name, avg(hba1c_latest) as mean_hba1c from {t} group by facility_name",
    "select registry_risk_tier, avg(annual_cost_aed) as cost from {t} group by registry_risk_tier",
    "select nationality, sum(case when glycaemic_control='well_controlled' then 1 else 0 end)*100.0/count(*) as pct from {t} group by nationality",
]
SCORE_INPUTS = {"age": 53, "bmi": 31.7, "hba1c_latest": 9.9, "sbp_latest": 147, "egfr_latest": 74, "adherence_pdc": 0.71}


class Stats:
    def __init__(self) -> None:
        self.lat: dict[str, list[float]] = {}
        self.err: dict[str, list[str]] = {}

    def add(self, step: str, seconds: float, error: str | None = None) -> None:
        self.lat.setdefault(step, []).append(seconds)
        if error:
            self.err.setdefault(step, []).append(error[:160])

    def report(self) -> None:
        print(f"\n{'step':10s} {'n':>5s} {'errors':>6s} {'p50 s':>7s} {'p95 s':>7s} {'max s':>7s}")
        for step, xs in self.lat.items():
            xs = sorted(xs); e = len(self.err.get(step, []))
            print(f"{step:10s} {len(xs):5d} {e:6d} {xs[len(xs)//2]:7.1f} {xs[max(0, int(len(xs)*0.95)-1)]:7.1f} {xs[-1]:7.1f}")
        for step, errs in self.err.items():
            distinct = list(dict.fromkeys(errs))[:3]
            print(f"\n{step}: {len(errs)} error(s), e.g.")
            for d in distinct:
                print(f"  - {d}")


async def token_for(client: httpx.AsyncClient, cid: str, secret: str) -> str:
    r = await client.post(f"{VIYA_URL}/SASLogon/oauth/token", auth=(cid, secret), data={"grant_type": "client_credentials"})
    r.raise_for_status()
    return r.json()["access_token"]


async def run_job(v: httpx.AsyncClient, sid: str, code: str, timeout: float) -> tuple[str, str]:
    r = await v.post(f"{VIYA_URL}/compute/sessions/{sid}/jobs", json={"code": code.splitlines()})
    r.raise_for_status()
    jid = r.json()["id"]
    t0 = time.time()
    while True:
        st = (await v.get(f"{VIYA_URL}/compute/sessions/{sid}/jobs/{jid}/state")).text.strip()
        if st in ("completed", "error", "warning", "canceled"):
            break
        if time.time() - t0 > timeout:
            return "timeout", ""
        await asyncio.sleep(0.5)
    log = await v.get(f"{VIYA_URL}/compute/sessions/{sid}/jobs/{jid}/log", params={"limit": 1000})
    errors = " | ".join(i.get("line", "") for i in log.json().get("items", []) if i.get("line", "").startswith("ERROR"))
    return st, errors


async def team(cid: str, secret: str, a: argparse.Namespace, stats: Stats) -> None:
    async with httpx.AsyncClient(verify=SSL_VERIFY, timeout=httpx.Timeout(30, read=300)) as anon:
        try:
            token = await token_for(anon, cid, secret)
        except Exception as e:
            stats.add("token", 0.0, f"{cid}: {e}"); return
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(verify=SSL_VERIFY, timeout=httpx.Timeout(30, read=300), headers=headers) as v:
        # one warm compute session per team, like the MCP server
        t0 = time.time()
        try:
            r = await v.get(f"{VIYA_URL}/compute/contexts", params={"filter": f"eq(name,'{a.context}')"})
            ctx = r.json()["items"][0]["id"]
            r = await v.post(f"{VIYA_URL}/compute/contexts/{ctx}/sessions", json={"name": f"bootcamp-load-{cid}"})
            r.raise_for_status()
            sid = r.json()["id"]
            stats.add("session", time.time() - t0)
        except Exception as e:
            stats.add("session", time.time() - t0, f"{cid}: {e}"); return
        lock = asyncio.Lock()  # a compute session runs one job at a time

        async def worker(w: int) -> None:
            for i in range(a.iterations):
                q = random.choice(QUERIES).format(t=a.table)
                uid = uuid.uuid4().hex[:6]
                code = f"cas q{uid}; proc fedsql sessref=q{uid}; {q}; quit; cas q{uid} terminate;"
                t1 = time.time()
                try:
                    async with lock:
                        st, errs = await run_job(v, sid, code, a.timeout)
                    stats.add("query", time.time() - t1, errs or (None if st == "completed" else st))
                except Exception as e:
                    stats.add("query", time.time() - t1, f"{cid}: {e}")
                if a.model:
                    t2 = time.time()
                    try:
                        r = await v.post(f"{VIYA_URL}/microanalyticScore/modules/{a.model}/steps/score",
                                         json={"inputs": [{"name": k, "value": val} for k, val in SCORE_INPUTS.items()]})
                        stats.add("score", time.time() - t2, None if r.status_code == 201 or r.status_code == 200 else f"{r.status_code} {r.text[:120]}")
                    except Exception as e:
                        stats.add("score", time.time() - t2, f"{cid}: {e}")
                await asyncio.sleep(random.uniform(0.5, a.think))

        try:
            await asyncio.gather(*[worker(w) for w in range(a.workers_per_team)])
        finally:
            await v.delete(f"{VIYA_URL}/compute/sessions/{sid}")


async def main_async(a: argparse.Namespace) -> None:
    with open(a.csv) as f:
        clients = [(r["client_id"], r["client_secret"]) for r in csv.DictReader(f)][: a.teams or None]
    print(f"{len(clients)} team(s) × {a.workers_per_team} participants × {a.iterations} questions on {VIYA_URL}")
    stats = Stats()
    t0 = time.time()
    await asyncio.gather(*[team(cid, s, a, stats) for cid, s in clients])
    print(f"\nwall {time.time() - t0:.0f}s")
    stats.report()
    total_err = sum(len(v) for v in stats.err.values())
    p95q = sorted(stats.lat.get("query", [0]))[max(0, int(len(stats.lat.get('query', [0])) * 0.95) - 1)]
    print(f"\n{'PASS' if total_err == 0 and p95q < 30 else 'FAIL'}: {total_err} error(s), query p95 {p95q:.1f}s (pass = 0 errors and p95 < 30 s)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", required=True)
    ap.add_argument("--teams", type=int, default=0, help="use only the first N clients (default all)")
    ap.add_argument("--workers-per-team", type=int, default=5)
    ap.add_argument("--iterations", type=int, default=4)
    ap.add_argument("--think", type=float, default=5.0, help="max seconds a participant 'thinks' between questions")
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--context", default=os.getenv("COMPUTE_CONTEXT_NAME", "SAS Job Execution compute context"))
    ap.add_argument("--table", default="Public.EHS_DIABETES")
    ap.add_argument("--model", default="", help="MAS module id to score against on every question")
    a = ap.parse_args()
    if not VIYA_URL:
        print("error: VIYA_URL is not set", file=sys.stderr); sys.exit(1)
    asyncio.run(main_async(a))


if __name__ == "__main__":
    main()
