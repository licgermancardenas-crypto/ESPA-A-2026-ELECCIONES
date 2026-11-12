"""Mapas estáticos en alta resolución (PNG 300 ppp) para el Excel, el Power BI y las piezas de redes.

- Nacionales (pronóstico 2026): favorito, probabilidad, competitividad, calidad, cambio frente a 2023 y voto
  por candidatura principal. Canarias se dibuja en un recuadro desplazado (convención cartográfica).
- Históricos: candidatura más votada por provincia en las generales 2015–2023 (Ministerio del Interior).
- Por provincia: candidatura más votada en cada municipio en 2023 + pronóstico 2026 de la circunscripción.
"""
from __future__ import annotations

import json

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.patches import Patch  # noqa: E402
from shapely.affinity import translate  # noqa: E402

from ..paths import ROOT  # noqa: E402
from . import datos  # noqa: E402
from .exportar import COLORES, NOMBRES, WEB_DATA  # noqa: E402

OUT = ROOT / "reports" / "mapas_29n"
BG, INK, MUTED, LINE = "#0a0024", "#f2ebfa", "#a08fc2", "#0a0024"
CLASE_COLOR = {"Muy competitiva": "#ff6b9a", "Competitiva": "#f2b84b", "Moderadamente competitiva": "#a21eff",
               "Poco competitiva": "#4f8dff", "Dominio claro": "#32a155"}
RAMP = ["#1d1640", "#33236e", "#4f35a3", "#7458d3", "#a08cf0", "#d6ccff"]
# familias oficiales -> color (históricos)
COLOR_FAM = {"PP": COLORES["PP"], "PSOE": COLORES["PSOE"], "Vox": COLORES["VOX"], "Sumar": "#e51c55",
             "Podemos y confluencias": COLORES["PODEMOS"], "Ciudadanos": "#eb6109", "ERC": COLORES["ERC"],
             "Convergència / Junts": COLORES["JUNTS"], "EH Bildu": COLORES["BILDU"], "PNV": COLORES["PNV"],
             "BNG": COLORES["BNG"], "Coalición Canaria": COLORES["CCA"], "UPN": COLORES["UPN_PP"],
             "NA+ (coalición UPN-PP-Cs)": COLORES["UPN_PP"], "Teruel Existe": "#2a9d8f", "Soria ¡Ya!": "#2a9d8f",
             "Otros": COLORES["OTROS"], "IU": "#b5193e", "Más País": "#0fdea8", "Compromís": COLORES["COMPROMIS"],
             "UPyD": "#e4007c", "CUP": "#ffed00", "PRC": "#c2ce0c"}
DESPL = (5.8, 7.2)   # traslado del recuadro de Canarias


def _provincias() -> gpd.GeoDataFrame:
    g = gpd.read_file(WEB_DATA / "geo" / "provincias.geojson")
    can = g.id.isin(["35", "38"])
    g.loc[can, "geometry"] = g.loc[can, "geometry"].apply(lambda x: translate(x, *DESPL))
    return g


def _fig(titulo: str, sub: str, figsize=(12, 9.6)):
    fig, ax = plt.subplots(figsize=figsize, facecolor=BG)
    ax.set_facecolor(BG)
    ax.set_axis_off()
    fig.text(0.04, 0.955, titulo, color=INK, fontsize=21, fontweight="bold", family="Arial")
    fig.text(0.04, 0.925, sub, color=MUTED, fontsize=11.5, family="Arial")
    fig.text(0.04, 0.025, "ATLAS Analytics · Pronóstico generales 29-N-2026 · Fuentes: BOE, Ministerio del Interior, INE, "
                          "encuestas publicadas (vía Wikipedia, pendiente de verificación)", color=MUTED, fontsize=8.5)
    return fig, ax


def _recuadro(ax):
    x0, y0 = -18.3 + DESPL[0], 27.5 + DESPL[1]
    ax.plot([x0 - .2, x0 + 5.3, x0 + 5.3], [y0 + 2.3, y0 + 2.3, y0 - .3], color=MUTED, lw=.8, alpha=.6)


