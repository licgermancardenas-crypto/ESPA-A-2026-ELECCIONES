"""Genera el tablero de Power BI del pronóstico 29-N como proyecto PBIP (TMDL + PBIR).

    reports/powerbi_29n/ATLAS_Espana_29N.pbip    <- abrir en Power BI Desktop y pulsar Actualizar
    reports/powerbi_29n/datos/*.csv              (pbi/datos.py)

Mapas: medidas DAX que arman un SVG con trazos precalculados (visual de imagen), sin visuales personalizados:
nacional por métrica (10), provincial por municipio, ubicación de la circunscripción y evolución 2015–2023.

Uso: python -m atlas_spain.pronostico.pbi.proyecto [--sin-datos]
"""
from __future__ import annotations

import argparse
import json
import shutil
import uuid

from ...paths import ROOT
from .base import (
    BASE_THEME, H, INK, MUTED, ORO, PBI_TEMAS, SCH, V_PAGE, V_REPORT, V_VISUAL, VIO, X0,
    C, Me, Pagina, barras, color, escribir, lit, proj, q, tabla, tabla_calculada, tabla_csv, tema,
)
from .datos import METRICAS

NOMBRE = "ATLAS_Espana_29N"
DIR = ROOT / "reports" / "powerbi_29n"
DATOS = DIR / "datos"
F = "Mapas"
PCT, PCT0, MIL = "0.0%", "0%", "#,0"
GRIS = "#E4DFEE"
WEB = "https://atlas-espana-29n.vercel.app"


def svg(ancho, alto, cuerpo: str) -> str:
    return (f'VAR svg = "<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 " & {ancho} & " " & {alto} & "\'>" & {cuerpo} & "</svg>"\n'
            '            RETURN "data:image/svg+xml;utf8," & SUBSTITUTE(SUBSTITUTE(svg, "%", "%25"), "#", "%23")')


SWITCH = "SWITCH(idm, " + ", ".join(f"{mid}, Provincias[{col}]" for mid, _, col, _ in METRICAS[:-1]) + f", Provincias[{METRICAS[-1][2]}])"


def leyenda_dax(x, y, paso=26, tam=15, filtro="Leyendas[metrica_id] = idm"):
    return (f"CONCATENATEX(FILTER(ALL(Leyendas), {filtro}), "
            f"\"<rect x='{x}' y='\" & ({y} + Leyendas[orden] * {paso}) & \"' width='20' height='15' rx='3' fill='\" & Leyendas[color] & \"' stroke='#B9AEDB' stroke-width='0.6'/>"
            f"<text x='{x + 28}' y='\" & ({y + 13} + Leyendas[orden] * {paso}) & \"' font-family='Segoe UI' font-size='{tam}' fill='{INK}'>\" & Leyendas[etiqueta] & \"</text>\", \"\", Leyendas[orden], ASC)")


