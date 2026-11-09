"""Genera el tablero de Power BI de ATLAS SPAIN como proyecto PBIP.

    reports/powerbi/ATLAS_Espana.pbip            <- abrir con Power BI Desktop
    reports/powerbi/ATLAS_Espana.SemanticModel/  (TMDL)
    reports/powerbi/ATLAS_Espana.Report/         (PBIR)
    reports/powerbi/datos/*.csv                  (src/atlas_spain/viz/powerbi_datos.py)

Mapas: DAX arma un SVG con los trazos precalculados y lo muestra el visual de
imagen, así responden a segmentadores sin visuales personalizados.

Uso:
    python -m atlas_spain.viz.powerbi_proyecto            (exporta datos y genera)
    python -m atlas_spain.viz.powerbi_proyecto --sin-datos
"""

from __future__ import annotations

import argparse
import json
import shutil
import uuid

from atlas_spain import paths
from atlas_spain.viz.pbi_base import (
    AZUL, BASE_THEME, BG, H, INK, LINEA, MUTED, ORO, PBI_TEMAS, ROJO, SCH, V_PAGE, V_REPORT, V_VISUAL, VIO, X0,
    C, Me, Pagina, barras, color, escribir, lit, proj, q, tabla, tabla_calculada, tabla_csv, tema,
)

NOMBRE = "ATLAS_Espana"
DIR = paths.ROOT / "reports" / "powerbi"
DATOS = DIR / "datos"
F = "Formato"
PCT, MIL = "0.0%", "#,0"

# ───────────────────────── colores por métrica ─────────────────────────
# (umbral superior, color) — el último sin umbral
ESCALAS = {
    1: ("Variación de población 10 años", [(-0.10, "#8A5A00"), (-0.05, "#C98A12"), (0, "#F2D58C"), (0.05, "#CDBFE6"), (0.10, "#8E73C4"), (None, "#4B2F8A")],
        ["< −10 %", "−10 a −5 %", "−5 a 0 %", "0 a 5 %", "5 a 10 %", "> 10 %"]),
    2: ("Densidad (hab./km²)", [(10, "#F3EFF9"), (25, "#D9CDEE"), (100, "#B19DDA"), (300, "#8467BD"), (1000, "#5B3F99"), (None, "#2E1B5E")],
        ["< 10", "10–25", "25–100", "100–300", "300–1.000", "> 1.000"]),
    3: ("Población", [(1000, "#F3EFF9"), (5000, "#D9CDEE"), (20000, "#B19DDA"), (100000, "#8467BD"), (500000, "#5B3F99"), (None, "#2E1B5E")],
        ["< 1.000", "1–5 mil", "5–20 mil", "20–100 mil", "100–500 mil", "> 500 mil"]),
    4: ("PIB per cápita (provincia)", [(22000, "#FFF6DD"), (25000, "#F8DE9A"), (28000, "#E9B949"), (32000, "#C98A12"), (36000, "#8A5A00"), (None, "#5C3B00")],
        ["< 22 k€", "22–25 k€", "25–28 k€", "28–32 k€", "32–36 k€", "> 36 k€"]),
    5: ("Tasa de paro EPA (CCAA)", [(0.07, "#EAF4F2"), (0.09, "#BFE0DA"), (0.11, "#7CC2B6"), (0.13, "#2E9C8F"), (0.15, "#1F6E66"), (None, "#0E3F3A")],
        ["< 7 %", "7–9 %", "9–11 %", "11–13 %", "13–15 %", "> 15 %"]),
}
SIN_DATO = "#E4E0EC"


def dax_color(idm_var: str, v: str) -> str:
    ramas = []
    for idm, (_, cortes, _) in ESCALAS.items():
        sw = ", ".join(f'{v} < {u}, "{c}"' for u, c in cortes[:-1])
        ramas.append(f'{idm}, SWITCH(TRUE(), {sw}, "{cortes[-1][1]}")')
    return f'IF(ISBLANK({v}), "{SIN_DATO}", SWITCH({idm_var}, {", ".join(ramas)}))'


def dax_valor_fila(t: str, nivel: str) -> str:
    """Valor de la métrica con columnas de la fila (rápido dentro de CONCATENATEX)."""
    if nivel == "prov":
        pib, paro = f"{t}[pib_pc]", "RELATED(CCAA[paro])"
    else:
        pib, paro = "RELATED(Provincias[pib_pc])", "RELATED(CCAA[paro])"
    return (f"SWITCH(idm, 1, DIVIDE({t}[pob_actual] - {t}[pob_hace10], {t}[pob_hace10]), "
            f"2, DIVIDE({t}[pob_actual], {t}[area_km2]), 3, {t}[pob_actual], 4, {pib}, 5, {paro})")


