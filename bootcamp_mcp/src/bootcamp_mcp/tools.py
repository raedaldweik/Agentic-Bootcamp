"""The eight bootcamp tools.

Every tool resolves its table or model through the scope first and refuses,
with a message that names what *is* allowed, before any request reaches Viya.
The Viya work itself is done with the upstream server's own building blocks:
``make_session_helpers`` (token → authenticated client, cached compute
session), the ``casManagement`` / ``rowSets`` / ``microanalyticScore`` REST
paths the upstream tools use, and the FedSQL helpers that generate, run and
read back a query. So a query here runs exactly the way ``query_data`` runs on
the 92-tool server, just on fewer tables.
"""

from __future__ import annotations

import contextlib
import uuid
from collections.abc import Awaitable, Callable
from typing import Annotated, Any

import httpx
from fastmcp import Context, FastMCP
from mcp.types import ToolAnnotations
from pydantic import BeforeValidator
from sas_mcp_server.helpers import fedsql_helpers
from sas_mcp_server.tools._common import coerce_json_dict, make_session_helpers
from sas_mcp_server.viya_client import (
    VIYA_ENDPOINT,
    get_json,
    get_paged_items,
    logger,
    post_json,
    raise_for_viya_status,
    return_items,
)
from sas_mcp_server.viya_utils import submit_job, wait_job

from .scope import ModelScope, ScopeError, TablePattern, TableRef, TableScope, check_where, qualify_query

# --- annotations -------------------------------------------------------------
# Same vocabulary as the upstream server's classification: a tool is read-only
# only if it neither changes state nor causes server-side work. query_data
# and the two scoring tools start work on Viya (a compute job, a MAS
# execution), so they are not read-only, but none of them can destroy anything.

READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {"list_tables", "describe_table", "preview_table", "list_models", "describe_model"}
)
WORK_TOOLS: frozenset[str] = frozenset({"query_data", "score", "score_table_rows"})
ALL_TOOLS: tuple[str, ...] = (
    "list_tables",
    "describe_table",
    "preview_table",
    "query_data",
    "list_models",
    "describe_model",
    "score",
    "score_table_rows",
)


def annotations_for(name: str) -> ToolAnnotations:
    if name in READ_ONLY_TOOLS:
        return ToolAnnotations(
            read_only_hint=True, destructive_hint=False, idempotent_hint=True, open_world_hint=False
        )
    return ToolAnnotations(
        read_only_hint=False, destructive_hint=False, idempotent_hint=True, open_world_hint=False
    )


JsonDict = Annotated[dict[str, Any], BeforeValidator(coerce_json_dict)]


def _out_of_scope(exc: ScopeError) -> dict[str, Any]:
    return {"status": "out_of_scope", "message": str(exc)}


def _is_404(exc: httpx.HTTPStatusError) -> bool:
    return exc.response is not None and exc.response.status_code == 404


def _cast_input(value: Any, mas_type: str) -> Any:
    """Coerce one value to what MAS expects for its declared input type."""
    if value is None or value == "":
        return None
    t = (mas_type or "").lower()
    if t in ("decimal", "double", "integer", "bigint", "int", "number"):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return str(value)


