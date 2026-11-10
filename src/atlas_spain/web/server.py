"""Servidor del dashboard web de ATLAS SPAIN.

    atlas web            -> http://127.0.0.1:8080

Sirve la aplicación (web/) y una API de solo lectura para las fichas:
    GET /api/ficha/{geo_id}          demografía, renta, historial electoral y autonómico de un territorio
    GET /api/secciones/{municipio}   GeoJSON de las secciones censales de un municipio con renta, población y 65+
    /api/*                            resto de endpoints de atlas_spain.api (fuentes, calidad, SQL Explorer…)
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache

import duckdb
from fastapi import FastAPI, HTTPException
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from atlas_spain import paths
from atlas_spain.api.main import app as api_app

WEB = paths.ROOT / "web"
app = FastAPI(title="ATLAS SPAIN — dashboard", docs_url=None, redoc_url=None)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.mount("/api/core", api_app)

GEO_ID = re.compile(r"^ES(-(CA|PR|MU)-\d{2,5})?$")


def _con():
    con = duckdb.connect(str(paths.WAREHOUSE), read_only=True)
    con.execute("SET memory_limit='512MB'; SET threads=2")
    return con


def _clean(o):
    if isinstance(o, float):
        return None if math.isnan(o) else round(o, 5)
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def _rows(con, sql, params=()):
    cur = con.execute(sql, list(params))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


@lru_cache(maxsize=512)
def _ficha(geo_id: str) -> dict:
    con = _con()
    try:
        nivel = {"ES": "nacional", "CA": "ccaa", "PR": "provincia", "MU": "municipio"}[geo_id.split("-")[1] if "-" in geo_id else "ES"]
        unidad = _rows(con, "select geo_id, geo_type, geo_name, parent_geo_id, official_code from gold.dim_geography where geo_id = ?", [geo_id])
        if not unidad:
            raise HTTPException(404, f"{geo_id} no existe")
        cadena, p = [], unidad[0]["parent_geo_id"]
        while p:
            r = _rows(con, "select geo_id, geo_name, parent_geo_id from gold.dim_geography where geo_id = ?", [p])
            if not r:
                break
            cadena.insert(0, {"id": r[0]["geo_id"], "n": r[0]["geo_name"]})
            p = r[0]["parent_geo_id"]
        pob = _rows(con, """select anyo, max(poblacion) filter (where sexo='T') t, max(poblacion) filter (where sexo='H') h,
                                   max(poblacion) filter (where sexo='M') m, any_value(origen) origen
                            from gold.fact_population where geo_id = ? group by anyo order by anyo""", [geo_id])
        geo = _rows(con, "select area_km2, lon, lat from gold.geo_boundaries where geo_id = ?", [geo_id])
        elecciones = _rows(con, """
            select f.election_id, f.familia, f.votos, f.escanos, f.vote_share
            from gold.results_by_family f where f.geo_id = ? and f.geo_level = ?
            order by f.election_id, f.votos desc""", [geo_id, nivel])
        participacion = _rows(con, """select election_id, censo, votantes, votos_blancos, votos_nulos, turnout
                                      from gold.fact_turnout where geo_id = ? and geo_level = ? order by election_id""",
                              [geo_id, nivel])
        agrup = _rows(con, """select election_id, agrupacion_siglas, votos, escanos, vote_share
                              from gold.results_by_group where geo_id = ? and geo_level = ?
                              qualify row_number() over (partition by election_id order by votos desc) <= 8
                              order by election_id, votos desc""", [geo_id, nivel])
        regional = []
        if con.execute("select count(*) from information_schema.tables where table_name='fact_regional_results'").fetchone()[0]:
            lvl = {"municipio": "municipio", "provincia": "territorio"}.get(nivel)
            if lvl:
                regional = _rows(con, """select election_id, tipo, anyo, candidatura, votos, escanos, votantes, censo
                                         from gold.fact_regional_results where geo_id = ? and nivel = ?
                                         order by anyo, votos desc""", [geo_id, lvl])
        renta, secciones = None, None
        if nivel == "municipio":
            cod = geo_id[6:]
            adrh = f"{paths.BRONZE.as_posix()}/INE-ADRH/parquet/*/*.parquet"
            r = _rows(con, f"""
                select max(valor) filter (where filtro_tv='482:284048' and secciones__cod is null and distritos__cod is null) renta,
                       count(distinct secciones__cod) n_secc,
                       min(valor) filter (where filtro_tv='482:284048' and secciones__cod is not null) renta_min,
                       max(valor) filter (where filtro_tv='482:284048' and secciones__cod is not null) renta_max,
                       max(valor) filter (where filtro_tv='260:366831' and secciones__cod is null and distritos__cod is null) pct65,
                       max(anyo) anyo
                from read_parquet('{adrh}', union_by_name=true)
                where coalesce(municipios__cod, substr(secciones__cod, 1, 5), substr(distritos__cod, 1, 5)) = ?""", [cod])
            renta = r[0] if r else None
            secciones = con.execute("select count(*) from gold.dim_geography where geo_type='seccion' and geo_id like ?",
                                    [f"ES-SE-{cod}%"]).fetchone()[0]
        censo = _rows(con, """select tipo_eleccion, periodo, electores from gold.fact_electoral_census
                              where geo_id = ? and dato='censo_votacion' and tipo_elector='CER'""", [geo_id])
    finally:
        con.close()
    return _clean({"unidad": unidad[0], "nivel": nivel, "cadena": cadena, "poblacion": pob,
                   "geo": geo[0] if geo else None, "elecciones": elecciones, "participacion": participacion,
                   "agrupaciones": agrup, "regional": regional, "renta": renta, "n_secciones": secciones,
                   "censo_electoral": censo})


@app.get("/api/ficha/{geo_id}")
def ficha(geo_id: str):
    if not GEO_ID.match(geo_id):
        raise HTTPException(400, "geo_id no válido")
    return JSONResponse(_ficha(geo_id))


@lru_cache(maxsize=64)
def _secciones(cod: str) -> bytes:
    import geopandas as gpd
    import shapely
    fichero = next((paths.DATA / "gold" / "geo").glob("secciones_*.parquet"))
    g = gpd.read_parquet(fichero, filters=[("CUMUN", "==", cod)])
    if g.empty:
        raise HTTPException(404, "municipio sin secciones")
    try:
        g["geometry"] = shapely.coverage_simplify(g.geometry.values, tolerance=0.00015)
    except Exception:
        g["geometry"] = g.geometry.simplify(0.00015)
    con = _con()
    try:
        adrh = con.execute(f"""
            select secciones__cod cusec,
                   max(valor) filter (where filtro_tv='482:284048') renta,
                   max(valor) filter (where filtro_tv='260:17338') pob,
                   max(valor) filter (where filtro_tv='260:366831') / 100 pct65
            from read_parquet('{paths.BRONZE.as_posix()}/INE-ADRH/parquet/*/*.parquet', union_by_name=true)
            where secciones__cod like ? group by 1""", [f"{cod}%"]).df()
    finally:
        con.close()
    g = g.merge(adrh, left_on="CUSEC", right_on="cusec", how="left")
    g["area"] = g.to_crs(3035).area / 1e6
    g["dens"] = g["pob"] / g["area"]
    out = gpd.GeoDataFrame({"id": g["CUSEC"], "dist": g["CUDIS"].str[-2:], "renta": g["renta"], "pob": g["pob"],
                            "pct65": g["pct65"], "dens": g["dens"].round(0), "area": g["area"].round(4)},
                           geometry=g.geometry, crs=4326)
    return out.to_json(na="null", drop_id=True).encode("utf-8")


@app.get("/api/secciones/{cod}")
def secciones(cod: str):
    if not re.fullmatch(r"\d{5}", cod):
        raise HTTPException(400, "código de municipio no válido")
    return Response(_secciones(cod), media_type="application/geo+json")


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


app.mount("/", StaticFiles(directory=WEB), name="web")


def main(host: str = "127.0.0.1", port: int = 8080) -> None:
    import uvicorn
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
