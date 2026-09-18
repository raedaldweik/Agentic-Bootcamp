"""Shared fixtures: a fake Viya behind httpx.MockTransport, and an in-process MCP client."""

from __future__ import annotations

import json
import os
import re
from contextlib import asynccontextmanager
from typing import Any

# Environment first: sas_mcp_server.config validates VIYA_ENDPOINT at import.
os.environ.setdefault("VIYA_ENDPOINT", "https://viya.test")
os.environ.setdefault("VIYA_AUTH", "true")
os.environ.setdefault("ALLOWED_TABLES", "CASUSER.REGISTRY_TEAM3,Public.EHS_FACILITIES")
os.environ.setdefault("ALLOWED_MODELS", "deterioration_team3")

import httpx
import pytest
from fastmcp import Client, FastMCP

VIYA = "https://viya.test"


class FakeViya:
    """Just enough of casManagement, dataTables/rowSets, compute and MAS to drive the tools."""

    def __init__(self) -> None:
        self.requests: list[tuple[str, str, dict[str, Any] | None]] = []
        self.tables: dict[str, dict[str, Any]] = {
            "CASUSER/REGISTRY_TEAM3": {
                "rowCount": 4000,
                "columnCount": 54,
                "state": "loaded",
                "scope": "global",
            },
            "PUBLIC/EHS_FACILITIES": {"rowCount": 18, "columnCount": 4, "state": "loaded", "scope": "global"},
        }
        self.columns = [
            {"name": "patient_id", "type": "char", "rawLength": 12, "label": "", "format": "$12."},
            {"name": "hba1c_latest", "type": "double", "rawLength": 8, "label": "", "format": ""},
            {"name": "bmi", "type": "double", "rawLength": 8, "label": "", "format": ""},
        ]
        self.rows = [
            {"cells": ["EHS-100092", 10.3, 31.7]},
            {"cells": ["EHS-100001", 6.8, 27.0]},
        ]
        self.modules: dict[str, dict[str, Any]] = {
            "deterioration_team3": {
                "id": "deterioration_team3",
                "name": "deterioration_team3",
                "description": "Champion GBM",
                "stepIds": ["score"],
            }
        }
        self.signature = {
            "id": "score",
            "inputs": [
                {"name": "hba1c_latest", "type": "decimal"},
                {"name": "bmi", "type": "decimal"},
                {"name": "patient_id", "type": "string"},
            ],
            "outputs": [{"name": "P_deterioration_next_12m1", "type": "decimal"}],
        }
        self.scored: list[dict[str, Any]] = []
        # compute: the query results served for WORK/_Q<uid> and WORK/_F<uid>
        self.query_columns = [
            {"name": "region", "type": "char", "format": "$20."},
            {"name": "n", "type": "double", "format": ""},
        ]
        self.query_rows = [{"cells": ["Ajman", 500]}, {"cells": ["Sharjah", 1200]}]

    @staticmethod
    def _json(payload: Any, status: int = 200) -> httpx.Response:
        return httpx.Response(status, json=payload)

    def handler(self, request: httpx.Request) -> httpx.Response:
        method, path = request.method, request.url.path
        body = json.loads(request.content) if request.content else None
        self.requests.append((method, path, body))

        m = re.fullmatch(r"/casManagement/servers/([^/]+)/caslibs/([^/]+)/tables/([^/]+)", path)
        if m and method == "GET":
            info = self.tables.get(f"{m.group(2).upper()}/{m.group(3).upper()}")
            return self._json(info) if info else self._json({"message": "not found"}, 404)
        m = re.fullmatch(r"/casManagement/servers/([^/]+)/caslibs/([^/]+)/tables/([^/]+)/columns", path)
        if m and method == "GET":
            if f"{m.group(2).upper()}/{m.group(3).upper()}" not in self.tables:
                return self._json({"message": "not found"}, 404)
            return self._json({"items": self.columns, "count": len(self.columns)})
        m = re.fullmatch(r"/casManagement/servers/([^/]+)/caslibs/([^/]+)/tables", path)
        if m and method == "GET":
            items = [
                {"name": key.split("/")[1], **val}
                for key, val in self.tables.items()
                if key.split("/")[0] == m.group(2).upper()
            ]
            return self._json({"items": items, "count": len(items)})
        if method == "GET" and path.startswith("/dataTables/dataSources/") and path.endswith("/columns"):
            return self._json({"items": self.columns, "count": len(self.columns)})
        if method == "GET" and path.startswith("/rowSets/tables/"):
            limit = int(request.url.params.get("limit", 100))
            return self._json({"items": self.rows[:limit], "count": len(self.rows)})
        # MAS
        m = re.fullmatch(r"/microanalyticScore/modules/([^/]+)", path)
        if m and method == "GET":
            mod = self.modules.get(m.group(1))
            return self._json(mod) if mod else self._json({"message": "no module"}, 404)
        if method == "GET" and path == "/microanalyticScore/modules":
            return self._json({"items": list(self.modules.values()), "count": len(self.modules)})
        m = re.fullmatch(r"/microanalyticScore/modules/([^/]+)/steps/([^/]+)", path)
        if m and method == "GET":
            if m.group(1) not in self.modules:
                return self._json({"message": "no module"}, 404)
            return self._json(self.signature)
        if m and method == "POST":
            self.scored.append(body)
            values = {i["name"]: i["value"] for i in body["inputs"]}
            p = 0.1 + 0.05 * float(values.get("hba1c_latest") or 0)
            return self._json({"outputs": [{"name": "P_deterioration_next_12m1", "value": round(p, 3)}]})
        # compute: column/row reads of the scratch tables
        m = re.fullmatch(r"/compute/sessions/([^/]+)/data/WORK/_[QF]([0-9a-f]+)/(columns|rows)", path)
        if m and method == "GET":
            if m.group(3) == "columns":
                return self._json({"items": self.query_columns, "count": len(self.query_columns)})
            return self._json({"items": self.query_rows, "count": len(self.query_rows)})
        return self._json({"message": f"unrouted {method} {path}"}, 404)


