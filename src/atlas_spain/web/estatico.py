"""Exporta la web como sitio estático (para publicarla en Vercel o cualquier hosting).

    python -m atlas_spain.web.estatico

Genera en web/data/ lo que en local sirve la API de Python:
    fichas/ca.json, fichas/<prov>.json   fichas de comunidades, provincias y municipios (formato compacto)
    secciones/<municipio>.json           GeoJSON de secciones censales (municipios con más de una sección)
    core/{sources,quality,executions}.json

Las fichas se calculan por lotes con las mismas consultas que `server._ficha` y se
comprimen con diccionarios (convocatorias, familias, siglas). El navegador las
expande al formato original (web/js/datos.js), así el panel no cambia.
"""

from __future__ import annotations

import gc
import json
import math
import re
from pathlib import Path

import duckdb
import geopandas as gpd
import pandas as pd
import pyarrow.parquet as pq
import shapely

from atlas_spain import paths

WEB = paths.ROOT / "web" / "data"
ADRH = f"{paths.BRONZE.as_posix()}/INE-ADRH/parquet/*/*.parquet"
NIVEL = "case when geo_id like 'ES-CA-%' then 'ccaa' when geo_id like 'ES-PR-%' then 'provincia' else 'municipio' end"


def _r(v, d=5):
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, float):
        if math.isnan(v):
            return None
        return int(v) if v.is_integer() else round(v, d)
    if hasattr(v, "item"):
        return _r(v.item(), d)
    return v


def _dump(obj, ruta: Path):
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


class Dic:
    """Lista de valores únicos con índice (para comprimir textos repetidos)."""

    def __init__(self):
        self.lista, self.idx = [], {}

    def __call__(self, v):
        if v not in self.idx:
            self.idx[v] = len(self.lista)
            self.lista.append(v)
        return self.idx[v]


def _df(con, sql, params=()):
    return con.execute(sql, list(params)).df()


