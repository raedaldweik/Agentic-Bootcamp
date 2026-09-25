#!/usr/bin/env python3
"""Load the bootcamp registry into the Public caslib of a Viya environment.

Uploads ``../data/ehs_diabetes_registry.csv`` and ``../data/ehs_facilities.csv`` to the
Viya Files service, then in one compute session reads each file with a DATA step whose
column types and lengths are derived from the CSV itself (no guessing), loads it into
``Public`` as a promoted (global) table, and saves a copy to the caslib's disk so it can
be reloaded after a CAS restart. Running it again replaces the tables.

    set VIYA_URL=https://viya.example.com
    python load_registry.py --csv clients.csv            # authenticates as the first team client
    python load_registry.py --client-id ... --client-secret ...

Any identity with CreateTable, Promote and DropTable on Public works; the team clients
have them (verify_team_client.py proves it). Requires: Python 3.10+, ``pip install httpx``.
"""
from __future__ import annotations

import argparse
import csv
import math
import os
import sys
import time
from pathlib import Path

import httpx

VIYA_URL = os.getenv("VIYA_URL", "").rstrip("/")
SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() not in ("false", "0", "no")
HERE = Path(__file__).resolve().parent
TABLES = [  # (CSV file, CAS table name)
    ("ehs_diabetes_registry.csv", "EHS_DIABETES"),
    ("ehs_facilities.csv", "EHS_FACILITIES"),
]


def die(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr); sys.exit(1)


def columns(path: Path) -> tuple[list[tuple[str, str, int]], int]:
    """(name, 'num'|'char', byte length) per column, plus the row count."""
    with path.open(encoding="utf-8", newline="") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    spec = []
    for i, name in enumerate(header):
        vals = [r[i] if i < len(r) else "" for r in rows]
        nonempty = [v for v in vals if v != ""]
        numeric = bool(nonempty)
        for v in nonempty:
            try:
                float(v)
            except ValueError:
                numeric = False; break
        width = max((len(v.encode("utf-8")) for v in vals), default=1)
        spec.append((name, "num" if numeric else "char", max(4, int(math.ceil(width / 4.0)) * 4)))
    return spec, len(rows)


def sas_program(file_id: str, table: str, spec: list[tuple[str, str, int]]) -> str:
    lengths = " ".join(f"{n} ${w}" if t == "char" else f"{n} 8" for n, t, w in spec)
    inputs = " ".join(f"{n} $" if t == "char" else n for n, t, _ in spec)
    return "\n".join([
        f'filename src filesrvc fileuri="/files/files/{file_id}";',
        f"data work.{table};",
        '  infile src dsd firstobs=2 truncover lrecl=32767 encoding="utf-8";',
        f"  length {lengths};",
        f"  input {inputs};",
        "run;",
        "cas s;",
        'libname pub cas caslib="Public" sessref=s;',
        f'proc casutil sessref=s; droptable casdata="{table}" incaslib="Public" quiet; quit;',
        f"data pub.{table} (promote=yes); set work.{table}; run;",
        "cas s terminate;",
    ])


def save_program(table: str) -> str:
    return "\n".join([
        "cas s;",
        f'proc casutil sessref=s; save casdata="{table}" incaslib="Public" outcaslib="Public" '
        f'casout="{table}.sashdat" replace; quit;',
        "cas s terminate;",
    ])


def run_job(client: httpx.Client, sid: str, code: str, timeout: float = 600) -> tuple[str, str]:
    r = client.post(f"{VIYA_URL}/compute/sessions/{sid}/jobs", json={"code": code.splitlines()})
    r.raise_for_status()
    jid = r.json()["id"]
    t0 = time.time()
    while True:
        st = client.get(f"{VIYA_URL}/compute/sessions/{sid}/jobs/{jid}/state").text.strip()
        if st in ("completed", "error", "warning", "canceled"):
            break
        if time.time() - t0 > timeout:
            return "timeout", ""
        time.sleep(1)
    log = "\n".join(i.get("line", "") for i in client.get(
        f"{VIYA_URL}/compute/sessions/{sid}/jobs/{jid}/log", params={"limit": 5000}).json().get("items", []))
    return st, log


