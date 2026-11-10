"""Data Quality Center: controles sobre el warehouse construido.

Dimensiones: completeness, validity, consistency, freshness, geographic_coverage,
historical_coverage, source_reliability. Cada control guarda métrica, umbral y
estado en ops.quality_results, con el run_id del build.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

from atlas_spain.warehouse import connect


@dataclass
class Result:
    check: str
    dimension: str
    dataset: str
    value: float | None
    threshold: str
    status: str          # pass | warn | fail | skip
    detail: str = ""


def _table_exists(con, schema: str, name: str) -> bool:
    return con.execute("select count(*) from information_schema.tables where table_schema=? and table_name=?",
                       [schema, name]).fetchone()[0] > 0


def _q(con, sql: str):
    return con.execute(sql).fetchone()


def run_checks(con) -> list[Result]:
    R: list[Result] = []

    # ── geografía ──
    if _table_exists(con, "gold", "dim_geography"):
        n_ccaa, n_prov, n_mun = _q(con, """select count(*) filter (where geo_type='ccaa'),
            count(*) filter (where geo_type='provincia'),
            count(*) filter (where geo_type='municipio' and valid_to is null) from gold.dim_geography""")
        R.append(Result("n_ccaa", "geographic_coverage", "dim_geography", n_ccaa, "=19",
                        "pass" if n_ccaa == 19 else "fail", "17 CCAA + Ceuta + Melilla"))
        R.append(Result("n_provincias", "geographic_coverage", "dim_geography", n_prov, "=52",
                        "pass" if n_prov == 52 else "fail", "50 provincias + Ceuta + Melilla"))
        R.append(Result("n_municipios_vigentes", "geographic_coverage", "dim_geography", n_mun, "8100–8200",
                        "pass" if 8100 <= n_mun <= 8200 else "warn"))
        dup = _q(con, "select count(*) - count(distinct geo_id) from gold.dim_geography")[0]
        R.append(Result("geo_id_unico", "validity", "dim_geography", dup, "=0", "pass" if dup == 0 else "fail"))
        orphans = _q(con, """select count(*) from gold.dim_geography g where parent_geo_id is not null
            and parent_geo_id not in (select geo_id from gold.dim_geography)""")[0]
        R.append(Result("padres_existentes", "consistency", "dim_geography", orphans, "=0",
                        "pass" if orphans == 0 else "fail", "todo parent_geo_id debe existir"))
        bad = _q(con, r"""select count(*) from gold.dim_geography where geo_type='municipio'
            and not regexp_full_match(official_code, '\d{5}')""")[0]
        R.append(Result("codigo_ine_municipio_5_digitos", "validity", "dim_geography", bad, "=0",
                     "pass" if bad == 0 else "fail"))

    if _table_exists(con, "gold", "geo_boundaries") and _table_exists(con, "gold", "dim_geography"):
        miss = _q(con, """select count(*) from gold.dim_geography g where g.geo_type='municipio' and g.valid_to is null
            and g.geo_id not in (select geo_id from gold.geo_boundaries)""")[0]
        R.append(Result("municipios_sin_geometria", "geographic_coverage", "geo_boundaries", miss, "<=5",
                        "pass" if miss <= 5 else "warn",
                        "diferencias esperables por altas/bajas entre diccionario y seccionado"))

    # ── población ──
    if _table_exists(con, "gold", "fact_population"):
        diff = _q(con, """
            with m as (select substr(geo_id,7,2) prov, anyo, sum(poblacion) p from gold.fact_population
                       where geo_level='municipio' and sexo='T' group by 1, 2),
                 p as (select substr(geo_id,7,2) prov, anyo, poblacion p from gold.fact_population
                       where geo_level='provincia' and sexo='T' and origen='publicado')
            select count(*) filter (where m.p <> p.p), count(*), max(abs(m.p - p.p)), min(anyo), max(anyo)
            from m join p using (prov, anyo)""")
        R.append(Result("suma_municipios_igual_provincia_publicada", "consistency", "fact_population", diff[0], "=0",
                        "pass" if diff[0] == 0 and diff[1] > 0 else ("warn" if diff[1] else "fail"),
                        f"pares provincia×año comparados: {diff[1]} ({diff[3]}–{diff[4]}); máx. diferencia: {diff[2]}"))
        der = _q(con, "select count(*), min(anyo), max(anyo) from gold.fact_population where origen='suma_municipios'")
        R.append(Result("filas_derivadas_de_municipios", "completeness", "fact_population", der[0], "informativo",
                        "pass", f"años {der[1]}–{der[2]}: tablas provinciales del INE congeladas en 2021"))
        hs = _q(con, """select count(*) from gold.fact_population t
            join gold.fact_population h using (geo_id, anyo) join gold.fact_population m using (geo_id, anyo)
            where t.sexo='T' and h.sexo='H' and m.sexo='M' and t.poblacion <> h.poblacion + m.poblacion""")[0]
        R.append(Result("total_igual_hombres_mas_mujeres", "consistency", "fact_population", hs, "=0",
                        "pass" if hs == 0 else "fail"))
        y0, y1, n = _q(con, "select min(anyo), max(anyo), count(distinct anyo) from gold.fact_population where geo_level='municipio'")
        R.append(Result("cobertura_historica_padron_municipal", "historical_coverage", "fact_population", n,
                        ">=25 años", "pass" if n >= 25 else "warn", f"{y0}–{y1}"))
        nulls = _q(con, "select avg((poblacion is null)::int) from gold.fact_population")[0]
        R.append(Result("nulos_poblacion", "completeness", "fact_population", nulls, "=0",
                        "pass" if nulls == 0 else "fail"))

    # ── electoral ──
    if _table_exists(con, "gold", "fact_turnout"):
        inc = _q(con, """select count(*) from silver.stg_ie_municipios
            where votantes <> votos_blancos + votos_nulos + votos_candidaturas""")[0]
        R.append(Result("votantes_cuadran", "consistency", "fact_turnout", inc, "=0", "pass" if inc == 0 else "fail"))
        imp = _q(con, """select count(*) filter (where (turnout > 1 and censo >= 1000) or turnout < 0),
                                count(*) filter (where turnout > 1 and censo < 1000),
                                string_agg(election_id || ' ' || geo_id, ', ') filter (where turnout > 1)
                         from gold.fact_turnout""")
        R.append(Result("participacion_en_rango", "validity", "fact_turnout", imp[0], "=0",
                        "pass" if imp[0] == 0 else "fail",
                        f"municipios < 1.000 electores con votantes > censo (dato de la fuente, p. ej. voto con "
                        f"certificación censal): {imp[1]} — {imp[2] or ''}"))
        neg = _q(con, """
            with m as (select election_id, substr(geo_id,7,2) prov, sum(votos) v from gold.fact_election_results
                       where geo_level='municipio' group by all),
                 p as (select election_id, substr(geo_id,7,2) prov, sum(votos) v from gold.fact_election_results
                       where geo_level='provincia' group by all)
            select count(*) filter (where p.v < m.v), count(*), sum(p.v - m.v) filter (where p.v >= m.v),
                   string_agg(p.election_id || ' ' || p.prov || ' (' || (p.v - m.v)::bigint || ')', ', ') filter (where p.v < m.v)
            from p join m using (election_id, prov)""")
        R.append(Result("provincia_mayor_o_igual_que_municipios", "consistency", "fact_election_results", neg[0], "=0",
                        "pass" if neg[0] == 0 else "warn",
                        f"{neg[1]} pares elección×provincia. Los ficheros municipales no incluyen el voto exterior (CERA): "
                        f"la provincia suma {int(neg[2] or 0):,} votos más en total. Casos con provincia < municipios "
                        f"(incoherencia de la fuente): {neg[3] or 'ninguno'}".replace(",", ".")))
        R.extend(seat_reconciliation(con))
    else:
        R.append(Result("datos_electorales", "completeness", "fact_election_results", None, "presentes", "skip",
                        "Sin ficheros de Infoelectoral (bloqueo anti-bot): ver PROJECT_STATUS.md"))

    # ── electoral autonómico (Open Data Euskadi) ──
    if _table_exists(con, "gold", "fact_regional_results"):
        for e, nt, nm, nme in con.execute("""
            select election_id,
                   sum(votos) filter (where nivel='territorio'), sum(votos) filter (where nivel='municipio'),
                   sum(votos) filter (where nivel='mesa')
            from gold.fact_regional_results group by 1 order by 1""").fetchall():
            ok = nt is not None and nt == nm == nme
            R.append(Result("niveles_cuadran", "consistency", f"regional {e}", (nm or 0) - (nt or 0), "=0",
                            "pass" if ok else "warn",
                            f"territorio {nt} · municipio {nm} · mesa {nme} (diferencias en la fuente se documentan, no se corrigen)"))
        R.extend(seat_reconciliation_regional(con))

    # ── frescura y fiabilidad de fuentes ──
    if _table_exists(con, "ops", "executions"):
        for sid, status, age_days in con.execute("""
            select source_id, arg_max(status, started_at),
                   date_diff('day', max(started_at), now()) from ops.executions group by 1 order by 1""").fetchall():
            R.append(Result("ultima_extraccion", "freshness", sid, age_days, "<=35 días",
                            "pass" if status in ("success", "partial") and age_days <= 35 else
                            ("fail" if status in ("failed", "blocked") else "warn"), f"estado: {status}"))
    if _table_exists(con, "gold", "dim_data_source"):
        tot, ok = _q(con, "select count(*), count(*) filter (where estado='disponible') from gold.dim_data_source")
        R.append(Result("fuentes_disponibles", "source_reliability", "dim_data_source", ok / tot if tot else None,
                        ">=0.7", "pass" if tot and ok / tot >= 0.7 else "warn", f"{ok}/{tot} responden"))
    return R


def seat_reconciliation(con) -> list[Result]:
    """Recalcula D'Hondt por provincia (Congreso) y compara con los escaños oficiales."""
    from atlas_spain.electoral.systems import congreso_district

    out = []
    rows = con.execute("""
        select r.election_id, r.geo_id, r.candidacy_id, r.votos, r.escanos, t.votos_blancos, t.numero_escanos
        from gold.fact_election_results r join gold.fact_turnout t using (election_id, geo_level, geo_id)
        where r.geo_level='provincia' and r.election_id like '02-%'""").fetchall()
    groups: dict = {}
    for e, g, c, v, s, blank, seats in rows:
        groups.setdefault((e, g), {"votes": {}, "official": {}, "blank": blank, "seats": seats})
        groups[(e, g)]["votes"][c] = v or 0
        groups[(e, g)]["official"][c] = s or 0
    mism = []
    for (e, g), d in groups.items():
        res = congreso_district(d["votes"], d["blank"] or 0, d["seats"] or 0, g[-2:])
        if res.seats != d["official"]:
            mism.append(f"{e} {g}")
    if groups:
        out.append(Result("dhondt_reproduce_escanos_oficiales", "consistency", "fact_election_results",
                          len(mism), "=0", "pass" if not mism else "fail",
                          f"{len(groups)} circunscripciones; discrepancias: {mism[:10]}"))
    return out


