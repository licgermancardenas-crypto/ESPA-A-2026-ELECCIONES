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
    # población de provincias y comunidades (la escala 3 es para municipios)
    33: ("Población", [(500000, "#F3EFF9"), (1000000, "#D9CDEE"), (2000000, "#B19DDA"), (4000000, "#8467BD"), (7000000, "#5B3F99"), (None, "#2E1B5E")],
         ["< 0,5 M", "0,5–1 M", "1–2 M", "2–4 M", "4–7 M", "> 7 M"]),
}
# Mapa de ciudad (secciones censales; Atlas de Renta del INE)
ESCALAS_CIUDAD = {
    1: ("Renta neta media por persona", [(9000, "#FFF6DD"), (11000, "#F8DE9A"), (13000, "#E9B949"), (15000, "#C98A12"), (18000, "#8A5A00"), (None, "#5C3B00")],
        ["< 9.000 €", "9–11 mil €", "11–13 mil €", "13–15 mil €", "15–18 mil €", "> 18.000 €"]),
    2: ("Densidad (hab./km²)", [(1000, "#F3EFF9"), (5000, "#D9CDEE"), (10000, "#B19DDA"), (20000, "#8467BD"), (30000, "#5B3F99"), (None, "#2E1B5E")],
        ["< 1.000", "1–5 mil", "5–10 mil", "10–20 mil", "20–30 mil", "> 30 mil"]),
    3: ("Población de 65 y más años", [(0.12, "#EAF4F2"), (0.16, "#BFE0DA"), (0.20, "#7CC2B6"), (0.24, "#2E9C8F"), (0.28, "#1F6E66"), (None, "#0E3F3A")],
        ["< 12 %", "12–16 %", "16–20 %", "20–24 %", "24–28 %", "> 28 %"]),
    4: ("Población de la sección", [(800, "#F3EFF9"), (1100, "#D9CDEE"), (1400, "#B19DDA"), (1700, "#8467BD"), (2100, "#5B3F99"), (None, "#2E1B5E")],
        ["< 800", "800–1.100", "1.100–1.400", "1.400–1.700", "1.700–2.100", "> 2.100"]),
}
SIN_DATO = "#E4E0EC"

# Color por siglas (prefijos). Es solo identidad visual: no agrega votos entre siglas distintas.
COLORES_PARTIDO = [
    ("EAJ-PNV", "#2E7D32"), ("EAJ", "#2E7D32"), ("PNV", "#2E7D32"),
    ("EH BILDU", "#00A39A"), ("BILDU", "#00A39A"), ("EH", "#00A39A"), ("HB", "#00A39A"), ("AMAIUR", "#00A39A"),
    ("PSE", "#E30613"), ("PSOE", "#E30613"), ("PSC", "#E30613"),
    ("PP", "#1E5BA8"), ("AP", "#1E5BA8"), ("CP", "#1E5BA8"), ("UPN", "#1E5BA8"),
    ("MÁS MADRID", "#0FDEC4"), ("MAS MADRID", "#0FDEC4"), ("UPYD", "#E5007E"), ("RESTO", "#B8B2C8"),
    ("PODEMOS", "#6B2C91"), ("ELKARREKIN", "#6B2C91"), ("SUMAR", "#E5007E"), ("VOX", "#5AC035"),
    ("EA", "#8DB600"), ("EE", "#B71C1C"), ("EB", "#9C2B2B"), ("IU", "#9C2B2B"), ("PCE", "#9C2B2B"),
    ("UCD", "#F28C28"), ("C´S", "#EB6109"), ("CS", "#EB6109"), ("CIUDADANOS", "#EB6109"), ("UA", "#4E6B8A"),
]


FAMILIAS_COLOR = {
    "PSOE": "#E30613", "PP": "#1E5BA8", "Vox": "#5AC035", "Ciudadanos": "#EB6109", "Podemos y confluencias": "#6B2C91",
    "Sumar": "#E5007E", "ERC": "#F5A800", "Convergència / Junts": "#00B4C5", "PNV": "#2E7D32", "EH Bildu": "#00897B",
    "BNG": "#76B3E0", "Coalición Canaria": "#F2D500", "Más País": "#0FDEC4", "Compromís": "#DF7F2A", "IU": "#9C2B2B",
    "UPN": "#3E6FB4", "NA+ (coalición UPN-PP-Cs)": "#3E6FB4", "PRC": "#A4C639", "CUP": "#FFE600", "Teruel Existe": "#037252",
    "Ahora Repúblicas (coalición)": "#F08A00", "CEUS (coalición)": "#4CAF50", "CPE (coalición)": "#8BC34A",
    "Se Acabó La Fiesta": "#8B5A2B", "PACMA": "#8EC43F", "UPyD": "#E5007E", "Nueva Canarias": "#7FB5DA", "UCD": "#F28C28", "CDS": "#3CB371", "AP / Coalición Popular": "#4A7BC8",
    "PCE": "#B22222", "Izquierda abertzale (HB / EH)": "#5F9F6F", "PNV-EA (coalición)": "#4E8F3A", "Partido Andalucista": "#3FA34D",
    "Unió Valenciana": "#E07B39", "PAR": "#F0B83C", "Otros": "#B8B2C8",
}


def dax_color_familia(expr: str) -> str:
    ramas = ", ".join(f'"{k}", "{c}"' for k, c in FAMILIAS_COLOR.items())
    return f'SWITCH({expr}, {ramas}, "#B8B2C8")'


def dax_color_partido(expr: str) -> str:
    ramas = ", ".join(f'LEFT({expr}, {len(k)}) = "{k}", "{c}"' for k, c in COLORES_PARTIDO)
    return 'SWITCH(TRUE(), ' + ramas + ', "#9A93AD")'



def dax_color(idm_var: str, v: str, escalas: dict = ESCALAS) -> str:
    ramas = []
    for idm, (_, cortes, _) in escalas.items():
        sw = ", ".join(f'{v} < {u}, "{c}"' for u, c in cortes[:-1])
        ramas.append(f'{idm}, SWITCH(TRUE(), {sw}, "{cortes[-1][1]}")')
    return f'IF(ISBLANK({v}), "{SIN_DATO}", SWITCH({idm_var}, {", ".join(ramas)}))'


def dax_valor_fila(t: str, nivel: str) -> str:
    """Valor de la métrica con columnas de la fila (rápido dentro de CONCATENATEX)."""
    if nivel == "ccaa":
        pib, paro = f"{t}[pib_pc]", f"{t}[paro]"
    elif nivel == "prov":
        pib, paro = f"{t}[pib_pc]", "RELATED(CCAA[paro])"
    else:
        pib, paro = "RELATED(Provincias[pib_pc])", "RELATED(CCAA[paro])"
    return (f"SWITCH(idm, 1, DIVIDE({t}[pob_actual] - {t}[pob_hace10], {t}[pob_hace10]), "
            f"2, DIVIDE({t}[pob_actual], {t}[area_km2]), 3, {t}[pob_actual], 4, {pib}, 5, {paro})")


