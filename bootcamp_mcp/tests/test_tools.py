from tests.conftest import result_of

EXPECTED_TOOLS = {
    "list_tables",
    "describe_table",
    "preview_table",
    "query_data",
    "list_models",
    "describe_model",
    "score",
    "score_table_rows",
}


async def test_exactly_the_eight_tools_with_annotations(mcp_client):
    async with mcp_client() as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert set(tools) == EXPECTED_TOOLS
    for name in ("list_tables", "describe_table", "preview_table", "list_models", "describe_model"):
        assert tools[name].annotations.read_only_hint is True
    for name in ("query_data", "score", "score_table_rows"):
        assert tools[name].annotations.read_only_hint is False
        assert tools[name].annotations.destructive_hint is False


async def test_no_models_means_no_model_tools(mcp_client):
    async with mcp_client(models="") as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {"list_tables", "describe_table", "preview_table", "query_data"}


async def test_no_tables_means_only_model_tools(mcp_client):
    async with mcp_client(tables="") as client:
        names = {t.name for t in await client.list_tools()}
    assert names == {"list_models", "describe_model", "score"}


async def test_list_tables_reports_ready_and_not_loaded(mcp_client, fake):
    del fake.tables["PUBLIC/EHS_FACILITIES"]
    async with mcp_client() as client:
        out = result_of(await client.call_tool("list_tables", {}))
    by_name = {t["table"]: t for t in out["tables"]}
    assert by_name["CASUSER.REGISTRY_TEAM3"]["status"] == "ready"
    assert by_name["CASUSER.REGISTRY_TEAM3"]["rows"] == 4000
    assert by_name["PUBLIC.EHS_FACILITIES"]["status"] == "not_loaded"


async def test_list_tables_expands_wildcards(mcp_client, fake):
    fake.tables["CASUSER/PATIENTS_TEAM3"] = {
        "rowCount": 10,
        "columnCount": 3,
        "state": "loaded",
        "scope": "global",
    }
    fake.tables["CASUSER/PATIENTS_TEAM4"] = {
        "rowCount": 10,
        "columnCount": 3,
        "state": "loaded",
        "scope": "global",
    }
    async with mcp_client(tables="CASUSER.*_TEAM3") as client:
        out = result_of(await client.call_tool("list_tables", {}))
    assert {t["table"] for t in out["tables"]} == {"CASUSER.REGISTRY_TEAM3", "CASUSER.PATIENTS_TEAM3"}


async def test_describe_table_in_and_out_of_scope(mcp_client, fake):
    async with mcp_client() as client:
        ok = result_of(await client.call_tool("describe_table", {"table": "registry_team3"}))
        refused = result_of(await client.call_tool("describe_table", {"table": "PUBLIC.HMEQ"}))
    assert ok["table"] == "CASUSER.REGISTRY_TEAM3"
    assert [c["name"] for c in ok["columns"]] == ["patient_id", "hba1c_latest", "bmi"]
    assert ok["rows"] == 4000
    assert refused["status"] == "out_of_scope"
    assert "CASUSER.REGISTRY_TEAM3" in refused["message"]
    # the refusal never reached Viya
    assert not any("HMEQ" in path.upper() for _, path, _ in fake.requests)


async def test_preview_table(mcp_client):
    async with mcp_client() as client:
        out = result_of(
            await client.call_tool("preview_table", {"table": "CASUSER.REGISTRY_TEAM3", "rows": 1})
        )
    assert out["columns"] == ["patient_id", "hba1c_latest", "bmi"]
    assert out["rows"] == [{"patient_id": "EHS-100092", "hba1c_latest": 10.3, "bmi": 31.7}]


async def test_query_data_qualifies_and_runs(mcp_client, submitted, fake):
    async with mcp_client() as client:
        out = result_of(
            await client.call_tool(
                "query_data", {"query": "select region, count(*) as n from registry_team3 group by region"}
            )
        )
    assert out["columns"] == ["region", "n"]
    assert out["rows"] == [{"region": "Ajman", "n": 500}, {"region": "Sharjah", "n": 1200}]
    assert out["tables"] == ["CASUSER.REGISTRY_TEAM3"]
    assert out["truncated"] is False
    # the SAS program submitted carries the qualified name and the cap
    assert "from CASUSER.REGISTRY_TEAM3 group by region" in submitted[0]
    assert "proc fedsql sessref=" in submitted[0]
    assert "limit 101" in submitted[0]  # start + limit + 1 probe row
    assert "proc datasets" in submitted[1]  # scratch tables cleaned up