def _lote(con, filtro: str, params: list, geo: pd.DataFrame) -> dict:
    """Fichas de todos los territorios que cumplen `filtro` (sobre geo_id)."""
    ids = _df(con, f"select geo_id from gold.dim_geography where {filtro} and geo_type in ('ccaa','provincia','municipio')", params).geo_id.tolist()
    if not ids:
        return {}
    E, F, S, O = Dic(), Dic(), Dic(), Dic()
    T = {g: {} for g in ids}
    por = lambda df: {k: v for k, v in df.groupby("geo_id", sort=False)}

    pob = por(_df(con, f"""select geo_id, anyo, max(poblacion) filter (where sexo='T') t, max(poblacion) filter (where sexo='H') h,
                                  max(poblacion) filter (where sexo='M') m, any_value(origen) origen
                           from gold.fact_population where {filtro} group by geo_id, anyo order by geo_id, anyo""", params))
    gb = _df(con, f"select geo_id, area_km2, lon, lat from gold.geo_boundaries where {filtro}", params).set_index("geo_id")
    el = por(_df(con, f"""select geo_id, election_id, familia, votos, escanos, vote_share from gold.results_by_family
                          where {filtro} and geo_level = {NIVEL} order by geo_id, election_id, votos desc""", params))
    pa = por(_df(con, f"""select geo_id, election_id, censo, votantes, votos_blancos, votos_nulos, turnout from gold.fact_turnout
                          where {filtro} and geo_level = {NIVEL} order by geo_id, election_id""", params))
    ag = por(_df(con, f"""select geo_id, election_id, agrupacion_siglas, votos, escanos, vote_share from gold.results_by_group
                          where {filtro} and geo_level = {NIVEL}
                          -- el panel solo muestra las candidaturas de la última convocatoria de cada tipo
                          qualify row_number() over (partition by geo_id, election_id order by votos desc) <= 8
                              and election_id = max(election_id) over (partition by geo_id, substr(election_id, 1, 2))
                          order by geo_id, election_id, votos desc""", params))
    reg = {}
    if con.execute("select count(*) from information_schema.tables where table_name='fact_regional_results'").fetchone()[0]:
        reg = por(_df(con, f"""select geo_id, election_id, tipo, anyo, candidatura, votos, escanos, votantes, censo
                               from gold.fact_regional_results
                               where {filtro} and nivel = case when geo_id like 'ES-PR-%' then 'territorio' else 'municipio' end
                                 and geo_id not like 'ES-CA-%'
                               order by geo_id, anyo, votos desc""", params))
    ce = por(_df(con, f"""select geo_id, tipo_eleccion, periodo, electores from gold.fact_electoral_census
                          where {filtro} and dato='censo_votacion' and tipo_elector='CER'""", params))
    munis = [g[6:] for g in ids if g.startswith("ES-MU-")]
    renta, nsec = {}, {}
    if munis:
        provs = sorted({m[:2] for m in munis})
        cond = " or ".join(f"coalesce(municipios__cod, substr(secciones__cod, 1, 5), substr(distritos__cod, 1, 5)) like '{p}%'" for p in provs)
        rd = con.execute(f"""
            select coalesce(municipios__cod, substr(secciones__cod, 1, 5), substr(distritos__cod, 1, 5)) cod,
                   max(valor) filter (where filtro_tv='482:284048' and secciones__cod is null and distritos__cod is null) renta,
                   count(distinct secciones__cod) n_secc,
                   min(valor) filter (where filtro_tv='482:284048' and secciones__cod is not null) renta_min,
                   max(valor) filter (where filtro_tv='482:284048' and secciones__cod is not null) renta_max,
                   max(valor) filter (where filtro_tv='260:366831' and secciones__cod is null and distritos__cod is null) pct65,
                   max(anyo) anyo
            from read_parquet('{ADRH}', union_by_name=true) where {cond} group by 1""").df()
        renta = {r.cod: {k: _r(getattr(r, k)) for k in ("renta", "n_secc", "renta_min", "renta_max", "pct65", "anyo")}
                 for r in rd.itertuples()}
        ns = con.execute(f"""select substr(geo_id, 7, 5) cod, count(*) n from gold.dim_geography
                             where geo_type='seccion' and ({' or '.join(f"geo_id like 'ES-SE-{p}%'" for p in provs)}) group by 1""").df()
        nsec = dict(zip(ns.cod, ns.n.astype(int)))

    for g in ids:
        u = geo.loc[g]
        cadena, p = [], u.parent_geo_id
        while isinstance(p, str) and p in geo.index:
            cadena.insert(0, [p, geo.at[p, "geo_name"]])
            p = geo.at[p, "parent_geo_id"]
        t = {"u": [u.geo_type, u.geo_name, u.parent_geo_id, u.official_code], "c": cadena}
        if g in pob:
            t["p"] = [[int(r.anyo), _r(r.t), _r(r.h), _r(r.m), O(r.origen)] for r in pob[g].itertuples()]
        if g in gb.index:
            b = gb.loc[g]
            t["g"] = [_r(b.area_km2, 3), _r(b.lon), _r(b.lat)]
        if g in el:
            t["e"] = [[E(r.election_id), F(r.familia), int(r.votos), _r(r.escanos), _r(r.vote_share)] for r in el[g].itertuples()]
        if g in pa:
            t["pa"] = [[E(r.election_id), _r(r.censo), _r(r.votantes), _r(r.votos_blancos), _r(r.votos_nulos), _r(r.turnout)]
                       for r in pa[g].itertuples()]
        if g in ag:
            t["a"] = [[E(r.election_id), S(r.agrupacion_siglas), int(r.votos), _r(r.escanos), _r(r.vote_share)] for r in ag[g].itertuples()]
        if g in reg:
            t["r"] = [{k: _r(getattr(r, k)) for k in ("election_id", "tipo", "anyo", "candidatura", "votos", "escanos", "votantes", "censo")}
                      for r in reg[g].itertuples()]
        if g in ce:
            t["ce"] = [{k: _r(getattr(r, k)) for k in ("tipo_eleccion", "periodo", "electores")} for r in ce[g].itertuples()]
        if g.startswith("ES-MU-"):
            t["re"] = renta.get(g[6:])
            t["ns"] = nsec.get(g[6:], 0)
        T[g] = t
    return {"E": E.lista, "F": F.lista, "S": S.lista, "O": O.lista, "T": T}


def fichas(con) -> int:
    geo = _df(con, "select geo_id, geo_type, geo_name, parent_geo_id, official_code from gold.dim_geography "
                   "where geo_type in ('pais','ccaa','provincia','municipio')").set_index("geo_id")
    geo = geo.astype(object).where(geo.notna(), None)
    _dump(_lote(con, "geo_id like ?", ["ES-CA-%"], geo), WEB / "fichas" / "ca.json")
    provs = sorted(g[6:] for g in geo.index if g.startswith("ES-PR-"))
    for p in provs:
        _dump(_lote(con, "(geo_id = ? or geo_id like ?)", [f"ES-PR-{p}", f"ES-MU-{p}%"], geo), WEB / "fichas" / f"{p}.json")
        print("fichas", p, flush=True)
    return len(provs)