def _guardar(fig, nombre):
    OUT.mkdir(parents=True, exist_ok=True)
    p = OUT / nombre
    fig.savefig(p, dpi=300, facecolor=BG)
    plt.close(fig)
    return p


def _leyenda(ax, items, loc="lower right"):
    h = [Patch(facecolor=c, edgecolor="none", label=t) for t, c in items]
    lg = ax.legend(handles=h, loc=loc, frameon=False, fontsize=10, labelcolor=INK)
    return lg


def _rampa(v, cortes):
    for i, c in enumerate(cortes):
        if v < c:
            return RAMP[i]
    return RAMP[-1]


def nacionales(C: list[dict]) -> list:
    g = _provincias()
    ccaa = gpd.read_file(WEB_DATA / "geo" / "ccaa.geojson")
    ccaa["geometry"] = ccaa.apply(lambda r: translate(r.geometry, *DESPL) if r.id.endswith("-05") else r.geometry, axis=1)
    idx = {c["provincia_id"]: c for c in C}
    out = []

    def pinta(nombre, titulo, sub, color_fn, items):
        fig, ax = _fig(titulo, sub)
        cols = g.id.map(lambda i: color_fn(idx[i]) if i in idx else "#2a2148")
        g.plot(ax=ax, color=cols, edgecolor=LINE, linewidth=.6)
        ccaa.boundary.plot(ax=ax, color="#e9b6ff", linewidth=.9, alpha=.55)
        _recuadro(ax)
        _leyenda(ax, items)
        out.append(_guardar(fig, nombre))

    cuenta = pd.Series([c["favorito"] for c in C]).value_counts()
    pinta("nacional_01_favorito.png", "Favorito por circunscripción", "Candidatura con más probabilidad de ser la más votada · 10.000 simulaciones",
          lambda c: COLORES[c["favorito"]], [(f"{NOMBRES[b]} ({n})", COLORES[b]) for b, n in cuenta.items()])
    cortes = [0.4, 0.5, 0.6, 0.75, 0.9]
    pinta("nacional_02_probabilidad.png", "Probabilidad del favorito", "Probabilidad de que el favorito sea la candidatura más votada",
          lambda c: _rampa(c["p_victoria_favorito"], cortes), list(zip(["<40 %", "40–50 %", "50–60 %", "60–75 %", "75–90 %", "≥90 %"], RAMP)))
    comp = pd.Series([c["competitividad"] for c in C]).value_counts()
    pinta("nacional_03_competitividad.png", "Competitividad pronosticada", "Según probabilidad del favorito y margen mediano",
          lambda c: CLASE_COLOR[c["competitividad"]], [(f"{k} ({comp.get(k, 0)})", v) for k, v in CLASE_COLOR.items()])
    pinta("nacional_04_calidad.png", "Calidad del dato", "Puntuación 0–100 (nómina, encuestas, continuidad legal, encuestas provinciales)",
          lambda c: {"Alta": "#32a155", "Media": "#f2b84b", "Baja": "#ff6b9a"}[c["calidad_clase"]],
          [("Alta", "#32a155"), ("Media", "#f2b84b"), ("Baja", "#ff6b9a")])
    eq = {"PP": "PP", "PSOE": "PSOE", "Vox": "VOX", "ERC": "ERC", "Convergència / Junts": "JUNTS", "EH Bildu": "BILDU", "PNV": "PNV", "BNG": "BNG"}
    mismo = lambda c: eq.get(c["ganador_2023"]) == c["favorito"] or (c["favorito"] == "UPN_PP" and c["ganador_2023"] == "PP")  # noqa: E731
    n_c = sum(not mismo(c) for c in C)
    pinta("nacional_05_cambio.png", f"Cambio frente a 2023 · {n_c} circunscripciones", "Color: favorito 2026 donde cambia la candidatura más votada; gris: sin cambio",
          lambda c: "#33295a" if mismo(c) else COLORES[c["favorito"]], [("Sin cambio", "#33295a")] +
          [(NOMBRES[b], COLORES[b]) for b in sorted({c["favorito"] for c in C if not mismo(c)})])
    cortes_v = [0.05, 0.1, 0.2, 0.3, 0.4]
    for i, b in enumerate(["PP", "PSOE", "VOX", "FA"], start=6):
        def fn(c, b=b):
            x = next((k for k in c["candidaturas"] if k["bloque"] == b), None)
            return _rampa(x["media"], cortes_v) if x else "#2a2148"
        pinta(f"nacional_{i:02d}_voto_{b.lower()}.png", f"Voto pronosticado · {NOMBRES[b]}", "Media de las simulaciones por circunscripción",
              fn, list(zip(["<5 %", "5–10 %", "10–20 %", "20–30 %", "30–40 %", "≥40 %"], RAMP)) + [("No concurre", "#2a2148")])
    return out


