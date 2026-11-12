"""Textos de LinkedIn listos para pegar (web y Power BI). Cifras calculadas de web29n/data.

Uso: python post.py <carpeta_salida>
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DATA = RAIZ / "web29n" / "data"


def pct(v):
    return f"{v * 100:.0f} %"


def main(salida: Path):
    R = json.loads((DATA / "resumen.json").read_text(encoding="utf-8"))
    B = json.loads((DATA / "backtest.json").read_text(encoding="utf-8"))
    C = json.loads((DATA / "contiendas.json").read_text(encoding="utf-8"))
    e = {x["bloque"]: x for x in R["escanos"]}
    s = next(r for r in B["resumen"] if r["modelo"] == B["modelo_seleccionado"])
    aj = sorted(C, key=lambda c: c["p_victoria_favorito"])[:3]
    ajs = ", ".join(f"{c['provincia']} ({R['cortos'].get(c['favorito'], c['favorito'])} {pct(c['p_victoria_favorito'])})" for c in aj)
    comun = (f"📊 PP {e['PP']['media']:.0f} escaños ({e['PP']['p10']}–{e['PP']['p90']}), PSOE {e['PSOE']['media']:.0f} ({e['PSOE']['p10']}–{e['PSOE']['p90']}), "
             f"Vox {e['VOX']['media']:.0f} ({e['VOX']['p10']}–{e['VOX']['p90']}).\n"
             f"🎯 Probabilidad de que el PP sea primero en escaños: {pct(R['p_pp_primero'])}. Mayoría PP + Vox: {pct(R['p_mayoria_pp_vox'])}.\n"
             f"⚖️ {R['muy_competitivas']} circunscripciones muy competitivas. Las más ajustadas: {ajs}.\n")
    metodo = (f"Cómo está hecho:\n• Candidaturas oficiales del BOE (534 listas) y resultados del Ministerio del Interior.\n"
              f"• Media de {R['n_encuestas']} encuestas publicadas hasta el {R['corte']}, con enlace a cada original.\n"
              f"• Swing proporcional validado a ciegas en cinco generales (2015–2023): acierta la más votada en el {pct(s['acierto_ganador'])} "
              f"de las circunscripciones.\n• 10.000 simulaciones con D'Hondt y barrera del 3 % en cada circunscripción.\n")
    veda = f"Nota: desde el {R['eleccion']['veda_desde']} rige la veda de sondeos (art. 69.7 LOREG); el pronóstico no se actualiza en esos días.\n"
    tags = "#Elecciones2026 #EleccionesGenerales #29N #España #DataScience #CienciaDeDatos #AnalisisElectoral #Politica"
    web = ("¿Quién gana el 29-N? Publicamos el pronóstico de las 52 circunscripciones del Congreso.\n\n" + comun + "\n" + metodo +
           "\nEn la web: mapa con 7 modos, ficha por circunscripción con escenarios, validación del modelo, encuestas y Data Quality Center. "
           "Funciona en el móvil.\n👉 https://atlas-espana-29n.vercel.app\n\n" + veda + "\n" + tags + " #DataViz #OpenData")
    pbi = ("El pronóstico del 29-N, ahora en Power BI.\n\n" + comun + "\n" +
           "9 páginas: panel nacional, mapa con 10 métricas, mapa por provincia con los 8.132 municipios, tabla de contiendas, "
           "ficha con escenarios, evolución 2015–2023, encuestas, validación y metodología.\n"
           "Los mapas se dibujan con medidas DAX que arman SVG: sin visuales personalizados. El proyecto (PBIP) se genera por código.\n\n"
           + metodo + "\n👉 Versión web: https://atlas-espana-29n.vercel.app\n\n" + veda + "\n" + tags + " #PowerBI #DAX #BusinessIntelligence")
    salida.mkdir(parents=True, exist_ok=True)
    (salida / "post_web.md").write_text(web, encoding="utf-8")
    (salida / "post_powerbi.md").write_text(pbi, encoding="utf-8")
    print(web, "\n\n----\n\n", pbi)


if __name__ == "__main__":
    main(Path(sys.argv[1]))
