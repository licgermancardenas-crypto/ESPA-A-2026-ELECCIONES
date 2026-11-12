"""CSV del tablero de Power BI 29-N (reports/powerbi_29n/datos/).

Dos lienzos: nacional (52 provincias, Canarias en recuadro) y provincial (municipios de cada provincia
ajustados a un lienzo propio de 1000 × 800, con la candidatura más votada en 2023).
"""
from __future__ import annotations

import json

import duckdb
import geopandas as gpd
import pandas as pd

from ...paths import ROOT, WAREHOUSE
from .. import datos as dpr
from ..exportar import COLORES, NOMBRES, WEB_DATA
from ..mapas import CLASE_COLOR, COLOR_FAM, RAMP
from . import geo

DIR = ROOT / "reports" / "powerbi_29n" / "datos"
ND, GRIS = "#D9D3E6", "#E4DFEE"
ALTO_NAC = 900
PROV_W, PROV_H = 1000, 800
# Rampa clara para el tema claro del Power BI
RAMPA = ["#EEE8F8", "#D3C4F0", "#AE95E3", "#8467BD", "#5B3F99", "#33215F"]
QCOL = {"Alta": "#32A155", "Media": "#E0A526", "Baja": "#C8102E"}
EQ23 = {"PP": "PP", "PSOE": "PSOE", "Vox": "VOX", "ERC": "ERC", "Convergència / Junts": "JUNTS", "EH Bildu": "BILDU",
        "PNV": "PNV", "BNG": "BNG", "Coalición Canaria": "CCA"}
METRICAS = [  # id, nombre, columna, descripción
    (1, "Favorito 2026", "c_fav", "Candidatura con más probabilidad de ser la más votada"),
    (2, "Probabilidad del favorito", "c_prob", "Probabilidad de que el favorito sea la más votada"),
    (3, "Competitividad 2026", "c_comp", "Clase según probabilidad y margen"),
    (4, "Cambio frente a 2023", "c_cambio", "Color del favorito donde cambia la más votada"),
    (5, "Más votada 2023", "c_g2023", "Resultado oficial 2023"),
    (6, "Calidad del dato", "c_cal", "Puntuación 0-100"),
    (7, "Voto PP", "c_v_pp", "Voto pronosticado del PP"),
    (8, "Voto PSOE", "c_v_psoe", "Voto pronosticado del PSOE"),
    (9, "Voto Vox", "c_v_vox", "Voto pronosticado de Vox"),
    (10, "Voto Frente Amplio", "c_v_fa", "Voto pronosticado de Frente Amplio"),
]


def _rampa(v, cortes):
    if v is None or pd.isna(v):
        return ND
    for i, c in enumerate(cortes):
        if v < c:
            return RAMPA[i]
    return RAMPA[-1]


def _csv(df, nombre):
    df.to_csv(DIR / nombre, index=False, encoding="utf-8")


def _limpia(s: str) -> str:
    return str(s).replace("'", "").replace("&", "y").replace('"', "")


