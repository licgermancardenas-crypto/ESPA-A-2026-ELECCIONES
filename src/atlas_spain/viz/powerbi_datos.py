"""Exporta las tablas del tablero de Power BI (CSV en reports/powerbi/datos/).

Mismo método que ATLAS Brasil: la geometría viaja como trazos SVG relativos a un
lienzo de 1000 px de ancho y DAX dibuja el mapa. Canarias se recoloca en un
recuadro abajo a la izquierda (convención cartográfica española); el recuadro se
marca en el SVG para que no se lea como posición real.

Todas las cifras salen del warehouse (gold) o de bronze con linaje. No se
exportan resultados electorales porque todavía no están cargados.
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import geopandas as gpd
import numpy as np
import pandas as pd
import shapely
from shapely.affinity import scale, translate
from shapely.geometry import MultiPolygon, Polygon

from atlas_spain import paths

SALIDA = paths.ROOT / "reports" / "powerbi" / "datos"
ANCHO = 1000
PROY = 25830          # UTM 30N (la del seccionado del INE)
CANARIAS = "05"


# ───────────────────────── geometría → SVG ─────────────────────────
def _anillo(coords, x0, y1, k) -> str:
    pts = np.round((np.asarray(coords)[:, :2] - [x0, 0]) * [k, -k] + [0, y1 * k]).astype(int)
    pts = pts[np.r_[True, np.any(np.diff(pts, axis=0) != 0, axis=1)]]
    if len(pts) < 4:
        return ""
    return "M" + " ".join(f"{a} {b}" for a, b in pts[:-1]) + "Z"


def trazo(geom, x0, y1, k) -> str:
    polys = geom.geoms if isinstance(geom, MultiPolygon) else [geom] if isinstance(geom, Polygon) else []
    return "".join(_anillo(p.exterior.coords, x0, y1, k) for p in polys)


def geometria():
    """Municipios en PROY con Canarias recolocada. Devuelve gdf municipios, provincias, ccaa y el lienzo."""
    sec = gpd.read_parquet(next((paths.DATA / "gold" / "geo").glob("secciones_*.parquet")))
    mun = pd.DataFrame(sec[["CUMUN", "CPRO", "CCA"]]).drop_duplicates("CUMUN").set_index("CUMUN")
    from atlas_spain.geo.build_geo import _dissolve
    g = _dissolve(sec, "CUMUN").set_index("CUMUN")
    g = g.join(mun[["CPRO", "CCA"]]).to_crs(PROY)
    rep = g.to_crs(4326).geometry.representative_point()
    g["lon"], g["lat"] = rep.x.round(5).values, rep.y.round(5).values

    # recuadro de Canarias (escala 0,85): bajo Ceuta y a la izquierda de Melilla
    pen = g[(g.CCA != CANARIAS) & (g.CPRO != "52")]
    can = g[g.CCA == CANARIAS]
    px0, py0, _, _ = pen.total_bounds
    cx0, cy0, cx1, cy1 = can.total_bounds
    esc = 0.85
    dx = (px0 + 20_000) - cx0
    dy = (py0 - 45_000) - (cy0 + (cy1 - cy0) * esc)

    def mover(geom):
        return translate(scale(geom, esc, esc, origin=(cx0, cy0)), dx, dy)
    g.loc[can.index, "geometry"] = can.geometry.apply(mover)
    bx0, by0, bx1, by1 = gpd.GeoSeries(g.loc[can.index, "geometry"]).total_bounds
    caja = shapely.box(bx0 - 15_000, by0 - 15_000, bx1 + 15_000, by1 + 15_000)

    x0, y0, x1, y1 = g.total_bounds
    x0, y0 = min(x0, caja.bounds[0]), min(y0, caja.bounds[1])
    k = ANCHO / (x1 - x0)
    alto = int(np.ceil((y1 - y0) * k))
    lienzo = {"x0": x0, "y1": y1, "k": k, "alto": alto, "caja_canarias": trazo(caja, x0, y1, k)}

    # simplificación de cobertura: los bordes compartidos se simplifican igual (sin rendijas)
    simp = shapely.coverage_simplify(g.geometry.values, tolerance=2.2 / k)
    g["path"] = [trazo(s, x0, y1, k) for s in simp]
    rp = g.geometry.representative_point()
    g["x"], g["y"] = ((rp.x - x0) * k).round(1), ((y1 - rp.y) * k).round(1)

    def nivel(col):
        d = _dissolve(g.reset_index(), col).set_index(col)
        d["path"] = [trazo(s, x0, y1, k) for s in shapely.coverage_simplify(d.geometry.values, tolerance=0.9 / k)]
        r = d.geometry.representative_point()
        d["cx"], d["cy"] = ((r.x - x0) * k).round().astype(int), ((y1 - r.y) * k).round().astype(int)
        return d
    return g, nivel("CPRO"), nivel("CCA"), lienzo


def geometria_regiones() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Trazos municipales en un lienzo de 1000 px por comunidad (zoom regional)."""
    import gc
    import pyarrow.parquet as pq
    from atlas_spain.geo.build_geo import _dissolve
    fichero = next((paths.DATA / "gold" / "geo").glob("secciones_*.parquet"))
    ccaas = sorted(pq.read_table(fichero, columns=["CCA"]).column("CCA").unique().to_pylist())
    filas, lienzos = [], []
    for cca in ccaas:
        sec = gpd.read_parquet(fichero, filters=[("CCA", "==", cca)]).to_crs(PROY)
        mun = _dissolve(sec, "CUMUN")
        a0, b0, a1, b1 = mun.total_bounds
        k = ANCHO / max(a1 - a0, b1 - b0)
        simp = shapely.coverage_simplify(mun.geometry.values, tolerance=1.0 / k)
        for cod, gm, orig in zip(mun.CUMUN, simp, mun.geometry):
            pt = orig.representative_point()
            x, y = (pt.x - a0) * k, (b1 - pt.y) * k
            filas.append((cod, trazo(gm, a0, b1, k) or f"M{x - 1.5:.0f} {y - 1.5:.0f}h3v3h-3Z", round(x), round(y)))
        lienzos.append((cca, int(np.ceil((a1 - a0) * k)), int(np.ceil((b1 - b0) * k))))
        del sec, mun
        gc.collect()
    return (pd.DataFrame(filas, columns=["municipio_ine", "path_ccaa", "x_ccaa", "y_ccaa"]).set_index("municipio_ine"),
            pd.DataFrame(lienzos, columns=["ccaa_ine", "ancho", "alto"]).set_index("ccaa_ine"))


