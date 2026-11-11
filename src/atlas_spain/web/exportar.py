"""Exporta los datos estáticos del dashboard web (web/data/).

    geo/{ccaa,provincias,municipios}.geojson   geometría ligera (EPSG:4326, 4 decimales)
    territorios.json                           atributos y métricas por territorio
    elecciones.json                            catálogo de convocatorias
    ganadores/{election_id}.json               ganador, cuota y participación por territorio
    resumen/{election_id}.json                 resultados nacionales y por CCAA por familia
    historia_nacional.json                     voto por familia en todas las generales
    familias.json                              colores por familia política
    insights.json                              hallazgos calculados (no redactados a mano)

Todo sale del warehouse; nada se escribe a mano salvo los colores de familia.
"""

from __future__ import annotations

import json
import math

import duckdb
import geopandas as gpd
import pandas as pd
import shapely

from atlas_spain import paths
from atlas_spain.viz.powerbi_proyecto import FAMILIAS_COLOR

OUT = paths.ROOT / "web" / "data"
TIPOS = {"02": "Generales", "04": "Municipales", "07": "Europeas"}


def _r(x, n=4):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    return round(float(x), n)


def num(x, d=0) -> str:
    """Formato español: 1.234.567,8"""
    t = f"{x:,.{d}f}"
    return t.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(x, d=1, signo=False) -> str:
    v = num(abs(x) * 100 if signo else x * 100, d)
    return (("+" if x >= 0 else "−") + v if signo else v) + " %"


def _san(o):
    """JSON estricto: NaN/inf -> null (el navegador no acepta NaN)."""
    if isinstance(o, float):
        return None if (math.isnan(o) or math.isinf(o)) else o
    if isinstance(o, dict):
        return {k: _san(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_san(v) for v in o]
    return o


def _write(rel: str, obj) -> None:
    p = OUT / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(_san(obj), ensure_ascii=False, separators=(",", ":"), allow_nan=False), encoding="utf-8")


def geometrias() -> dict:
    src = paths.DATA / "gold" / "geo"
    out = {}
    for nivel, fichero, tol, pref in (("ccaa", "ccaa_2024.geojson", 0.004, "ES-CA-"),
                                       ("provincias", "provincia_2024.geojson", 0.003, "ES-PR-"),
                                       ("municipios", "municipio_2024.geojson", 0.0018, "ES-MU-")):
        g = gpd.read_file(src / fichero)
        try:
            geoms = shapely.coverage_simplify(g.geometry.values, tolerance=tol)
        except Exception:
            geoms = shapely.simplify(g.geometry.values, tol, preserve_topology=True)
        g = gpd.GeoDataFrame({"id": g["geo_id"]}, geometry=geoms, crs=4326)
        g = g[~g.geometry.is_empty]
        (OUT / "geo").mkdir(parents=True, exist_ok=True)
        g.to_file(OUT / "geo" / f"{nivel}.geojson", driver="GeoJSON", COORDINATE_PRECISION=4)
        out[nivel] = len(g)
    return out


