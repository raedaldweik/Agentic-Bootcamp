import pytest

from bootcamp_mcp.scope import (
    ModelScope,
    ScopeError,
    TableScope,
    check_where,
    parse_list,
    qualify_query,
    referenced_tables,
)

SCOPE = TableScope.from_env("CASUSER.REGISTRY_TEAM3, Public.EHS_FACILITIES,casuser.*_team3")


def test_parse_list_trims_and_dedups():
    assert parse_list(" a, b ,\n c,a ") == ["a", "b", "c"]
    assert parse_list("") == []
    assert parse_list(None) == []


def test_table_scope_requires_caslib():
    with pytest.raises(ScopeError):
        TableScope.from_env("REGISTRY_TEAM3")


def test_allows_is_case_insensitive_and_supports_wildcards():
    assert SCOPE.allows("casuser", "registry_team3")
    assert SCOPE.allows("CASUSER", "PATIENTS_TEAM3")
    assert SCOPE.allows("public", "ehs_facilities")
    assert not SCOPE.allows("CASUSER", "PATIENTS_TEAM4")
    assert not SCOPE.allows("PUBLIC", "HMEQ")


def test_resolve_qualified_and_bare():
    assert SCOPE.resolve("casuser.registry_team3").qualified == "CASUSER.REGISTRY_TEAM3"
    assert SCOPE.resolve('"Public"."EHS_FACILITIES"'.replace('"', "")).qualified == "PUBLIC.EHS_FACILITIES"
    # bare names resolve when only one allowed caslib could hold them
    assert SCOPE.resolve("REGISTRY_TEAM3").qualified == "CASUSER.REGISTRY_TEAM3"
    assert SCOPE.resolve("ehs_facilities").qualified == "PUBLIC.EHS_FACILITIES"


def test_resolve_refuses_outside_scope_with_allowed_list():
    with pytest.raises(ScopeError) as exc:
        SCOPE.resolve("PUBLIC.HMEQ")
    assert "CASUSER.REGISTRY_TEAM3" in str(exc.value)
    with pytest.raises(ScopeError):
        SCOPE.resolve("HMEQ")


def test_resolve_bare_is_ambiguous_across_caslibs():
    scope = TableScope.from_env("CASUSER.*,PUBLIC.*")
    with pytest.raises(ScopeError) as exc:
        scope.resolve("REGISTRY_TEAM3")
    assert "ambiguous" in str(exc.value)


def test_model_scope():
    models = ModelScope.from_env("Deterioration_TEAM3, risk_*")
    assert models.allows("deterioration_team3")
    assert models.allows("risk_v2")
    assert not models.allows("deterioration_team4")
    assert models.resolve("DETERIORATION_TEAM3") == "deterioration_team3"
    with pytest.raises(ScopeError):
        models.resolve("other_model")
    assert models.exact == ["deterioration_team3"]


@pytest.mark.parametrize(
    "sql, expected",
    [
        ("select count(*) from CASUSER.REGISTRY_TEAM3", ["CASUSER.REGISTRY_TEAM3"]),
        (
            "SELECT * FROM registry_team3 r JOIN public.ehs_facilities f ON r.primary_facility_id = f.facility_id",
            ["registry_team3", "public.ehs_facilities"],
        ),
        ("select * from a, b as bb, c cc where a.x = b.x", ["a", "b", "c"]),
        (
            "select * from (select region from casuser.registry_team3) t group by region",
            ["casuser.registry_team3"],
        ),
        ('select * from "CASUSER"."REGISTRY_TEAM3"', ['"CASUSER"."REGISTRY_TEAM3"']),
        ("select 'from secret.table' as s from x", ["x"]),
        ("select * from x -- from hidden.table\n where 1=1", ["x"]),
        ("select * from x /* join other.t */", ["x"]),
        ("select 1", []),
        ("select * from a left outer join b on a.k=b.k inner join c on b.k=c.k", ["a", "b", "c"]),
    ],
)
def test_referenced_tables(sql, expected):
    assert referenced_tables(sql) == expected


def test_qualify_query_rewrites_bare_names_and_keeps_rest():
    sql = "select region, count(*) as n from registry_team3 where region = 'Ajman' group by region"
    out, refs = qualify_query(sql, SCOPE)
    assert (
        out
        == "select region, count(*) as n from CASUSER.REGISTRY_TEAM3 where region = 'Ajman' group by region"
    )
    assert [r.qualified for r in refs] == ["CASUSER.REGISTRY_TEAM3"]


def test_qualify_query_join_and_subquery():
    sql = (
        "select f.region, t.n from (select primary_facility_id, count(*) n from registry_team3 group by 1) t "
        "join ehs_facilities f on t.primary_facility_id = f.facility_id"
    )
    out, refs = qualify_query(sql, SCOPE)
    assert "from CASUSER.REGISTRY_TEAM3 group by" in out
    assert "join PUBLIC.EHS_FACILITIES f on" in out
    assert {r.qualified for r in refs} == {"CASUSER.REGISTRY_TEAM3", "PUBLIC.EHS_FACILITIES"}


def test_qualify_query_refuses_foreign_table():
    with pytest.raises(ScopeError) as exc:
        qualify_query("select * from registry_team3 r join public.hmeq h on r.id = h.id", SCOPE)
    assert "PUBLIC.HMEQ" in str(exc.value)


def test_qualify_query_ignores_names_in_strings_and_comments():
    out, refs = qualify_query("select 'public.hmeq' as s from registry_team3 -- public.hmeq", SCOPE)
    assert out.startswith("select 'public.hmeq' as s from CASUSER.REGISTRY_TEAM3")
    assert len(refs) == 1


def test_check_where():
    assert check_where("") is None
    assert check_where("region = 'Ajman' and hba1c_latest >= 9") is None
    assert check_where("1=1; drop table x") is not None
    assert check_where("id in (select id from other)") is not None