def exportar() -> dict:
    DIR.mkdir(parents=True, exist_ok=True)
    C = json.loads((WEB_DATA / "contiendas.json").read_text(encoding="utf-8"))
    R = json.loads((WEB_DATA / "resumen.json").read_text(encoding="utf-8"))
    B = json.loads((WEB_DATA / "backtest.json").read_text(encoding="utf-8"))
    E = json.loads((WEB_DATA / "encuestas.json").read_text(encoding="utf-8"))
    Q = json.loads((WEB_DATA / "calidad.json").read_text(encoding="utf-8"))

    # ---- geometría nacional
    g = gpd.read_file(WEB_DATA / "geo" / "provincias.geojson")
    g["geometry"] = [geo.proyectar(x, i in ("35", "38")) for x, i in zip(g.geometry, g.id)]
    b = g.total_bounds
    lz = geo.Lienzo(b, ancho=10_000, x0=20, y0=20, alto=ALTO_NAC - 40)
    ancho = lz.ancho + 40
    can = g[g.id.isin(["35", "38"])].total_bounds
    cx0, cy1 = lz.xy(pd.DataFrame([[can[0], can[3]]]).to_numpy())[0]
    cx1, cy0 = lz.xy(pd.DataFrame([[can[2], can[1]]]).to_numpy())[0]
    caja_can = [round(cx0 - 14), round(cy1 - 30), round(cx1 - cx0 + 28), round(cy0 - cy1 + 44)]
    geo_nac = {i: (geo.trazo(x, lz, tol_px=0.35), *geo.centroide_px(x, lz)) for i, x in zip(g.id, g.geometry)}

    # ---- históricos
    hist = {}
    for e in ["02-201512", "02-201606", "02-201904", "02-201911", "02-202307"]:
        r = dpr.resultados(e)
        hist[e] = r.loc[r.groupby("provincia_id").votos.idxmax()].set_index("provincia_id").familia

    # ---- provincias
    filas = []
    for c in C:
        p = c["provincia_id"]
        g23 = c["ganador_2023"]
        mismo = EQ23.get(g23) == c["favorito"] or (c["favorito"] == "UPN_PP" and g23 == "PP")
        vot = {k["bloque"]: k["media"] for k in c["candidaturas"]}
        path, x, y = geo_nac[p]
        fila = {
            "provincia_id": p, "provincia": c["provincia"], "ccaa": c["ccaa"], "escanos": c["escanos"],
            "favorito": NOMBRES[c["favorito"]], "favorito_bloque": c["favorito"], "favorito_siglas": c["favorito_siglas"],
            "p_victoria": round(c["p_victoria_favorito"], 4), "voto_favorito": round(c["voto_favorito"], 4),
            "voto_p10": round(c["voto_favorito_p10"], 4), "voto_p90": round(c["voto_favorito_p90"], 4),
            "margen_p50": round(c["margen_p50"], 4), "margen_p10": round(c["margen_p10"], 4), "margen_p90": round(c["margen_p90"], 4),
            "escanos_favorito": round(c["escanos_fav"], 2), "competitividad": c["competitividad"], "calidad": c["calidad"],
            "calidad_clase": c["calidad_clase"], "ganador_2023": g23, "voto_ganador_2023": round(c["voto_ganador_2023"], 4),
            "cambia_2023": "Sí" if not mismo else "No",
            "c_fav": COLORES[c["favorito"]], "c_prob": _rampa(c["p_victoria_favorito"], [0.4, 0.5, 0.6, 0.75, 0.9]),
            "c_comp": CLASE_COLOR[c["competitividad"]], "c_cambio": GRIS if mismo else COLORES[c["favorito"]],
            "c_g2023": COLOR_FAM.get(g23, "#8A7FA6"), "c_cal": QCOL[c["calidad_clase"]],
            "c_v_pp": _rampa(vot.get("PP", vot.get("UPN_PP")), [0.05, 0.1, 0.2, 0.3, 0.4]) if ("PP" in vot or "UPN_PP" in vot) else ND,
            "c_v_psoe": _rampa(vot.get("PSOE"), [0.05, 0.1, 0.2, 0.3, 0.4]) if "PSOE" in vot else ND,
            "c_v_vox": _rampa(vot.get("VOX"), [0.05, 0.1, 0.2, 0.3, 0.4]) if "VOX" in vot else ND,
            "c_v_fa": _rampa(vot.get("FA"), [0.05, 0.1, 0.2, 0.3, 0.4]) if "FA" in vot else ND,
            "path": path, "cx": x, "cy": y, "etiqueta": _limpia(c["provincia"].split("/")[0]),
        }
        for e, s in hist.items():
            fila[f"c_{e[3:]}"] = COLOR_FAM.get(s.get(p), "#8A7FA6")
            fila[f"g_{e[3:]}"] = s.get(p)
        filas.append(fila)
    prov = pd.DataFrame(filas)

    # ---- municipios (lienzo provincial)
    mun = gpd.read_file(ROOT / "web" / "data" / "geo" / "municipios.geojson")
    mun["prov"] = mun.id.str[6:8]
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    m = con.sql("select geo_id, familia, votos from gold.results_by_family where election_id='02-202307' and geo_level='municipio'").df()
    nm = con.sql("select geo_id, geo_name from gold.dim_geography where geo_type='municipio'").df().set_index("geo_id").geo_name
    con.close()
    tot = m.groupby("geo_id").votos.sum()
    top = m.loc[m.groupby("geo_id").votos.idxmax()].set_index("geo_id")
    filas, dims = [], {}
    for p, gp in mun.groupby("prov"):
        gp = gp.copy()
        gp["geometry"] = [geo.proyectar(x, False) for x in gp.geometry]
        lzp = geo.Lienzo(gp.total_bounds, ancho=PROV_W - 40, x0=20, y0=20, alto=PROV_H - 40)
        dims[p] = (lzp.ancho + 40, lzp.alto + 40, geo.trazo(gp.union_all(), lzp, tol_px=0.4))
        for i, x in zip(gp.id, gp.geometry):
            fam = top.familia.get(i)
            filas.append({"municipio_id": i, "provincia_id": p, "municipio": _limpia(nm.get(i, i)),
                          "ganador_2023": fam, "voto_ganador_2023": round(float(top.votos.get(i, 0) / tot.get(i, 1)), 4) if fam else None,
                          "color": COLOR_FAM.get(fam, "#8A7FA6"), "path_prov": geo.trazo(x, lzp, tol_px=0.5, area_min=1.5)})
    mu = pd.DataFrame(filas)
    prov["ancho"] = prov.provincia_id.map(lambda p: dims[p][0])
    prov["alto"] = prov.provincia_id.map(lambda p: dims[p][1])
    prov["borde_prov"] = prov.provincia_id.map(lambda p: dims[p][2])
    _csv(prov, "provincias.csv")
    _csv(mu, "municipios.csv")

    # ---- candidaturas y escenarios
    cand = [{"provincia_id": c["provincia_id"], "bloque": k["bloque"], "candidatura": NOMBRES[k["bloque"]],
             "siglas": k["siglas"], "cabeza_lista": _limpia(k["cabeza_lista"] or ""), "implantacion": k["tipo_previo"],
             "voto_medio": k["media"], "voto_p10": k["p10"], "voto_p90": k["p90"], "p_victoria": k["p_victoria"],
             "escanos_media": k["escanos_media"], "escanos_p10": k["escanos_p10"], "escanos_p90": k["escanos_p90"],
             "p_escano": k["p_al_menos_1"], "color": COLORES[k["bloque"]]} for c in C for k in c["candidaturas"]]
    _csv(pd.DataFrame(cand).round(4), "candidaturas.csv")
    esc = [{"provincia_id": c["provincia_id"], "escenario": e["escenario"].split(" (")[0], "orden": i, "bloque": b,
            "candidatura": NOMBRES[b], "voto": round(e["voto"][b], 4), "escanos": round(v, 2), "color": COLORES[b]}
           for c in C for i, e in enumerate(c["escenarios"]) for b, v in e["escanos"].items() if b != "OTROS"]
    _csv(pd.DataFrame(esc), "escenarios.csv")
    en = pd.DataFrame(R["escanos"]).assign(color=lambda d: d.bloque.map(COLORES))
    _csv(en.round(2), "escanos_nacional.csv")
    dist = pd.DataFrame({"escanos": range(len(R["dist_pp_vox"])), "simulaciones": R["dist_pp_vox"]})
    _csv(dist[dist.simulaciones > 0].assign(mayoria=lambda d: (d.escanos >= 176).map({True: "≥ 176", False: "< 176"})), "dist_pp_vox.csv")

    # ---- encuestas
    serie = pd.DataFrame(E["serie"])
    serie = serie[serie.campo_fin >= "2025-06-01"]
    largo = serie.melt(id_vars=["instituto", "campo_fin"], value_vars=[k for k in ["PP", "PSOE", "VOX", "FA", "SUMAR", "PODEMOS", "SALF"] if k in serie],
                       var_name="partido", value_name="estimacion").dropna()
    largo["estimacion"] = largo.estimacion / 100
    _csv(largo, "encuestas_serie.csv")
    us = pd.DataFrame(E["usadas"])
    cols = [c for c in ["instituto", "medio", "campo_inicio", "campo_fin", "muestra", "PP", "PSOE", "VOX", "FA", "PODEMOS", "SALF", "fuente_original"] if c in us]
    _csv(us[cols].fillna(""), "encuestas_usadas.csv")

    # ---- validación y calidad
    _csv(pd.DataFrame(B["tabla"]), "backtest.csv")
    _csv(pd.DataFrame(B["resumen"]).assign(seleccionado=lambda d: (d.modelo == B["modelo_seleccionado"]).astype(int)), "modelos.csv")
    _csv(pd.DataFrame(B["error_encuestas"]), "error_encuestas.csv")
    _csv(pd.DataFrame(Q["fuentes"]), "fuentes.csv")
    _csv(pd.DataFrame({"orden": range(len(Q["limitaciones"])), "limitacion": Q["limitaciones"]}), "limitaciones.csv")

    # ---- leyendas por métrica
    ley = []
    def add(mid, items):
        for o, (col, et) in enumerate(items):
            ley.append({"metrica_id": mid, "orden": o, "color": col, "etiqueta": et})
    fav = prov.favorito_bloque.value_counts()
    add(1, [(COLORES[b], f"{NOMBRES[b]} ({n})") for b, n in fav.items()])
    add(2, list(zip(RAMPA, ["menos de 40 %", "40-50 %", "50-60 %", "60-75 %", "75-90 %", "90 % o más"])))
    cc = prov.competitividad.value_counts()
    add(3, [(v, f"{k} ({cc.get(k, 0)})") for k, v in CLASE_COLOR.items()])
    ch = prov[prov.cambia_2023 == "Sí"].favorito_bloque.value_counts()
    add(4, [(GRIS, f"Sin cambio ({int((prov.cambia_2023 == 'No').sum())})")] + [(COLORES[b], f"{NOMBRES[b]} ({n})") for b, n in ch.items()])
    g23 = prov.ganador_2023.value_counts()
    add(5, [(COLOR_FAM.get(f, "#8A7FA6"), f"{f} ({n})") for f, n in g23.items()])
    qq = prov.calidad_clase.value_counts()
    add(6, [(v, f"{k} ({qq.get(k, 0)})") for k, v in QCOL.items()])
    for mid in (7, 8, 9, 10):
        add(mid, list(zip(RAMPA, ["menos de 5 %", "5-10 %", "10-20 %", "20-30 %", "30-40 %", "40 % o más"])) + [(ND, "No concurre")])
    _csv(pd.DataFrame(ley), "leyendas.csv")
    _csv(pd.DataFrame([{"id": a, "metrica": b, "columna": c, "descripcion": d} for a, b, c, d in METRICAS]), "metricas.csv")

    P = {"ancho_nac": ancho, "alto_nac": ALTO_NAC, "caja_can": caja_can, "corte": R["corte"], "modelo": R["modelo"],
         "n_encuestas": R["n_encuestas"], "p_pp_primero": R["p_pp_primero"], "p_psoe_primero": R["p_psoe_primero"],
         "p_mayoria": R["p_mayoria_pp_vox"], "muy_competitivas": R["muy_competitivas"],
         "acierto": next(r["acierto_ganador"] for r in B["resumen"] if r["modelo"] == B["modelo_seleccionado"]),
         "mae": next(r["mae_pp"] for r in B["resumen"] if r["modelo"] == B["modelo_seleccionado"]),
         "sigma_nac": B["sigma_nac"], "sigma_prov": B["sigma_prov"], "generado": R["generado"]}
    (DIR / "parametros.json").write_text(json.dumps(P, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"provincias {len(prov)} · municipios {len(mu)} · trazos nac {prov.path.str.len().sum()/1e6:.2f} M · mun {mu.path_prov.str.len().sum()/1e6:.2f} M car.")
    return P
