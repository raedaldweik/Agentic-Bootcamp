#!/usr/bin/env python3
"""Create (or delete) the per-team OAuth clients the RAM tool sources sign in with.

Mirrors SAS's ``create_viya_oauth_client.py`` from the RAM examples, for N teams at once:
one client per team (client_credentials grant, its own UID/GID, `authorities` = its id),
one Viya group per client with the same id, and one parent group ``bootcamp-clients``
that every team group is a member of, so the administrator grants the platform rights
(compute context, Public caslib, Model Studio) once, to the parent.

    export VIYA_URL=https://viya.example.com
    export ACCESS_TOKEN=<a Viya administrator's token>      # or CODE=<authorization code>
    python create_team_clients.py --teams 10 --out clients.csv
    python create_team_clients.py --teams 10 --delete           # tear down

Federated (Microsoft) administrators cannot use a password grant; get a token by opening
    $VIYA_URL/SASLogon/oauth/authorize?client_id=sas.cli&response_type=code
in a signed-in browser and exporting the code as CODE (valid ~10 minutes, single use).

Requires: Python 3.10+, ``pip install httpx``.
"""
from __future__ import annotations

import argparse
import csv
import os
import secrets
import sys
from urllib.parse import quote

import httpx

VIYA_URL = os.getenv("VIYA_URL", "").rstrip("/")
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() not in ("false", "0", "no")
PARENT_GROUP = os.getenv("PARENT_GROUP", "bootcamp-clients")


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def admin_token(client: httpx.Client) -> str:
    token = os.getenv("ACCESS_TOKEN")
    if token:
        return token
    code = os.getenv("CODE")
    if code:
        r = client.post(f"{VIYA_URL}/SASLogon/oauth/token", auth=("sas.cli", ""),
                        data={"grant_type": "authorization_code", "code": code.strip()})
        if r.status_code != 200:
            die(f"authorization code exchange failed: {r.status_code} {r.text[:200]}")
        return r.json()["access_token"]
    user, pw = os.getenv("VIYA_USERNAME"), os.getenv("VIYA_PASSWORD")
    if user and pw:
        r = client.post(f"{VIYA_URL}/SASLogon/oauth/token", auth=("sas.cli", ""),
                        data={"grant_type": "password", "username": user, "password": pw})
        if r.status_code != 200:
            die(f"password grant failed (federated accounts cannot use it): {r.status_code} {r.text[:200]}")
        return r.json()["access_token"]
    die("set ACCESS_TOKEN, or CODE from "
        f"{VIYA_URL}/SASLogon/oauth/authorize?client_id=sas.cli&response_type=code")
    return ""  # unreachable


def team_id(prefix: str, n: int) -> str:
    return f"{prefix}{n:02d}"


def create_group(client: httpx.Client, headers: dict, gid: str, name: str) -> None:
    r = client.post(f"{VIYA_URL}/identities/groups", headers=headers, json={"id": gid, "name": name})
    if r.status_code == 409:
        print(f"  group {gid}: exists")
    elif r.status_code in (200, 201):
        print(f"  group {gid}: created")
    else:
        print(f"  group {gid}: FAILED {r.status_code} {r.text[:200]}")


def add_group_to_group(client: httpx.Client, headers: dict, parent: str, child: str) -> None:
    r = client.put(f"{VIYA_URL}/identities/groups/{quote(parent, safe='')}/groupMembers/{quote(child, safe='')}",
                   headers=headers)
    if r.status_code in (200, 201, 204, 409):
        print(f"  {child} ∈ {parent}: ok")
    else:
        print(f"  {child} ∈ {parent}: FAILED {r.status_code} {r.text[:200]}")


def add_users(client: httpx.Client, headers: dict, gid: str, users: list[str]) -> None:
    for u in users:
        r = client.put(f"{VIYA_URL}/identities/groups/{quote(gid, safe='')}/userMembers/{quote(u.lower(), safe='')}",
                       headers=headers)
        status = "ok" if r.status_code in (200, 201, 204, 409) else f"FAILED {r.status_code}"
        print(f"  user {u} in {gid}: {status}")