def medidas(P) -> list:
    an, al = P["ancho_nac"], P["alto_nac"]
    cx, cy, cw, ch = P["caja_can"]
    caja = (f"\"<rect x='{cx}' y='{cy}' width='{cw}' height='{ch}' rx='10' fill='none' stroke='#B9AEDB' stroke-dasharray='6 5'/>"
            f"<text x='{cx + 12}' y='{cy + 22}' font-family='Segoe UI' font-size='15' fill='{MUTED}'>Canarias</text>\"")
    base = """
            VAR sel = VALUES(Provincias[provincia_id])
            VAR todo = COUNTROWS(sel) = COUNTROWS(ALL(Provincias))"""
    agrupar = ("CONCATENATEX(DISTINCT(SELECTCOLUMNS(t, \"@c\", [@c])), VAR col = [@c] RETURN \"<g fill='\" & col & \"'>\" & "
               "CONCATENATEX(FILTER(t, [@c] = col), \"<path d='\" & Provincias[path] & \"'/>\", \"\") & \"</g>\", \"\")")
    resalte = ("IF(todo, \"\", \"<g fill='none' stroke='#1D1631' stroke-width='4' transform='scale(0.5)'>\" & "
               "CONCATENATEX(FILTER(ALL(Provincias), Provincias[provincia_id] IN sel), \"<path d='\" & Provincias[path] & \"'/>\", \"\") & \"</g>\")")
    m = [
        ("Corte", f'"Encuestas hasta {P["corte"]} · {P["n_encuestas"]} encuestas · modelo {P["modelo"]} · 10.000 simulaciones"', None, None),
        ("Circunscripciones", "COUNTROWS(Provincias)", MIL, "KPI"),
        ("Escaños totales", "SUM(Provincias[escanos])", MIL, "KPI"),
        ("Prob PP primero", f"{P['p_pp_primero']}", PCT0, "KPI"),
        ("Prob PSOE primero", f"{P['p_psoe_primero']}", PCT0, "KPI"),
        ("Prob mayoria PP Vox", f"{P['p_mayoria']}", PCT0, "KPI"),
        ("Muy competitivas", 'CALCULATE(COUNTROWS(Provincias), Provincias[competitividad] = "Muy competitiva") + 0', MIL, "KPI"),
        ("Cambian vs 2023", 'CALCULATE(COUNTROWS(Provincias), Provincias[cambia_2023] = "Sí") + 0', MIL, "KPI"),
        ("Acierto backtest", f"{P['acierto']}", PCT0, "KPI"),
        ("Error medio backtest", f"{P['mae']}", "0.00", "KPI"),
        ("Escaños esperados", "SUM('Escaños nacional'[media])", "0", "Escaños"),
        ("Escaños P10", "SUM('Escaños nacional'[p10])", "0", "Escaños"),
        ("Escaños P90", "SUM('Escaños nacional'[p90])", "0", "Escaños"),
        ("Simulaciones", "SUM('Dist PP Vox'[simulaciones])", MIL, "Escaños"),
        ("Escaños esperados circ", "SUM(Candidaturas[escanos_media])", "0.0", "Escaños"),
        ("Escaños escenario", "SUM(Escenarios[escanos])", "0.0", "Escaños"),
        ("Estimación media", "AVERAGE('Encuestas serie'[estimacion])", PCT, "Encuestas"),
        ("Error medio pp", "AVERAGE(Backtest[mae_pp])", "0.00", "Validación"),
        ("Acierto ganador", "AVERAGE(Backtest[acierto_ganador])", PCT0, "Validación"),
        # ficha
        ("Circ seleccionada", 'IF(HASONEVALUE(Provincias[provincia_id]), SELECTEDVALUE(Provincias[provincia]) & " · " & SELECTEDVALUE(Provincias[escanos]) & " escaños", "Elige una circunscripción")', None, "Ficha"),
        ("Favorito sel", 'IF(HASONEVALUE(Provincias[provincia_id]), SELECTEDVALUE(Provincias[favorito]), "—")', None, "Ficha"),
        ("P victoria sel", "IF(HASONEVALUE(Provincias[provincia_id]), SELECTEDVALUE(Provincias[p_victoria]))", PCT0, "Ficha"),
        ("Voto favorito sel", 'IF(HASONEVALUE(Provincias[provincia_id]), FORMAT(SELECTEDVALUE(Provincias[voto_favorito]), "0.0%") & " [" & FORMAT(SELECTEDVALUE(Provincias[voto_p10]), "0%") & "–" & FORMAT(SELECTEDVALUE(Provincias[voto_p90]), "0%") & "]", "—")', None, "Ficha"),
        ("Competitividad sel", 'IF(HASONEVALUE(Provincias[provincia_id]), SELECTEDVALUE(Provincias[competitividad]), "—")', None, "Ficha"),
        ("Calidad sel", 'IF(HASONEVALUE(Provincias[provincia_id]), SELECTEDVALUE(Provincias[calidad_clase]) & " · " & SELECTEDVALUE(Provincias[calidad]) & "/100", "—")', None, "Ficha"),
        ("Ganador 2023 sel", 'IF(HASONEVALUE(Provincias[provincia_id]), SELECTEDVALUE(Provincias[ganador_2023]) & " (" & FORMAT(SELECTEDVALUE(Provincias[voto_ganador_2023]), "0.0%") & ")", "—")', None, "Ficha"),
        ("Color candidatura", 'SELECTEDVALUE(Candidaturas[color], "#FFFFFF")', None, "Formato"),
        ("Color escaños", "SELECTEDVALUE('Escaños nacional'[color], \"#9A93AD\")", None, "Formato"),
        ("Color escenario", 'SELECTEDVALUE(Escenarios[color], "#FFFFFF")', None, "Formato"),
        ("Color favorito", 'SELECTEDVALUE(Provincias[c_fav], "#FFFFFF")', None, "Formato"),
        ("Color competitividad", 'SELECTEDVALUE(Provincias[c_comp], "#FFFFFF")', None, "Formato"),
        # ── mapas
        ("Mapa nacional", f"""
            VAR idm = SELECTEDVALUE('Métrica del mapa'[id], 1)
            {base}
            VAR t = ADDCOLUMNS(ALL(Provincias), "@c", IF(todo || Provincias[provincia_id] IN sel, {SWITCH}, "{GRIS}"))
            VAR grupos = {agrupar}
            VAR titulo = "<text x='{an + 10}' y='60' font-family='Segoe UI Semibold' font-size='24' fill='{INK}'>" & SELECTEDVALUE('Métrica del mapa'[Métrica], "Favorito 2026") & "</text>"
            VAR ley = {leyenda_dax(an + 10, 84, paso=30, tam=17)}
            VAR cuerpo = "<g stroke='#FFFFFF' stroke-width='1.6' stroke-linejoin='round' transform='scale(0.5)'>" & grupos & "</g>" & {resalte} & {caja} & titulo & ley
            {svg(an + 380, al, "cuerpo")}""", None, F, {"dataCategory": "ImageUrl"}),
        ("Mapa provincial", f"""
            VAR pid = SELECTEDVALUE(Provincias[provincia_id], "28")
            VAR pw = CALCULATE(MAX(Provincias[ancho]), ALL(Provincias), Provincias[provincia_id] = pid)
            VAR ph = CALCULATE(MAX(Provincias[alto]), ALL(Provincias), Provincias[provincia_id] = pid)
            VAR borde = CALCULATE(MAX(Provincias[borde_prov]), ALL(Provincias), Provincias[provincia_id] = pid)
            VAR t = ADDCOLUMNS(FILTER(ALL(Municipios), Municipios[provincia_id] = pid && Municipios[path_prov] <> ""), "@c", Municipios[color])
            VAR grupos = CONCATENATEX(DISTINCT(SELECTCOLUMNS(t, "@c", [@c])), VAR col = [@c] RETURN "<g fill='" & col & "'>" & CONCATENATEX(FILTER(t, [@c] = col), "<path d='" & Municipios[path_prov] & "'/>", "") & "</g>", "")
            VAR cuerpo = "<g stroke='#FFFFFF' stroke-width='0.8' stroke-linejoin='round' transform='scale(0.5)'>" & grupos & "</g>"
                & "<g fill='none' stroke='{INK}' stroke-width='3' transform='scale(0.5)'><path d='" & borde & "'/></g>"
            {svg("pw", "ph", "cuerpo")}""", None, F, {"dataCategory": "ImageUrl"}),
        ("Leyenda del mapa", f"""
            VAR idm = SELECTEDVALUE('Métrica del mapa'[id], 1)
            VAR n = CALCULATE(COUNTROWS(Leyendas), ALL(Leyendas), Leyendas[metrica_id] = idm)
            VAR cuerpo = "<text x='4' y='18' font-family='Segoe UI Semibold' font-size='16' fill='{INK}'>" & SELECTEDVALUE('Métrica del mapa'[Métrica], "Favorito 2026") & "</text>" & {leyenda_dax(4, 32)}
            {svg(420, "(44 + n * 26)", "cuerpo")}""", None, F, {"dataCategory": "ImageUrl"}),
        ("Mapa ubicación", f"""
            VAR pid = SELECTEDVALUE(Provincias[provincia_id], "28")
            VAR t = ADDCOLUMNS(ALL(Provincias), "@c", IF(Provincias[provincia_id] = pid, "{VIO}", "{GRIS}"))
            VAR grupos = {agrupar}
            VAR cuerpo = "<g stroke='#FFFFFF' stroke-width='1.6' transform='scale(0.5)'>" & grupos & "</g>" & {caja}
            {svg(an, al, "cuerpo")}""", None, F, {"dataCategory": "ImageUrl"}),
    ]
    for e, nom in [("201512", "2015"), ("201606", "2016"), ("201904", "Abr 2019"), ("201911", "Nov 2019"), ("202307", "2023")]:
        m.append((f"Mapa {nom}", f"""
            VAR t = ADDCOLUMNS(ALL(Provincias), "@c", Provincias[c_{e}])
            VAR grupos = {agrupar}
            VAR cuerpo = "<g stroke='#FFFFFF' stroke-width='1.6' transform='scale(0.5)'>" & grupos & "</g>"
                & "<text x='{an - 20}' y='70' text-anchor='end' font-family='Segoe UI Black' font-size='72' fill='{INK}'>{nom}</text>"
            {svg(an, al, "cuerpo")}""", None, F, {"dataCategory": "ImageUrl"}))
    return m