def historicos() -> list:
    g = _provincias()
    out = []
    for e, nom in [("02-201512", "2015"), ("02-201606", "2016"), ("02-201904", "abril 2019"), ("02-201911", "noviembre 2019"), ("02-202307", "2023")]:
        r = datos.resultados(e)
        gan = r.loc[r.groupby("provincia_id").votos.idxmax()].set_index("provincia_id").familia
        esc = r.groupby("familia").escanos.sum().sort_values(ascending=False)
        fig, ax = _fig(f"Generales {nom} · candidatura más votada", "Resultado oficial por circunscripción (Ministerio del Interior)")
        g.plot(ax=ax, color=g.id.map(lambda i: COLOR_FAM.get(gan.get(i), "#8a7fa6")), edgecolor=LINE, linewidth=.6)
        _recuadro(ax)
        cnt = gan.value_counts()
        _leyenda(ax, [(f"{f} · {cnt[f]} circ. · {int(esc.get(f, 0))} esc.", COLOR_FAM.get(f, "#8a7fa6")) for f in cnt.index])
        out.append(_guardar(fig, f"historico_{e[3:]}.png"))
    return out


def provinciales(C: list[dict]) -> list:
    mun = gpd.read_file(ROOT / "web" / "data" / "geo" / "municipios.geojson")
    mun["prov"] = mun.id.str[6:8]
    import duckdb
    from ..paths import WAREHOUSE
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    m = con.sql("select geo_id, familia, votos from gold.results_by_family where election_id='02-202307' and geo_level='municipio'").df()
    con.close()
    gan = m.loc[m.groupby("geo_id").votos.idxmax()].set_index("geo_id").familia
    out = []
    for c in C:
        p = c["provincia_id"]
        gp = mun[mun.prov == p]
        if gp.empty:
            continue
        fig, ax = _fig(f"{c['provincia']} · {c['escanos']} escaños",
                       f"Favorito 2026: {NOMBRES[c['favorito']]} ({c['p_victoria_favorito']:.0%}) · {c['competitividad']} · "
                       f"Municipios: más votada en 2023", figsize=(12, 10))
        gp.plot(ax=ax, color=gp.id.map(lambda i: COLOR_FAM.get(gan.get(i), "#8a7fa6")), edgecolor=LINE, linewidth=.25)
        cnt = gp.id.map(gan).value_counts()
        items = [(f"{f} · {n} municipios", COLOR_FAM.get(f, "#8a7fa6")) for f, n in cnt.head(6).items()]
        K = sorted([k for k in c["candidaturas"] if k["bloque"] != "OTROS"], key=lambda k: -k["media"])[:6]
        txt = "\n".join(f"{NOMBRES[k['bloque']][:28]:<28} {k['media']*100:5.1f} %  {k['escanos_media']:4.1f} esc." for k in K)
        fig.text(0.70, 0.86, "Pronóstico 2026", color=INK, fontsize=12, fontweight="bold")
        fig.text(0.70, 0.70, txt, color=INK, fontsize=9, family="Consolas", va="bottom")
        _leyenda(ax, items, loc="lower left")
        out.append(_guardar(fig, f"provincia_{p}.png"))
    return out


def ejecutar(provincias: bool = True) -> dict:
    C = json.loads((WEB_DATA / "contiendas.json").read_text(encoding="utf-8"))
    res = {"nacionales": nacionales(C), "historicos": historicos()}
    if provincias:
        res["provinciales"] = provinciales(C)
    return res
