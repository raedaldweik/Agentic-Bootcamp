"""The Sanad dataset: CSV tables, and a read-only SQL view of them.

Every table is a CSV in backend/data/sanad/, described in schema.json next to it.
A table that records things happening over time names its event-time column there;
the shop state "as of" a moment is then simply the rows up to that moment (see ops).

`Snapshot` is a small in-memory SQLite database built from a set of tables, used to
answer ad-hoc questions. Its queries come from a language model, so they are confined:
one SELECT (or WITH) statement, no writes, no PRAGMA or ATTACH, a time budget and a
row cap.
"""
from __future__ import annotations

import csv
import json
import os
import re
import sqlite3
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

DATA_DIR = Path(os.getenv("SANAD_DATA_DIR") or Path(__file__).resolve().parents[2] / "data" / "sanad")
MAX_ROWS = 200            # rows returned to the model per query
QUERY_BUDGET_S = 3.0      # wall-clock budget per statement


class QueryError(Exception):
    """A query the tool refuses or SQLite rejects; the message goes back to the model."""


_INT = re.compile(r"^-?\d+$")
_FLOAT = re.compile(r"^-?\d+\.\d+$")


def _infer(values: list[str]) -> str:
    seen = [v for v in values if v != ""]
    if not seen:
        return "TEXT"
    if all(_INT.match(v) for v in seen):
        return "INTEGER"
    if all(_INT.match(v) or _FLOAT.match(v) for v in seen):
        return "REAL"
    return "TEXT"


def _cast(v: str, kind: str) -> Any:
    if v == "":
        return None
    if kind == "INTEGER":
        return int(v)
    if kind == "REAL":
        return float(v)
    return v


@lru_cache(maxsize=1)
def raw() -> dict[str, Any]:
    """Everything on disk, typed: {note, scenario_start, tables: {name: {description, columns
    (name -> note), kinds (name -> SQL type), event_time, rows: [dict]}}}."""
    schema_path = DATA_DIR / "schema.json"
    schema = json.loads(schema_path.read_text()) if schema_path.exists() else {}
    described = schema.get("tables") or {}
    tables: dict[str, Any] = {}
    for path in sorted(DATA_DIR.glob("*.csv")):
        name = path.stem
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            if not header:
                continue
            lines = list(reader)
        kinds = {c: _infer([r[i] for r in lines if i < len(r)]) for i, c in enumerate(header)}
        rows = [{c: _cast(r[i] if i < len(r) else "", kinds[c]) for i, c in enumerate(header)} for r in lines]
        d = described.get(name) or {}
        tables[name] = {"description": d.get("description", ""),
                        "columns": {c: (d.get("columns") or {}).get(c, "") for c in header},
                        "kinds": kinds, "event_time": d.get("event_time"), "rows": rows}
    # keep the order schema.json gives (it reads masters first, then events)
    ordered = {n: tables[n] for n in described if n in tables}
    ordered.update({n: t for n, t in tables.items() if n not in ordered})
    return {"note": schema.get("note", ""), "scenario_start": schema.get("scenario_start", ""), "tables": ordered}


# ─── Read-only SQL over a set of tables ──────────────────────────────────
_ALLOWED = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, sqlite3.SQLITE_RECURSIVE}
_LEADING = re.compile(r"^\s*(select|with)\b", re.I)


def _authorize(action: int, arg1, arg2, dbname, source) -> int:
    return sqlite3.SQLITE_OK if action in _ALLOWED else sqlite3.SQLITE_DENY


def _single_statement(sql: str) -> str:
    """Strip comments and a trailing semicolon, then insist on one SELECT / WITH statement."""
    s = re.sub(r"--[^\n]*", " ", sql or "")
    s = re.sub(r"/\*.*?\*/", " ", s, flags=re.S).strip()
    s = s.rstrip(";").strip()
    if not s:
        raise QueryError("Empty query.")
    if not _LEADING.match(s):
        raise QueryError("Only SELECT statements (optionally starting WITH) are allowed.")
    if ";" in re.sub(r"'(?:[^']|'')*'", "''", s):
        raise QueryError("Send one statement at a time.")
    return s


class Snapshot:
    """An in-memory database of `tables` ({name: [row dict]}), read-only once built.
    One per question, used from a single thread at a time."""

    def __init__(self, tables: dict[str, list[dict]], *, now: str = ""):
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        for name, rows in tables.items():
            if not rows:
                cols = _EMPTY_COLUMNS.get(name)
                if cols:
                    self._db.execute(f'CREATE TABLE "{name}" ({", ".join(chr(34) + c + chr(34) for c in cols)})')
                continue
            cols = list(rows[0].keys())
            self._db.execute(f'CREATE TABLE "{name}" ({", ".join(chr(34) + c + chr(34) for c in cols)})')
            self._db.executemany(f'INSERT INTO "{name}" VALUES ({", ".join("?" * len(cols))})',
                                 [[_sqlable(r.get(c)) for c in cols] for r in rows])
        # the shop's "now": queries use now_ts() rather than the server's clock
        self._db.create_function("now_ts", 0, lambda: now, deterministic=True)
        self._db.commit()
        self._db.set_authorizer(_authorize)

    def run(self, sql: str, *, max_rows: int = MAX_ROWS) -> dict[str, Any]:
        """Run one read-only statement. Returns {columns, rows, row_count, truncated}."""
        statement = _single_statement(sql)
        deadline = time.monotonic() + QUERY_BUDGET_S
        self._db.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 20_000)
        try:
            cur = self._db.execute(statement)
            columns = [d[0] for d in cur.description or []]
            fetched = cur.fetchmany(max_rows + 1)
        except sqlite3.OperationalError as e:
            if "interrupted" in str(e).lower():
                raise QueryError(f"The query ran longer than {QUERY_BUDGET_S:.0f}s and was stopped. "
                                 "Aggregate or filter it further.") from e
            raise QueryError(f"SQLite: {e}") from e
        except sqlite3.DatabaseError as e:
            msg = str(e)
            if "not authorized" in msg.lower():
                msg = "Only reading is allowed (no writes, PRAGMA or ATTACH)."
            raise QueryError(f"SQLite: {msg}") from e
        finally:
            self._db.set_progress_handler(None, 0)
        truncated = len(fetched) > max_rows
        rows = [dict(zip(columns, (round(v, 4) if isinstance(v, float) else v for v in r)))
                for r in fetched[:max_rows]]
        return {"columns": columns, "rows": rows, "row_count": len(rows), "truncated": truncated}

    def close(self) -> None:
        try:
            self._db.close()
        except Exception:
            pass


def _sqlable(v: Any) -> Any:
    if v is None or isinstance(v, (int, float, str)):
        return v
    if isinstance(v, bool):
        return int(v)
    return str(v)


# Column lists for tables that can legitimately be empty at some moments, so a
# query against them returns no rows instead of "no such table".
_EMPTY_COLUMNS: dict[str, list[str]] = {}


def declare_columns(name: str, columns: list[str]) -> None:
    _EMPTY_COLUMNS[name] = columns


for _name, _t in raw()["tables"].items():
    declare_columns(_name, list(_t["columns"].keys()))
