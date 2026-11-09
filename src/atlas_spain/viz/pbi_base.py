"""Piezas comunes para generar proyectos PBIP (TMDL + PBIR) por código.

Extraídas del generador de ATLAS Brasil (BRASIL-ELECCIONES/src/viz/powerbi_proyecto.py)
para que los tableros de ATLAS compartan el mismo lenguaje visual.
"""
from __future__ import annotations

import json
from pathlib import Path

PBI_TEMAS = Path(r"C:\Program Files\Microsoft Power BI Desktop\bin\WebView2Resources\minerva\sharedresources\BaseThemes")
BASE_THEME = "CY26SU02"
V_VISUAL, V_PAGE, V_REPORT = "2.4.0", "2.0.0", "3.0.0"
SCH = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition"

# paleta ATLAS (violeta) + acentos España
INK, VIO, MUTED, BG, LINEA = "#1D1631", "#5B3F99", "#6B6480", "#F4F1F9", "#E4DFEE"
ORO, ROJO, AZUL = "#E0A526", "#C8102E", "#1F4E9C"
W, H = 1600, 900
X0 = 222

def q(nombre: str) -> str:
    """Nombre TMDL, entre comillas simples si hace falta."""
    if nombre.replace("_", "").isalnum() and nombre.isascii() and not nombre[0].isdigit():
        return nombre
    return "'" + nombre.replace("'", "''") + "'"


TIPOS_M = {"string": "type text", "int64": "Int64.Type", "double": "type number", "dateTime": "type date"}


def tabla_csv(nombre, archivo, columnas, medidas=(), ocultas=(), extra_col=None, oculta_tabla=False) -> str:
    """columnas: [(nombre, tipo, formato|None)]"""
    extra_col = extra_col or {}
    out = [f"table {q(nombre)}"] + (["\tisHidden"] if oculta_tabla else []) + [""]
    for m in medidas:
        out += medida(m)
    for c, t, fmt in columnas:
        out.append(f"\tcolumn {q(c)}")
        out.append(f"\t\tdataType: {t}")
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out.append(f"\t\tsummarizeBy: {'sum' if t in ('int64', 'double') and c in extra_col.get('_sum', ()) else 'none'}")
        out.append(f"\t\tsourceColumn: {c}")
        if c in ocultas:
            out.append("\t\tisHidden")
        for k, v in extra_col.get(c, {}).items():
            out.append(f"\t\t{k}: {v}" if v != "" else f"\t\t{k}")
        out.append("")
    tipos = ", ".join(f'{{"{c}", {TIPOS_M[t]}}}' for c, t, _ in columnas)
    out += [f"\tpartition {q(nombre)} = m", "\t\tmode: import", "\t\tsource =", "\t\t\t\tlet",
            f'\t\t\t\t    Origen = Csv.Document(File.Contents(CarpetaDatos & "{archivo}"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
            "\t\t\t\t    Encabezados = Table.PromoteHeaders(Origen, [PromoteAllScalars = true]),",
            f'\t\t\t\t    Tipos = Table.TransformColumnTypes(Encabezados, {{{tipos}}}, "en-US")',
            "\t\t\t\tin", "\t\t\t\t    Tipos", ""]
    return "\n".join(out) + "\n"


def medida(m) -> list[str]:
    nombre, expr, fmt, carpeta = m[:4]
    extra = m[4] if len(m) > 4 else {}
    lineas = [ln.rstrip() for ln in expr.strip("\n").split("\n") if ln.strip()]
    out = [f"\tmeasure {q(nombre)} ="]
    ind = min(len(ln) - len(ln.lstrip()) for ln in lineas)
    out += ["\t\t\t" + ln[ind:] for ln in lineas]
    if fmt:
        out.append(f"\t\tformatString: {fmt}")
    if carpeta:
        out.append(f"\t\tdisplayFolder: {carpeta}")
    for k, v in extra.items():
        out.append(f"\t\t{k}: {v}")
    out.append("")
    return out