def modelo(P) -> dict[str, str]:
    T = {}
    s, i, d = "string", "int64", "double"
    cols_p = [("provincia_id", s, None), ("provincia", s, None), ("ccaa", s, None), ("escanos", i, "0"), ("favorito", s, None),
              ("favorito_bloque", s, None), ("favorito_siglas", s, None), ("p_victoria", d, PCT0), ("voto_favorito", d, PCT),
              ("voto_p10", d, PCT), ("voto_p90", d, PCT), ("margen_p50", d, PCT), ("margen_p10", d, PCT), ("margen_p90", d, PCT),
              ("escanos_favorito", d, "0.0"), ("competitividad", s, None), ("calidad", i, "0"), ("calidad_clase", s, None),
              ("ganador_2023", s, None), ("voto_ganador_2023", d, PCT), ("cambia_2023", s, None)] + \
             [(c, s, None) for c in ("c_fav", "c_prob", "c_comp", "c_cambio", "c_g2023", "c_cal", "c_v_pp", "c_v_psoe", "c_v_vox", "c_v_fa",
                                     "c_201512", "c_201606", "c_201904", "c_201911", "c_202307", "g_201512", "g_201606", "g_201904",
                                     "g_201911", "g_202307", "path", "etiqueta", "borde_prov")] + \
             [("cx", i, None), ("cy", i, None), ("ancho", i, None), ("alto", i, None)]
    ocultas = tuple(c for c, _, _ in cols_p if c.startswith(("c_", "path", "cx", "cy", "ancho", "alto", "borde", "etiqueta")))
    T["Provincias"] = tabla_csv("Provincias", "provincias.csv", cols_p, ocultas=ocultas,
                                extra_col={"provincia_id": {"isKey": ""}, "provincia": {"sortByColumn": "provincia_id"}})
    T["Municipios"] = tabla_csv("Municipios", "municipios.csv", [("municipio_id", s, None), ("provincia_id", s, None), ("municipio", s, None),
                                                                 ("ganador_2023", s, None), ("voto_ganador_2023", d, PCT), ("color", s, None),
                                                                 ("path_prov", s, None)], ocultas=("color", "path_prov"))
    T["Candidaturas"] = tabla_csv("Candidaturas", "candidaturas.csv", [
        ("provincia_id", s, None), ("bloque", s, None), ("candidatura", s, None), ("siglas", s, None), ("cabeza_lista", s, None),
        ("implantacion", s, None), ("voto_medio", d, PCT), ("voto_p10", d, PCT), ("voto_p90", d, PCT), ("p_victoria", d, PCT0),
        ("escanos_media", d, "0.0"), ("escanos_p10", d, "0"), ("escanos_p90", d, "0"), ("p_escano", d, PCT0), ("color", s, None)],
        ocultas=("color",), extra_col={"_sum": ("escanos_media",)})
    T["Escenarios"] = tabla_csv("Escenarios", "escenarios.csv", [("provincia_id", s, None), ("escenario", s, None), ("orden", i, None),
                                                                 ("bloque", s, None), ("candidatura", s, None), ("voto", d, PCT),
                                                                 ("escanos", d, "0.0"), ("color", s, None)], ocultas=("color", "orden"),
                                extra_col={"escenario": {"sortByColumn": "orden"}})
    T["Escaños nacional"] = tabla_csv("Escaños nacional", "escanos_nacional.csv", [("bloque", s, None), ("nombre", s, None), ("media", d, "0.0"),
                                                                                   ("p10", d, "0"), ("p50", d, "0"), ("p90", d, "0"), ("color", s, None)],
                                      ocultas=("color",))
    T["Dist PP Vox"] = tabla_csv("Dist PP Vox", "dist_pp_vox.csv", [("escanos", i, "0"), ("simulaciones", i, MIL), ("mayoria", s, None)])
    T["Encuestas serie"] = tabla_csv("Encuestas serie", "encuestas_serie.csv", [("instituto", s, None), ("campo_fin", "dateTime", "dd/mm/yyyy"),
                                                                                ("partido", s, None), ("estimacion", d, PCT)])
    T["Encuestas usadas"] = tabla_csv("Encuestas usadas", "encuestas_usadas.csv", [
        ("instituto", s, None), ("medio", s, None), ("campo_inicio", s, None), ("campo_fin", s, None), ("muestra", s, None), ("PP", s, None),
        ("PSOE", s, None), ("VOX", s, None), ("FA", s, None), ("PODEMOS", s, None), ("SALF", s, None), ("fuente_original", s, None)])
    T["Backtest"] = tabla_csv("Backtest", "backtest.csv", [("eleccion", s, None), ("modelo", s, None), ("lambda", d, "0.00"), ("kl", d, "0.0000"),
                                                           ("mae_pp", d, "0.00"), ("acierto_ganador", d, PCT0), ("error_escanos", i, "0")])
    T["Modelos"] = tabla_csv("Modelos", "modelos.csv", [("modelo", s, None), ("kl", d, "0.0000"), ("mae_pp", d, "0.00"),
                                                        ("acierto_ganador", d, PCT0), ("error_escanos", d, "0.0"), ("seleccionado", i, "0")])
    T["Error encuestas"] = tabla_csv("Error encuestas", "error_encuestas.csv", [("eleccion", s, None), ("bloque", s, None), ("error_log", d, "0.000")])
    T["Fuentes"] = tabla_csv("Fuentes", "fuentes.csv", [("fuente", s, None), ("origen", s, None), ("url", s, None), ("tipo", s, None),
                                                        ("estado", s, None), ("control", s, None)])
    T["Limitaciones"] = tabla_csv("Limitaciones", "limitaciones.csv", [("orden", i, None), ("limitacion", s, None)])
    T["Leyendas"] = tabla_csv("Leyendas", "leyendas.csv", [("metrica_id", i, None), ("orden", i, None), ("color", s, None), ("etiqueta", s, None)],
                              oculta_tabla=True)
    filas = ",\n    ".join(f'{{{mid}, "{n}"}}' for mid, n, _, _ in METRICAS)
    T["Métrica del mapa"] = tabla_calculada("Métrica del mapa", f'DATATABLE("id", INTEGER, "Métrica", STRING, {{\n    {filas}\n}})',
                                            [("id", "int64", None, {"isHidden": True}), ("Métrica", "string", None, {"sortByColumn": "id"})])
    T["Medidas"] = tabla_calculada("Medidas", "{BLANK()}", [("Value", "string", None, {"isHidden": True})], medidas(P))
    archivos = {f"definition/tables/{n}.tmdl": s_ for n, s_ in T.items()}
    archivos["definition/expressions.tmdl"] = (
        f'expression CarpetaDatos = "{DATOS}\\" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        "\tannotation PBI_ResultType = Text\n")
    rels = [("rel_cand_prov", "Candidaturas.provincia_id", "Provincias.provincia_id"),
            ("rel_esc_prov", "Escenarios.provincia_id", "Provincias.provincia_id"),
            ("rel_mun_prov", "Municipios.provincia_id", "Provincias.provincia_id")]
    archivos["definition/relationships.tmdl"] = "\n".join(f"relationship {n}\n\tfromColumn: {a}\n\ttoColumn: {b}\n" for n, a, b in rels)
    archivos["definition/database.tmdl"] = "database\n\tcompatibilityLevel: 1600\n"
    orden = json.dumps(["CarpetaDatos"] + list(T), ensure_ascii=False)
    archivos["definition/model.tmdl"] = (
        "model Model\n\tculture: es-ES\n\tdefaultPowerBIDataSourceVersion: powerBI_V3\n\tdiscourageImplicitMeasures\n"
        "\tsourceQueryCulture: es-ES\n\tdataAccessOptions\n\t\tlegacyRedirects\n\t\treturnErrorValuesAsNull\n\n"
        f"annotation PBI_QueryOrder = {orden}\n\n" + "\n".join(f"ref table {q(n)}" for n in T) + "\n")
    archivos["definition.pbism"] = json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}}, indent=2)
    return archivos