def create_client_(client: httpx.Client, headers: dict, cid: str, secret: str, uid: int) -> bool:
    body = {"client_id": cid, "client_secret": secret, "authorities": [cid],
            "authorized_grant_types": ["client_credentials"], "uid": str(uid), "gid": str(uid)}
    r = client.post(f"{VIYA_URL}/SASLogon/oauth/clients", headers=headers, json=body)
    if r.status_code == 201:
        print(f"  client {cid}: created (uid/gid {uid})")
        return True
    if r.status_code == 409:
        print(f"  client {cid}: exists (secret unchanged; delete and recreate to rotate it)")
        return False
    print(f"  client {cid}: FAILED {r.status_code} {r.text[:200]}")
    return False


def delete_all(client: httpx.Client, headers: dict, prefix: str, teams: int) -> None:
    for n in range(1, teams + 1):
        cid = team_id(prefix, n)
        r = client.delete(f"{VIYA_URL}/SASLogon/oauth/clients/{cid}", headers=headers)
        print(f"  client {cid}: {'deleted' if r.status_code in (200, 204) else 'absent' if r.status_code == 404 else 'FAILED ' + str(r.status_code)}")
        r = client.delete(f"{VIYA_URL}/identities/groups/{quote(cid, safe='')}", headers=headers)
        print(f"  group {cid}: {'deleted' if r.status_code in (200, 204) else 'absent' if r.status_code == 404 else 'FAILED ' + str(r.status_code)}")
    r = client.delete(f"{VIYA_URL}/identities/groups/{quote(PARENT_GROUP, safe='')}", headers=headers)
    print(f"  group {PARENT_GROUP}: {'deleted' if r.status_code in (200, 204) else 'absent' if r.status_code == 404 else 'FAILED ' + str(r.status_code)}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--teams", type=int, default=10)
    ap.add_argument("--prefix", default="ram-team")
    ap.add_argument("--uid-start", type=int, default=2101, help="uid/gid of team 01; each team adds 1")
    ap.add_argument("--members", default="", help="comma-separated Viya user ids added to every team group (facilitators)")
    ap.add_argument("--out", default="clients.csv", help="where the client ids and secrets are written (keep it private)")
    ap.add_argument("--delete", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    if not VIYA_URL:
        die("VIYA_URL is not set")

    plan = [(team_id(a.prefix, n), a.uid_start + n - 1) for n in range(1, a.teams + 1)]
    if a.dry_run:
        print(f"Would {'delete' if a.delete else 'create'} on {VIYA_URL}:")
        for cid, uid in plan:
            print(f"  {cid}  uid/gid {uid}  group {cid} ∈ {PARENT_GROUP}")
        return

    with httpx.Client(verify=SSL_VERIFY, timeout=60) as client:
        headers = {"Authorization": f"Bearer {admin_token(client)}", "Content-Type": "application/json"}
        if a.delete:
            delete_all(client, headers, a.prefix, a.teams)
            return
        print(f"Parent group {PARENT_GROUP} (grant the platform rights to this one):")
        create_group(client, headers, PARENT_GROUP, "Bootcamp MCP clients (all teams)")
        members = [m.strip() for m in a.members.split(",") if m.strip()]
        rows = []
        for cid, uid in plan:
            print(f"Team {cid}:")
            create_group(client, headers, cid, f"Bootcamp team ({cid})")
            add_group_to_group(client, headers, PARENT_GROUP, cid)
            add_users(client, headers, cid, members)
            secret = secrets.token_urlsafe(24)
            if create_client_(client, headers, cid, secret, uid):
                rows.append({"client_id": cid, "client_secret": secret, "uid": uid,
                             "token_url": f"{VIYA_URL}/SASLogon/oauth/token"})
        if rows:
            with open(a.out, "w", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["client_id", "client_secret", "uid", "token_url"])
                w.writeheader(); w.writerows(rows)
            os.chmod(a.out, 0o600)
            print(f"\nWrote {len(rows)} client(s) to {a.out}. The secrets are shown nowhere else; keep the file private.")
        print(f"\nNext: grant {PARENT_GROUP} the compute context, Public caslib and Model Studio rights "
              f"(README.md), then run verify_team_client.py --csv {a.out}")


if __name__ == "__main__":
    main()