def tabla_calculada(nombre, dax, columnas, medidas=(), oculta=False) -> str:
    out = [f"table {q(nombre)}"]
    if oculta:
        out.append("\tisHidden")
    out.append("")
    for m in medidas:
        out += medida(m)
    for c, t, fmt, extra in columnas:
        out += [f"\tcolumn {q(c)}", f"\t\tdataType: {t}"]
        if fmt:
            out.append(f"\t\tformatString: {fmt}")
        out += ["\t\tsummarizeBy: none", f"\t\tsourceColumn: [{c}]"]
        for k, v in (extra or {}).items():
            out.append(f"\t\t{k}: {v}" if v is not True else f"\t\t{k}")
        out.append("")
    out += [f"\tpartition {q(nombre)} = calculated", "\t\tmode: import", "\t\tsource =",
            *["\t\t\t\t" + ln for ln in dax.strip().split("\n")], ""]
    return "\n".join(out) + "\n"


def parametro(nombre, col, ini, fin, paso, fmt) -> str:
    return tabla_calculada(nombre, f"GENERATESERIES({ini}, {fin}, {paso})", [(col, "double", fmt, {"sourceColumn": "[Value]"})]) \
        .replace(f"\t\tsourceColumn: [{col}]\n\t\tsourceColumn: [Value]", "\t\tsourceColumn: [Value]")


# ---------------------------------------------------------------------------
# medidas DAX

def lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, (int, float)):
        s = f"{float(v):g}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def color(c):
    return {"solid": {"color": lit(c)}}


def C(t, c):
    return {"Column": {"Expression": {"SourceRef": {"Entity": t}}, "Property": c}}


def Me(m, t="Medidas"):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": t}}, "Property": m}}


def color_fx(m):
    return {"solid": {"color": {"expr": Me(m)}}}


def proj(campo, nombre=None):
    k = "Column" if "Column" in campo else "Measure"
    ref = f'{campo[k]["Expression"]["SourceRef"]["Entity"]}.{campo[k]["Property"]}'
    p = {"field": campo, "queryRef": ref, "nativeQueryRef": (nombre or "").strip() or campo[k]["Property"]}
    if nombre:
        p["displayName"] = nombre
    return p


def qref(campo):
    k = "Column" if "Column" in campo else "Measure"
    return f'{campo[k]["Expression"]["SourceRef"]["Entity"]}.{campo[k]["Property"]}'


TODOS = {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}