NAV = [("p01_panel", "Panel nacional", "◉"), ("p02_mapa", "Mapa nacional", "▦"), ("p03_provincia", "Mapa por provincia", "▩"),
       ("p04_circunscripciones", "Circunscripciones", "▤"), ("p05_ficha", "Ficha y escenarios", "☑"),
       ("p06_evolucion", "Evolución 2015–2023", "↗"), ("p07_encuestas", "Encuestas", "%"), ("p08_validacion", "Validación", "✓"),
       ("p09_datos", "Datos y metodología", "ℹ")]


def barra_nav(pg: Pagina, activa: str):
    pg.texto(0, 0, 200, H, [[("ATLAS", {"size": 20, "bold": True, "color": "#FFFFFF", "font": "Segoe UI Black"})],
                             [("ESPAÑA 29-N", {"size": 9, "bold": True, "color": ORO})],
                             [("Generales · Congreso", {"size": 9, "color": "#CFC7E2"})]], fondo=INK)
    for k, (dest, et, ic) in enumerate(NAV):
        act = dest == activa
        pg.boton(10, 98 + k * 42, 180, 36, f"{ic}   {et}", dest, fondo=VIO if act else "#2A2147",
                 fg="#FFFFFF" if act else "#D9D2EA", size=10, hover="#3D3166")
    pg.texto(10, 490, 180, 300, [[("Cómo navegar", {"size": 9, "bold": True, "color": ORO})],
                                 [("• Ctrl+clic en los botones en Power BI Desktop", {"size": 8.5, "color": "#CFC7E2"})],
                                 [("• Los segmentadores filtran y resaltan los mapas", {"size": 8.5, "color": "#CFC7E2"})],
                                 [("Veda", {"size": 9, "bold": True, "color": ORO})],
                                 [("Art. 69.7 LOREG: sin difusión de sondeos desde el 24-nov. Pronóstico congelado con encuestas hasta esa fecha.", {"size": 8.5, "color": "#CFC7E2"})],
                                 [("Web: atlas-espana-29n.vercel.app", {"size": 8.5, "color": "#E9B6FF", "url": WEB})]])