def geometria_ciudades(min_secciones: int = 5) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Lienzo propio por municipio (1000 px en su lado mayor) con secciones y distritos.

    Solo municipios con al menos `min_secciones` secciones (en los demás el zoom no aporta)."""
    import gc
    import pyarrow.parquet as pq
    fichero = next((paths.DATA / "gold" / "geo").glob("secciones_*.parquet"))
    provincias = sorted(pq.read_table(fichero, columns=["CPRO"]).column("CPRO").unique().to_pylist())
    from atlas_spain.geo.build_geo import _dissolve
    filas_s, filas_d, lienzos = [], [], []
    for cpro in provincias:  # por provincia: la máquina tiene poca RAM
        sec = gpd.read_parquet(fichero, filters=[("CPRO", "==", cpro)]).to_crs(PROY)
        n = sec.groupby("CUMUN")["CUSEC"].transform("count")
        sec = sec[n >= min_secciones]
        filas_s, filas_d, lienzos = _ciudades(sec, filas_s, filas_d, lienzos, _dissolve)
        del sec
        gc.collect()
    S = pd.DataFrame(filas_s, columns=["cusec", "municipio_ine", "cudis", "path", "x", "y", "area_km2"])
    D = pd.DataFrame(filas_d, columns=["cudis", "municipio_ine", "path", "x", "y"])
    L = pd.DataFrame(lienzos, columns=["municipio_ine", "ancho", "alto", "n_secciones"])
    return S, D, L


def _ciudades(sec, filas_s, filas_d, lienzos, _dissolve):
    for mun, sub in sec.groupby("CUMUN"):
        a0, b0, a1, b1 = sub.total_bounds
        k = ANCHO / max(a1 - a0, b1 - b0)
        tol = 1.1 / k
        geoms = shapely.coverage_simplify(sub.geometry.values, tolerance=tol)
        rp = sub.geometry.representative_point()
        for cusec, cudis, gsec, pt, area in zip(sub.CUSEC, sub.CUDIS, geoms, rp, sub.geometry.area):
            filas_s.append((cusec, mun, cudis, trazo(gsec, a0, b1, k) or
                            f"M{(pt.x - a0) * k - 2:.0f} {(b1 - pt.y) * k - 2:.0f}h4v4h-4Z",
                            round((pt.x - a0) * k), round((b1 - pt.y) * k), round(area / 1e6, 4)))
        dis = _dissolve(sub, "CUDIS")
        for cudis, gd in zip(dis.CUDIS, shapely.coverage_simplify(dis.geometry.values, tolerance=tol)):
            c = gd.representative_point()
            filas_d.append((cudis, mun, trazo(gd, a0, b1, k), round((c.x - a0) * k), round((b1 - c.y) * k)))
        lienzos.append((mun, int(np.ceil((a1 - a0) * k)), int(np.ceil((b1 - b0) * k)), len(sub)))
    return filas_s, filas_d, lienzos


# ───────────────────────── tablas ─────────────────────────
def _sql(con, q):
    return con.execute(q).df()


def exportar() -> dict:
    SALIDA.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(paths.WAREHOUSE), read_only=True)
    try:
        y1 = int(con.execute("select max(anyo) from gold.fact_population where geo_level='municipio'").fetchone()[0])
        y0 = y1 - 10
        pop = _sql(con, f"""
            select geo_id, geo_level,
                   max(poblacion) filter (where anyo={y1}) as pob_actual,
                   max(poblacion) filter (where anyo={y0}) as pob_hace10
            from gold.fact_population where sexo='T' group by all""").set_index("geo_id")
        geo = _sql(con, "select geo_id, geo_type, geo_name, parent_geo_id, official_code from gold.dim_geography").set_index("geo_id")
        area = _sql(con, "select geo_id, area_km2 from gold.geo_boundaries").set_index("geo_id")
        pib = _sql(con, """
            select geo_id, anyo, valor from gold.fact_economy_province
            where indicador like '%per capita' and tipo='Dato base' and geo_id like 'ES-PR-%'""")
        paro = _sql(con, f"""
            select coalesce('ES-CA-' || comunidades_y_ciudades_autonomas__cod, 'ES') as geo_id,
                   anyo, periodo, anyo || '-' || periodo as trimestre, valor as tasa_paro
            from read_parquet('{paths.BRONZE.as_posix()}/INE-EPA-PARO-CCAA/parquet/*/*.parquet')
            where sexo='Ambos sexos' and totales_de_edad='Total' and valor is not null""")
        censo = _sql(con, """select geo_id, electores from gold.fact_electoral_census
                             where dato='censo_votacion' and tipo_elector='CER' and geo_level='municipio'""").set_index("geo_id")
        serie = _sql(con, """
            select p.geo_id, p.geo_level as nivel, g.geo_name as nombre, p.anyo, p.poblacion, p.origen
            from gold.fact_population p join gold.dim_geography g using (geo_id)
            where p.sexo='T' and p.geo_level in ('nacional','ccaa','provincia','municipio')""")
        fuentes = _sql(con, """select source_id, organismo, dataset, categoria, granularidad, cobertura_historica,
                                      frecuencia, licencia, estado, http_status, metodo_extraccion,
                                      coalesce(nullif(connector,''),'—') as conector, ultima_extraccion_estado
                               from gold.dim_data_source""")
        ejec = _sql(con, """select execution_id, source_id, dataset, strftime(started_at, '%Y-%m-%d %H:%M') as inicio,
                                   status as estado, records_downloaded as descargados, records_processed as procesados,
                                   errors as errores, round(duration_s, 1) as duracion_s,
                                   left(coalesce(error_detail, ''), 180) as detalle, coalesce(version, '') as version
                            from ops.executions order by started_at desc""")
        calidad = _sql(con, """select check_name as control, dimension, dataset, value as valor, threshold as umbral,
                                      status as estado, detail as detalle
                               from ops.quality_results
                               where run_id = (select arg_max(run_id, run_at) from ops.quality_results)""")
        hay_reg = con.execute("""select count(*) from information_schema.tables
                                 where table_schema='gold' and table_name='fact_regional_results'""").fetchone()[0]
        if hay_reg:
            res_reg = _sql(con, """
                select election_id, tipo, anyo, nivel, provincia_ine, municipio_ine, candidatura,
                       votos, coalesce(escanos, 0) as escanos
                from gold.fact_regional_results where nivel in ('territorio', 'municipio') and votos > 0""")
            part_reg = _sql(con, """
                select election_id, tipo, anyo, nivel, provincia_ine, municipio_ine, censo, votantes, nulos, blancos,
                       validos, votos_candidaturas, turnout, ganador, cuota_ganador
                from gold.regional_turnout where nivel in ('territorio', 'municipio')""")
        else:
            res_reg = part_reg = pd.DataFrame()
        hay_nac = con.execute("""select count(*) from information_schema.tables
                                 where table_schema='gold' and table_name='results_by_family'""").fetchone()[0]
        if hay_nac:
            nac_conv = _sql(con, """
                select e.election_id, e.election_type, e.anno, e.mes, e.fecha,
                       case e.election_type when 'congreso' then 'Generales' when 'municipales' then 'Municipales'
                            when 'europeas' then 'Europeas' else e.election_type end || ' ' ||
                       case when e.election_type = 'congreso' and e.anno = 2019
                            then (case e.mes when 4 then 'abril ' else 'noviembre ' end) else '' end || e.anno as convocatoria,
                       e.anno * 1000 + e.mes * 10 + cast(e.tipo_eleccion as int) as orden
                from gold.dim_election e""")
            nac_fam = _sql(con, """
                select election_id, geo_level, geo_id, familia, votos, escanos, vote_share
                from gold.results_by_family where geo_level in ('nacional', 'ccaa', 'provincia')""")
            nac_part = _sql(con, """
                select t.election_id, t.geo_level, t.geo_id, t.censo, t.votantes, t.votos_validos, t.votos_blancos,
                       t.votos_nulos, t.turnout
                from gold.fact_turnout t where t.geo_level in ('nacional', 'ccaa', 'provincia', 'municipio')""")
            nac_gan = _sql(con, """
                with r as (
                    select g.election_id, g.geo_level, g.geo_id, g.agrupacion_siglas, g.votos, g.vote_share,
                           coalesce(f.familia, 'Otros') as familia,
                           row_number() over (partition by g.election_id, g.geo_level, g.geo_id order by g.votos desc) as rk
                    from gold.results_by_group g
                    left join gold.party_family_map f
                           on f.election_id = g.election_id and f.agrupacion_siglas = g.agrupacion_siglas
                    where g.geo_level in ('provincia', 'municipio', 'ccaa'))
                select a.election_id, a.geo_level, a.geo_id, a.agrupacion_siglas as ganador, a.familia as familia_ganador,
                       a.vote_share as cuota_ganador, a.vote_share - coalesce(b.vote_share, 0) as margen,
                       b.agrupacion_siglas as segundo
                from r a left join r b on b.election_id = a.election_id and b.geo_level = a.geo_level
                                      and b.geo_id = a.geo_id and b.rk = 2
                where a.rk = 1""")
            nac_ind = _sql(con, """
                select i.election_id, i.geo_level, i.geo_id, i.enep, i.enpp, i.gallagher, i.competitividad,
                       v.volatilidad_pedersen
                from gold.election_indices i
                left join gold.volatility v using (election_id, geo_level, geo_id)
                where i.geo_level in ('nacional', 'ccaa', 'provincia')""")
        else:
            nac_conv = nac_fam = nac_part = nac_gan = nac_ind = pd.DataFrame()
        adrh_glob = f"{paths.BRONZE.as_posix()}/INE-ADRH/parquet/*/*.parquet"
        adrh = _sql(con, f"""
            with b as (
                select *, dense_rank() over (partition by parse_dirpath(filename)
                                             order by _ingested_at desc) as rk
                from read_parquet('{adrh_glob}', union_by_name = true, filename = true))
            select coalesce(secciones__cod, distritos__cod, municipios__cod) as codigo,
                   case when secciones__cod is not null then 'seccion'
                        when distritos__cod is not null then 'distrito' else 'municipio' end as nivel,
                   anyo, case filtro_tv when '482:284048' then 'renta neta media por persona'
                                  when '260:17338' then 'población'
                                  when '260:366831' then '% población de 65 y más' end as indicador, valor
            from b where rk = 1 and valor is not null and filtro_tv is not null""") if list(paths.BRONZE.glob("INE-ADRH/parquet/*/*.parquet"))             else pd.DataFrame(columns=["codigo", "nivel", "anyo", "indicador", "valor"])
    finally:
        con.close()

    g, prov, ccaa, lienzo = geometria()

    # ── municipios
    M = pd.DataFrame(index=g.index)
    M["geo_id"] = "ES-MU-" + M.index
    M["municipio_ine"] = M.index
    M["provincia_ine"], M["ccaa_ine"] = g["CPRO"], g["CCA"]
    M["nombre"] = geo["geo_name"].reindex(M["geo_id"]).values
    M["pob_actual"] = pop["pob_actual"].reindex(M["geo_id"]).values
    M["pob_hace10"] = pop["pob_hace10"].reindex(M["geo_id"]).values
    M["area_km2"] = area["area_km2"].reindex(M["geo_id"]).round(2).values
    M["electores_and_2026"] = censo["electores"].reindex(M["geo_id"]).values
    for c in ("path", "x", "y", "lon", "lat"):
        M[c] = g[c].values
    # municipios demasiado pequeños para el lienzo: marcador de 2 px en su posición
    vacio = M["path"].fillna("") == ""
    M.loc[vacio, "path"] = [f"M{x - 1:.0f} {y - 1:.0f}h2v2h-2Z" for x, y in zip(M.loc[vacio, "x"], M.loc[vacio, "y"])]
    R, LR = geometria_regiones()
    for c in ("path_ccaa", "x_ccaa", "y_ccaa"):
        M[c] = R[c].reindex(M.index).values
    S, D, L = geometria_ciudades()
    L = L.set_index("municipio_ine")
    M["lienzo_ancho"] = L["ancho"].reindex(M.index).values
    M["lienzo_alto"] = L["alto"].reindex(M.index).values
    M["n_secciones"] = L["n_secciones"].reindex(M.index).fillna(1).astype(int).values
    if not adrh.empty:
        piv = adrh.pivot_table(index=["codigo", "nivel"], columns="indicador", values="valor", aggfunc="first")
        piv.columns = [str(c) for c in piv.columns]
        def col(df, nombre):
            return df[nombre] if nombre in df.columns else pd.Series(index=df.index, dtype=float)
        sec_v = piv.xs("seccion", level="nivel") if "seccion" in piv.index.get_level_values(1) else piv.iloc[0:0]
        mun_v = piv.xs("municipio", level="nivel") if "municipio" in piv.index.get_level_values(1) else piv.iloc[0:0]
        S["renta_pp"] = col(sec_v, "renta neta media por persona").reindex(S["cusec"]).values
        S["poblacion"] = col(sec_v, "población").reindex(S["cusec"]).values
        S["pct_65"] = (col(sec_v, "% población de 65 y más").reindex(S["cusec"]) / 100).values
        M["renta_pp"] = col(mun_v, "renta neta media por persona").reindex(M.index).values
        anyo_adrh = int(adrh["anyo"].max())
    else:
        S["renta_pp"] = S["poblacion"] = S["pct_65"] = np.nan
        M["renta_pp"] = np.nan
        anyo_adrh = None
    tramos = [(0, 100, "1 · < 100"), (100, 1000, "2 · 100–1.000"), (1000, 5000, "3 · 1.000–5.000"),
              (5000, 20000, "4 · 5.000–20.000"), (20000, 100000, "5 · 20.000–100.000"),
              (100000, 500000, "6 · 100.000–500.000"), (500000, 1e9, "7 · > 500.000")]
    M["nombre_completo"] = M["nombre"] + " (" + geo["geo_name"].reindex("ES-PR-" + M["provincia_ine"]).values + ")"
    M["tamano"] = pd.cut(M["pob_actual"].fillna(0), [t[0] for t in tramos] + [1e9], labels=[t[2] for t in tramos],
                         right=False).astype(str)

    # ── provincias
    P = pd.DataFrame(index=prov.index)
    P["geo_id"] = "ES-PR-" + P.index
    P["provincia_ine"] = P.index
    P["nombre"] = geo["geo_name"].reindex(P["geo_id"]).values
    P["ccaa_ine"] = geo["parent_geo_id"].reindex(P["geo_id"]).str[-2:].values
    P["pob_actual"] = pop["pob_actual"].reindex(P["geo_id"]).values
    P["pob_hace10"] = pop["pob_hace10"].reindex(P["geo_id"]).values
    P["area_km2"] = area["area_km2"].reindex(P["geo_id"]).round(1).values
    ult = pib.sort_values("anyo").groupby("geo_id").tail(1).set_index("geo_id")
    P["pib_pc"] = ult["valor"].reindex(P["geo_id"]).round(0).values
    P["pib_pc_anyo"] = ult["anyo"].reindex(P["geo_id"]).values
    P["n_municipios"] = M.groupby("provincia_ine").size().reindex(P.index).values
    for c in ("path", "cx", "cy"):
        P[c] = prov[c].values

    # ── CCAA
    A = pd.DataFrame(index=ccaa.index)
    A["geo_id"] = "ES-CA-" + A.index
    A["ccaa_ine"] = A.index
    A["nombre"] = geo["geo_name"].reindex(A["geo_id"]).values
    A["pob_actual"] = pop["pob_actual"].reindex(A["geo_id"]).values
    A["pob_hace10"] = pop["pob_hace10"].reindex(A["geo_id"]).values
    A["area_km2"] = area["area_km2"].reindex(A["geo_id"]).round(1).values
    up = paro.sort_values(["anyo", "periodo"]).groupby("geo_id").tail(1).set_index("geo_id")
    A["paro"] = up["tasa_paro"].reindex(A["geo_id"]).values / 100
    A["paro_trimestre"] = up["trimestre"].reindex(A["geo_id"]).values
    A["n_provincias"] = P.groupby("ccaa_ine").size().reindex(A.index).values
    A["n_municipios"] = M.groupby("ccaa_ine").size().reindex(A.index).values
    for c in ("path", "cx", "cy"):
        A[c] = ccaa[c].values
    A["lienzo_ancho"] = LR["ancho"].reindex(A.index).values
    A["lienzo_alto"] = LR["alto"].reindex(A.index).values
    pp = P.dropna(subset=["pib_pc"]).assign(w=lambda d: d.pib_pc * d.pob_actual).groupby("ccaa_ine")[["w", "pob_actual"]].sum()
    A["pib_pc"] = (pp["w"] / pp["pob_actual"]).round(0).reindex(A.index).values

    pib_serie = pib.rename(columns={"valor": "pib_pc"})
    pib_serie["provincia_ine"] = pib_serie["geo_id"].str[-2:]
    paro["ccaa_ine"] = paro["geo_id"].str[-2:].where(paro["geo_id"] != "ES", "00")
    serie["anyo"] = serie["anyo"].astype(int)
    prov_ccaa = P.set_index("provincia_ine")["ccaa_ine"]
    serie["ccaa_ine"] = np.select(
        [serie.nivel == "ccaa", serie.nivel == "provincia", serie.nivel == "municipio"],
        [serie.geo_id.str[-2:], serie.geo_id.str[-2:].map(prov_ccaa), serie.geo_id.str[6:8].map(prov_ccaa)], "00")
    serie["provincia_ine"] = np.where(serie.nivel.isin(["provincia", "municipio"]), serie.geo_id.str[6:8], "")
    serie["municipio_ine"] = np.where(serie.nivel == "municipio", serie.geo_id.str[6:], "")

    if not res_reg.empty:
        def etiqueta(e):
            region, cod = e.split("-", 1)
            t, num = cod[0], int(cod[1:])
            anyo = num if num > 1900 else (1900 + num if num > 50 else 2000 + num)
            if region == "MAD":
                return f"Asamblea de Madrid {anyo}"
            return ("Parlamento Vasco " if t == "P" else "Congreso (en Euskadi) ") + str(anyo)
        for df in (res_reg, part_reg):
            df["convocatoria"] = df["election_id"].map(etiqueta)
            df["orden"] = df["anyo"].astype(int) * 10 + (df["tipo"] == "congreso").astype(int)
            df["geo_id"] = np.where(df["nivel"] == "territorio", "ES-PR-" + df["provincia_ine"].astype(str),
                                    "ES-MU-" + df["municipio_ine"].astype(str))
        res_reg["municipio_ine"] = res_reg["municipio_ine"].where(res_reg["nivel"] == "municipio", None)
        part_reg["municipio_ine"] = part_reg["municipio_ine"].where(part_reg["nivel"] == "municipio", None)
    salidas = {"municipios.csv": M.reset_index(drop=True), "provincias.csv": P.reset_index(drop=True),
               "ccaa.csv": A.reset_index(drop=True), "poblacion_serie.csv": serie,
               "pib_provincia.csv": pib_serie[["provincia_ine", "anyo", "pib_pc"]],
               "paro_ccaa.csv": paro[["ccaa_ine", "anyo", "periodo", "trimestre", "tasa_paro"]],
               "fuentes.csv": fuentes, "ejecuciones.csv": ejec, "calidad.csv": calidad,
               "secciones.csv": S, "distritos.csv": D,
               "elecciones_regionales.csv": res_reg, "participacion_regional.csv": part_reg,
               "nac_convocatorias.csv": nac_conv, "nac_familias.csv": nac_fam, "nac_participacion.csv": nac_part,
               "nac_ganadores_mun.csv": nac_gan[nac_gan.geo_level == "municipio"] if not nac_gan.empty else nac_gan,
               "nac_ganadores_prov.csv": nac_gan[nac_gan.geo_level == "provincia"] if not nac_gan.empty else nac_gan, "nac_indices.csv": nac_ind}
    for nombre, df in salidas.items():
        df.to_csv(SALIDA / nombre, index=False, encoding="utf-8")
    params = {"anyo_actual": y1, "anyo_base": y0, "anyo_adrh": anyo_adrh, "lienzo": {"alto": lienzo["alto"]},
              "caja_canarias": lienzo["caja_canarias"],
              "corte": pd.Timestamp.now(tz="Europe/Madrid").strftime("%d/%m/%Y %H:%M"),
              "largos": {"munis": int(M["path"].str.len().sum()), "prov": int(P["path"].str.len().sum())}}
    (SALIDA / "parametros.json").write_text(json.dumps(params, ensure_ascii=False, indent=2), encoding="utf-8")
    return params


if __name__ == "__main__":
    print(json.dumps(exportar(), ensure_ascii=False, indent=2)[:600])