class Pagina:
    def __init__(self, nombre, titulo, subtitulo="", tipo=None, w=W, h=H, oculta=False, nav=True):
        self.nombre, self.titulo, self.tipo, self.w, self.h = nombre, titulo, tipo, w, h
        self.visuales, self.n, self.oculta = [], 0, oculta
        self.binding = None
        self.filtros = []
        if nav:
            self.encabezado(titulo, subtitulo)

    # -- contenedor genérico
    def add(self, tipo, x, y, w, h, query=None, objects=None, vco=None, sort=None, titulo=None, extra=None):
        self.n += 1
        nombre = f"{self.nombre[:20]}_{self.n:02d}_{tipo[:12]}"
        v = {"visualType": tipo}
        if query:
            v["query"] = {"queryState": {r: {"projections": ps} for r, ps in query.items()}}
            if sort:
                v["query"]["sortDefinition"] = {"sort": [{"field": f, "direction": d} for f, d in sort], "isDefaultSort": False}
        if objects:
            v["objects"] = objects
        vco = dict(vco or {})
        if titulo is not None:
            vco.setdefault("title", [{"properties": {"show": lit(bool(titulo)), **({"text": lit(titulo)} if titulo else {})}}])
        if vco:
            v["visualContainerObjects"] = vco
        if extra:
            v.update(extra)
        self.visuales.append({"$schema": f"{SCH}/visualContainer/{V_VISUAL}/schema.json", "name": nombre,
                              "position": {"x": x, "y": y, "z": self.n * 100, "width": w, "height": h, "tabOrder": self.n * 100},
                              "visual": v})
        return self.visuales[-1]

    # -- piezas
    def texto(self, x, y, w, h, parrafos, fondo=None, borde=False):
        pars = []
        for p in parrafos:
            if isinstance(p, str):
                p = [(p, {})]
            runs = []
            for txt, est in p:
                st = {"fontFamily": est.get("font", "Segoe UI"), "fontSize": f"{est.get('size', 11)}pt",
                      "color": est.get("color", INK)}
                if est.get("bold"):
                    st["fontWeight"] = "bold"
                r = {"value": txt, "textStyle": st}
                if est.get("url"):
                    r["url"] = est["url"]
                runs.append(r)
            par = {"textRuns": runs}
            if p and p[0][1].get("align"):
                par["horizontalTextAlignment"] = p[0][1]["align"]
            pars.append(par)
        vco = {"background": [{"properties": {"show": lit(bool(fondo)), **({"color": color(fondo), "transparency": lit(0)} if fondo else {})}}],
               "border": [{"properties": {"show": lit(borde)}}], "dropShadow": [{"properties": {"show": lit(False)}}],
               "visualHeader": [{"properties": {"show": lit(False)}}]}
        return self.add("textbox", x, y, w, h, objects={"general": [{"properties": {"paragraphs": pars}}]}, vco=vco)

    def boton(self, x, y, w, h, texto, destino=None, tipo="PageNavigation", fondo=VIO, fg="#FFFFFF", size=11,
              hover=None, icono="blank", alin="left", web=None, borde=None, transp=0, transp_hover=0):
        link = {"show": lit(True), "type": lit(tipo)}
        if tipo == "PageNavigation":
            link["navigationSection"] = lit(destino)
        elif tipo == "Drillthrough":
            link["drillthroughSection"] = lit(destino)
        elif tipo == "WebUrl":
            link["webUrl"] = lit(web)
        objs = {
            "icon": [{"properties": {"shapeType": lit(icono)}, "selector": {"id": "default"}},
                     *([{"properties": {"show": lit(icono != "blank")}}])],
            "text": [{"properties": {"show": lit(True)}},
                     {"properties": {"text": lit(texto), "fontColor": color(fg), "fontSize": lit(size), "fontFamily": lit("Segoe UI Semibold"),
                                     "horizontalAlignment": lit(alin), "leftMargin": lit(14)}, "selector": {"id": "default"}}],
            "fill": [{"properties": {"show": lit(True)}},
                     {"properties": {"fillColor": color(fondo), "transparency": lit(transp)}, "selector": {"id": "default"}},
                     {"properties": {"fillColor": color(hover or ORO), "transparency": lit(transp_hover)}, "selector": {"id": "hover"}}],
            "outline": [{"properties": {"show": lit(bool(borde)), **({"lineColor": color(borde), "weight": lit(1)} if borde else {})}}],
            "shape": [{"properties": {"tileShape": lit("rectangleRounded"), "roundEdge": lit(8)}}],
        }
        vco = {"visualLink": [{"properties": link}], "visualHeader": [{"properties": {"show": lit(False)}}],
               "dropShadow": [{"properties": {"show": lit(False)}}], "background": [{"properties": {"show": lit(False)}}],
               "border": [{"properties": {"show": lit(False)}}]}
        return self.add("actionButton", x, y, w, h, objects=objs, vco=vco)

    def tarjeta(self, x, y, w, h, campo, etiqueta, fx=None, size=26, fg=INK):
        objs = {"labels": [{"properties": {"color": color_fx(fx) if fx else color(fg), "fontSize": lit(size),
                                           "fontFamily": lit("Segoe UI Semibold"), "labelDisplayUnits": lit(0)}}],
                "categoryLabels": [{"properties": {"show": lit(True), "color": color(MUTED), "fontSize": lit(10)}}]}
        return self.add("card", x, y, w, h, query={"Values": [proj(campo, etiqueta)]}, objects=objs, titulo="")

    def imagen(self, x, y, w, h, medida, titulo=None):
        objs = {"image": [{"properties": {"sourceType": lit("imageUrl"), "sourceUrl": {"expr": Me(medida)}}}],
                "imageScaling": [{"properties": {"imageScalingType": lit("Fit")}}]}
        return self.add("image", x, y, w, h, objects=objs, titulo=titulo,
                        vco={"visualHeader": [{"properties": {"show": lit(False)}}]})

    def segmentador(self, x, y, w, h, campo, titulo, modo="Dropdown", sync=None, unico=False, horizontal=False, presel=None):
        objs = {"data": [{"properties": {"mode": lit(modo)}}],
                "header": [{"properties": {"show": lit(True), "text": lit(titulo), "fontColor": color(INK), "textSize": lit(10)}}],
                "items": [{"properties": {"textSize": lit(10), "fontColor": color(INK)}}]}
        if unico:
            objs["selection"] = [{"properties": {"singleSelect": lit(True), "strictSingleSelect": lit(False)}}]
        if horizontal:
            objs["general"] = [{"properties": {"orientation": lit(1)}}]
        if presel is not None:
            ent, prop = campo["Column"]["Expression"]["SourceRef"]["Entity"], campo["Column"]["Property"]
            objs.setdefault("general", [{"properties": {}}])[0]["properties"]["filter"] = {"filter": {
                "Version": 2, "From": [{"Name": "t", "Entity": ent, "Type": 0}],
                "Where": [{"Condition": {"In": {"Expressions": [{"Column": {"Expression": {"SourceRef": {"Source": "t"}}, "Property": prop}}],
                                                "Values": [[lit(presel)["expr"]]]}}}]}}
        extra = {"syncGroup": {"groupName": sync, "fieldChanges": True, "filterChanges": True}} if sync else None
        return self.add("slicer", x, y, w, h, query={"Values": [proj(campo)]}, objects=objs, titulo="", extra=extra)

    def encabezado(self, titulo, sub):
        self.texto(X0, 14, 1000, 44, [[(titulo, {"size": 22, "bold": True, "font": "Segoe UI Semibold"})]])
        if sub:
            self.texto(X0, 54, 1150, 28, [[(sub, {"size": 10.5, "color": MUTED})]])
        self.add("card", 1250, 18, 330, 50, query={"Values": [proj(Me("Corte"), " ")]},
                 objects={"labels": [{"properties": {"color": color(MUTED), "fontSize": lit(8.5), "fontFamily": lit("Segoe UI")}}],
                          "categoryLabels": [{"properties": {"show": lit(False)}}], "wordWrap": [{"properties": {"show": lit(True)}}]},
                 vco={"background": [{"properties": {"show": lit(False)}}], "border": [{"properties": {"show": lit(False)}}],
                      "dropShadow": [{"properties": {"show": lit(False)}}], "visualHeader": [{"properties": {"show": lit(False)}}],
                      "title": [{"properties": {"show": lit(False)}}]})

    def json(self):
        p = {"$schema": f"{SCH}/page/{V_PAGE}/schema.json", "name": self.nombre, "displayName": self.titulo,
             "displayOption": "FitToPage", "height": self.h, "width": self.w}
        if self.tipo:
            p["type"] = self.tipo
        if self.binding:
            p["pageBinding"] = self.binding
        if self.filtros:
            p["filterConfig"] = {"filters": self.filtros}
        if self.oculta:
            p["visibility"] = "HiddenInViewMode"
        return p


