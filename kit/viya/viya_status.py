#!/usr/bin/env python3
"""One screen of facts about a Viya environment: is SAS Logon up, can my identity be
resolved for an OS launch, does CAS accept a session, and how many sessions and
launcher processes exist right now.

    set VIYA_URL=https://viya.example.com
    set CODE=<code from /SASLogon/oauth/authorize?client_id=sas.cli&response_type=code>
    python viya_status.py                      # as you, the administrator (sees every session)
    python viya_status.py --csv clients.csv    # as the first team client (sees its own)

Read-only. Requires: Python 3.10+, ``pip install httpx``.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import httpx

from create_team_clients import admin_token

VIYA_URL = os.getenv("VIYA_URL", "").rstrip("/")
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() not in ("false", "0", "no")


def line(status: str, what: str, detail: str) -> None:
    print(f"  {status:5s} {what:22s} {detail[:220]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="clients.csv: authenticate as the first team client instead of the administrator")
    ap.add_argument("--cas-server", default="cas-shared-default")
    a = ap.parse_args()
    if not VIYA_URL:
        print("error: VIYA_URL is not set", file=sys.stderr); sys.exit(1)
    print(f"{VIYA_URL}")
    with httpx.Client(verify=SSL_VERIFY, timeout=httpx.Timeout(20, read=60)) as anon:
        try:
            r = anon.get(f"{VIYA_URL}/SASLogon/token_keys")
            line("OK" if r.status_code == 200 else "FAIL", "sas logon", f"{r.status_code} token keys" if r.status_code == 200 else f"{r.status_code} {r.text[:120]}")
        except httpx.HTTPError as e:
            line("FAIL", "sas logon", f"unreachable: {e}")
            sys.exit(1)
        if a.csv:
            with open(a.csv) as f:
                first = next(csv.DictReader(f))
            r = anon.post(f"{VIYA_URL}/SASLogon/oauth/token", auth=(first["client_id"], first["client_secret"]),
                          data={"grant_type": "client_credentials"})
            if r.status_code != 200:
                line("FAIL", "token", f"{first['client_id']}: {r.status_code} {r.text[:120]}"); sys.exit(1)
            token = r.json()["access_token"]; line("OK", "token", f"client {first['client_id']}")
        else:
            token = admin_token(anon); line("OK", "token", "administrator")

    with httpx.Client(verify=SSL_VERIFY, timeout=httpx.Timeout(20, read=120),
                      headers={"Authorization": f"Bearer {token}"}) as v:
        # who am I, and can the platform turn me into an OS identity (what CAS and the launcher need)
        r = v.get(f"{VIYA_URL}/identities/users/@currentUser")
        me = r.json().get("id") if r.status_code == 200 else None
        line("OK" if me else "note", "identity", f"user {me}" if me else f"{r.status_code} (a client identity has no user record; that is normal)")
        if me:
            r = v.get(f"{VIYA_URL}/identities/users/@currentUser/identifier")
            if r.status_code == 200:
                line("OK", "os identity", f"uid={r.json().get('uid')} gid={r.json().get('gid')} (CAS and the launcher can run processes as you)")
            else:
                line("FAIL", "os identity", f"{r.status_code} {r.text[:160]} -> this is the 'No user credentials could be found for OS process launch' condition")
        # CAS: does it accept a session for me right now
        r = v.get(f"{VIYA_URL}/casManagement/servers/{a.cas_server}/caslibs", params={"limit": 1})
        if r.status_code == 200:
            line("OK", "cas session", f"{a.cas_server} answered ({r.json().get('count', '?')} caslibs)")
        else:
            line("FAIL", "cas session", f"{r.status_code} {r.text[:200]}")
        r = v.get(f"{VIYA_URL}/casManagement/servers/{a.cas_server}/sessions", params={"limit": 200})
        if r.status_code == 200:
            items = r.json().get("items", [])
            owners = sorted({s.get("owner", "?") for s in items})
            line("OK", "cas sessions", f"{len(items)} open; owners: {', '.join(owners) or 'none'}")
        else:
            line("note", "cas sessions", f"{r.status_code} (administrators see the list)")
        # compute and launcher
        r = v.get(f"{VIYA_URL}/compute/sessions", params={"limit": 200})
        if r.status_code == 200:
            items = r.json().get("items", [])
            owners = sorted({s.get("owner", "?") for s in items})
            line("OK", "compute sessions", f"{len(items)} open; owners: {', '.join(owners) or 'none'}")
        else:
            line("note", "compute sessions", f"{r.status_code} {r.text[:120]}")
        r = v.get(f"{VIYA_URL}/launcher/processes", params={"limit": 200})
        if r.status_code == 200:
            items = r.json().get("items", [])
            states = {}
            for p in items:
                states[p.get("state", "?")] = states.get(p.get("state", "?"), 0) + 1
            line("OK", "launcher processes", f"{len(items)}; " + ", ".join(f"{k}={n}" for k, n in sorted(states.items())))
        else:
            line("note", "launcher processes", f"{r.status_code} {r.text[:120]}")
        r = v.get(f"{VIYA_URL}/compute/contexts", params={"limit": 50})
        if r.status_code == 200:
            line("OK", "compute contexts", ", ".join(c.get("name", "?") for c in r.json().get("items", []))[:200])
        else:
            line("note", "compute contexts", f"{r.status_code}")


if __name__ == "__main__":
    main()