def secciones(con) -> int:
    fichero = next((paths.DATA / "gold" / "geo").glob("secciones_*.parquet"))
    provs = sorted(pq.read_table(fichero, columns=["CPRO"]).column("CPRO").unique().to_pylist())
    n = 0
    for p in provs:
        g = gpd.read_parquet(fichero, filters=[("CPRO", "==", p)])
        adrh = con.execute(f"""
            select secciones__cod cusec,
                   max(valor) filter (where filtro_tv='482:284048') renta,
                   max(valor) filter (where filtro_tv='260:17338') pob,
                   max(valor) filter (where filtro_tv='260:366831') / 100 pct65
            from read_parquet('{ADRH}', union_by_name=true)
            where secciones__cod like '{p}%' group by 1""").df()
        g = g.merge(adrh, left_on="CUSEC", right_on="cusec", how="left")
        g["area"] = g.to_crs(3035).area / 1e6
        g["dens"] = g["pob"] / g["area"]
        for cod, m in g.groupby("CUMUN"):
            if len(m) < 2:
                continue
            try:
                geom = shapely.coverage_simplify(m.geometry.values, tolerance=0.00015)
            except Exception:
                geom = m.geometry.simplify(0.00015).values
            geom = shapely.set_precision(geom, 1e-5)
            out = gpd.GeoDataFrame({"id": m["CUSEC"].values, "dist": m["CUDIS"].str[-2:].values,
                                    "renta": m["renta"].values, "pob": m["pob"].values, "pct65": m["pct65"].round(4).values,
                                    "dens": m["dens"].round(0).values, "area": m["area"].round(4).values},
                                   geometry=geom, crs=4326)
            (WEB / "secciones").mkdir(parents=True, exist_ok=True)
            txt = re.sub(r"(-?\d+\.\d{5})\d+", r"\1", out.to_json(na="null", drop_id=True)).replace(", ", ",").replace(": ", ":")
            (WEB / "secciones" / f"{cod}.json").write_text(txt, encoding="utf-8")
            n += 1
        del g
        gc.collect()
        print("secciones", p, flush=True)
    return n


def core():
    import yaml
    reg = yaml.safe_load((paths.CONFIG / "encuestas.yaml").read_text(encoding="utf-8")) or {}
    _dump({"encuestas": reg.get("encuestas") or []}, WEB / "core" / "encuestas.json")
    from fastapi.testclient import TestClient
    from atlas_spain.api.main import app
    c = TestClient(app)
    for nombre, url in (("sources", "/sources"), ("quality", "/quality"), ("executions", "/operations/executions?limit=500")):
        r = c.get(url)
        r.raise_for_status()
        _dump(r.json(), WEB / "core" / f"{nombre}.json")


def motor():
    """Copia el motor estadístico y el panel a web/_lib para la función serverless (api/stats.py)."""
    import shutil
    from atlas_spain.stats import panel as P
    lib = paths.ROOT / "web" / "_lib"
    shutil.rmtree(lib, ignore_errors=True)
    (lib / "atlas_spain" / "stats").mkdir(parents=True)
    (lib / "atlas_spain" / "__init__.py").write_text('"""Copia mínima para la función serverless."""\n', encoding="utf-8")
    for f in (paths.ROOT / "src" / "atlas_spain" / "stats").glob("*.py"):
        shutil.copy(f, lib / "atlas_spain" / "stats" / f.name)
    npz = paths.DATA / "gold" / "stat_panel.npz"
    if not npz.exists():
        P.exportar(npz)
    shutil.copy(npz, lib / "stat_panel.npz")


def exportar():
    motor()
    core()
    con = duckdb.connect(str(paths.WAREHOUSE), read_only=True)
    con.execute("SET memory_limit='900MB'; SET threads=2")
    try:
        nf = fichas(con)
        ns = secciones(con)
    finally:
        con.close()
    print(f"listo: fichas de {nf} provincias + comunidades, {ns} municipios con secciones")


if __name__ == "__main__":
    exportar()