def fx_valores(campo_fmt, medida_color, prop="backColor"):
    return {"properties": {prop: color_fx(medida_color)}, "selector": {**TODOS, "metadata": qref(campo_fmt)}}


def tabla(pg, x, y, w, h, campos, titulo, fx=(), sort=None, size=10):
    objs = {"columnHeaders": [{"properties": {"fontColor": color("#FFFFFF"), "backColor": color(INK), "fontSize": lit(size),
                                              "wordWrap": lit(True)}}],
            "values": [{"properties": {"fontSize": lit(size), "backColorPrimary": color("#FFFFFF"),
                                       "backColorSecondary": color("#F8F6FC")}}] + [fx_valores(c, m) for c, m in fx],
            "grid": [{"properties": {"gridHorizontalColor": color(LINEA), "rowPadding": lit(3)}}],
            "total": [{"properties": {"totals": lit(False)}}]}
    return pg.add("tableEx", x, y, w, h, query={"Values": [proj(c, n) for c, n in campos]}, objects=objs, titulo=titulo, sort=sort)


def barras(pg, x, y, w, h, cat, val, titulo, fx=None, tipo="clusteredBarChart", sort=None, etiquetas=True, nombre_val=None,
           ejes=True, size_et=9, rango=None):
    va = {"show": lit(ejes), "gridlineShow": lit(False), "showAxisTitle": lit(False)}
    if rango:
        va.update({"start": lit(rango[0]), "end": lit(rango[1])})
    objs = {"labels": [{"properties": {"show": lit(etiquetas), "fontSize": lit(size_et), "color": color(INK)}}],
            "valueAxis": [{"properties": va}],
            "categoryAxis": [{"properties": {"fontSize": lit(9), "labelColor": color(INK), "showAxisTitle": lit(False)}}],
            "legend": [{"properties": {"show": lit(False)}}]}
    if fx:
        objs["dataPoint"] = [{"properties": {"fill": color_fx(fx)}, "selector": TODOS}]
    return pg.add(tipo, x, y, w, h, query={"Category": [proj(cat)], "Y": [proj(val, nombre_val)]}, objects=objs,
                  titulo=titulo, sort=sort or [(val, "Descending")])