def xml(t: str) -> str:
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def leyenda_dax(x: int, y: int, escalas: dict = ESCALAS, var: str = "idm") -> str:
    """Leyenda SVG que cambia con la métrica elegida."""
    ramas = []
    for idm, (titulo, cortes, etiquetas) in escalas.items():
        s = f"<text x='{x}' y='{y}' font-family='Segoe UI' font-size='15' font-weight='700' fill='{INK}'>{xml(titulo)}</text>"
        for i, ((_, c), et) in enumerate(zip(cortes, etiquetas)):
            yy = y + 14 + i * 22
            s += (f"<rect x='{x}' y='{yy}' width='22' height='16' rx='3' fill='{c}' stroke='#FFFFFF'/>"
                  f"<text x='{x + 30}' y='{yy + 13}' font-family='Segoe UI' font-size='13' fill='{INK}'>{xml(et)}</text>")
        ramas.append(f'{idm}, "{s}"')
    return f"SWITCH({var}, {', '.join(ramas)})"


# mapa base: "Mapa" (colores opacos) o "Satélite" (ortofoto PNOA debajo y colores semitransparentes)
VAR_SAT = """VAR sat = SELECTEDVALUE('Mapa base'[id], 1) = 2
            VAR op = IF(sat, "0.58", "1")"""


def svg_envolver(alto, cuerpo: str, ancho="1000") -> str:
    """Envuelve el cuerpo en un SVG. La medida debe declarar antes VAR_SAT (sat, op)."""
    pie = (f"<text x='{int(ancho) - 6}' y='{int(alto) - 6}' text-anchor='end' font-family='Segoe UI' "
           "font-size='10' fill='#6B6480'>Ortofoto PNOA © IGN (CC BY 4.0)</text>")
    fondo = f'IF(sat, [Fondo satélite SVG] & "{pie}", "")'
    return (f'VAR svg = "<svg xmlns=\'http://www.w3.org/2000/svg\' viewBox=\'0 0 {ancho} {alto}\'>" & {fondo} & {cuerpo} & "</svg>"\n'
            '            RETURN "data:image/svg+xml;utf8," & SUBSTITUTE(SUBSTITUTE(svg, "%", "%25"), "#", "%23")')