def exportar() -> dict:
    OUT.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(paths.WAREHOUSE), read_only=True)
    q = lambda s: con.execute(s).df()
    try:
        y1 = int(con.execute("select max(anyo) from gold.fact_population where geo_level='municipio'").fetchone()[0])
        y0 = y1 - 10
        terr = q(f"""
            with p as (select geo_id, max(poblacion) filter (where anyo={y1} and sexo='T') pob,
                              max(poblacion) filter (where anyo={y0} and sexo='T') pob10,
                              max(poblacion) filter (where anyo=1996 and sexo='T') pob96
                       from gold.fact_population group by 1)
            select g.geo_id, g.geo_type, g.geo_name, g.parent_geo_id, p.pob, p.pob10, p.pob96, b.area_km2, b.lon, b.lat
            from gold.dim_geography g left join p using (geo_id)
            left join gold.geo_boundaries b using (geo_id)
            where g.geo_type in ('pais','ccaa','provincia','municipio')""")
        renta = q(f"""select 'ES-MU-' || municipios__cod as geo_id, valor
                      from read_parquet('{paths.BRONZE.as_posix()}/INE-ADRH/parquet/*/*.parquet', union_by_name=true)
                      where filtro_tv='482:284048' and municipios__cod is not null and secciones__cod is null
                        and distritos__cod is null""")
        elec = q("""select e.election_id, e.tipo_eleccion, e.anno, e.mes, cast(e.fecha as varchar) fecha,
                           (select count(*) from gold.fact_turnout t where t.election_id = e.election_id
                              and t.geo_level='municipio') munis
                    from gold.dim_election e order by e.anno, e.mes""")
        gan = q("""
            with r as (
                select g.election_id, g.geo_level, g.geo_id, g.agrupacion_siglas, g.votos, g.vote_share,
                       coalesce(f.familia, 'Otros') familia,
                       row_number() over (partition by g.election_id, g.geo_level, g.geo_id order by g.votos desc) rk
                from gold.results_by_group g
                left join gold.party_family_map f using (election_id, agrupacion_siglas)
                where g.geo_level in ('ccaa','provincia','municipio'))
            select a.election_id, a.geo_id, a.familia, a.agrupacion_siglas, a.vote_share,
                   a.vote_share - coalesce(b.vote_share, 0) margen, b.familia familia2, t.turnout
            from r a left join r b on b.election_id=a.election_id and b.geo_level=a.geo_level and b.geo_id=a.geo_id and b.rk=2
            left join gold.fact_turnout t on t.election_id=a.election_id and t.geo_level=a.geo_level and t.geo_id=a.geo_id
            where a.rk = 1""")
        fam = q("""select f.election_id, f.geo_level, f.geo_id, f.familia, f.votos, f.escanos, f.vote_share,
                          t.turnout, t.censo, t.votantes
                   from gold.results_by_family f
                   left join gold.fact_turnout t using (election_id, geo_level, geo_id)
                   where f.geo_level in ('nacional','ccaa')""")
        ind = q("""select i.election_id, i.geo_id, i.enep, i.enpp, i.gallagher, v.volatilidad_pedersen
                   from gold.election_indices i left join gold.volatility v using (election_id, geo_level, geo_id)
                   where i.geo_level='nacional'""")
        swing = q("""
            with f as (select election_id, geo_id, familia, vote_share from gold.results_by_family
                       where geo_level='provincia' and election_id in ('02-201911','02-202307'))
            select a.geo_id, a.familia, a.vote_share - coalesce(b.vote_share,0) d
            from f a left join f b on b.geo_id=a.geo_id and b.familia=a.familia and b.election_id='02-201911'
            where a.election_id='02-202307'""")
    finally:
        con.close()

    # ── territorios ──
    terr = terr.merge(renta, on="geo_id", how="left").rename(columns={"valor": "renta"})
    T = {}
    for r in terr.itertuples():
        T[r.geo_id] = {"n": r.geo_name, "t": r.geo_type, "p": r.parent_geo_id, "pob": _r(r.pob, 0), "pob10": _r(r.pob10, 0),
                       "pob96": _r(r.pob96, 0), "km2": _r(r.area_km2, 2), "lon": _r(r.lon, 4), "lat": _r(r.lat, 4),
                       "renta": _r(r.renta, 0)}
    _write("territorios.json", {"anyo": y1, "anyo_base": y0, "t": T})

    # ── elecciones ──
    E = []
    for r in elec.itertuples():
        nombre = f"{TIPOS.get(r.tipo_eleccion, r.tipo_eleccion)} " + (
            ("abril " if r.mes == 4 else "noviembre ") if r.tipo_eleccion == "02" and r.anno == 2019 else "") + str(r.anno)
        E.append({"id": r.election_id, "tipo": TIPOS.get(r.tipo_eleccion), "anyo": int(r.anno), "mes": int(r.mes),
                  "fecha": r.fecha, "nombre": nombre, "munis": int(r.munis)})
    _write("elecciones.json", E)

    # ── ganadores por convocatoria ──
    for e, sub in gan.groupby("election_id"):
        _write(f"ganadores/{e}.json", {r.geo_id: [r.familia, r.agrupacion_siglas, _r(r.vote_share), _r(r.margen),
                                                   r.familia2, _r(r.turnout)] for r in sub.itertuples()})

    # ── resumen por convocatoria (nacional y CCAA) ──
    ind = ind.set_index("election_id")
    for e, sub in fam.groupby("election_id"):
        res = {}
        for g, s2 in sub.groupby("geo_id"):
            s2 = s2.sort_values("votos", ascending=False)
            res[g] = {"turnout": _r(s2.turnout.iloc[0]), "censo": _r(s2.censo.iloc[0], 0), "votantes": _r(s2.votantes.iloc[0], 0),
                      "f": [[x.familia, _r(x.votos, 0), _r(x.escanos, 0), _r(x.vote_share)] for x in s2.itertuples()]}
        i = ind.loc[e] if e in ind.index else None
        _write(f"resumen/{e}.json", {"geo": res, "enep": _r(i.enep) if i is not None else None,
                                     "gallagher": _r(i.gallagher) if i is not None else None,
                                     "volatilidad": _r(i.volatilidad_pedersen) if i is not None else None})

    # ── historia nacional (generales) ──
    gen = fam[(fam.geo_level == "nacional") & fam.election_id.str.startswith("02-")]
    hist = {e: {x.familia: [_r(x.vote_share), _r(x.escanos, 0)] for x in s.itertuples()} for e, s in gen.groupby("election_id")}
    _write("historia_nacional.json", hist)
    _write("familias.json", FAMILIAS_COLOR)

    # ── insights calculados ──
    mun = terr[(terr.geo_type == "municipio") & terr.pob.notna() & terr.pob10.notna() & (terr.pob10 > 0)].copy()
    mun["var"] = mun.pob / mun.pob10 - 1
    grandes = mun[mun.pob >= 20000]
    ins = []
    top = grandes.nlargest(5, "var")
    ins.append({"tipo": "demografia", "titulo": "Las ciudades que más crecen",
                "texto": f"Entre los municipios de más de 20.000 habitantes, {top.iloc[0].geo_name} lidera el crecimiento "
                         f"{y0}–{y1}: {pct(top.iloc[0]['var'], signo=True)}.",
                "items": [[r.geo_id, r.geo_name, _r(r.var)] for r in top.itertuples()]})
    # caídas > 50 % suelen ser segregaciones de término municipal, no despoblación: se excluyen del listado
    caen = mun[(mun.pob10 >= 1000) & (mun["var"] > -0.5)].nsmallest(5, "var")
    perd = (mun["var"] < 0).mean()
    ins.append({"tipo": "demografia", "titulo": "La España que se vacía",
                "texto": f"El {pct(perd, 0)} de los municipios tiene hoy menos habitantes que en {y0}. Mayores caídas entre "
                         f"municipios de más de 1.000 habitantes (se excluyen pérdidas superiores al 50 %, que suelen "
                         f"deberse a segregaciones de término municipal).",
                "items": [[r.geo_id, r.geo_name, _r(r.var)] for r in caen.itertuples()]})
    rr = terr[(terr.geo_type == "municipio") & terr.renta.notna() & (terr.pob >= 20000)]
    if not rr.empty:
        ri, po = rr.nlargest(5, "renta"), rr.nsmallest(5, "renta")
        ins.append({"tipo": "renta", "titulo": "La brecha de renta",
                    "texto": f"Entre municipios de más de 20.000 habitantes, la renta neta por persona va de "
                             f"{num(po.iloc[0].renta)} € ({po.iloc[0].geo_name}) a {num(ri.iloc[0].renta)} € "
                             f"({ri.iloc[0].geo_name}): {num(ri.iloc[0].renta / po.iloc[0].renta, 1)} veces más.",
                    "items": [[r.geo_id, r.geo_name, _r(r.renta, 0)] for r in ri.itertuples()]})
    if not swing.empty:
        sw = swing[swing.familia.isin(["PP", "PSOE", "Vox"])]
        for fml in ("PP", "Vox"):
            s3 = sw[sw.familia == fml].nlargest(3, "d") if fml == "PP" else sw[sw.familia == fml].nsmallest(3, "d")
            nombre = {g: T.get(g, {}).get("n") for g in s3.geo_id}
            verbo = "más crece" if fml == "PP" else "más retrocede"
            ins.append({"tipo": "elecciones", "titulo": f"Dónde {verbo} {fml} (2019 → 2023)",
                        "texto": f"En las generales de 2023, {fml} {verbo.split()[1]} sobre todo en "
                                 f"{nombre[s3.iloc[0].geo_id]} ({'+' if s3.iloc[0].d >= 0 else '−'}{num(abs(s3.iloc[0].d) * 100, 1)} puntos).",
                        "items": [[r.geo_id, nombre[r.geo_id], _r(r.d)] for r in s3.itertuples()]})
    vol = ind[ind.index.astype(str).str.startswith("02-")].dropna(subset=["volatilidad_pedersen"]).sort_values("volatilidad_pedersen", ascending=False)
    if not vol.empty:
        ins.append({"tipo": "elecciones", "titulo": "Los terremotos electorales",
                    "texto": "Las generales con mayor volatilidad (cambio neto de voto entre familias respecto a la anterior) "
                             "fueron " + ", ".join(f"{e[3:7]}{' (' + ('abr' if e[7:] == '04' else 'nov') + ')' if e[3:7] == '2019' else ''}"
                                                    f" con {pct(v, 0)}" for e, v in vol.volatilidad_pedersen.head(3).items()) + ".",
                    "items": [[e, e, _r(v)] for e, v in vol.volatilidad_pedersen.head(5).items()]})
    _write("insights.json", ins)
    return {"geo": geometrias(), "territorios": len(T), "elecciones": len(E), "insights": len(ins)}


if __name__ == "__main__":
    print(exportar())