@pytest.fixture
def fake() -> FakeViya:
    return FakeViya()


@pytest.fixture
def submitted() -> list[str]:
    """SAS code submitted to the (patched) compute session, in order."""
    return []


@pytest.fixture
def mcp_client(fake: FakeViya, submitted: list[str], monkeypatch):
    """An in-process MCP client over a server whose Viya is *fake*."""
    import sas_mcp_server.tools._common as common
    from sas_mcp_server import viya_client

    from bootcamp_mcp import tools as bootcamp_tools
    from bootcamp_mcp.scope import ModelScope, TableScope

    transport = httpx.MockTransport(fake.handler)

    def make_client(token: str | None):
        return httpx.AsyncClient(transport=transport, base_url=VIYA)

    async def get_cached_session(client, context_name, token):
        return "sess-1"

    async def submit_job(client, session_id, code):
        submitted.append(code)
        return f"job-{len(submitted)}"

    async def wait_job(client, session_id, job_id, poll=2):
        return "completed", "NOTE: PROC FEDSQL used 0.1 seconds.", ""

    monkeypatch.setattr(common, "make_client", make_client)
    monkeypatch.setattr(common, "get_cached_session", get_cached_session)
    monkeypatch.setattr(bootcamp_tools, "submit_job", submit_job)
    monkeypatch.setattr(bootcamp_tools, "wait_job", wait_job)
    monkeypatch.setattr(viya_client, "VIYA_ENDPOINT", VIYA)
    monkeypatch.setattr(bootcamp_tools, "VIYA_ENDPOINT", VIYA)

    @asynccontextmanager
    async def build(
        tables: str = "CASUSER.REGISTRY_TEAM3,Public.EHS_FACILITIES", models: str = "deterioration_team3"
    ):
        mcp = FastMCP("bootcamp-test")

        async def get_token(ctx):
            return "test-token"

        bootcamp_tools.register(
            mcp,
            get_token,
            tables=TableScope.from_env(tables),
            models=ModelScope.from_env(models),
            cas_server="cas-shared-default",
            context_name="Test Context",
            max_rows=500,
            max_score_rows=50,
        )
        async with Client(mcp) as client:
            yield client

    return build


def result_of(call) -> dict[str, Any]:
    """The structured payload of a FastMCP tool result."""
    return call.data if call.data is not None else json.loads(call.content[0].text)