def nueva(nombre, titulo, sub):
    pg = Pagina(nombre, titulo, sub)
    barra_nav(pg, nombre)
    return pg


def tarjetas(pg, y, items, w=220, h=86, x=X0):
    for k, (m, et) in enumerate(items):
        pg.tarjeta(x + k * (w + 10), y, w, h, Me(m), et, size=22)


def grafico(pg, tipo, x, y, w, h, cat, ys, titulo, serie=None, leyenda=True, etiquetas=False, sort=None):
    objs = {"legend": [{"properties": {"show": lit(leyenda), "position": lit("Top"), "fontSize": lit(9)}}],
            "labels": [{"properties": {"show": lit(etiquetas), "fontSize": lit(8.5), "color": color(INK)}}],
            "valueAxis": [{"properties": {"gridlineShow": lit(False), "showAxisTitle": lit(False)}}],
            "categoryAxis": [{"properties": {"fontSize": lit(9), "labelColor": color(INK), "showAxisTitle": lit(False)}}]}
    qy = {"Category": [proj(cat)], "Y": [proj(v) for v in ys]}
    if serie:
        qy["Series"] = [proj(serie)]
    return pg.add(tipo, x, y, w, h, query=qy, objects=objs, titulo=titulo, sort=sort)


def informe(P) -> dict:
    pags = []
    metrica = lambda pg, x, y, w=330, h=58, presel=None, sync="metrica": pg.segmentador(  # noqa: E731
        x, y, w, h, C("Métrica del mapa", "Métrica"), "Métrica del mapa", unico=True, sync=sync, presel=presel)
    prov = lambda pg, x, y, w=330, h=58, unico=False, presel=None, sync=None: pg.segmentador(  # noqa: E731
        x, y, w, h, C("Provincias", "provincia"), "Circunscripción", sync=sync or ("prov" + ("u" if unico else "")), unico=unico, presel=presel)
    ccaa = lambda pg, x, y, w=330, h=58: pg.segmentador(x, y, w, h, C("Provincias", "ccaa"), "Comunidad autónoma", sync="ccaa")  # noqa: E731

    # 1 ── Panel
    pg = nueva("p01_panel", "Pronóstico generales 29-N-2026 · Congreso",
               f"52 circunscripciones · 350 escaños · {P['n_encuestas']} encuestas hasta {P['corte']} · swing proporcional validado a ciegas · 10.000 simulaciones")
    tarjetas(pg, 92, [("Prob PP primero", "PP primero en escaños"), ("Prob mayoria PP Vox", "Mayoría PP + Vox (≥176)"),
                      ("Prob PSOE primero", "PSOE primero en escaños"), ("Muy competitivas", "Circunscripciones muy competitivas"),
                      ("Cambian vs 2023", "Cambian de más votada vs 2023"), ("Acierto backtest", "Acierto del ganador (backtest)")], w=220)
    barras(pg, X0, 190, 460, 704, C("Escaños nacional", "nombre"), Me("Escaños esperados"), "Escaños esperados por candidatura (media)",
           fx="Color escaños", sort=[(Me("Escaños esperados"), "Descending")])
    metrica(pg, X0 + 470, 190, w=300, presel="Favorito 2026")
    ccaa(pg, X0 + 780, 190, w=300)
    pg.imagen(X0 + 470, 254, 908, 640, "Mapa nacional")
    pags.append(pg)

    # 2 ── Mapa nacional
    pg = nueva("p02_mapa", "Mapa nacional", "10 métricas · el segmentador de comunidad resalta sus provincias · Canarias en recuadro")
    metrica(pg, X0, 92, w=360, presel="Favorito 2026")
    ccaa(pg, X0, 160, w=360)
    pg.imagen(X0 + 370, 88, 1008, 806, "Mapa nacional")
    tabla(pg, X0, 228, 360, 666, [(C("Provincias", "provincia"), "Circunscripción"), (C("Provincias", "favorito_siglas"), "Favorito"),
                                  (C("Provincias", "p_victoria"), "P"), (C("Provincias", "competitividad"), "Competitividad")],
          "Circunscripciones", fx=[(C("Provincias", "favorito_siglas"), "Color favorito")], sort=[(C("Provincias", "p_victoria"), "Ascending")])
    pags.append(pg)

    # 3 ── Mapa por provincia
    pg = nueva("p03_provincia", "Mapa por provincia", "Municipios: candidatura más votada en 2023 · tabla: pronóstico 2026 de la circunscripción")
    prov(pg, X0, 92, w=300, unico=True, presel="Madrid")
    pg.imagen(X0, 158, 300, 300, "Mapa ubicación")
    pg.imagen(X0 + 310, 88, 760, 806, "Mapa provincial")
    tabla(pg, X0 + 1080, 88, 298, 400, [(C("Candidaturas", "siglas"), "Candidatura"), (C("Candidaturas", "voto_medio"), "Voto"),
                                         (C("Candidaturas", "escanos_media"), "Esc.")], "Pronóstico 2026",
          fx=[(C("Candidaturas", "siglas"), "Color candidatura")], sort=[(C("Candidaturas", "voto_medio"), "Descending")])
    tabla(pg, X0, 466, 300, 428, [(C("Municipios", "municipio"), "Municipio"), (C("Municipios", "ganador_2023"), "Más votada 2023"),
                                  (C("Municipios", "voto_ganador_2023"), "%")], "Municipios 2023", sort=[(C("Municipios", "municipio"), "Ascending")])
    tabla(pg, X0 + 1080, 498, 298, 396, [(C("Municipios", "ganador_2023"), "Más votada 2023"), (C("Municipios", "municipio"), "Municipios")],
          "Municipios por candidatura más votada")
    pags.append(pg)

    # 4 ── Circunscripciones
    pg = nueva("p04_circunscripciones", "Circunscripciones", "52 contiendas: favorito, probabilidad, voto con intervalo 80 %, margen, escaños, competitividad y calidad")
    ccaa(pg, X0, 92, w=300)
    pg.segmentador(X0 + 310, 92, 300, 58, C("Provincias", "competitividad"), "Competitividad", sync="comp")
    pg.segmentador(X0 + 620, 92, 300, 58, C("Provincias", "favorito"), "Favorito", sync="fav")
    tabla(pg, X0, 160, 1378, 734, [(C("Provincias", "provincia"), "Circunscripción"), (C("Provincias", "ccaa"), "Comunidad"),
                                   (C("Provincias", "escanos"), "Escaños"), (C("Provincias", "favorito_siglas"), "Favorito"),
                                   (C("Provincias", "p_victoria"), "P(victoria)"), (C("Provincias", "voto_favorito"), "Voto"),
                                   (C("Provincias", "voto_p10"), "P10"), (C("Provincias", "voto_p90"), "P90"),
                                   (C("Provincias", "margen_p50"), "Margen"), (C("Provincias", "escanos_favorito"), "Esc. favorito"),
                                   (C("Provincias", "competitividad"), "Competitividad"), (C("Provincias", "ganador_2023"), "Más votada 2023"),
                                   (C("Provincias", "calidad"), "Calidad")], "Tabla de contiendas",
          fx=[(C("Provincias", "favorito_siglas"), "Color favorito"), (C("Provincias", "competitividad"), "Color competitividad")],
          sort=[(C("Provincias", "p_victoria"), "Ascending")])
    pags.append(pg)

    # 5 ── Ficha
    pg = nueva("p05_ficha", "Ficha de circunscripción y escenarios", "Voto y escaños por candidatura · escenarios nacionales según margen PP–PSOE en escaños")
    prov(pg, X0, 92, w=300, unico=True, presel="Sevilla", sync="ficha")
    pg.imagen(X0, 158, 300, 260, "Mapa ubicación")
    for k, (m, et) in enumerate([("Circ seleccionada", "Circunscripción"), ("Favorito sel", "Favorito"), ("P victoria sel", "P(más votada)"),
                                 ("Voto favorito sel", "Voto [IC 80 %]"), ("Competitividad sel", "Competitividad")]):
        pg.tarjeta(X0 + 310 + k * 214, 92, 206, 76, Me(m), et, size=13 if k in (0, 1, 3, 4) else 20)
    tabla(pg, X0 + 310, 176, 1068, 330, [(C("Candidaturas", "siglas"), "Candidatura"), (C("Candidaturas", "cabeza_lista"), "Cabeza de lista"),
                                         (C("Candidaturas", "voto_medio"), "Voto"), (C("Candidaturas", "voto_p10"), "P10"),
                                         (C("Candidaturas", "voto_p90"), "P90"), (C("Candidaturas", "p_victoria"), "P(más votada)"),
                                         (C("Candidaturas", "escanos_media"), "Escaños"), (C("Candidaturas", "p_escano"), "P(≥1 esc.)"),
                                         (C("Candidaturas", "implantacion"), "Implantación")],
          "Pronóstico por candidatura", fx=[(C("Candidaturas", "siglas"), "Color candidatura")], sort=[(C("Candidaturas", "voto_medio"), "Descending")])
    grafico(pg, "clusteredColumnChart", X0 + 310, 516, 1068, 378, C("Escenarios", "candidatura"), [Me("Escaños escenario")],
            "Escaños por escenario", serie=C("Escenarios", "escenario"))
    pg.tarjeta(X0, 428, 300, 70, Me("Ganador 2023 sel"), "Más votada en 2023", size=12)
    pg.tarjeta(X0, 506, 300, 70, Me("Calidad sel"), "Calidad del dato", size=13)
    pg.texto(X0, 584, 300, 310, [[("Escenarios", {"size": 11, "bold": True})],
                                  [("Las 10.000 simulaciones nacionales se agrupan por margen PP–PSOE en escaños: 20 % más favorable al PSOE, "
                                    "todas (base) y 20 % más favorable al PP. Se muestra qué ocurre en esta circunscripción en cada grupo.", {"size": 9, "color": MUTED})]],
             fondo="#FFFFFF")
    pags.append(pg)

    # 6 ── Evolución
    pg = nueva("p06_evolucion", "Evolución 2015–2023", "Candidatura más votada por circunscripción en las cinco generales (resultado oficial, Ministerio del Interior)")
    for k, nom in enumerate(["2015", "2016", "Abr 2019", "Nov 2019", "2023"]):
        pg.imagen(X0 + k * 276, 92, 270, 220, f"Mapa {nom}")
    tabla(pg, X0, 322, 1378, 572, [(C("Provincias", "provincia"), "Circunscripción"), (C("Provincias", "g_201512"), "2015"),
                                   (C("Provincias", "g_201606"), "2016"), (C("Provincias", "g_201904"), "Abr 2019"),
                                   (C("Provincias", "g_201911"), "Nov 2019"), (C("Provincias", "g_202307"), "2023"),
                                   (C("Provincias", "favorito"), "Favorito 2026"), (C("Provincias", "p_victoria"), "P")],
          "Más votada por elección", sort=[(C("Provincias", "provincia"), "Ascending")])
    pags.append(pg)

    # 7 ── Encuestas
    pg = nueva("p07_encuestas", "Encuestas", "Estimaciones de voto publicadas (vía Wikipedia, con enlace a la original; pendientes de verificación)")
    grafico(pg, "lineChart", X0, 92, 1378, 420, C("Encuestas serie", "campo_fin"), [Me("Estimación media")], "Estimación de voto desde junio de 2025",
            serie=C("Encuestas serie", "partido"))
    tabla(pg, X0, 522, 1378, 372, [(C("Encuestas usadas", "instituto"), "Instituto"), (C("Encuestas usadas", "medio"), "Medio"),
                                   (C("Encuestas usadas", "campo_fin"), "Fin de campo"), (C("Encuestas usadas", "muestra"), "Muestra"),
                                   (C("Encuestas usadas", "PP"), "PP"), (C("Encuestas usadas", "PSOE"), "PSOE"), (C("Encuestas usadas", "VOX"), "Vox"),
                                   (C("Encuestas usadas", "FA"), "FA"), (C("Encuestas usadas", "PODEMOS"), "Podemos"), (C("Encuestas usadas", "SALF"), "SALF"),
                                   (C("Encuestas usadas", "fuente_original"), "Fuente original")], "Encuestas usadas en la media (una por instituto, 21 días)",
          sort=[(C("Encuestas usadas", "campo_fin"), "Descending")])
    pags.append(pg)

    # 8 ── Validación
    pg = nueva("p08_validacion", "Validación del modelo", "Backtesting a ciegas con origen móvil: 2015, 2016, abril 2019, noviembre 2019 y 2023")
    tabla(pg, X0, 92, 680, 230, [(C("Modelos", "modelo"), "Modelo"), (C("Modelos", "kl"), "KL"), (C("Modelos", "mae_pp"), "Error (pp)"),
                                 (C("Modelos", "acierto_ganador"), "Acierto ganador"), (C("Modelos", "error_escanos"), "Escaños mal asignados"),
                                 (C("Modelos", "seleccionado"), "Elegido")], "Comparación de modelos (media 2016–2023)",
          sort=[(C("Modelos", "kl"), "Ascending")])
    grafico(pg, "lineChart", X0 + 690, 92, 688, 400, C("Backtest", "eleccion"), [Me("Error medio pp")], "Error medio por elección (pp)",
            serie=C("Backtest", "modelo"))
    tabla(pg, X0, 332, 680, 562, [(C("Backtest", "eleccion"), "Elección"), (C("Backtest", "modelo"), "Modelo"), (C("Backtest", "mae_pp"), "Error"),
                                  (C("Backtest", "acierto_ganador"), "Acierto"), (C("Backtest", "kl"), "KL"), (C("Backtest", "error_escanos"), "Escaños")],
          "Métricas por elección", sort=[(C("Backtest", "eleccion"), "Descending")])
    pg.texto(X0 + 690, 502, 688, 392, [
        [("Cómo se valida", {"size": 12, "bold": True})],
        [("Cada elección se predice solo con resultados anteriores y encuestas cerradas 6 días antes. Los modelos con parámetros se entrenan "
          "con transiciones previas; λ se elige dentro de ellas. Hay un test automático que demuestra que el resultado objetivo no altera la predicción.", {"size": 10})],
        [("Selección", {"size": 12, "bold": True})],
        [(f"Se elige el modelo más simple cuya KL no supera a la mejor en más de 0,002: swing proporcional (error {P['mae']:.2f} pp, "
          f"acierto {P['acierto']:.0%}).", {"size": 10})],
        [("Incertidumbre", {"size": 12, "bold": True})],
        [(f"σ nacional {P['sigma_nac']} (error común de las encuestas) y σ provincial {P['sigma_prov']}, calibrados por log score y cobertura "
          "del intervalo 80 % en voto y escaños.", {"size": 10})]], fondo="#FFFFFF")
    pags.append(pg)

    # 9 ── Datos y metodología
    pg = nueva("p09_datos", "Datos, calidad y metodología", "Cada dato es trazable a su fuente")
    tabla(pg, X0, 92, 680, 330, [(C("Fuentes", "fuente"), "Fuente"), (C("Fuentes", "tipo"), "Tipo"), (C("Fuentes", "estado"), "Estado"),
                                 (C("Fuentes", "control"), "Control")], "Fuentes")
    tabla(pg, X0, 432, 680, 462, [(C("Limitaciones", "limitacion"), "Limitación")], "Limitaciones conocidas",
          sort=[(C("Limitaciones", "orden"), "Ascending")])
    pg.texto(X0 + 690, 92, 688, 802, [
        [("Qué se pronostica", {"size": 12, "bold": True})],
        [("Las 52 circunscripciones del Congreso (350 escaños). Por contienda: favorito, probabilidad de ser la más votada, voto con intervalo "
          "80 %, margen, escaños por candidatura (D'Hondt, barrera 3 %), competitividad, escenarios y calidad del dato.", {"size": 10})],
        [("Modelo", {"size": 12, "bold": True})],
        [("Voto provincial = media nacional de encuestas × fuerza relativa previa de la provincia (swing proporcional), normalizado. "
          "Media de encuestas: ventana de 21 días, vida media 7 días, una por instituto, peso √muestra.", {"size": 10})],
        [("Equivalencias", {"size": 12, "bold": True})],
        [("Solo continuidad legal. Frente Amplio, Compromís y Unidad del Pueblo Canario usan Sumar 2023 como sustituto geográfico "
          "(declarado, 1,5× incertidumbre). Podemos y SALF: europeas 2024 de la misma formación.", {"size": 10})],
        [("Fuentes", {"size": 12, "bold": True})],
        [("Candidaturas: BOE-A-2026-23103. Resultados: Ministerio del Interior. Cartografía: INE. Encuestas: Wikipedia (secundaria, enlace a la original).", {"size": 10})],
        [("Veda", {"size": 12, "bold": True})],
        [("Art. 69.7 LOREG: no se difunden sondeos en los cinco días previos a la votación.", {"size": 10})]], fondo="#FFFFFF")
    pags.append(pg)

    archivos = {}
    for p in pags:
        archivos[f"definition/pages/{p.nombre}/page.json"] = p.json()
        for v in p.visuales:
            archivos[f"definition/pages/{p.nombre}/visuals/{v['name']}/visual.json"] = v
    archivos["definition/pages/pages.json"] = {"$schema": f"{SCH}/pagesMetadata/1.0.0/schema.json",
                                               "pageOrder": [p.nombre for p in pags], "activePageName": "p01_panel"}
    archivos["definition/version.json"] = {"$schema": f"{SCH}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}
    ver = {"visual": V_VISUAL, "report": V_REPORT, "page": V_PAGE}
    archivos["definition/report.json"] = {
        "$schema": f"{SCH}/report/{V_REPORT}/schema.json",
        "themeCollection": {"baseTheme": {"name": BASE_THEME, "reportVersionAtImport": ver, "type": "SharedResources"},
                            "customTheme": {"name": "AtlasEspana29N.json", "reportVersionAtImport": ver, "type": "RegisteredResources"}},
        "objects": {"outspacePane": [{"properties": {"expanded": lit(False)}}],
                    "section": [{"properties": {"verticalAlignment": lit("Top")}}]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "AtlasEspana29N.json", "path": "AtlasEspana29N.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True, "useEnhancedTooltips": True,
                     "useDefaultAggregateDisplayName": True}}
    archivos["StaticResources/RegisteredResources/AtlasEspana29N.json"] = tema()
    archivos["definition.pbir"] = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                                   "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NOMBRE}.SemanticModel"}}}
    return archivos