# ───────────────────────── modelo ─────────────────────────
def medidas(P) -> list:
    alto = P["lienzo"]["alto"]
    caja = P["caja_canarias"]
    ley = leyenda_dax(720, alto - 175)
    ccaa_sel = "VAR sel = VALUES(CCAA[ccaa_ine])\n            VAR todo = NOT ISFILTERED(CCAA[ccaa_ine]) && NOT ISFILTERED(CCAA[nombre])"
    caja_svg = (f"\"<path d='{caja}' fill='none' stroke='{MUTED}' stroke-width='1' stroke-dasharray='5 4'/>"
                f"<text x='14' y='{alto - 8}' font-family='Segoe UI' font-size='12' fill='{MUTED}'>Canarias (escala 0,85)</text>\"")
    g = lambda w, extra="": f"\"<g stroke='#FFFFFF' stroke-width='{w}' stroke-linejoin='round' fill-opacity='\" & op & \"'{extra}>\""
    PREF_CCAA = g(1.4) + ' & formas & "</g>" & etiquetas & '
    PREF_PROV = g(0.8) + """ & formas & "</g>" & "<g fill='none' stroke='#1D1631' stroke-opacity='0.7' stroke-width='1.4'>" & ccaa & "</g>" & """
    PREF_MUN = g(0.15) + """ & grupos & "</g>" & "<g fill='none' stroke='#1D1631' stroke-opacity='0.6' stroke-width='0.9'>" & prov & "</g>" & """
    LEY_REGION = ("\"<g transform='translate(10,\" & (alto + 24) & \")'>\" & "
                  + leyenda_dax(0, 16, ESCALAS, "idm") + ' & "</g>"')
    LEY_ELEC = (
        "CONCATENATEX(ADDCOLUMNS(TOPN(9, cuenta, [@n], DESC), \"@k\", [@n] * 100000 + UNICODE([@f]) * 100 + LEN([@f])), "
        "VAR f = [@f] VAR i = RANKX(ADDCOLUMNS(TOPN(9, cuenta, [@n], DESC), \"@k\", [@n] * 100000 + UNICODE([@f]) * 100 + LEN([@f])), [@k], , DESC) "
        f"RETURN \"<rect x='700' y='\" & ({P['lienzo']['alto']} - 250 + i * 22) & \"' width='20' height='15' rx='3' fill='\" & "
        + dax_color_familia("f") +
        f" & \"'/><text x='728' y='\" & ({P['lienzo']['alto']} - 237 + i * 22) & \"' font-family='Segoe UI' font-size='13' fill='#1D1631'>\" "
        "& SUBSTITUTE(f, \"&\", \"&amp;\") & \" · \" & [@n] & \"</text>\", \"\", [@k], DESC)")
    LEY_CIUDAD = ("\"<g transform='translate(10,\" & (alto + 24) & \")'>\" & "
                  + leyenda_dax(0, 16, ESCALAS_CIUDAD, "idk") + ' & "</g>"')
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
        ("SVG España comunidades", f"""
            {VAR_SAT}
            VAR idm = SELECTEDVALUE('Métrica del mapa'[id], 1)
            VAR idc = IF(idm = 3, 33, idm)
            {ccaa_sel}
            VAR formas = CONCATENATEX(ALL(CCAA),
                VAR v = {dax_valor_fila("CCAA", "ccaa")}
                VAR c = IF(todo || CCAA[ccaa_ine] IN sel, {dax_color("idc", "v")}, "#EEEBF3")
                RETURN "<path d='" & CCAA[path] & "' fill='" & c & "'/>", "")
            VAR etiquetas = CONCATENATEX(ALL(CCAA),
                VAR v = {dax_valor_fila("CCAA", "ccaa")}
                VAR txt = SWITCH(idm, 1, FORMAT(v, "+0.0%;-0.0%"), 2, FORMAT(v, "#,0"), 3, FORMAT(v / 1000000, "0.0") & " M", 4, FORMAT(v / 1000, "0.0") & " k€", 5, FORMAT(v, "0.0%"))
                RETURN IF(CCAA[n_municipios] > 2, "<text x='" & CCAA[cx] & "' y='" & CCAA[cy] & "' text-anchor='middle' font-family='Segoe UI' font-size='15' font-weight='700' fill='#1D1631' stroke='#FFFFFF' stroke-width='3' paint-order='stroke'>" & txt & "</text>"), "")
            VAR leyenda = {leyenda_dax(720, alto - 175, var="idc")}
            {svg_envolver(alto, PREF_CCAA + caja_svg + ' & leyenda')}""",
         None, F, {"dataCategory": "ImageUrl"}),
        ("SVG España provincias", f"""
            {VAR_SAT}
            VAR idm = SELECTEDVALUE('Métrica del mapa'[id], 1)
            VAR idc = IF(idm = 3, 33, idm)
            {ccaa_sel}
            VAR formas = CONCATENATEX(ALL(Provincias),
                VAR v = {dax_valor_fila("Provincias", "prov")}
                VAR c = IF(todo || Provincias[ccaa_ine] IN sel, {dax_color("idc", "v")}, "#EEEBF3")
                RETURN "<path d='" & Provincias[path] & "' fill='" & c & "'/>", "")
            VAR ccaa = CONCATENATEX(ALL(CCAA), "<path d='" & CCAA[path] & "'/>", "")
            VAR leyenda = {leyenda_dax(720, alto - 175, var="idc")}
            {svg_envolver(alto, PREF_PROV + caja_svg + ' & leyenda')}""",
         None, F, {"dataCategory": "ImageUrl"}),
        ("SVG España municipios", f"""
            {VAR_SAT}
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
            {svg_envolver(alto, PREF_MUN + caja_svg + ' & leyenda')}""",
         None, F, {"dataCategory": "ImageUrl"}),
        ("SVG región municipios", f"""
            VAR idm = SELECTEDVALUE('Métrica del mapa'[id], 1)
            VAR cc = SELECTEDVALUE(CCAA[ccaa_ine])
            VAR ancho = SELECTEDVALUE(CCAA[lienzo_ancho])
            VAR alto = SELECTEDVALUE(CCAA[lienzo_alto])
            VAR t = ADDCOLUMNS(CALCULATETABLE(Municipios, REMOVEFILTERS(Municipios), Municipios[ccaa_ine] = cc), "@c",
                VAR v = {dax_valor_fila("Municipios", "mun")}
                RETURN {dax_color("idm", "v")})
            VAR grupos = CONCATENATEX(DISTINCT(SELECTCOLUMNS(t, "@c", [@c])),
                VAR col = [@c]
                RETURN "<g fill='" & col & "'>" & CONCATENATEX(FILTER(t, [@c] = col), "<path d='" & Municipios[path_ccaa] & "'/>", "") & "</g>", "")
            VAR leyenda = {LEY_REGION}
            VAR svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 " & MAX(ancho, 320) & " " & (alto + 175) & "'>"
                & "<g stroke='#FFFFFF' stroke-width='0.5' stroke-linejoin='round'>" & grupos & "</g>" & leyenda & "</svg>"
            RETURN "data:image/svg+xml;utf8," & SUBSTITUTE(SUBSTITUTE(svg, "%", "%25"), "#", "%23")""",
         None, F, {"dataCategory": "ImageUrl"}),
        ("Fondo satélite SVG", f"""
            "<image href='data:image/jpeg;base64," & CONCATENATEX('Fondo satélite', 'Fondo satélite'[texto], "", 'Fondo satélite'[orden], ASC)
                & "' x='0' y='0' width='1000' height='{alto}' preserveAspectRatio='none'/>\"""", None, F),
        ("SVG España", """
            VAR nivel = SELECTEDVALUE('Nivel del mapa'[id], 2)
            RETURN SWITCH(TRUE(),
                nivel = 1, [SVG España comunidades],
                nivel = 3 && HASONEVALUE(CCAA[ccaa_ine]), [SVG región municipios],
                nivel = 3, [SVG España municipios],
                [SVG España provincias])""", None, F, {"dataCategory": "ImageUrl"}),
        # ---- elecciones nacionales (Infoelectoral)
        ("Territorio electoral", """
            IF(HASONEVALUE(CCAA[ccaa_ine]) && (ISFILTERED(CCAA[nombre]) || ISFILTERED(CCAA[ccaa_ine])),
               "ES-CA-" & SELECTEDVALUE(CCAA[ccaa_ine]), "ES")""", None, F),
        ("Votos (nac)", "VAR g = [Territorio electoral] RETURN CALCULATE(SUM('Resultados familia'[votos]), 'Resultados familia'[geo_id] = g, REMOVEFILTERS(CCAA))", MIL, "Elecciones"),
        ("Escaños (nac)", "VAR g = [Territorio electoral] RETURN CALCULATE(SUM('Resultados familia'[escanos]), 'Resultados familia'[geo_id] = g, REMOVEFILTERS(CCAA))", "0", "Elecciones"),
        ("% voto (nac)", "DIVIDE([Votos (nac)], CALCULATE([Votos (nac)], REMOVEFILTERS('Resultados familia'[familia])))", PCT, "Elecciones"),
        ("Participación (nac)", """
            VAR g = [Territorio electoral]
            RETURN CALCULATE(DIVIDE(SUM('Participación nacional'[votantes]), SUM('Participación nacional'[censo])),
                             'Participación nacional'[geo_id] = g, REMOVEFILTERS(CCAA))""", PCT, "Elecciones"),
        ("Votantes (nac)", "VAR g = [Territorio electoral] RETURN CALCULATE(SUM('Participación nacional'[votantes]), 'Participación nacional'[geo_id] = g, REMOVEFILTERS(CCAA))", MIL, "Elecciones"),
        ("Más votado (nac)", """
            VAR t = ADDCOLUMNS(VALUES('Resultados familia'[familia]), "@v", [Votos (nac)])
            RETURN MAXX(TOPN(1, FILTER(t, 'Resultados familia'[familia] <> "Otros"), [@v], DESC), 'Resultados familia'[familia])""", None, "Elecciones"),
        ("ENEP (nac)", "VAR g = [Territorio electoral] RETURN CALCULATE(AVERAGE('Índices electorales'[enep]), 'Índices electorales'[geo_id] = g, REMOVEFILTERS(CCAA))", "0.00", "Elecciones"),
        ("Gallagher (nac)", "VAR g = [Territorio electoral] RETURN CALCULATE(AVERAGE('Índices electorales'[gallagher]), 'Índices electorales'[geo_id] = g, REMOVEFILTERS(CCAA))", "0.00", "Elecciones"),
        ("Volatilidad (nac)", "VAR g = [Territorio electoral] RETURN CALCULATE(AVERAGE('Índices electorales'[volatilidad_pedersen]), 'Índices electorales'[geo_id] = g, REMOVEFILTERS(CCAA))", PCT, "Elecciones"),
        ("Color familia", f"VAR f = SELECTEDVALUE('Resultados familia'[familia]) RETURN {dax_color_familia('f')}", None, F),
        ("Título elecciones", """
            SELECTEDVALUE('Convocatorias nacionales'[convocatoria], "Elegí una convocatoria") & " · " &
            IF([Territorio electoral] = "ES", "España", SELECTEDVALUE(CCAA[nombre])) & " · partido más votado por " &
            IF(SELECTEDVALUE('Nivel del mapa'[id], 2) = 3, "municipio", "provincia")""", None, F),
        ("SVG elecciones provincias", f"""
            {VAR_SAT}
            {ccaa_sel}
            VAR tp = ADDCOLUMNS(ALL(Provincias), "@f", CALCULATE(SELECTEDVALUE('Ganador provincia'[familia_ganador])))
            VAR provs = CONCATENATEX(tp,
                VAR f = [@f]
                VAR c = IF(todo || Provincias[ccaa_ine] IN sel, IF(ISBLANK(f), "{SIN_DATO}", {dax_color_familia('f')}), "#EEEBF3")
                RETURN "<path d='" & Provincias[path] & "' fill='" & c & "'/>", "")
            VAR cuenta = ADDCOLUMNS(DISTINCT(SELECTCOLUMNS(FILTER(tp, NOT ISBLANK([@f])), "@f", [@f])),
                "@n", COUNTROWS(FILTER(tp, [@f] = EARLIER([@f]))))
            VAR ley = {LEY_ELEC}
            VAR cuerpo = "<g stroke='#FFFFFF' stroke-width='0.9' stroke-linejoin='round' fill-opacity='" & op & "'>" & provs & "</g>"
            {svg_envolver(P["lienzo"]["alto"], 'cuerpo & ' + caja_svg + ' & ley')}""",
         None, F, {"dataCategory": "ImageUrl"}),
        ("SVG elecciones municipios", f"""
            {VAR_SAT}
            {ccaa_sel}
            VAR tm = ADDCOLUMNS(ALL(Municipios), "@f", CALCULATE(SELECTEDVALUE('Ganador municipio'[familia_ganador])))
            VAR munis = CONCATENATEX(DISTINCT(SELECTCOLUMNS(tm, "@f", [@f])),
                VAR fam = [@f]
                VAR c = IF(ISBLANK(fam), "{SIN_DATO}", {dax_color_familia('fam')})
                RETURN "<g fill='" & c & "'>" & CONCATENATEX(FILTER(tm, [@f] = fam && (todo || Municipios[ccaa_ine] IN sel)),
                    "<path d='" & Municipios[path] & "'/>", "") & "</g>", "")
            VAR fondo = CONCATENATEX(ALL(Provincias), "<path d='" & Provincias[path] & "'/>", "")
            VAR cuenta = ADDCOLUMNS(DISTINCT(SELECTCOLUMNS(FILTER(tm, NOT ISBLANK([@f])), "@f", [@f])),
                "@n", COUNTROWS(FILTER(tm, [@f] = EARLIER([@f]))))
            VAR ley = {LEY_ELEC}
            VAR cuerpo = "<g fill='#EEEBF3' fill-opacity='" & IF(sat, "0.25", "1") & "'>" & fondo & "</g><g stroke='#FFFFFF' stroke-width='0.15' fill-opacity='" & op & "'>" & munis & "</g>"
                & "<g fill='none' stroke='#1D1631' stroke-opacity='0.6' stroke-width='0.9'>" & fondo & "</g>"
            {svg_envolver(P["lienzo"]["alto"], 'cuerpo & ' + caja_svg + ' & ley')}""",
         None, F, {"dataCategory": "ImageUrl"}),
        ("SVG elecciones", """
            IF(SELECTEDVALUE('Nivel del mapa'[id], 2) = 3, [SVG elecciones municipios], [SVG elecciones provincias])""",
         None, F, {"dataCategory": "ImageUrl"}),
        # ---- elecciones regionales (Open Data Euskadi)
        ("Votos (regional)", "CALCULATE(SUM('Elecciones regionales'[votos]), 'Elecciones regionales'[nivel] = \"territorio\")", MIL, "Elecciones"),
        ("% voto (regional)", """
            DIVIDE([Votos (regional)], CALCULATE([Votos (regional)], REMOVEFILTERS('Elecciones regionales'[candidatura])))""", PCT, "Elecciones"),
        ("Escaños (regional)", "CALCULATE(SUM('Elecciones regionales'[escanos]), 'Elecciones regionales'[nivel] = \"territorio\")", "0", "Elecciones"),
        ("Censo (regional)", "CALCULATE(SUM('Participación regional'[censo]), 'Participación regional'[nivel] = \"territorio\")", MIL, "Elecciones"),
        ("Votantes (regional)", "CALCULATE(SUM('Participación regional'[votantes]), 'Participación regional'[nivel] = \"territorio\")", MIL, "Elecciones"),
        ("Participación (regional)", "DIVIDE([Votantes (regional)], [Censo (regional)])", PCT, "Elecciones"),
        ("Ganador (regional)", """
            VAR t = ADDCOLUMNS(VALUES('Elecciones regionales'[candidatura]), "@v", [Votos (regional)])
            RETURN MAXX(TOPN(1, t, [@v], DESC), 'Elecciones regionales'[candidatura])""", None, "Elecciones"),
        ("Convocatoria elegida", "SELECTEDVALUE(Convocatorias[Convocatoria], \"Elegí una convocatoria\")", None, F),
        ("Color partido", f"VAR p = UPPER(SELECTEDVALUE('Elecciones regionales'[candidatura])) RETURN {dax_color_partido('p')}", None, F),
        ("SVG Euskadi ganador", f"""
            VAR provs = CALCULATETABLE(VALUES('Participación regional'[provincia_ine]))
            VAR cc = MAXX(FILTER(ALL(Provincias), Provincias[provincia_ine] IN provs), Provincias[ccaa_ine])
            VAR ancho = LOOKUPVALUE(CCAA[lienzo_ancho], CCAA[ccaa_ine], cc)
            VAR alto = LOOKUPVALUE(CCAA[lienzo_alto], CCAA[ccaa_ine], cc)
            VAR t = ADDCOLUMNS(CALCULATETABLE(Municipios, REMOVEFILTERS(Municipios), Municipios[ccaa_ine] = cc), "@g",
                CALCULATE(SELECTEDVALUE('Participación regional'[ganador]), 'Participación regional'[nivel] = "municipio"))
            VAR formas = CONCATENATEX(t,
                VAR g = UPPER([@g])
                VAR c = IF(ISBLANK([@g]), "{SIN_DATO}", {dax_color_partido('g')})
                RETURN "<path d='" & Municipios[path_ccaa] & "' fill='" & c & "'/>", "")
            VAR partidos = ADDCOLUMNS(DISTINCT(SELECTCOLUMNS(FILTER(t, NOT ISBLANK([@g])), "@g", [@g])),
                "@n", COUNTROWS(FILTER(t, [@g] = EARLIER([@g]))))
            VAR ley = CONCATENATEX(TOPN(8, partidos, [@n], DESC),
                VAR g = UPPER([@g])
                VAR i = RANKX(partidos, [@n], , DESC, Dense)
                RETURN "<rect x='10' y='" & (alto + 10 + i * 24) & "' width='22' height='16' rx='3' fill='" & {dax_color_partido('g')} & "'/>"
                    & "<text x='40' y='" & (alto + 23 + i * 24) & "' font-family='Segoe UI' font-size='14' fill='#1D1631'>"
                    & SUBSTITUTE(SUBSTITUTE(SUBSTITUTE([@g], "&", "&amp;"), "<", "&lt;"), ">", "&gt;") & " · " & [@n] & IF([@n] = 1, " municipio", " municipios") & "</text>", "", [@n], DESC)
            VAR svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 " & ancho & " " & (alto + 230) & "'>"
                & "<text x='10' y='" & (alto + 22) & "' font-family='Segoe UI' font-size='15' font-weight='700' fill='#1D1631'>Partido más votado por municipio</text>"
                & "<g stroke='#FFFFFF' stroke-width='0.8' stroke-linejoin='round'>" & formas & "</g>" & ley & "</svg>"
            RETURN "data:image/svg+xml;utf8," & SUBSTITUTE(SUBSTITUTE(svg, "%", "%25"), "#", "%23")""",
         None, F, {"dataCategory": "ImageUrl"}),
        ("Título mapa nivel", """
            "Mapa por " & LOWER(SELECTEDVALUE('Nivel del mapa'[Nivel], "Provincia")) & " · " &
            SELECTEDVALUE('Métrica del mapa'[Métrica], "Variación de población 10 años")""", None, F),
        # ---- ciudad (secciones censales)
        ("Ciudad elegida", """
            IF(HASONEVALUE(Municipios[municipio_ine]), SELECTEDVALUE(Municipios[nombre_completo]),
               "Elegí un municipio en el segmentador")""", None, F),
        ("Secciones", "COUNTROWS(Secciones)", MIL, "Ciudad"),
        ("Distritos", "COUNTROWS('Distritos ciudad')", MIL, "Ciudad"),
        ("Población secciones", "SUM(Secciones[poblacion])", MIL, "Ciudad"),
        ("Renta neta por persona", """
            VAR t = FILTER(Secciones, NOT ISBLANK(Secciones[renta_pp]) && NOT ISBLANK(Secciones[poblacion]))
            RETURN DIVIDE(SUMX(t, Secciones[renta_pp] * Secciones[poblacion]), SUMX(t, Secciones[poblacion]))""",
         "#,0 €", "Ciudad"),
        ("% 65 y más", """
            VAR t = FILTER(Secciones, NOT ISBLANK(Secciones[pct_65]) && NOT ISBLANK(Secciones[poblacion]))
            RETURN DIVIDE(SUMX(t, Secciones[pct_65] * Secciones[poblacion]), SUMX(t, Secciones[poblacion]))""", PCT, "Ciudad"),
        ("Densidad secciones", "DIVIDE([Población secciones], SUM(Secciones[area_km2]))", "#,0", "Ciudad"),
        ("Brecha de renta entre secciones", "DIVIDE(MAX(Secciones[renta_pp]), MIN(Secciones[renta_pp]))", "0.0", "Ciudad"),
        ("SVG ciudad", f"""
            VAR m = SELECTEDVALUE(Municipios[municipio_ine])
            VAR ancho = SELECTEDVALUE(Municipios[lienzo_ancho])
            VAR alto = SELECTEDVALUE(Municipios[lienzo_alto])
            VAR idk = SELECTEDVALUE('Métrica ciudad'[id], 1)
            VAR t = ADDCOLUMNS(CALCULATETABLE(Secciones, REMOVEFILTERS(Secciones), Secciones[municipio_ine] = m), "@c",
                VAR v = SWITCH(idk, 1, Secciones[renta_pp], 2, DIVIDE(Secciones[poblacion], Secciones[area_km2]),
                               3, Secciones[pct_65], 4, Secciones[poblacion])
                RETURN {dax_color("idk", "v", ESCALAS_CIUDAD)})
            VAR grupos = CONCATENATEX(DISTINCT(SELECTCOLUMNS(t, "@c", [@c])),
                VAR col = [@c]
                RETURN "<g fill='" & col & "'>" & CONCATENATEX(FILTER(t, [@c] = col), "<path d='" & Secciones[path] & "'/>", "") & "</g>", "")
            VAR dt = CALCULATETABLE('Distritos ciudad', REMOVEFILTERS('Distritos ciudad'), 'Distritos ciudad'[municipio_ine] = m)
            VAR dist = CONCATENATEX(dt, "<path d='" & 'Distritos ciudad'[path] & "'/>", "")
            VAR etiq = CONCATENATEX(dt,
                "<text x='" & 'Distritos ciudad'[x] & "' y='" & 'Distritos ciudad'[y] & "' text-anchor='middle' font-family='Segoe UI' font-size='16' font-weight='700' fill='#1D1631' stroke='#FFFFFF' stroke-width='3.5' paint-order='stroke'>D" & RIGHT('Distritos ciudad'[cudis], 2) & "</text>", "")
            VAR leyenda = {LEY_CIUDAD}
            VAR svg = "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 " & MAX(ancho, 320) & " " & (alto + 175) & "'>"
                & "<g stroke='#FFFFFF' stroke-width='0.6' stroke-linejoin='round'>" & grupos & "</g>"
                & "<g fill='none' stroke='#1D1631' stroke-width='2.2' stroke-linejoin='round'>" & dist & "</g>"
                & IF(COUNTROWS(dt) > 1, etiq, "") & leyenda & "</svg>"
            RETURN IF(ISBLANK(m) || ISBLANK(ancho), BLANK(),
                "data:image/svg+xml;utf8," & SUBSTITUTE(SUBSTITUTE(svg, "%", "%25"), "#", "%23"))""",
         None, F, {"dataCategory": "ImageUrl"}),
    ]
    return m