def seat_reconciliation_regional(con) -> list[Result]:
    """Recalcula escaños donde la fuente los publica (Congreso y Parlamento Vasco)."""
    from atlas_spain.electoral.dhondt import dhondt
    from atlas_spain.electoral.systems import congreso_district

    rows = con.execute("""select election_id, tipo, provincia_ine, candidatura, coalesce(votos, 0), coalesce(escanos, 0),
                                 coalesce(blancos, 0), coalesce(validos, 0)
                          from gold.fact_regional_results where nivel='territorio'""").fetchall()
    grupos: dict = {}
    for e, tipo, prov, cand, v, s, b, val in rows:
        g = grupos.setdefault((e, tipo, prov), {"v": {}, "s": {}, "b": b, "validos": val})
        g["v"][cand], g["s"][cand] = v, s
    comprobadas, difieren = 0, []
    for (e, tipo, prov), g in grupos.items():
        total = sum(g["s"].values())
        if total == 0:
            continue  # la fuente no publica escaños para esa convocatoria
        comprobadas += 1
        if tipo == "congreso":
            res = congreso_district(g["v"], g["b"], total, prov)
        elif tipo == "asamblea_madrid":
            # 5 % de los votos válidos; "Resto de partidos" es un agregado de la fuente y no recibe escaños
            v = {k: x for k, x in g["v"].items() if k != "Resto de partidos"}
            res = dhondt(v, total, threshold=0.05, threshold_base=g["validos"])
            res.seats["Resto de partidos"] = 0
        else:
            res = dhondt(g["v"], total, threshold=0.03, blank_votes=g["b"])
        if res.seats != g["s"]:
            difieren.append(f"{e} {prov}")
    if not comprobadas:
        return []
    return [Result("dhondt_reproduce_escanos_regionales", "consistency", "fact_regional_results", len(difieren), "=0",
                   "pass" if not difieren else "warn",
                   f"{comprobadas} circunscripciones con escaños publicados; difieren: {difieren[:10]} "
                   "(Parlamento Vasco: barrera 3 %; Asamblea de Madrid: 5 % de válidos. La barrera legal de "
                   "convocatorias vascas antiguas no está verificada)")]


def main() -> int:
    con = connect()
    run_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    try:
        results = run_checks(con)
        con.execute("""create table if not exists ops.quality_results (
            run_id varchar, run_at timestamptz, check_name varchar, dimension varchar, dataset varchar,
            value double, threshold varchar, status varchar, detail varchar)""")
        for r in results:
            con.execute("insert into ops.quality_results values (?,?,?,?,?,?,?,?,?)",
                        [run_id, now, r.check, r.dimension, r.dataset, r.value, r.threshold, r.status, r.detail])
    finally:
        con.close()
    width = max(len(r.check) for r in results) if results else 10
    for r in results:
        print(f"[{r.status:>4}] {r.dimension:<20} {r.dataset:<22} {r.check:<{width}} = {r.value} ({r.threshold}) {r.detail}")
    fails = sum(r.status == "fail" for r in results)
    print(f"\nrun_id={run_id}: {len(results)} controles, {fails} fallos")
    return 1 if fails else 0