def xml(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def leyenda_dax(x: int, y: int) -> str:
    """Leyenda SVG que cambia con la métrica elegida."""
    ramas = []
    for idm, (titulo, cortes, etiquetas) in ESCALAS.items():
        s = f"<text x='{x}' y='{y}' font-family='Segoe UI' font-size='15' font-weight='700' fill='{INK}'>{xml(titulo)}</text>"
        for i, ((_, c), et) in enumerate(zip(cortes, etiquetas)):
            yy = y + 14 + i * 22
            s += (f"<rect x='{x}' y='{yy}' width='22' height='16' rx='3' fill='{c}' stroke='#FFFFFF'/>"
                  f"<text x='{x + 30}' y='{yy + 13}' font-family='Segoe UI' font-size='13' fill='{INK}'>{xml(et)}</text>")
        ramas.append(f'{idm}, "{s}"')
    return f"SWITCH(idm, {', '.join(ramas)})"


def svg_envolver(alto: int, cuerpo: str) -> str:
    return (f'VAR svg = "<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 1000 {alto}\'>" & {cuerpo} & "</svg>"\n'
            '            RETURN "data:image/svg+xml;utf8," & SUBSTITUTE(SUBSTITUTE(svg, "%", "%25"), "#", "%23")')


# ───────────────────────── modelo ─────────────────────────
def medidas(P) -> list:
    alto = P["lienzo"]["alto"]
    caja = P["caja_canarias"]
    ley = leyenda_dax(720, alto - 175)
    ccaa_sel = "VAR sel = VALUES(CCAA[ccaa_ine])\n            VAR todo = NOT ISFILTERED(CCAA[ccaa_ine]) && NOT ISFILTERED(CCAA[nombre])"
    caja_svg = (f"\"<path d='{caja}' fill='none' stroke='{MUTED}' stroke-width='1' stroke-dasharray='5 4'/>"
                f"<text x='14' y='{alto - 8}' font-family='Segoe UI' font-size='12' fill='{MUTED}'>Canarias (escala 0,85)</text>\"")
    m = [
        ("Corte", f'"Datos a {P["corte"]} · Fuentes: INE, Eurostat, Congreso"', None, F),
        ("Población", "SUM(Municipios[pob_actual])", MIL, "Demografía"),
        ("Población hace 10 años", "SUM(Municipios[pob_hace10])", MIL, "Demografía"),
        ("Variación población 10 años", """
            VAR conAmbos = FILTER(Municipios, NOT ISBLANK(Municipios[pob_hace10]) && NOT ISBLANK(Municipios[pob_actual]))
            VAR a = SUMX(conAmbos, Municipios[pob_actual])
            VAR b = SUMX(conAmbos, Municipios[pob_hace10])
            RETURN DIVIDE(a - b, b)""", "+0.0%;-0.0%;0.0%", "Demografía"),
        ("Densidad", "DIVIDE([Población], SUM(Municipios[area_km2]))", "#,0.0", "Demografía"),
        ("Municipios", "COUNTROWS(Municipios)", MIL, "Demografía"),
        ("Municipios que pierden población", """
            COUNTROWS(FILTER(Municipios, Municipios[pob_actual] < Municipios[pob_hace10]))""", MIL, "Demografía"),
        ("% municipios que pierden población", "DIVIDE([Municipios que pierden población], [Municipios])", PCT, "Demografía"),
        ("Provincias", "DISTINCTCOUNT(Municipios[provincia_ine])", "0", "Demografía"),
        ("Comunidades", "DISTINCTCOUNT(Municipios[ccaa_ine])", "0", "Demografía"),
        ("Población (serie)", "SUM('Serie población'[poblacion])", MIL, "Demografía"),
        ("Año actual", f"{P['anyo_actual']}", "0", "Demografía"),
        ("PIB per cápita", """
            VAR t = FILTER(Provincias, NOT ISBLANK(Provincias[pib_pc]))
            RETURN DIVIDE(SUMX(t, Provincias[pib_pc] * Provincias[pob_actual]), SUMX(t, Provincias[pob_actual]))""",
         "#,0 €", "Economía"),
        ("PIB per cápita (serie)", "AVERAGE('PIB provincia'[pib_pc])", "#,0 €", "Economía"),
        ("Tasa de paro", """
            VAR ult = CALCULATE(MAX(Paro[trimestre]), ALL(Paro))
            RETURN IF(HASONEVALUE(CCAA[ccaa_ine]),
                CALCULATE(AVERAGE(Paro[tasa_paro]), Paro[trimestre] = ult) / 100,
                CALCULATE(AVERAGE(Paro[tasa_paro]), Paro[trimestre] = ult, Paro[ccaa_ine] = "00", REMOVEFILTERS(CCAA)) / 100)""",
         PCT, "Economía"),
        ("Tasa de paro (serie)", "AVERAGE(Paro[tasa_paro]) / 100", PCT, "Economía"),
        ("Trimestre EPA", "CALCULATE(MAX(Paro[trimestre]), ALL(Paro))", None, "Economía"),
        ("Electores Andalucía 2026", "SUM(Municipios[electores_and_2026])", MIL, "Electoral"),
        ("Electores / población", """
            VAR t = FILTER(Municipios, NOT ISBLANK(Municipios[electores_and_2026]))
            RETURN DIVIDE(SUMX(t, Municipios[electores_and_2026]), SUMX(t, Municipios[pob_actual]))""", PCT, "Electoral"),
        ("Fuentes catalogadas", "COUNTROWS(Fuentes)", "0", "Operaciones"),
        ("Fuentes disponibles", 'COUNTROWS(FILTER(Fuentes, Fuentes[estado] = "disponible"))', "0", "Operaciones"),
        ("Fuentes con conector", 'COUNTROWS(FILTER(Fuentes, Fuentes[conector] <> "—"))', "0", "Operaciones"),
        ("Filas procesadas", "SUM(Ejecuciones[procesados])", MIL, "Operaciones"),
        ("Controles OK", 'COUNTROWS(FILTER(Calidad, Calidad[estado] = "pass"))', "0", "Operaciones"),
        ("Controles con fallo", 'COUNTROWS(FILTER(Calidad, Calidad[estado] = "fail"))', "0", "Operaciones"),
        ("Color estado fuente", """
            SWITCH(SELECTEDVALUE(Fuentes[estado]), "disponible", "#D7EFE9", "bloqueado_antibot", "#F6D1D1", "#FBEBC8")""", None, F),
        ("Color estado control", """
            SWITCH(SELECTEDVALUE(Calidad[estado]), "pass", "#D7EFE9", "fail", "#F6D1D1", "warn", "#FBEBC8", "#EEEAF4")""", None, F),
        ("Color estado ejecución", """
            SWITCH(SELECTEDVALUE(Ejecuciones[estado]), "success", "#D7EFE9", "partial", "#FBEBC8", "#F6D1D1")""", None, F),
        ("Título mapa", """"Mapa · " & SELECTEDVALUE('Métrica del mapa'[Métrica], "Variación de población 10 años")""", None, F),
        ("SVG España provincias", f"""
            VAR idm = SELECTEDVALUE('Métrica del mapa'[id], 1)
            {ccaa_sel}
            VAR formas = CONCATENATEX(ALL(Provincias),
                VAR v = {dax_valor_fila("Provincias", "prov")}
                VAR c = IF(todo || Provincias[ccaa_ine] IN sel, {dax_color("idm", "v")}, "#EEEBF3")
                RETURN "<path d='" & Provincias[path] & "' fill='" & c & "'/>", "")
            VAR ccaa = CONCATENATEX(ALL(CCAA), "<path d='" & CCAA[path] & "'/>", "")
            VAR leyenda = {ley}
            {svg_envolver(alto, '"<g stroke=\'#FFFFFF\' stroke-width=\'0.8\' stroke-linejoin=\'round\'>" & formas & "</g>" & "<g fill=\'none\' stroke=\'#1D1631\' stroke-opacity=\'0.7\' stroke-width=\'1.4\'>" & ccaa & "</g>" & ' + caja_svg + ' & leyenda')}""",
         None, F, {"dataCategory": "ImageUrl"}),
        ("SVG España municipios", f"""
            VAR idm = SELECTEDVALUE('Métrica del mapa'[id], 1)
            {ccaa_sel}
            VAR t = ADDCOLUMNS(ALL(Municipios), "@c",
                VAR v = {dax_valor_fila("Municipios", "mun")}
                RETURN IF(todo || Municipios[ccaa_ine] IN sel, {dax_color("idm", "v")}, "#EEEBF3"))
            VAR grupos = CONCATENATEX(DISTINCT(SELECTCOLUMNS(t, "@c", [@c])),
                VAR col = [@c]
                RETURN "<g fill='" & col & "'>" & CONCATENATEX(FILTER(t, [@c] = col), "<path d='" & Municipios[path] & "'/>", "") & "</g>", "")
            VAR prov = CONCATENATEX(ALL(Provincias), "<path d='" & Provincias[path] & "'/>", "")
            VAR leyenda = {ley}
            {svg_envolver(alto, '"<g stroke=\'#FFFFFF\' stroke-width=\'0.15\'>" & grupos & "</g>" & "<g fill=\'none\' stroke=\'#1D1631\' stroke-opacity=\'0.6\' stroke-width=\'0.9\'>" & prov & "</g>" & ' + caja_svg + ' & leyenda')}""",
         None, F, {"dataCategory": "ImageUrl"}),
    ]
    return m


def modelo(P) -> dict[str, str]:
    T = {}
    T["CCAA"] = tabla_csv("CCAA", "ccaa.csv", [
        ("geo_id", "string", None), ("ccaa_ine", "string", None), ("nombre", "string", None),
        ("pob_actual", "int64", MIL), ("pob_hace10", "int64", MIL), ("area_km2", "double", "#,0"),
        ("paro", "double", PCT), ("paro_trimestre", "string", None), ("n_provincias", "int64", "0"),
        ("n_municipios", "int64", MIL), ("path", "string", None), ("cx", "int64", None), ("cy", "int64", None)],
        ocultas=("geo_id", "path", "cx", "cy", "pob_actual", "pob_hace10"),
        extra_col={"ccaa_ine": {"isKey": ""}, "nombre": {"sortByColumn": "ccaa_ine"}})
    T["Provincias"] = tabla_csv("Provincias", "provincias.csv", [
        ("geo_id", "string", None), ("provincia_ine", "string", None), ("nombre", "string", None), ("ccaa_ine", "string", None),
        ("pob_actual", "int64", MIL), ("pob_hace10", "int64", MIL), ("area_km2", "double", "#,0"),
        ("pib_pc", "double", "#,0 €"), ("pib_pc_anyo", "int64", "0"), ("n_municipios", "int64", MIL),
        ("path", "string", None), ("cx", "int64", None), ("cy", "int64", None)],
        ocultas=("geo_id", "path", "cx", "cy", "ccaa_ine", "pob_actual", "pob_hace10"),
        extra_col={"provincia_ine": {"isKey": ""}, "nombre": {"sortByColumn": "provincia_ine"}})
    T["Municipios"] = tabla_csv("Municipios", "municipios.csv", [
        ("geo_id", "string", None), ("municipio_ine", "string", None), ("provincia_ine", "string", None),
        ("ccaa_ine", "string", None), ("nombre", "string", None), ("pob_actual", "int64", MIL),
        ("pob_hace10", "int64", MIL), ("area_km2", "double", "#,0.0"), ("electores_and_2026", "int64", MIL),
        ("path", "string", None), ("x", "double", None), ("y", "double", None), ("lon", "double", "0.000"),
        ("lat", "double", "0.000"), ("tamano", "string", None)],
        ocultas=("geo_id", "path", "x", "y", "provincia_ine", "ccaa_ine", "pob_actual", "pob_hace10",
                 "electores_and_2026", "lon", "lat"),
        extra_col={"municipio_ine": {"isKey": ""}, "lon": {"dataCategory": "Longitude"},
                   "lat": {"dataCategory": "Latitude"}})
    T["Serie población"] = tabla_csv("Serie población", "poblacion_serie.csv", [
        ("geo_id", "string", None), ("nivel", "string", None), ("nombre", "string", None), ("anyo", "int64", "0"),
        ("poblacion", "int64", MIL), ("origen", "string", None), ("ccaa_ine", "string", None),
        ("provincia_ine", "string", None), ("municipio_ine", "string", None)],
        ocultas=("geo_id", "ccaa_ine", "provincia_ine", "municipio_ine"))
    T["PIB provincia"] = tabla_csv("PIB provincia", "pib_provincia.csv", [
        ("provincia_ine", "string", None), ("anyo", "int64", "0"), ("pib_pc", "double", "#,0 €")], ocultas=("provincia_ine",))
    T["Paro"] = tabla_csv("Paro", "paro_ccaa.csv", [
        ("ccaa_ine", "string", None), ("anyo", "int64", "0"), ("periodo", "string", None),
        ("trimestre", "string", None), ("tasa_paro", "double", "0.00")], ocultas=("ccaa_ine",))
    T["Fuentes"] = tabla_csv("Fuentes", "fuentes.csv", [(c, "string", None) for c in (
        "source_id", "organismo", "dataset", "categoria", "granularidad", "cobertura_historica", "frecuencia",
        "licencia", "estado", "http_status", "metodo_extraccion", "conector", "ultima_extraccion_estado")])
    T["Ejecuciones"] = tabla_csv("Ejecuciones", "ejecuciones.csv", [
        ("execution_id", "string", None), ("source_id", "string", None), ("dataset", "string", None),
        ("inicio", "string", None), ("estado", "string", None), ("descargados", "int64", MIL),
        ("procesados", "int64", MIL), ("errores", "int64", "0"), ("duracion_s", "double", "#,0.0"),
        ("detalle", "string", None), ("version", "string", None)])
    T["Calidad"] = tabla_csv("Calidad", "calidad.csv", [
        ("control", "string", None), ("dimension", "string", None), ("dataset", "string", None),
        ("valor", "double", "#,0.###"), ("umbral", "string", None), ("estado", "string", None), ("detalle", "string", None)])
    filas = ",\n    ".join(f'{{{i}, "{t}"}}' for i, (t, _, _) in ESCALAS.items())
    T["Métrica del mapa"] = tabla_calculada("Métrica del mapa",
        f'DATATABLE("id", INTEGER, "Métrica", STRING, {{\n    {filas}\n}})',
        [("id", "int64", None, {"isHidden": True}), ("Métrica", "string", None, {"sortByColumn": "id"})])
    T["Medidas"] = tabla_calculada("Medidas", "{BLANK()}", [("Value", "string", None, {"isHidden": True})], medidas(P))

    archivos = {f"definition/tables/{n}.tmdl": s for n, s in T.items()}
    archivos["definition/expressions.tmdl"] = (
        f'expression CarpetaDatos = "{DATOS}\\" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        "\tannotation PBI_ResultType = Text\n")
    rels = [("rel_prov_ccaa", "Provincias.ccaa_ine", "CCAA.ccaa_ine"),
            ("rel_mun_prov", "Municipios.provincia_ine", "Provincias.provincia_ine"),
            ("rel_serie_ccaa", "'Serie población'.ccaa_ine", "CCAA.ccaa_ine"),
            ("rel_pib_prov", "'PIB provincia'.provincia_ine", "Provincias.provincia_ine"),
            ("rel_paro_ccaa", "Paro.ccaa_ine", "CCAA.ccaa_ine")]
    archivos["definition/relationships.tmdl"] = "\n".join(
        f"relationship {n}\n\tfromColumn: {a}\n\ttoColumn: {b}\n" for n, a, b in rels)
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


# ───────────────────────── informe ─────────────────────────
NAV = [("p01_resumen", "Resumen España", "◉"), ("p02_provincias", "Mapa provincial", "▦"),
       ("p03_municipios", "Mapa municipal", "▩"), ("p04_demografia", "Demografía", "≋"),
       ("p05_economia", "Economía", "€"), ("p06_censo", "Censo electoral", "✔"),
       ("p07_operaciones", "Datos y calidad", "⚙"), ("p08_metodologia", "Metodología", "ℹ")]


def barra_nav(pg: Pagina, activa: str):
    pg.texto(0, 0, 200, H, [[("ATLAS", {"size": 20, "bold": True, "color": "#FFFFFF", "font": "Segoe UI Black"})],
                             [("SPAIN", {"size": 9, "bold": True, "color": ORO})],
                             [("Inteligencia territorial", {"size": 9, "color": "#CFC7E2"})]], fondo=INK)
    for i, (dest, et, ic) in enumerate(NAV):
        act = dest == activa
        pg.boton(10, 98 + i * 44, 180, 38, f"{ic}   {et}", dest, fondo=VIO if act else "#2A2147",
                 fg="#FFFFFF" if act else "#D9D2EA", size=10.5, hover="#3D3166")
    pg.texto(10, 470, 180, 260, [[("Estado", {"size": 9, "bold": True, "color": ORO})],
                                 [("Resultados electorales oficiales: pendientes de carga (Infoelectoral exige "
                                   "descarga manual).", {"size": 8.5, "color": "#CFC7E2"})],
                                 [("Cómo navegar", {"size": 9, "bold": True, "color": ORO})],
                                 [("• Ctrl+clic en los botones en Power BI Desktop", {"size": 8.5, "color": "#CFC7E2"})],
                                 [("• Clic en barras o filas: filtra la página", {"size": 8.5, "color": "#CFC7E2"})],
                                 [("• Segmentador de comunidad: resalta en los mapas", {"size": 8.5, "color": "#CFC7E2"})]])


def nueva(nombre, titulo, sub):
    pg = Pagina(nombre, titulo, sub)
    barra_nav(pg, nombre)
    return pg


def tarjetas(pg, y, items, w=220, h=92, x=X0):
    for i, (m, et) in enumerate(items):
        pg.tarjeta(x + i * (w + 12), y, w, h, Me(m), et, size=22)


def informe(P) -> dict:
    pags = []
    ccaa_slicer = lambda pg, x, y, w=300, h=58: pg.segmentador(x, y, w, h, C("CCAA", "nombre"), "Comunidad autónoma",
                                                                sync="ccaa")
    metrica_slicer = lambda pg, x, y, w=300, h=58: pg.segmentador(x, y, w, h, C("Métrica del mapa", "Métrica"),
                                                                   "Métrica del mapa", unico=True, sync="metrica")

    # 1 resumen
    pg = nueva("p01_resumen", "España en cifras", f"Padrón a 1 de enero de {P['anyo_actual']} · cartografía censal INE 2024")
    tarjetas(pg, 96, [("Población", "Población"), ("Variación población 10 años", f"Variación {P['anyo_base']}–{P['anyo_actual']}"),
                      ("Comunidades", "CCAA y ciudades autónomas"), ("Provincias", "Provincias"), ("Municipios", "Municipios")], w=262)
    tarjetas(pg, 200, [("% municipios que pierden población", "Municipios que pierden población"),
                       ("Tasa de paro", "Paro EPA (último trimestre)"), ("PIB per cápita", "PIB per cápita (ponderado)"),
                       ("Fuentes disponibles", "Fuentes disponibles"), ("Fuentes catalogadas", "Fuentes catalogadas")], w=262)
    pg.imagen(X0, 304, 720, 586, "SVG España provincias")
    metrica_slicer(pg, X0 + 735, 304, 300, 58)
    ccaa_slicer(pg, X0 + 1045, 304, 320, 58)
    tabla(pg, X0 + 735, 372, 630, 518,
          [(C("CCAA", "nombre"), "Comunidad"), (Me("Población"), "Población"),
           (Me("Variación población 10 años"), "Var. 10 años"), (Me("Densidad"), "hab./km²"),
           (C("CCAA", "paro"), "Paro EPA"), (C("CCAA", "n_municipios"), "Municipios")],
          "Comunidades autónomas", sort=[(Me("Población"), "Descending")])
    pags.append(pg)

    # 2 mapa provincial
    pg = nueva("p02_provincias", "Mapa provincial", "Elegí la métrica; el segmentador de comunidad resalta su territorio")
    pg.imagen(X0, 96, 860, 794, "SVG España provincias")
    metrica_slicer(pg, X0 + 875, 96, 490, 58)
    ccaa_slicer(pg, X0 + 875, 164, 490, 58)
    tabla(pg, X0 + 875, 232, 490, 658,
          [(C("Provincias", "nombre"), "Provincia"), (Me("Población"), "Población"),
           (Me("Variación población 10 años"), "Var. 10 años"), (Me("Densidad"), "hab./km²"),
           (C("Provincias", "pib_pc"), "PIB pc")],
          "Provincias", sort=[(Me("Población"), "Descending")], size=9)
    pags.append(pg)

    # 3 mapa municipal
    pg = nueva("p03_municipios", "Mapa municipal", "8.132 municipios · PIB y paro se heredan de la provincia y la comunidad")
    pg.imagen(X0, 96, 860, 794, "SVG España municipios")
    metrica_slicer(pg, X0 + 875, 96, 490, 58)
    ccaa_slicer(pg, X0 + 875, 164, 490, 58)
    tabla(pg, X0 + 875, 232, 490, 658,
          [(C("Municipios", "nombre"), "Municipio"), (Me("Población"), "Población"),
           (Me("Variación población 10 años"), "Var. 10 años"), (Me("Densidad"), "hab./km²")],
          "Municipios", sort=[(Me("Población"), "Descending")], size=9)
    pags.append(pg)

    # 4 demografía
    pg = nueva("p04_demografia", "Demografía", "Cifras oficiales del Padrón 1996–" + str(P["anyo_actual"]))
    ccaa_slicer(pg, X0, 96, 340, 58)
    pg.segmentador(X0 + 350, 96, 340, 58, C("Municipios", "tamano"), "Tamaño del municipio", sync="tamano")
    tarjetas(pg, 164, [("Población", "Población"), ("Variación población 10 años", "Variación 10 años"),
                       ("Municipios que pierden población", "Municipios en retroceso"), ("Densidad", "hab./km²")], w=330)
    lc = pg.add("lineChart", X0, 268, 680, 300,
           query={"Category": [proj(C("Serie población", "anyo"))], "Y": [proj(Me("Población (serie)"), "Población")]},
           objects={"lineStyles": [{"properties": {"strokeWidth": lit(3)}}],
                    "dataPoint": [{"properties": {"fill": color(VIO)}}],
                    "categoryAxis": [{"properties": {"showAxisTitle": lit(False)}}],
                    "valueAxis": [{"properties": {"showAxisTitle": lit(False)}}]},
           titulo="Evolución de la población (filtrada por comunidad)")
    lc["filterConfig"] = {"filters": [{"name": "f_nivel", "field": C("Serie población", "nivel"), "type": "Categorical",
        "filter": {"Version": 2, "From": [{"Name": "s", "Entity": "Serie población", "Type": 0}],
                   "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "s"}}, "Property": "nivel"}}],
                                                   "Values": [[lit("ccaa")["expr"]]]}}}]}}]}
    barras(pg, X0 + 690, 268, 676, 300, C("Municipios", "tamano"), Me("Población"), "Población por tamaño de municipio",
           tipo="clusteredColumnChart", sort=[(C("Municipios", "tamano"), "Ascending")])
    tabla(pg, X0, 578, 1366, 312,
          [(C("Municipios", "nombre"), "Municipio"), (C("Provincias", "nombre"), "Provincia"), (Me("Población"), "Población"),
           (Me("Población hace 10 años"), f"Población {P['anyo_base']}"), (Me("Variación población 10 años"), "Variación"),
           (Me("Densidad"), "hab./km²"), (C("Municipios", "tamano"), "Tamaño")],
          "Municipios", sort=[(Me("Población"), "Descending")], size=9)
    pags.append(pg)

    # 5 economía
    pg = nueva("p05_economia", "Economía", "Contabilidad Regional (INE) y Encuesta de Población Activa")
    ccaa_slicer(pg, X0, 96, 340, 58)
    tarjetas(pg, 96, [("PIB per cápita", "PIB per cápita"), ("Tasa de paro", "Paro EPA"), ("Trimestre EPA", "Último trimestre")],
             w=330, h=58, x=X0 + 352)
    barras(pg, X0, 166, 560, 724, C("Provincias", "nombre"), Me("PIB per cápita"), "PIB per cápita por provincia (último año)",
           nombre_val="PIB pc")
    pg.add("lineChart", X0 + 572, 166, 794, 360,
           query={"Category": [proj(C("Paro", "trimestre"))], "Y": [proj(Me("Tasa de paro (serie)"), "Paro")]},
           objects={"lineStyles": [{"properties": {"strokeWidth": lit(2.5)}}], "dataPoint": [{"properties": {"fill": color("#2E9C8F")}}],
                    "categoryAxis": [{"properties": {"showAxisTitle": lit(False)}}], "valueAxis": [{"properties": {"showAxisTitle": lit(False)}}]},
           titulo="Tasa de paro EPA (promedio de las comunidades seleccionadas)")
    pg.add("lineChart", X0 + 572, 536, 794, 354,
           query={"Category": [proj(C("PIB provincia", "anyo"))], "Y": [proj(Me("PIB per cápita (serie)"), "PIB pc")]},
           objects={"lineStyles": [{"properties": {"strokeWidth": lit(2.5)}}], "dataPoint": [{"properties": {"fill": color(ORO)}}],
                    "categoryAxis": [{"properties": {"showAxisTitle": lit(False)}}], "valueAxis": [{"properties": {"showAxisTitle": lit(False)}}]},
           titulo="PIB per cápita medio de las provincias (sin ponderar)")
    pags.append(pg)

    # 6 censo electoral
    pg = nueva("p06_censo", "Censo electoral", "INE · Oficina del Censo Electoral · único proceso publicado: autonómicas de Andalucía, mayo 2026")
    tarjetas(pg, 96, [("Electores Andalucía 2026", "Electores residentes (CER)"), ("Electores / población", "Electores / población")], w=340)
    pg.texto(X0 + 720, 96, 646, 92, [[("Los resultados electorales oficiales (generales, municipales, europeas) se "
                                       "incorporarán cuando se carguen los ficheros de Infoelectoral. Este censo es el único "
                                       "dato electoral publicado hoy por el INE.", {"size": 10, "color": MUTED})]], fondo="#FFFFFF")
    barras(pg, X0, 200, 560, 690, C("Provincias", "nombre"), Me("Electores Andalucía 2026"), "Electores por provincia",
           nombre_val="Electores")
    tabla(pg, X0 + 572, 200, 794, 690,
          [(C("Municipios", "nombre"), "Municipio"), (C("Provincias", "nombre"), "Provincia"),
           (Me("Electores Andalucía 2026"), "Electores"), (Me("Población"), "Población"), (Me("Electores / población"), "Electores/pob.")],
          "Municipios de Andalucía", sort=[(Me("Electores Andalucía 2026"), "Descending")], size=9)
    pg.filtros = [{"name": "f_andalucia", "field": C("CCAA", "ccaa_ine"), "type": "Categorical",
                   "filter": {"Version": 2, "From": [{"Name": "c", "Entity": "CCAA", "Type": 0}],
                              "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "c"}}, "Property": "ccaa_ine"}}],
                                                              "Values": [[lit("01")["expr"]]]}}}]}}]
    pags.append(pg)

    # 7 operaciones
    pg = nueva("p07_operaciones", "Datos y calidad", "Data Operations Center: fuentes verificadas en vivo, ejecuciones y controles")
    tarjetas(pg, 96, [("Fuentes catalogadas", "Fuentes catalogadas"), ("Fuentes disponibles", "Responden"),
                      ("Fuentes con conector", "Con conector"), ("Filas procesadas", "Filas procesadas"),
                      ("Controles OK", "Controles OK"), ("Controles con fallo", "Controles con fallo")], w=218)
    tabla(pg, X0, 200, 820, 380,
          [(C("Fuentes", "source_id"), "Fuente"), (C("Fuentes", "organismo"), "Organismo"), (C("Fuentes", "categoria"), "Categoría"),
           (C("Fuentes", "granularidad"), "Granularidad"), (C("Fuentes", "estado"), "Estado")],
          "Registro de fuentes", fx=[(C("Fuentes", "estado"), "Color estado fuente")], size=9)
    barras(pg, X0 + 832, 200, 534, 380, C("Fuentes", "categoria"), Me("Fuentes catalogadas"), "Fuentes por categoría",
           nombre_val="Fuentes")
    tabla(pg, X0, 590, 680, 300,
          [(C("Ejecuciones", "source_id"), "Fuente"), (C("Ejecuciones", "inicio"), "Inicio"), (C("Ejecuciones", "estado"), "Estado"),
           (C("Ejecuciones", "procesados"), "Filas"), (C("Ejecuciones", "duracion_s"), "Seg.")],
          "Ejecuciones de ingesta", fx=[(C("Ejecuciones", "estado"), "Color estado ejecución")], size=9)
    tabla(pg, X0 + 692, 590, 674, 300,
          [(C("Calidad", "control"), "Control"), (C("Calidad", "dimension"), "Dimensión"), (C("Calidad", "estado"), "Estado"),
           (C("Calidad", "detalle"), "Detalle")],
          "Controles de calidad (último run)", fx=[(C("Calidad", "estado"), "Color estado control")], size=9)
    pags.append(pg)

    # 8 metodología
    pg = nueva("p08_metodologia", "Metodología y limitaciones", "Qué hay, de dónde sale y qué falta")
    pg.texto(X0, 100, 1360, 780, [
        [("Fuentes", {"size": 13, "bold": True})],
        [("Padrón municipal (INE, 1996–2025), Contabilidad Regional (INE), EPA (INE), censo electoral (INE-OCE), "
          "cartografía de secciones censales (INE, 1-ene-2024). Todas descargadas por API o fichero oficial y trazables por ejecución.", {"size": 11})],
        [("Población provincial y autonómica", {"size": 13, "bold": True})],
        [("El INE congeló sus tablas provinciales y autonómicas en 2021. De 2022 en adelante ATLAS suma los municipios; "
          "en 1996–2021 esa suma coincide con la cifra oficial en 1.299 de 1.300 casos (Almería 1996: −76 habitantes).", {"size": 11})],
        [("Mapas", {"size": 13, "bold": True})],
        [("Límites obtenidos disolviendo las secciones censales del INE (no las líneas límite jurídicas del IGN). Canarias se "
          "muestra en recuadro a escala 0,85. Las zonas en blanco son terrenos sin municipio (p. ej. Bardenas Reales).", {"size": 11})],
        [("PIB per cápita", {"size": 13, "bold": True})],
        [("Dato provincial del INE. Las comunidades uniprovinciales solo se publican como CCAA y se asignan a su provincia. "
          "El agregado 'ponderado' pondera por población actual.", {"size": 11})],
        [("Lo que todavía no está", {"size": 13, "bold": True})],
        [("Resultados electorales (Infoelectoral bloquea la descarga automática: carga manual pendiente), autonómicas, "
          "continuidad de partidos, índices compuestos y modelos predictivos. Ver PROJECT_STATUS.md.", {"size": 11})],
    ], fondo="#FFFFFF")
    pags.append(pg)

    archivos = {}
    for p in pags:
        archivos[f"definition/pages/{p.nombre}/page.json"] = p.json()
        for v in p.visuales:
            archivos[f"definition/pages/{p.nombre}/visuals/{v['name']}/visual.json"] = v
    archivos["definition/pages/pages.json"] = {"$schema": f"{SCH}/pagesMetadata/1.0.0/schema.json",
                                               "pageOrder": [p.nombre for p in pags], "activePageName": "p01_resumen"}
    archivos["definition/version.json"] = {"$schema": f"{SCH}/versionMetadata/1.0.0/schema.json", "version": "2.0.0"}
    ver = {"visual": V_VISUAL, "report": V_REPORT, "page": V_PAGE}
    archivos["definition/report.json"] = {
        "$schema": f"{SCH}/report/{V_REPORT}/schema.json",
        "themeCollection": {"baseTheme": {"name": BASE_THEME, "reportVersionAtImport": ver, "type": "SharedResources"},
                            "customTheme": {"name": "AtlasEspana.json", "reportVersionAtImport": ver, "type": "RegisteredResources"}},
        "objects": {"outspacePane": [{"properties": {"expanded": lit(False)}}],
                    "section": [{"properties": {"verticalAlignment": lit("Top")}}]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": "AtlasEspana.json", "path": "AtlasEspana.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "exportDataMode": "AllowSummarized",
                     "defaultDrillFilterOtherVisuals": True, "allowChangeFilterTypes": True, "useEnhancedTooltips": True,
                     "useDefaultAggregateDisplayName": True}}
    archivos["StaticResources/RegisteredResources/AtlasEspana.json"] = tema()
    archivos["definition.pbir"] = {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json",
                                   "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NOMBRE}.SemanticModel"}}}
    return archivos