def modelo(P) -> dict[str, str]:
    T = {}
    T["CCAA"] = tabla_csv("CCAA", "ccaa.csv", [
        ("geo_id", "string", None), ("ccaa_ine", "string", None), ("nombre", "string", None),
        ("pob_actual", "int64", MIL), ("pob_hace10", "int64", MIL), ("area_km2", "double", "#,0"),
        ("paro", "double", PCT), ("paro_trimestre", "string", None), ("pib_pc", "double", "#,0 €"), ("lienzo_ancho", "int64", None), ("lienzo_alto", "int64", None), ("n_provincias", "int64", "0"),
        ("n_municipios", "int64", MIL), ("path", "string", None), ("cx", "int64", None), ("cy", "int64", None)],
        ocultas=("geo_id", "path", "cx", "cy", "pob_actual", "pob_hace10", "lienzo_ancho", "lienzo_alto"),
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
        ("lat", "double", "0.000"), ("tamano", "string", None), ("nombre_completo", "string", None),
        ("lienzo_ancho", "int64", None), ("lienzo_alto", "int64", None), ("n_secciones", "int64", "0"),
        ("renta_pp", "double", "#,0 €"), ("path_ccaa", "string", None), ("x_ccaa", "int64", None), ("y_ccaa", "int64", None)],
        ocultas=("geo_id", "path", "x", "y", "provincia_ine", "ccaa_ine", "pob_actual", "pob_hace10",
                 "electores_and_2026", "lon", "lat", "lienzo_ancho", "lienzo_alto", "path_ccaa", "x_ccaa", "y_ccaa"),
        extra_col={"municipio_ine": {"isKey": ""}, "lon": {"dataCategory": "Longitude"},
                   "lat": {"dataCategory": "Latitude"}})
    T["Secciones"] = tabla_csv("Secciones", "secciones.csv", [
        ("cusec", "string", None), ("municipio_ine", "string", None), ("cudis", "string", None), ("path", "string", None),
        ("x", "int64", None), ("y", "int64", None), ("area_km2", "double", "#,0.00"), ("renta_pp", "double", "#,0 €"),
        ("poblacion", "int64", MIL), ("pct_65", "double", PCT)],
        ocultas=("municipio_ine", "path", "x", "y"), extra_col={"cusec": {"isKey": ""}})
    T["Distritos ciudad"] = tabla_csv("Distritos ciudad", "distritos.csv", [
        ("cudis", "string", None), ("municipio_ine", "string", None), ("path", "string", None),
        ("x", "int64", None), ("y", "int64", None)], oculta_tabla=True)
    T["Elecciones regionales"] = tabla_csv("Elecciones regionales", "elecciones_regionales.csv", [
        ("election_id", "string", None), ("tipo", "string", None), ("anyo", "int64", "0"), ("nivel", "string", None),
        ("provincia_ine", "string", None), ("municipio_ine", "string", None), ("candidatura", "string", None),
        ("votos", "int64", MIL), ("escanos", "int64", "0"), ("convocatoria", "string", None), ("orden", "int64", None),
        ("geo_id", "string", None)],
        ocultas=("election_id", "tipo", "provincia_ine", "municipio_ine", "orden", "geo_id", "votos", "escanos"))
    T["Participación regional"] = tabla_csv("Participación regional", "participacion_regional.csv", [
        ("election_id", "string", None), ("tipo", "string", None), ("anyo", "int64", "0"), ("nivel", "string", None),
        ("provincia_ine", "string", None), ("municipio_ine", "string", None), ("censo", "int64", MIL),
        ("votantes", "int64", MIL), ("nulos", "int64", MIL), ("blancos", "int64", MIL), ("validos", "int64", MIL),
        ("votos_candidaturas", "int64", MIL), ("turnout", "double", PCT), ("ganador", "string", None),
        ("cuota_ganador", "double", PCT), ("convocatoria", "string", None), ("orden", "int64", None), ("geo_id", "string", None)],
        ocultas=("election_id", "tipo", "provincia_ine", "municipio_ine", "orden", "geo_id"))
    T["Convocatorias"] = tabla_calculada("Convocatorias",
        "DISTINCT(SELECTCOLUMNS('Participación regional', \"election_id\", [election_id], \"Convocatoria\", [convocatoria], \"orden\", [orden]))",
        [("election_id", "string", None, {"isHidden": True}),
         ("Convocatoria", "string", None, {"sortByColumn": "orden"}),
         ("orden", "int64", None, {"isHidden": True})])
    T["Convocatorias nacionales"] = tabla_csv("Convocatorias nacionales", "nac_convocatorias.csv", [
        ("election_id", "string", None), ("election_type", "string", None), ("anno", "int64", "0"), ("mes", "int64", "0"),
        ("fecha", "string", None), ("convocatoria", "string", None), ("orden", "int64", None)],
        ocultas=("election_id", "mes", "orden", "fecha"),
        extra_col={"election_id": {"isKey": ""}, "convocatoria": {"sortByColumn": "orden"}})
    T["Resultados familia"] = tabla_csv("Resultados familia", "nac_familias.csv", [
        ("election_id", "string", None), ("geo_level", "string", None), ("geo_id", "string", None), ("familia", "string", None),
        ("votos", "int64", MIL), ("escanos", "int64", "0"), ("vote_share", "double", PCT)],
        ocultas=("election_id", "geo_level", "geo_id", "votos", "escanos", "vote_share"))
    T["Participación nacional"] = tabla_csv("Participación nacional", "nac_participacion.csv", [
        ("election_id", "string", None), ("geo_level", "string", None), ("geo_id", "string", None), ("censo", "int64", MIL),
        ("votantes", "int64", MIL), ("votos_validos", "int64", MIL), ("votos_blancos", "int64", MIL),
        ("votos_nulos", "int64", MIL), ("turnout", "double", PCT)], oculta_tabla=True)
    T["Ganador municipio"] = tabla_csv("Ganador municipio", "nac_ganadores_mun.csv", [
        ("election_id", "string", None), ("geo_id", "string", None), ("ganador", "string", None),
        ("familia_ganador", "string", None), ("cuota_ganador", "double", PCT), ("margen", "double", PCT),
        ("segundo", "string", None)], ocultas=("election_id", "geo_id"))
    T["Ganador provincia"] = tabla_csv("Ganador provincia", "nac_ganadores_prov.csv", [
        ("election_id", "string", None), ("geo_id", "string", None), ("ganador", "string", None),
        ("familia_ganador", "string", None), ("cuota_ganador", "double", PCT), ("margen", "double", PCT),
        ("segundo", "string", None)], ocultas=("election_id", "geo_id"))
    T["Índices electorales"] = tabla_csv("Índices electorales", "nac_indices.csv", [
        ("election_id", "string", None), ("geo_level", "string", None), ("geo_id", "string", None), ("enep", "double", "0.00"),
        ("enpp", "double", "0.00"), ("gallagher", "double", "0.00"), ("competitividad", "double", PCT),
        ("volatilidad_pedersen", "double", PCT)], oculta_tabla=True)
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
    filas = ",\n    ".join(f'{{{i}, "{t}"}}' for i, (t, _, _) in ESCALAS.items() if i < 10)
    T["Métrica del mapa"] = tabla_calculada("Métrica del mapa",
        f'DATATABLE("id", INTEGER, "Métrica", STRING, {{\n    {filas}\n}})',
        [("id", "int64", None, {"isHidden": True}), ("Métrica", "string", None, {"sortByColumn": "id"})])
    T["Fondo satélite"] = tabla_csv("Fondo satélite", "fondo_satelite.csv",
        [("orden", "int64", "0"), ("texto", "string", None)], oculta_tabla=True)
    T["Mapa base"] = tabla_calculada("Mapa base",
        'DATATABLE("id", INTEGER, "Mapa base", STRING, {{1, "Mapa"}, {2, "Satélite"}})',
        [("id", "int64", None, {"isHidden": True}), ("Mapa base", "string", None, {"sortByColumn": "id"})])
    T["Nivel del mapa"] = tabla_calculada("Nivel del mapa",
        'DATATABLE("id", INTEGER, "Nivel", STRING, {{1, "Comunidad autónoma"}, {2, "Provincia"}, {3, "Municipio"}})',
        [("id", "int64", None, {"isHidden": True}), ("Nivel", "string", None, {"sortByColumn": "id"})])
    filas_c = ",\n    ".join(f'{{{i}, "{t}"}}' for i, (t, _, _) in ESCALAS_CIUDAD.items())
    T["Métrica ciudad"] = tabla_calculada("Métrica ciudad",
        f'DATATABLE("id", INTEGER, "Métrica", STRING, {{\n    {filas_c}\n}})',
        [("id", "int64", None, {"isHidden": True}), ("Métrica", "string", None, {"sortByColumn": "id"})])
    T["Medidas"] = tabla_calculada("Medidas", "{BLANK()}", [("Value", "string", None, {"isHidden": True})], medidas(P))

    archivos = {f"definition/tables/{n}.tmdl": s for n, s in T.items()}
    archivos["definition/expressions.tmdl"] = (
        f'expression CarpetaDatos = "{DATOS}\\" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
        "\tannotation PBI_ResultType = Text\n")
    rels = [("rel_prov_ccaa", "Provincias.ccaa_ine", "CCAA.ccaa_ine"),
            ("rel_mun_prov", "Municipios.provincia_ine", "Provincias.provincia_ine"),
            ("rel_sec_mun", "Secciones.municipio_ine", "Municipios.municipio_ine"),
            ("rel_reg_conv", "'Elecciones regionales'.election_id", "Convocatorias.election_id"),
            ("rel_fam_conv", "'Resultados familia'.election_id", "'Convocatorias nacionales'.election_id"),
            ("rel_npart_conv", "'Participación nacional'.election_id", "'Convocatorias nacionales'.election_id"),
            ("rel_gmun_conv", "'Ganador municipio'.election_id", "'Convocatorias nacionales'.election_id"),
            ("rel_gprov_conv", "'Ganador provincia'.election_id", "'Convocatorias nacionales'.election_id"),
            ("rel_ind_conv", "'Índices electorales'.election_id", "'Convocatorias nacionales'.election_id"),
            ("rel_gmun_mun", "'Ganador municipio'.geo_id", "Municipios.geo_id"),
            ("rel_gprov_prov", "'Ganador provincia'.geo_id", "Provincias.geo_id"),
            ("rel_part_conv", "'Participación regional'.election_id", "Convocatorias.election_id"),
            ("rel_part_mun", "'Participación regional'.municipio_ine", "Municipios.municipio_ine"),
            ("rel_dis_mun", "'Distritos ciudad'.municipio_ine", "Municipios.municipio_ine"),
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
NAV = [("p01_resumen", "Resumen España", "◉"), ("p02_mapa", "Mapa de España", "▦"),
       ("p03_ciudad", "Mapa de ciudad", "▩"), ("p03a_elecciones", "Elecciones nacionales", "☑"),
       ("p03c_historico", "Comparador histórico", "↗"), ("p03b_euskadi", "Autonómicas", "◧"), ("p04_demografia", "Demografía", "≋"),
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

    # 2 mapa de España: comunidad / provincia / municipio
    pg = nueva("p02_mapa", "Mapa de España", "Elegí el nivel (comunidad, provincia o municipio) y la métrica; "
                                             "el segmentador de comunidad resalta su territorio")
    pg.add("card", X0, 92, 860, 40, query={"Values": [proj(Me("Título mapa nivel"), " ")]},
           objects={"labels": [{"properties": {"color": color(VIO), "fontSize": lit(13), "fontFamily": lit("Segoe UI Semibold")}}],
                    "categoryLabels": [{"properties": {"show": lit(False)}}]}, titulo="")
    pg.imagen(X0, 138, 860, 752, "SVG España")
    pg.segmentador(X0 + 875, 92, 490, 58, C("Nivel del mapa", "Nivel"), "Nivel del mapa", modo="Basic", unico=True,
                   horizontal=True, presel="Provincia")
    metrica_slicer(pg, X0 + 875, 158, 490, 58)
    ccaa_slicer(pg, X0 + 875, 224, 490, 58)
    pg.segmentador(X0 + 875, 292, 490, 58, C("Mapa base", "Mapa base"), "Mapa base", modo="Basic", unico=True,
                   horizontal=True, presel="Mapa", sync="fondo")
    tabla(pg, X0 + 875, 358, 490, 532,
          [(C("Provincias", "nombre"), "Provincia"), (Me("Población"), "Población"),
           (Me("Variación población 10 años"), "Var. 10 años"), (Me("Densidad"), "hab./km²"),
           (Me("PIB per cápita"), "PIB pc")],
          "Provincias", sort=[(Me("Población"), "Descending")], size=9)
    pags.append(pg)

    # 3 mapa de ciudad: distritos y secciones censales
    sub_c = (f"Secciones censales y distritos · renta y población: Atlas de Renta del INE ({P.get('anyo_adrh') or 's/d'}) · "
             "solo municipios con 5 o más secciones")
    pg = nueva("p03_ciudad", "Mapa de ciudad", sub_c)
    pg.segmentador(X0, 92, 330, 58, C("Provincias", "nombre"), "Provincia", sync="prov_ciudad")
    pg.segmentador(X0 + 340, 92, 330, 58, C("Municipios", "nombre_completo"), "Municipio", unico=True,
                   presel="Madrid (Madrid)")
    pg.segmentador(X0 + 680, 92, 300, 58, C("Métrica ciudad", "Métrica"), "Métrica del mapa", unico=True)
    pg.add("card", X0, 158, 860, 40, query={"Values": [proj(Me("Ciudad elegida"), " ")]},
           objects={"labels": [{"properties": {"color": color(VIO), "fontSize": lit(14), "fontFamily": lit("Segoe UI Semibold")}}],
                    "categoryLabels": [{"properties": {"show": lit(False)}}]}, titulo="")
    pg.imagen(X0, 204, 860, 686, "SVG ciudad")
    for i, (m, et) in enumerate([("Población secciones", "Población (Atlas de Renta)"), ("Renta neta por persona", "Renta neta por persona"),
                                 ("% 65 y más", "Población de 65+"), ("Brecha de renta entre secciones", "Más rica / más pobre (acotado INE)")]):
        pg.tarjeta(X0 + 875 + (i % 2) * 248, 158 + (i // 2) * 92, 240, 84, Me(m), et, size=18)
    tabla(pg, X0 + 875, 344, 490, 546,
          [(C("Secciones", "cusec"), "Sección"), (C("Secciones", "cudis"), "Distrito"), (C("Secciones", "renta_pp"), "Renta pp"),
           (C("Secciones", "poblacion"), "Población"), (C("Secciones", "pct_65"), "65+")],
          "Secciones censales", sort=[(C("Secciones", "renta_pp"), "Descending")], size=9)
    pags.append(pg)

    # 3a elecciones nacionales
    pg = nueva("p03a_elecciones", "Elecciones nacionales",
               "Generales 2015–2023, municipales 2019–2023 y europeas 2019–2024 · Ministerio del Interior (Infoelectoral) · "
               "familias políticas según tabla documentada")
    pg.segmentador(X0, 92, 300, 58, C("Convocatorias nacionales", "convocatoria"), "Convocatoria", unico=True,
                   presel="Generales 2023", sync="conv_nac")
    ccaa_slicer(pg, X0 + 310, 92, 300, 58)
    pg.segmentador(X0 + 620, 92, 240, 58, C("Nivel del mapa", "Nivel"), "Mapa por", modo="Basic", unico=True,
                   horizontal=True, presel="Provincia")
    pg.segmentador(X0 + 610, 146, 250, 50, C("Mapa base", "Mapa base"), "Mapa base", modo="Basic", unico=True,
                   horizontal=True, presel="Mapa", sync="fondo")
    pg.add("card", X0, 156, 600, 36, query={"Values": [proj(Me("Título elecciones"), " ")]},
           objects={"labels": [{"properties": {"color": color(VIO), "fontSize": lit(12), "fontFamily": lit("Segoe UI Semibold")}}],
                    "categoryLabels": [{"properties": {"show": lit(False)}}]}, titulo="")
    pg.imagen(X0, 196, 860, 694, "SVG elecciones")
    for i, (m, et) in enumerate([("Participación (nac)", "Participación"), ("Más votado (nac)", "Más votado"),
                                 ("ENEP (nac)", "Nº efectivo de partidos"), ("Volatilidad (nac)", "Volatilidad vs. anterior")]):
        pg.tarjeta(X0 + 875 + (i % 2) * 248, 92 + (i // 2) * 76, 240, 70, Me(m), et, size=17)
    barras(pg, X0 + 875, 248, 490, 330, C("Resultados familia", "familia"), Me("% voto (nac)"), "Porcentaje de voto",
           fx="Color familia", nombre_val="% voto")
    tabla(pg, X0 + 875, 588, 490, 302,
          [(C("Resultados familia", "familia"), "Familia"), (Me("Votos (nac)"), "Votos"), (Me("% voto (nac)"), "% voto"),
           (Me("Escaños (nac)"), "Escaños")], "Resultados", sort=[(Me("Votos (nac)"), "Descending")], size=9)
    pags.append(pg)

    # 3c comparador histórico
    pg = nueva("p03c_historico", "Comparador histórico", "Evolución del voto por familia política en las elecciones generales "
                                                       "(nacional o comunidad elegida) y volatilidad entre convocatorias")
    ccaa_slicer(pg, X0, 92, 340, 58)
    pg.segmentador(X0 + 350, 92, 340, 58, C("Convocatorias nacionales", "election_type"), "Tipo de elección", unico=True,
                   presel="congreso")
    lc = pg.add("lineChart", X0, 160, 900, 420,
                query={"Category": [proj(C("Convocatorias nacionales", "convocatoria"))],
                       "Series": [proj(C("Resultados familia", "familia"))], "Y": [proj(Me("% voto (nac)"), "% voto")]},
                objects={"lineStyles": [{"properties": {"strokeWidth": lit(3), "showMarker": lit(True)}}],
                         "legend": [{"properties": {"show": lit(True), "position": lit("Right")}}],
                         "categoryAxis": [{"properties": {"showAxisTitle": lit(False)}}],
                         "valueAxis": [{"properties": {"showAxisTitle": lit(False)}}]},
                titulo="Porcentaje de voto por familia", sort=[(C("Convocatorias nacionales", "convocatoria"), "Ascending")])
    barras(pg, X0 + 912, 160, 454, 420, C("Convocatorias nacionales", "convocatoria"), Me("Volatilidad (nac)"),
           "Volatilidad de Pedersen", tipo="clusteredColumnChart", sort=[(C("Convocatorias nacionales", "convocatoria"), "Ascending")],
           nombre_val="Volatilidad")
    tabla(pg, X0, 590, 1366, 300,
          [(C("Provincias", "nombre"), "Provincia"), (C("Convocatorias nacionales", "convocatoria"), "Convocatoria"),
           (C("Ganador provincia", "ganador"), "Más votado"), (C("Ganador provincia", "cuota_ganador"), "% del ganador"),
           (C("Ganador provincia", "segundo"), "Segundo"), (C("Ganador provincia", "margen"), "Margen")],
          "Ganador por provincia y convocatoria", size=9)
    pags.append(pg)

    # 3b elecciones País Vasco (Open Data Euskadi)
    pg = nueva("p03b_euskadi", "Elecciones autonómicas",
               "Parlamento Vasco 1980–2024 y Congreso 2023 en la CAPV (Open Data Euskadi) · Asamblea de Madrid 1991–2023 "
               "(Datos Abiertos Comunidad de Madrid; el resto de partidos llega agregado)")
    pg.segmentador(X0, 92, 360, 58, C("Convocatorias", "Convocatoria"), "Convocatoria", unico=True,
                   presel="Parlamento Vasco 2024")
    tarjetas(pg, 92, [("Participación (regional)", "Participación"), ("Votantes (regional)", "Votantes"),
                      ("Censo (regional)", "Censo"), ("Ganador (regional)", "Más votado")], w=240, h=58, x=X0 + 372)
    pg.imagen(X0, 160, 640, 730, "SVG Euskadi ganador")
    barras(pg, X0 + 652, 160, 714, 400, C("Elecciones regionales", "candidatura"), Me("% voto (regional)"),
           "Porcentaje de voto por candidatura", fx="Color partido", nombre_val="% voto")
    tabla(pg, X0 + 652, 570, 714, 320,
          [(C("Elecciones regionales", "candidatura"), "Candidatura"), (Me("Votos (regional)"), "Votos"),
           (Me("% voto (regional)"), "% voto"), (Me("Escaños (regional)"), "Escaños")],
          "Resultados (escaños solo cuando la fuente los publica)", sort=[(Me("Votos (regional)"), "Descending")], size=9)
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
        [("Mapa de ciudad", {"size": 13, "bold": True})],
        [("Secciones y distritos del seccionado INE 2024. Renta neta media por persona, población y % de 65+ del Atlas de "
          "Distribución de Renta de los Hogares (INE, año 2024). El INE acota los extremos por confidencialidad: las secciones "
          "con renta ≥ 40.089 € o ≤ 5.828 € se publican con ese valor de corte.", {"size": 11})],
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
    if con_datos or not (DATOS / "fondo_satelite.csv").exists():
        from atlas_spain.viz.powerbi_fondo import exportar as exportar_fondo
        exportar_fondo()
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