async def test_query_data_refuses_foreign_table_before_running(mcp_client, submitted):
    async with mcp_client() as client:
        out = result_of(
            await client.call_tool(
                "query_data", {"query": "select * from registry_team3 r join public.hmeq h on r.id=h.id"}
            )
        )
    assert out["status"] == "out_of_scope"
    assert "PUBLIC.HMEQ" in out["message"]
    assert submitted == []


async def test_query_data_refuses_writes(mcp_client, submitted):
    async with mcp_client() as client:
        out = result_of(await client.call_tool("query_data", {"query": "drop table casuser.registry_team3"}))
    assert out["status"] == "invalid_query"
    assert submitted == []


async def test_query_data_caps_limit(mcp_client, submitted):
    async with mcp_client() as client:
        out = result_of(
            await client.call_tool("query_data", {"query": "select * from registry_team3", "limit": 99999})
        )
    assert out["limit"] == 500


async def test_list_and_describe_models(mcp_client):
    async with mcp_client() as client:
        listed = result_of(await client.call_tool("list_models", {}))
        described = result_of(await client.call_tool("describe_model", {"model": "DETERIORATION_TEAM3"}))
        refused = result_of(await client.call_tool("describe_model", {"model": "someone_elses_model"}))
    assert listed["count"] == 1
    assert listed["models"][0]["step"] == "score"
    assert [i["name"] for i in listed["models"][0]["inputs"]] == ["hba1c_latest", "bmi", "patient_id"]
    assert described["outputs"][0]["name"] == "P_deterioration_next_12m1"
    assert refused["status"] == "out_of_scope"


async def test_list_models_reports_unpublished(mcp_client, fake):
    fake.modules.clear()
    async with mcp_client() as client:
        listed = result_of(await client.call_tool("list_models", {}))
    assert listed["models"][0]["status"] == "not_found"


async def test_score_casts_inputs_and_reports_missing(mcp_client, fake):
    async with mcp_client() as client:
        out = result_of(
            await client.call_tool(
                "score", {"model": "deterioration_team3", "inputs": {"HBA1C_LATEST": "10.3", "extra": 1}}
            )
        )
    assert out["step"] == "score"
    assert out["outputs"] == {"P_deterioration_next_12m1": 0.615}
    assert out["missing_inputs"] == ["bmi", "patient_id"]
    sent = {i["name"]: i["value"] for i in fake.scored[0]["inputs"]}
    assert sent == {"hba1c_latest": 10.3}


async def test_score_accepts_json_string_inputs(mcp_client, fake):
    async with mcp_client() as client:
        out = result_of(
            await client.call_tool(
                "score", {"model": "deterioration_team3", "inputs": '{"hba1c_latest": 6.8, "bmi": 27}'}
            )
        )
    assert out["outputs"]["P_deterioration_next_12m1"] == 0.44


async def test_score_table_rows_end_to_end(mcp_client, fake, submitted):
    fake.query_columns = [
        {"name": "patient_id", "type": "char", "format": "$12."},
        {"name": "hba1c_latest", "type": "double", "format": ""},
        {"name": "bmi", "type": "double", "format": ""},
    ]
    fake.query_rows = [{"cells": ["EHS-100092", 10.3, 31.7]}, {"cells": ["EHS-100001", 6.8, 27.0]}]
    async with mcp_client() as client:
        out = result_of(
            await client.call_tool(
                "score_table_rows",
                {
                    "model": "deterioration_team3",
                    "table": "registry_team3",
                    "where": "hba1c_latest >= 6",
                    "order_by": "hba1c_latest desc",
                    "limit": 2,
                    "id_columns": "patient_id, hba1c_latest",
                },
            )
        )
    assert out["table"] == "CASUSER.REGISTRY_TEAM3"
    assert out["count"] == 2
    assert out["rows"][0] == {
        "patient_id": "EHS-100092",
        "hba1c_latest": 10.3,
        "P_deterioration_next_12m1": 0.615,
    }
    assert "from CASUSER.REGISTRY_TEAM3 where hba1c_latest >= 6 order by hba1c_latest desc" in submitted[0]
    assert len(fake.scored) == 2


async def test_score_table_rows_rejects_smuggled_sql(mcp_client, submitted):
    async with mcp_client() as client:
        out = result_of(
            await client.call_tool(
                "score_table_rows",
                {"model": "deterioration_team3", "table": "registry_team3", "where": "1=1; drop table x"},
            )
        )
    assert out["status"] == "invalid_query"
    assert submitted == []