def errors_in(log: str) -> str:
    return " | ".join(l.strip() for l in log.splitlines() if l.startswith("ERROR"))[:400]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--csv", help="clients.csv from create_team_clients.py (the first client is used)")
    ap.add_argument("--client-id"); ap.add_argument("--client-secret")
    ap.add_argument("--context", default=os.getenv("COMPUTE_CONTEXT_NAME", "SAS Job Execution compute context"))
    ap.add_argument("--cas-server", default="cas-shared-default")
    ap.add_argument("--data-dir", default=str(HERE.parent / "data"), help="folder holding the two CSVs")
    ap.add_argument("--no-save", action="store_true", help="load into memory only, do not save a copy to the caslib's disk")
    a = ap.parse_args()
    if not VIYA_URL:
        die("VIYA_URL is not set")
    if a.csv:
        with open(a.csv) as f:
            first = next(csv.DictReader(f))
        client_id, secret = first["client_id"], first["client_secret"]
    elif a.client_id and a.client_secret:
        client_id, secret = a.client_id, a.client_secret
    else:
        die("give --csv or --client-id and --client-secret")
    data_dir = Path(a.data_dir)
    for fn, _ in TABLES:
        if not (data_dir / fn).exists():
            die(f"{data_dir / fn} not found")

    with httpx.Client(verify=SSL_VERIFY, timeout=httpx.Timeout(60, read=600)) as anon:
        r = anon.post(f"{VIYA_URL}/SASLogon/oauth/token", auth=(client_id, secret),
                      data={"grant_type": "client_credentials"})
        if r.status_code != 200:
            die(f"token for {client_id}: {r.status_code} {r.text[:200]}")
        token = r.json()["access_token"]
    print(f"Loading into Public on {VIYA_URL} as {client_id}")

    failed = 0
    with httpx.Client(verify=SSL_VERIFY, timeout=httpx.Timeout(60, read=600),
                      headers={"Authorization": f"Bearer {token}"}) as v:
        r = v.get(f"{VIYA_URL}/compute/contexts", params={"filter": f"eq(name,'{a.context}')"})
        items = r.json().get("items", []) if r.status_code == 200 else []
        if not items:
            die(f"compute context {a.context!r} not visible: {r.status_code} {r.text[:200]}")
        r = v.post(f"{VIYA_URL}/compute/contexts/{items[0]['id']}/sessions", json={"name": "bootcamp-load"})
        if r.status_code not in (200, 201):
            die(f"compute session: {r.status_code} {r.text[:300]}")
        sid = r.json()["id"]
        uploaded: list[str] = []
        try:
            for fn, table in TABLES:
                path = data_dir / fn
                spec, nrows = columns(path)
                print(f"\n{table} from {fn}: {nrows} rows, {len(spec)} columns")
                r = v.post(f"{VIYA_URL}/files/files", params={"filename": fn},
                           content=path.read_bytes(),
                           headers={"Content-Type": "text/csv", "Accept": "application/vnd.sas.file+json"})
                if r.status_code not in (200, 201):
                    print(f"  FAIL  upload      {r.status_code} {r.text[:200]}"); failed += 1; continue
                file_id = r.json()["id"]; uploaded.append(file_id)
                print(f"  ok    upload      files/files/{file_id}")
                st, log = run_job(v, sid, sas_program(file_id, table, spec))
                if st != "completed" or errors_in(log):
                    print(f"  FAIL  load        state={st} {errors_in(log)}"); failed += 1; continue
                r = v.get(f"{VIYA_URL}/casManagement/servers/{a.cas_server}/caslibs/Public/tables/{table}")
                got = (r.json().get("rowCount"), r.json().get("columnCount")) if r.status_code == 200 else None
                if got == (nrows, len(spec)):
                    print(f"  ok    load        Public.{table} promoted: {got[0]} rows, {got[1]} columns")
                else:
                    print(f"  FAIL  load        Public.{table} shows {got}, expected ({nrows}, {len(spec)})"); failed += 1; continue
                if not a.no_save:
                    st, log = run_job(v, sid, save_program(table))
                    if st == "completed" and not errors_in(log):
                        print(f"  ok    save        {table}.sashdat written to the Public caslib (survives a CAS restart)")
                    else:
                        print(f"  note  save        not saved to disk, in memory only: {errors_in(log) or st}. "
                              "Rerun this script after a CAS restart.")
        finally:
            for fid in uploaded:
                v.delete(f"{VIYA_URL}/files/files/{fid}")
            v.delete(f"{VIYA_URL}/compute/sessions/{sid}")
    if failed:
        print(f"\n{failed} table(s) failed."); sys.exit(1)
    print("\nBoth tables are in Public. Next: python verify_team_client.py --csv clients.csv --write")


if __name__ == "__main__":
    main()