def generar(con_datos: bool = True):
    if con_datos:
        from .datos import exportar
        exportar()
    P = json.loads((DATOS / "parametros.json").read_text(encoding="utf-8"))
    sm, rp = DIR / f"{NOMBRE}.SemanticModel", DIR / f"{NOMBRE}.Report"
    for d in (rp / "definition", sm / "definition"):
        shutil.rmtree(d, ignore_errors=True)
    escribir(modelo(P), sm)
    escribir(informe(P), rp)
    tb = rp / "StaticResources" / "SharedResources" / "BaseThemes" / f"{BASE_THEME}.json"
    tb.parent.mkdir(parents=True, exist_ok=True)
    if (PBI_TEMAS / f"{BASE_THEME}.json").exists():
        shutil.copy(PBI_TEMAS / f"{BASE_THEME}.json", tb)
    for carpeta, tipo in ((sm, "SemanticModel"), (rp, "Report")):
        plat = carpeta / ".platform"
        lid = json.loads(plat.read_text())["config"]["logicalId"] if plat.exists() else str(uuid.uuid4())
        plat.write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": tipo, "displayName": NOMBRE}, "config": {"version": "2.0", "logicalId": lid}}, indent=2))
    (DIR / f"{NOMBRE}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NOMBRE}.Report"}}], "settings": {"enableAutoRecovery": True}}, indent=2))
    (DIR / ".gitignore").write_text("**/.pbi/localSettings.json\n", encoding="utf-8")
    print(f"proyecto: {DIR / (NOMBRE + '.pbip')}")
    return DIR / f"{NOMBRE}.pbip"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-datos", action="store_true")
    generar(not ap.parse_args().sin_datos)