def tema() -> dict:
    caja = {"border": [{"show": True, "color": {"solid": {"color": LINEA}}, "radius": 12}],
            "dropShadow": [{"show": True, "color": {"solid": {"color": "#5B3F99"}}, "transparency": 88, "position": "Outer",
                            "preset": "Custom", "shadowSpread": 0, "shadowBlur": 10, "angle": 90, "shadowDistance": 3}],
            "background": [{"show": True, "color": {"solid": {"color": "#FFFFFF"}}, "transparency": 0}],
            "title": [{"fontColor": {"solid": {"color": INK}}, "fontSize": 11, "fontFamily": "Segoe UI Semibold"}],
            "padding": [{"top": 8, "bottom": 8, "left": 10, "right": 10}],
            "visualHeader": [{"foreground": {"solid": {"color": MUTED}}, "transparency": 0}]}
    return {"name": "ATLAS España",
            "dataColors": [ROJO, AZUL, VIO, ORO, "#7A5FB5", "#2E9C8F", "#9A93AD", "#E06C3C"],
            "foreground": INK, "foregroundNeutralSecondary": MUTED, "foregroundNeutralTertiary": "#9A93AD",
            "background": "#FFFFFF", "backgroundLight": BG, "backgroundNeutral": LINEA, "tableAccent": VIO,
            "good": "#2E9C8F", "neutral": ORO, "bad": ROJO, "maximum": ROJO, "center": "#F4F1F9", "minimum": AZUL,
            "hyperlink": VIO, "visitedHyperlink": VIO,
            "textClasses": {"callout": {"fontSize": 26, "fontFace": "Segoe UI Semibold", "color": INK},
                            "title": {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": INK},
                            "header": {"fontSize": 11, "fontFace": "Segoe UI Semibold", "color": INK},
                            "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": INK}},
            "visualStyles": {
                "*": {"*": caja},
                "page": {"*": {"background": [{"color": {"solid": {"color": BG}}, "transparency": 0}],
                               "outspace": [{"color": {"solid": {"color": "#E9E4F2"}}}]}},
                "textbox": {"*": {"border": [{"show": False}], "dropShadow": [{"show": False}],
                                  "background": [{"show": False}], "padding": [{"top": 4, "bottom": 4, "left": 6, "right": 6}]}},
                "actionButton": {"*": {"border": [{"show": False}], "dropShadow": [{"show": False}], "background": [{"show": False}],
                                       "padding": [{"top": 0, "bottom": 0, "left": 0, "right": 0}]}},
                "image": {"*": {"padding": [{"top": 4, "bottom": 4, "left": 4, "right": 4}]}},
                "slicer": {"*": {"padding": [{"top": 4, "bottom": 4, "left": 8, "right": 8}]}}}}


# ===========================================================================
# escribir el proyecto
# ===========================================================================

def escribir(archivos: dict, base: Path):
    for rel, cont in archivos.items():
        p = base / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        txt = cont if isinstance(cont, str) else json.dumps(cont, ensure_ascii=False, indent=2)
        p.write_text(txt, encoding="utf-8", newline="\n" if rel.endswith(".tmdl") else None)

