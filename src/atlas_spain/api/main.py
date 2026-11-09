"""API de ATLAS SPAIN (solo lectura sobre el warehouse).

    uvicorn atlas_spain.api.main:app --port 8000

Endpoints:
    GET  /health
    GET  /sources                 catálogo de fuentes verificado
    GET  /operations/executions   Data Operations Center (log de ejecuciones)
    GET  /quality                 último run de controles de calidad
    GET  /geo/{geo_id}            radiografía de un territorio (atributos, hijos, población)
    GET  /geo/{geo_id}/population serie de población
    GET  /tables                  tablas disponibles (silver/gold) con nº de filas
    POST /sql                     SQL Explorer: una sola sentencia SELECT, máx. 5.000 filas
"""

from __future__ import annotations

import duckdb
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from atlas_spain import paths

app = FastAPI(title="ATLAS SPAIN API", version="0.1.0")

MAX_ROWS = 5000
ALLOWED_SCHEMAS = ("silver", "gold", "ops")


def _con() -> duckdb.DuckDBPyConnection:
    if not paths.WAREHOUSE.exists():
        raise HTTPException(503, "Warehouse no construido: ejecutar `atlas build`")
    con = duckdb.connect(str(paths.WAREHOUSE), read_only=True)
    con.execute("SET memory_limit='512MB'; SET threads=2")
    return con


def _rows(sql: str, params: list | None = None, limit: int = MAX_ROWS) -> list[dict]:
    con = _con()
    try:
        cur = con.execute(sql, params or [])
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, r)) for r in cur.fetchmany(limit)]
    finally:
        con.close()


@app.get("/health")
def health():
    return {"status": "ok", "warehouse": paths.WAREHOUSE.exists()}


@app.get("/sources")
def sources(categoria: str | None = None, estado: str | None = None):
    sql = "select * from gold.dim_data_source where 1=1"
    p = []
    if categoria:
        sql += " and categoria = ?"; p.append(categoria)
    if estado:
        sql += " and estado = ?"; p.append(estado)
    return _rows(sql + " order by categoria, source_id", p)


@app.get("/operations/executions")
def executions(source_id: str | None = None, limit: int = 200):
    sql = """select execution_id, source_id, dataset, started_at, duration_s, status,
                    records_downloaded, records_processed, errors, error_detail, version
             from ops.executions"""
    p = []
    if source_id:
        sql += " where source_id = ?"; p.append(source_id)
    return _rows(sql + " order by started_at desc", p, min(limit, MAX_ROWS))


@app.get("/quality")
def quality():
    return _rows("""select * from ops.quality_results
                    where run_id = (select arg_max(run_id, run_at) from ops.quality_results)
                    order by status, dimension""")


@app.get("/geo/{geo_id}")
def geo(geo_id: str):
    unit = _rows("select * from gold.dim_geography where geo_id = ?", [geo_id])
    if not unit:
        raise HTTPException(404, f"{geo_id} no existe en el registro geográfico")
    children = _rows("select geo_id, geo_type, geo_name from gold.dim_geography where parent_geo_id = ? order by geo_id",
                     [geo_id])
    pop = _rows("""select anyo, poblacion from gold.fact_population
                   where geo_id = ? and sexo = 'T' order by anyo desc limit 1""", [geo_id])
    return {"unit": unit[0], "children": children, "ultima_poblacion": pop[0] if pop else None,
            "fuente_poblacion": "INE — Cifras oficiales de población (Padrón)"}


@app.get("/geo/{geo_id}/population")
def population(geo_id: str):
    return _rows("select anyo, sexo, poblacion, tipo_dato from gold.fact_population where geo_id = ? order by anyo, sexo",
                 [geo_id])


@app.get("/tables")
def tables():
    return _rows(f"""select schema_name, table_name, estimated_size as filas
                     from duckdb_tables() where schema_name in {ALLOWED_SCHEMAS}
                     order by schema_name, table_name""")


class SqlQuery(BaseModel):
    sql: str


def validate_select(sql: str) -> None:
    """Acepta exactamente una sentencia SELECT. La conexión además es read_only."""
    try:
        stmts = duckdb.extract_statements(sql)
    except duckdb.Error as exc:
        raise HTTPException(400, f"SQL inválido: {exc}") from exc
    if len(stmts) != 1:
        raise HTTPException(400, "Se admite una única sentencia")
    if stmts[0].type != duckdb.StatementType.SELECT:
        raise HTTPException(400, "Solo se admiten consultas SELECT")
    lowered = sql.lower()
    for banned in ("read_csv", "read_parquet", "read_json", "read_text", "read_blob", "glob(", "attach", "copy ",
                   "install", "load ", "httpfs", "getenv"):
        if banned in lowered:
            raise HTTPException(400, f"Función no permitida en el explorador: {banned.strip()}")


@app.post("/sql")
def sql_explorer(q: SqlQuery):
    validate_select(q.sql)
    con = _con()
    try:
        con.execute("SET enable_external_access=false")
        cur = con.execute(q.sql)
        cols = [d[0] for d in cur.description]
        data = cur.fetchmany(MAX_ROWS + 1)
    except duckdb.Error as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        con.close()
    return {"columns": cols, "rows": [list(r) for r in data[:MAX_ROWS]], "truncated": len(data) > MAX_ROWS}