def generar(con_datos: bool = True):
    if con_datos:
        from atlas_spain.viz.powerbi_datos import exportar
        exportar()
    P = json.loads((DATOS / "parametros.json").read_text(encoding="utf-8"))
    sm, rp = DIR / f"{NOMBRE}.SemanticModel", DIR / f"{NOMBRE}.Report"
    for d in (rp / "definition", sm / "definition"):
        shutil.rmtree(d, ignore_errors=True)
    escribir(modelo(P), sm)
    escribir(informe(P), rp)
    tb = rp / "StaticResources" / "SharedResources" / "BaseThemes" / f"{BASE_THEME}.json"
    tb.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(PBI_TEMAS / f"{BASE_THEME}.json", tb)
    for carpeta, tipo in ((sm, "SemanticModel"), (rp, "Report")):
        plat = carpeta / ".platform"
        lid = json.loads(plat.read_text())["config"]["logicalId"] if plat.exists() else str(uuid.uuid4())
        plat.write_text(json.dumps({
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": tipo, "displayName": NOMBRE}, "config": {"version": "2.0", "logicalId": lid}}, indent=2))
    (DIR / f"{NOMBRE}.pbip").write_text(json.dumps({
        "$schema": "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json",
        "version": "1.0", "artifacts": [{"report": {"path": f"{NOMBRE}.Report"}}], "settings": {"enableAutoRecovery": True}},
        indent=2))
    (DIR / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\ndatos/\n", encoding="utf-8")
    print(f"proyecto: {DIR / (NOMBRE + '.pbip')}")
    return DIR / f"{NOMBRE}.pbip"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sin-datos", action="store_true")
    generar(not ap.parse_args().sin_datos)
