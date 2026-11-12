"""Excel ejecutivo del pronóstico 29-N: tablas con filtros + mapas nacionales, históricos y provinciales."""
from __future__ import annotations

import json

import pandas as pd

from ..paths import ROOT
from . import mapas
from .exportar import NOMBRES, WEB_DATA

SALIDA = ROOT / "reports" / "excel" / "ATLAS_Espana_29N.xlsx"


def ejecutar() -> str:
    R = json.loads((WEB_DATA / "resumen.json").read_text(encoding="utf-8"))
    C = json.loads((WEB_DATA / "contiendas.json").read_text(encoding="utf-8"))
    B = json.loads((WEB_DATA / "backtest.json").read_text(encoding="utf-8"))
    E = json.loads((WEB_DATA / "encuestas.json").read_text(encoding="utf-8"))
    Q = json.loads((WEB_DATA / "calidad.json").read_text(encoding="utf-8"))
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    wb_w = pd.ExcelWriter(SALIDA, engine="xlsxwriter")
    wb = wb_w.book
    H = wb.add_format({"bold": True, "font_color": "#FFFFFF", "bg_color": "#3D0880", "border": 0, "text_wrap": True, "valign": "vcenter"})
    T = wb.add_format({"bold": True, "font_size": 18, "font_color": "#3D0880"})
    S = wb.add_format({"font_color": "#6E5C93", "italic": True})
    PCT = wb.add_format({"num_format": "0.0%"})
    NUM1 = wb.add_format({"num_format": "0.0"})

    def hoja(nombre, df, titulo, nota, formatos=None):
        df.to_excel(wb_w, sheet_name=nombre, startrow=3, index=False)
        ws = wb_w.sheets[nombre]
        ws.write(0, 0, titulo, T)
        ws.write(1, 0, nota, S)
        for j, c in enumerate(df.columns):
            ws.write(3, j, c, H)
            w = max(10, min(45, int(df[c].astype(str).str.len().quantile(.9)) + 2 if len(df) else 12, ))
            fmt = (formatos or {}).get(c)
            ws.set_column(j, j, max(w, len(c) * 0.9), fmt)
        ws.autofilter(3, 0, 3 + len(df), len(df.columns) - 1)
        ws.freeze_panes(4, 1)
        return ws

    # Resumen
    ws = wb.add_worksheet("Resumen")
    ws.write(0, 0, "ATLAS España · Pronóstico elecciones generales 29-N-2026 (Congreso)", T)
    ws.write(1, 0, f"Encuestas hasta {R['corte']} · {R['n_encuestas']} encuestas · modelo {R['modelo']} · "
                   f"{R['n_sims']:,} simulaciones · generado {R['generado']}".replace(",", "."), S)
    kpis = [("Prob. PP primero en escaños", R["p_pp_primero"]), ("Prob. PSOE primero en escaños", R["p_psoe_primero"]),
            ("Prob. mayoría PP + Vox (≥176)", R["p_mayoria_pp_vox"]), ("Prob. mayoría absoluta PP", R["p_mayoria_absoluta_pp"]),
            ("Circunscripciones muy competitivas", R["muy_competitivas"])]
    for i, (k, v) in enumerate(kpis):
        ws.write(3 + i, 0, k)
        ws.write(3 + i, 1, v, PCT if isinstance(v, float) else None)
    ws.write(10, 0, "Escaños por candidatura", H)
    for j, h in enumerate(["Media", "P10", "P50", "P90"]):
        ws.write(10, 1 + j, h, H)
    for i, x in enumerate(R["escanos"]):
        ws.write(11 + i, 0, x["nombre"])
        ws.write(11 + i, 1, x["media"], NUM1)
        ws.write(11 + i, 2, x["p10"]); ws.write(11 + i, 3, x["p50"]); ws.write(11 + i, 4, x["p90"])
    ws.set_column(0, 0, 44)
    ch = wb.add_chart({"type": "bar"})
    n = len(R["escanos"])
    ch.add_series({"name": "Escaños esperados", "categories": ["Resumen", 11, 0, 10 + n, 0], "values": ["Resumen", 11, 1, 10 + n, 1],
                   "fill": {"color": "#A21EFF"}, "data_labels": {"value": True, "num_format": "0"}})
    ch.set_title({"name": "Escaños esperados (media de 10.000 simulaciones)"})
    ch.set_y_axis({"reverse": True}); ch.set_legend({"none": True}); ch.set_size({"width": 620, "height": 520})
    ws.insert_chart("G3", ch)

    # Contiendas
    rows = [{"Provincia": c["provincia"], "Comunidad": c["ccaa"], "Escaños": c["escanos"], "Favorito": NOMBRES[c["favorito"]],
             "Siglas": c["favorito_siglas"], "Prob. victoria": c["p_victoria_favorito"], "Voto favorito": c["voto_favorito"],
             "Voto P10": c["voto_favorito_p10"], "Voto P90": c["voto_favorito_p90"], "Margen P50": c["margen_p50"],
             "Margen P10": c["margen_p10"], "Margen P90": c["margen_p90"], "Escaños favorito": c["escanos_fav"],
             "Competitividad": c["competitividad"], "Más votada 2023": c["ganador_2023"], "Voto 2023": c["voto_ganador_2023"],
             "Calidad": c["calidad"], "Clase calidad": c["calidad_clase"]} for c in C]
    df = pd.DataFrame(rows).sort_values("Prob. victoria")
    p = {k: PCT for k in ["Prob. victoria", "Voto favorito", "Voto P10", "Voto P90", "Margen P50", "Margen P10", "Margen P90", "Voto 2023"]}
    ws = hoja("Contiendas", df, "52 circunscripciones del Congreso", "Ordenado de la más ajustada a la más segura. Filtros en la cabecera.", {**p, "Escaños favorito": NUM1})
    ws.conditional_format(4, 5, 3 + len(df), 5, {"type": "3_color_scale", "min_color": "#FF6B9A", "mid_color": "#F2B84B", "max_color": "#32A155"})

    # Candidaturas
    rows = [{"Provincia": c["provincia"], "Comunidad": c["ccaa"], "Bloque": NOMBRES[k["bloque"]], "Siglas BOE": k["siglas"],
             "Cabeza de lista": k["cabeza_lista"], "Implantación": k["tipo_previo"], "Voto medio": k["media"], "Voto P10": k["p10"],
             "Voto P90": k["p90"], "Prob. más votada": k["p_victoria"], "Escaños medios": k["escanos_media"],
             "Escaños P10": k["escanos_p10"], "Escaños P90": k["escanos_p90"], "Prob. ≥1 escaño": k["p_al_menos_1"]}
            for c in C for k in c["candidaturas"]]
    hoja("Candidaturas", pd.DataFrame(rows), "Voto y escaños por candidatura y circunscripción", "Candidaturas proclamadas (BOE-A-2026-23103). OTROS agrega el resto.",
         {"Voto medio": PCT, "Voto P10": PCT, "Voto P90": PCT, "Prob. más votada": PCT, "Escaños medios": NUM1, "Prob. ≥1 escaño": PCT})

    # Escenarios
    rows = []
    for c in C:
        for e in c["escenarios"]:
            for b, v in e["escanos"].items():
                if b != "OTROS":
                    rows.append({"Provincia": c["provincia"], "Escenario": e["escenario"], "Más votada": NOMBRES[e["ganador"]],
                                 "Bloque": NOMBRES[b], "Voto": e["voto"][b], "Escaños": v})
    hoja("Escenarios", pd.DataFrame(rows), "Escenarios nacionales por circunscripción",
         "Grupos de simulaciones por margen PP–PSOE en escaños: 20 % inferior, todas, 20 % superior.", {"Voto": PCT, "Escaños": NUM1})

    # Encuestas, validación y calidad
    eu = pd.DataFrame(E["usadas"])[[c for c in ["instituto", "medio", "campo_inicio", "campo_fin", "muestra", "PP", "PSOE", "VOX", "FA", "FV",
                                                 "PODEMOS", "SALF", "ERC", "JUNTS", "fuente_original"] if c in pd.DataFrame(E["usadas"]).columns]]
    hoja("Encuestas", eu, "Encuestas usadas en la media", "Fuente secundaria (Wikipedia) pendiente de verificación; enlace a la publicación original.")
    hoja("Validación", pd.DataFrame(B["tabla"]), "Backtesting a ciegas (origen móvil)", f"Modelo elegido: {B['modelo_seleccionado']} · σ nac {B['sigma_nac']} · σ prov {B['sigma_prov']}")
    hoja("Calidad", pd.DataFrame(Q["fuentes"]), "Data Quality Center · fuentes", " · ".join(Q["limitaciones"][:2]))

    # Mapas
    m = mapas.ejecutar(provincias=True)

    def galeria(nombre, titulo, archivos, cols=2, escala=0.17):
        ws = wb.add_worksheet(nombre)
        ws.write(0, 0, titulo, T)
        ws.write(1, 0, "Imágenes a 300 ppp (archivo original en reports/mapas_29n). Escaladas para la vista; copiar o abrir el PNG para la resolución completa.", S)
        alto = int(3000 * escala / 20) + 2
        for i, f in enumerate(archivos):
            r, c = divmod(i, cols)
            ws.insert_image(3 + r * alto, c * 11, str(f), {"x_scale": escala, "y_scale": escala, "object_position": 3})
    galeria("Mapas nacionales", "Mapas nacionales · pronóstico 2026", m["nacionales"])
    galeria("Mapas históricos", "Generales 2015–2023 · candidatura más votada por circunscripción", m["historicos"])
    galeria("Mapas provinciales", "Mapas por provincia · municipios 2023 + pronóstico 2026", m["provinciales"], cols=3, escala=0.12)
    wb_w.close()
    return str(SALIDA)