def register(
    mcp: FastMCP,
    get_token: Callable[[Context], Awaitable[str]],
    *,
    tables: TableScope,
    models: ModelScope,
    cas_server: str,
    context_name: str,
    max_rows: int = 500,
    max_score_rows: int = 50,
    score_step: str = "auto",
) -> list[str]:
    """Register the bootcamp tools on *mcp* and return the names registered.

    Table tools are registered only when ``tables`` is non-empty and model
    tools only when ``models`` is: a server configured without models simply
    has no scoring tools, so an agent cannot be told about a capability it
    does not have.
    """
    viya_session, compute_tool_session = make_session_helpers(get_token)
    registered: list[str] = []

    def tool(fn: Callable[..., Any]) -> Any:
        registered.append(fn.__name__)
        return mcp.tool(fn, annotations=annotations_for(fn.__name__))

    # --- shared Viya calls ---------------------------------------------------

    async def table_info(client: httpx.AsyncClient, ref: TableRef) -> dict[str, Any]:
        """One row of list_tables: casManagement's view of the table, or why not."""
        try:
            info = await get_json(
                f"/casManagement/servers/{cas_server}/caslibs/{ref.caslib}/tables/{ref.table}", client
            )
        except httpx.HTTPStatusError as exc:
            if _is_404(exc):
                return {
                    "table": ref.qualified,
                    "status": "not_loaded",
                    "message": (
                        f"{ref.qualified} is allowed but not in CAS memory (or does not exist yet). "
                        "Ask the facilitator or the Design Thinking Agent to load and promote it."
                    ),
                }
            raise
        return {
            "table": ref.qualified,
            "status": "ready",
            "rows": info.get("rowCount"),
            "columns": info.get("columnCount"),
            "state": info.get("state"),
            "scope": info.get("scope"),
        }

    async def tables_matching(client: httpx.AsyncClient, pattern: TablePattern) -> list[dict[str, Any]]:
        """Expand one wildcard pattern by listing the caslib(s) it names."""
        if "*" in pattern.caslib:
            items, _ = await get_paged_items(
                f"/casManagement/servers/{cas_server}/caslibs", client, limit=500
            )
            caslibs = [
                str(i["name"]) for i in items if i.get("name") and pattern.matches_caslib(str(i["name"]))
            ]
        else:
            caslibs = [pattern.caslib]
        rows: list[dict[str, Any]] = []
        for caslib in caslibs:
            try:
                items, _ = await get_paged_items(
                    f"/casManagement/servers/{cas_server}/caslibs/{caslib}/tables", client, limit=500
                )
            except httpx.HTTPStatusError as exc:
                if _is_404(exc):
                    continue
                raise
            for item in items:
                name = item.get("name", "")
                if pattern.matches(caslib, name):
                    rows.append(
                        {
                            "table": f"{caslib.upper()}.{name.upper()}",
                            "status": "ready",
                            "rows": item.get("rowCount"),
                            "columns": item.get("columnCount"),
                            "state": item.get("state"),
                            "scope": item.get("scope"),
                        }
                    )
        return rows

    async def run_query(ctx: Context, name: str, sql: str, limit: int, start: int) -> dict[str, Any]:
        """Run one scoped FedSQL SELECT the way the upstream ``query_data`` does.

        *sql* must already be screened and qualified. Returns the upstream
        result shape (``columns, rows, count, start, limit, truncated,
        column_types``) or one of its structured error dicts.
        """
        uid = uuid.uuid4().hex[:8]
        code = fedsql_helpers.build_query_code(sql, target="cas", limit=limit, start=start, uid=uid)
        async with compute_tool_session(name, ctx, context_name) as (client, session_id):
            job_id = await submit_job(client, session_id, code)
            state, log, _ = await wait_job(client, session_id, job_id, poll=0.5)
            try:
                mapped = fedsql_helpers.map_error(log)
                if mapped is not None:
                    return mapped
                if state != "completed":
                    return {
                        "status": "query_failed",
                        "message": f"The query ended in state '{state}' without a reported error.",
                        "sas_errors": [],
                    }
                col_items, _ = await get_paged_items(
                    f"/compute/sessions/{session_id}/data/WORK/_Q{uid}/columns", client, limit=1000
                )
                columns = fedsql_helpers.describe_columns(col_items)
                row_items, _ = await get_paged_items(
                    f"/compute/sessions/{session_id}/data/WORK/_F{uid}/rows",
                    client,
                    limit=limit + 1,
                    start=start,
                )
                truncated = len(row_items) > limit
                rows = fedsql_helpers.convert_rows(row_items[:limit], columns)
                return {
                    "columns": [c["name"] for c in columns],
                    "rows": rows,
                    "count": len(rows),
                    "start": start,
                    "limit": limit,
                    "truncated": truncated,
                    "column_types": {c["name"]: c["type"] for c in columns},
                }
            finally:
                with contextlib.suppress(Exception):
                    await submit_job(client, session_id, fedsql_helpers.build_cleanup_code(uid))

    async def module_and_step(client: httpx.AsyncClient, module_id: str) -> tuple[dict[str, Any], str]:
        """The MAS module document and the step this server scores with."""
        module = await get_json(f"/microanalyticScore/modules/{module_id}", client)
        if score_step != "auto":
            return module, score_step
        steps = [s for s in (module.get("stepIds") or []) if isinstance(s, str)]
        for preferred in ("score", "execute"):
            if preferred in steps:
                return module, preferred
        return module, (steps[0] if steps else "score")

    async def signature(client: httpx.AsyncClient, module_id: str, step: str) -> dict[str, Any]:
        return await get_json(f"/microanalyticScore/modules/{module_id}/steps/{step}", client)

    def model_not_found(module_id: str) -> dict[str, Any]:
        return {
            "model": module_id,
            "status": "not_found",
            "message": (
                f"Model {module_id!r} is allowed but is not published to SAS Micro Analytic Service yet. "
                "Publish the champion model first (the Design Thinking Agent does this), then try again."
            ),
        }

    def build_inputs(sig: dict[str, Any], provided: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
        """Match provided values to the signature's inputs, case-insensitively."""
        lookup = {str(k).lower(): v for k, v in provided.items()}
        inputs: dict[str, Any] = {}
        missing: list[str] = []
        for spec in sig.get("inputs") or []:
            name = spec.get("name")
            if not name:
                continue
            if name.lower() in lookup:
                inputs[name] = _cast_input(lookup[name.lower()], spec.get("type", ""))
            else:
                missing.append(name)
        return inputs, missing

    async def score_once(
        client: httpx.AsyncClient, module_id: str, step: str, inputs: dict[str, Any]
    ) -> dict[str, Any]:
        body = {"inputs": [{"name": k, "value": v} for k, v in inputs.items()]}
        result = await post_json(f"/microanalyticScore/modules/{module_id}/steps/{step}", client, body=body)
        outputs = result.get("outputs") if isinstance(result, dict) else None
        if isinstance(outputs, list):
            return {o.get("name"): o.get("value") for o in outputs if isinstance(o, dict) and o.get("name")}
        return result if isinstance(result, dict) else {"result": result}

    # --- table tools --------------------------------------------------------

    if tables:

        @tool
        async def list_tables(ctx: Context) -> dict[str, Any]:
            """List the tables this server can query, with their row and column counts.

            Start here. Only the tables configured for this bootcamp team are
            listed; nothing else on the Viya environment is visible or
            queryable through this server. A table shown as ``not_loaded`` is
            allowed but not yet in CAS memory.
            """
            async with viya_session("list_tables", ctx) as client:
                rows: list[dict[str, Any]] = []
                for pattern in tables.patterns:
                    if pattern.is_wildcard:
                        rows.extend(await tables_matching(client, pattern))
                    else:
                        rows.append(await table_info(client, TableRef(pattern.caslib, pattern.table)))
                return {"count": len(rows), "tables": rows, "cas_server": cas_server}

        @tool
        async def describe_table(table: str, ctx: Context) -> dict[str, Any]:
            """Columns of one allowed table: name, type, label and format, plus the row count.

            Call this before writing a query so column names and types are
            right. ``table`` is ``caslib.table`` (a bare table name works when
            only one caslib is in scope).
            """
            try:
                ref = tables.resolve(table)
            except ScopeError as exc:
                return _out_of_scope(exc)
            async with viya_session("describe_table", ctx) as client:
                try:
                    items, _ = await get_paged_items(
                        f"/casManagement/servers/{cas_server}/caslibs/{ref.caslib}/tables/{ref.table}/columns",
                        client,
                        limit=500,
                    )
                except httpx.HTTPStatusError as exc:
                    if _is_404(exc):
                        return {**(await table_info(client, ref)), "columns": []}
                    raise
                info = await table_info(client, ref)
                return {
                    "table": ref.qualified,
                    "rows": info.get("rows"),
                    "column_count": len(items),
                    "columns": return_items(items, ["name", "type", "rawLength", "label", "format"]),
                }

        @tool
        async def preview_table(table: str, ctx: Context, rows: int = 5) -> dict[str, Any]:
            """The first few rows of one allowed table, to see what the values look like.

            Args:
                table: ``caslib.table`` (bare name allowed when unambiguous).
                rows: How many rows (default 5, at most 100).
            """
            try:
                ref = tables.resolve(table)
            except ScopeError as exc:
                return _out_of_scope(exc)
            limit = max(1, min(int(rows), 100, max_rows))
            data_source_id = f"cas~fs~{cas_server}~fs~{ref.caslib}"
            table_id = f"cas~fs~{cas_server}~fs~{ref.caslib}~fs~{ref.table}"
            async with viya_session("preview_table", ctx) as client:
                columns: list[str] = []
                col_start, col_limit = 0, 100
                while True:
                    col_resp = await client.get(
                        f"{VIYA_ENDPOINT}/dataTables/dataSources/{data_source_id}/tables/{ref.table}/columns",
                        params={"start": col_start, "limit": col_limit},
                        follow_redirects=True,
                    )
                    if col_resp.status_code == 404:
                        return {**(await table_info(client, ref)), "rows": []}
                    raise_for_viya_status(col_resp)
                    col_data = col_resp.json()
                    columns.extend(str(item.get("name")) for item in col_data.get("items", []))
                    col_start += col_limit
                    if col_start >= col_data.get("count", 0):
                        break
                row_resp = await client.get(
                    f"{VIYA_ENDPOINT}/rowSets/tables/{table_id}/rows",
                    params={"start": 0, "limit": limit},
                    follow_redirects=True,
                )
                raise_for_viya_status(row_resp)
                row_data = row_resp.json()
                out_rows = [
                    dict(zip(columns, item.get("cells", []), strict=False))
                    for item in row_data.get("items", [])
                ]
                return {"table": ref.qualified, "columns": columns, "rows": out_rows, "count": len(out_rows)}

        @tool
        async def query_data(query: str, ctx: Context, limit: int = 100, start: int = 0) -> dict[str, Any]:
            """Run a FedSQL SELECT over the allowed tables and return the rows.

            Use it for every number: counts, rates, means, group-bys, joins
            between allowed tables, and the row of one patient. Aggregate in
            SQL rather than pulling rows, and add ORDER BY for stable paging.

            Only the allowed tables can appear after FROM or JOIN; a bare table
            name is qualified for you when only one caslib is in scope. The
            dialect is FedSQL: derived tables instead of WITH, double-quote a
            reserved word used as a name, string literals in single quotes.
            Any LIMIT in the text is ignored in favour of ``limit``.

            Args:
                query: One FedSQL SELECT statement.
                limit: Rows per page (default 100; capped by the server).
                start: Row offset for paging.

            Returns:
                ``{columns, rows, count, start, limit, truncated, column_types, tables}``
                or a status dict (``out_of_scope``, ``invalid_query``,
                ``table_not_found``, ``column_not_found``, ``syntax_error``,
                ``query_failed``) whose ``message`` names the fix.
            """
            limit = max(1, min(int(limit), max_rows))
            error = fedsql_helpers.screen_query(query, limit, start)
            if error is not None:
                return error
            try:
                sql, refs = qualify_query(query, tables)
            except ScopeError as exc:
                return _out_of_scope(exc)
            result = await run_query(ctx, "query_data", sql, limit, start)
            if "rows" in result:
                result["tables"] = [r.qualified for r in refs]
            return result

    # --- model tools --------------------------------------------------------

    if models:

        @tool
        async def list_models(ctx: Context) -> dict[str, Any]:
            """List the published models this server can score with, and what each one needs.

            Each entry carries the model's inputs (the columns it expects) and
            outputs (what it returns, usually a probability). Only the models
            configured for this team are listed.
            """
            async with viya_session("list_models", ctx) as client:
                ids: list[str] = list(models.exact)
                if any("*" in p for p in models.patterns):
                    items, _ = await get_paged_items("/microanalyticScore/modules", client, limit=500)
                    for item in items:
                        mid = str(item.get("id", ""))
                        if mid and models.allows(mid) and mid.lower() not in ids:
                            ids.append(mid.lower())
                out: list[dict[str, Any]] = []
                for module_id in ids:
                    try:
                        module, step = await module_and_step(client, module_id)
                        sig = await signature(client, module_id, step)
                    except httpx.HTTPStatusError as exc:
                        if _is_404(exc):
                            out.append(model_not_found(module_id))
                            continue
                        raise
                    out.append(
                        {
                            "model": module_id,
                            "status": "ready",
                            "name": module.get("name"),
                            "description": module.get("description"),
                            "step": step,
                            "inputs": return_items(sig.get("inputs") or [], ["name", "type"]),
                            "outputs": return_items(sig.get("outputs") or [], ["name", "type"]),
                        }
                    )
                return {"count": len(out), "models": out}

        @tool
        async def describe_model(model: str, ctx: Context) -> dict[str, Any]:
            """The full input and output signature of one allowed model.

            Call it before ``score`` to know the exact variable names and types.
            """
            try:
                module_id = models.resolve(model)
            except ScopeError as exc:
                return _out_of_scope(exc)
            async with viya_session("describe_model", ctx) as client:
                try:
                    module, step = await module_and_step(client, module_id)
                    sig = await signature(client, module_id, step)
                except httpx.HTTPStatusError as exc:
                    if _is_404(exc):
                        return model_not_found(module_id)
                    raise
                return {
                    "model": module_id,
                    "name": module.get("name"),
                    "description": module.get("description"),
                    "step": step,
                    "inputs": sig.get("inputs") or [],
                    "outputs": sig.get("outputs") or [],
                }

        @tool
        async def score(model: str, inputs: JsonDict, ctx: Context) -> dict[str, Any]:
            """Score one record with an allowed model.

            Args:
                model: The model name (see ``list_models``).
                inputs: The record as ``{"column": value, ...}``. Names are
                    matched to the model's inputs case-insensitively; extra
                    keys are ignored and missing ones are reported.

            Returns:
                ``{model, step, outputs: {name: value}, missing_inputs}``.
            """
            try:
                module_id = models.resolve(model)
            except ScopeError as exc:
                return _out_of_scope(exc)
            async with viya_session("score", ctx) as client:
                try:
                    _, step = await module_and_step(client, module_id)
                    sig = await signature(client, module_id, step)
                except httpx.HTTPStatusError as exc:
                    if _is_404(exc):
                        return model_not_found(module_id)
                    raise
                mas_inputs, missing = build_inputs(sig, inputs)
                outputs = await score_once(client, module_id, step, mas_inputs)
                return {"model": module_id, "step": step, "outputs": outputs, "missing_inputs": missing}

    if tables and models:

        @tool
        async def score_table_rows(
            model: str,
            table: str,
            ctx: Context,
            where: str = "",
            limit: int = 10,
            order_by: str = "",
            id_columns: str = "",
        ) -> dict[str, Any]:
            """Pull rows from an allowed table and score each one with an allowed model, in one call.

            The typical use: "score patient EHS-100092" or "score the ten
            highest-cost patients at Al Rams". Columns are matched to the
            model's inputs by name, so a table the model was trained on needs
            no mapping.

            Args:
                model: The model name (see ``list_models``).
                table: ``caslib.table`` (bare name allowed when unambiguous).
                where: A condition on the table's columns, e.g.
                    ``patient_id = 'EHS-100092'`` or ``region = 'Ajman' and hba1c_latest >= 9``.
                limit: Rows to score (default 10, capped by the server).
                order_by: Optional ordering, e.g. ``annual_cost_aed desc``.
                id_columns: Comma-separated columns to echo back next to the
                    scores (default: every column of the row).

            Returns:
                ``{model, table, step, count, rows: [{...columns, ...outputs}]}``.
            """
            try:
                module_id = models.resolve(model)
                ref = tables.resolve(table)
            except ScopeError as exc:
                return _out_of_scope(exc)
            for fragment in (where, order_by):
                problem = check_where(fragment)
                if problem:
                    return {"status": "invalid_query", "message": problem}
            n = max(1, min(int(limit), max_score_rows, max_rows))
            sql = f"select * from {ref.qualified}"
            if where.strip():
                sql += f" where {where.strip()}"
            if order_by.strip():
                sql += f" order by {order_by.strip()}"
            error = fedsql_helpers.screen_query(sql, n, 0)
            if error is not None:
                return error
            try:
                sql, _ = qualify_query(sql, tables)
            except ScopeError as exc:
                return _out_of_scope(exc)
            data = await run_query(ctx, "score_table_rows", sql, n, 0)
            if "rows" not in data:
                return data
            keep = [c.strip() for c in id_columns.split(",") if c.strip()]
            async with viya_session("score_table_rows", ctx) as client:
                try:
                    _, step = await module_and_step(client, module_id)
                    sig = await signature(client, module_id, step)
                except httpx.HTTPStatusError as exc:
                    if _is_404(exc):
                        return model_not_found(module_id)
                    raise
                scored: list[dict[str, Any]] = []
                missing: list[str] = []
                for row in data["rows"]:
                    mas_inputs, missing = build_inputs(sig, row)
                    outputs = await score_once(client, module_id, step, mas_inputs)
                    if keep:
                        lower = {str(k).lower(): v for k, v in row.items()}
                        echo = {c: lower.get(c.lower()) for c in keep}
                    else:
                        echo = dict(row)
                    scored.append({**echo, **outputs})
            return {
                "model": module_id,
                "table": ref.qualified,
                "step": step,
                "count": len(scored),
                "truncated": data.get("truncated", False),
                "rows": scored,
                "missing_inputs": missing,
            }

    logger.info("Bootcamp tools registered: %s", ", ".join(registered))
    return registered


__all__ = ["ALL_TOOLS", "READ_ONLY_TOOLS", "WORK_TOOLS", "annotations_for", "register"]
