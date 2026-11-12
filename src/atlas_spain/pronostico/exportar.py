"""Exporta el pronóstico 29-N a web29n/data (JSON estáticos versionados en git: la web se despliega en
Vercel desde GitHub sin pasos locales) y a reports/pronostico_29n/ (tablas para Excel y Power BI)."""
from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ..paths import ROOT
from . import backtest, candidaturas, datos, features
from .datos import OTROS

WEB = ROOT / "web29n"
WEB_DATA = WEB / "data"
REPORTS = ROOT / "reports" / "pronostico_29n"

# Colores de bloque (identidad habitual de cada formación; OTROS en gris violáceo Atlas)
COLORES = {
    "PP": "#1d84ce", "UPN_PP": "#3aa0e6", "PSOE": "#e30613", "VOX": "#5ac035", "FA": "#d6338a",
    "COMPROMIS": "#f28b25", "UPC": "#b23a8f", "PODEMOS": "#7b3f98", "SALF": "#8a6d3b", "ERC": "#f5b400",
    "JUNTS": "#20c0b0", "BILDU": "#9acd32", "BILDU_ERC": "#7fb22c", "PNV": "#2e8b57", "BNG": "#7ec8e3",
    "CCA": "#ffd500", "ADELANTE": "#2fa36b", OTROS: "#8a7fa6",
}
NOMBRES = {
    "PP": "Partido Popular", "UPN_PP": "UPN–PP (Navarra)", "PSOE": "PSOE (incl. PSC, PSdeG, PSIB, PSN)", "VOX": "Vox",
    "FA": "Frente Amplio y confluencias", "COMPROMIS": "Compromís: Front Valencià", "UPC": "Unidad del Pueblo Canario",
    "PODEMOS": "Podemos", "SALF": "Se Acabó La Fiesta", "ERC": "ERC", "JUNTS": "Junts per Catalunya",
    "BILDU": "EH Bildu", "BILDU_ERC": "EH Bildu–ERC (Navarra)", "PNV": "EAJ-PNV", "BNG": "BNG",
    "CCA": "Coalición Canaria", "ADELANTE": "Adelante Andalucía", OTROS: "Otras candidaturas",
}
CORTOS = {"UPN_PP": "UPN-PP", "BILDU": "EH Bildu", "BILDU_ERC": "Bildu-ERC", "COMPROMIS": "Compromís", "ADELANTE": "Adelante",
          "PODEMOS": "Podemos", "JUNTS": "Junts", "OTROS": "Otros", "CCA": "CC", "VOX": "Vox"}


def _conv(x):
    if isinstance(x, np.integer):
        return int(x)
    if isinstance(x, np.floating):
        return None if np.isnan(x) else round(float(x), 5)
    if isinstance(x, (np.ndarray, set, tuple)):
        return list(x)
    if isinstance(x, (pd.Timestamp,)):
        return x.isoformat()
    return str(x)


def _w(nombre: str, obj) -> None:
    p = WEB_DATA / nombre
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, separators=(",", ":"), default=_conv), encoding="utf-8")


def _limpiar(x):
    """NaN -> None recursivo (JSON válido)."""
    if isinstance(x, dict):
        return {k: _limpiar(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_limpiar(v) for v in x]
    if isinstance(x, float) and np.isnan(x):
        return None
    return x


def historico_2023() -> dict:
    """Ganador (más votos) y escaños 2023 por provincia, con familias oficiales."""
    r = datos.resultados("02-202307")
    tot = r.groupby("provincia_id").votos.sum()
    out = {}
    for p, g in r.groupby("provincia_id"):
        g = g.sort_values("votos", ascending=False)
        out[p] = {"ganador": g.familia.iloc[0], "voto_ganador": float(g.votos.iloc[0] / tot[p]),
                  "margen": float((g.votos.iloc[0] - g.votos.iloc[1]) / tot[p]),
                  "familias": [{"f": f, "v": round(float(v / tot[p]), 4), "e": int(e)}
                               for f, v, e in zip(g.familia, g.votos, g.escanos) if v / tot[p] >= 0.005]}
    return out


def ejecutar() -> None:
    cfg = datos.config()
    P = json.loads((backtest.SALIDA / "pronostico.json").read_text(encoding="utf-8"))
    B = json.loads((backtest.SALIDA / "backtest.json").read_text(encoding="utf-8"))
    hist = historico_2023()
    nac = P["nacional"]

    # --- contiendas
    cont = []
    for c in P["contiendas"]:
        h = hist.get(c["provincia_id"], {})
        c2 = {k: v for k, v in c.items() if k not in ("calidad_motivos",)}
        c2["ganador_2023"] = h.get("ganador")
        c2["voto_ganador_2023"] = h.get("voto_ganador")
        c2["margen_2023"] = h.get("margen")
        c2["familias_2023"] = h.get("familias", [])
        c2["calidad_motivos"] = c["calidad_motivos"]
        c2["escanos_fav"] = next(x["escanos_media"] for x in c["candidaturas"] if x["bloque"] == c["favorito"])
        cont.append(c2)
    _w("contiendas.json", _limpiar(cont))

    # --- resumen nacional
    bloques = [b for b in nac["escanos"]]
    escanos = sorted(({"bloque": b, "nombre": NOMBRES.get(b, b), **v} for b, v in nac["escanos"].items()),
                     key=lambda x: -x["media"])
    comp = pd.Series([c["competitividad"] for c in cont]).value_counts().to_dict()
    fav = pd.Series([c["favorito"] for c in cont]).value_counts().to_dict()
    resumen = {
        "generado": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "eleccion": cfg["eleccion_objetivo"], "modelo": P["modelo"], "sigma_nac": P["sigma_nac"],
        "sigma_prov": P["sigma_prov"], "n_sims": P["n_sims"], "corte": nac["corte"], "n_encuestas": nac["n_encuestas"],
        "media_encuestas": nac["media_encuestas"], "escanos": escanos,
        "p_pp_primero": nac["p_pp_primero"], "p_psoe_primero": nac["p_psoe_primero"],
        "p_mayoria_pp_vox": nac["p_mayoria_pp_vox"], "p_mayoria_absoluta_pp": nac["p_mayoria_absoluta_pp"],
        "dist_pp_vox": nac["dist_pp_vox"], "competitividad": comp, "favoritos": fav,
        "contiendas": len(cont), "escanos_total": int(sum(c["escanos"] for c in cont)),
        "calidad": pd.Series([c["calidad_clase"] for c in cont]).value_counts().to_dict(),
        "muy_competitivas": int(sum(c["competitividad"] == "Muy competitiva" for c in cont)),
        "colores": COLORES, "nombres": NOMBRES, "cortos": CORTOS,
    }
    _w("resumen.json", _limpiar(resumen))

    # --- organizaciones (bloques)
    cand = candidaturas.cargar()
    cand = cand[cand.proclamada]
    inv = {s: b for b, d in cfg["bloques"].items() for s in d["siglas"]}
    cand = cand.assign(bloque=cand.siglas.map(inv).fillna(OTROS))
    orgs = []
    for b, d in cfg["bloques"].items():
        provs = sorted(cand.loc[cand.bloque == b, "provincia_id"].unique())
        if not provs:
            continue
        e = nac["escanos"].get(b, {})
        orgs.append({"bloque": b, "nombre": NOMBRES.get(b, b), "siglas": sorted(set(cand.loc[cand.bloque == b, "siglas"])),
                     "provincias": provs, "n_provincias": len(provs), "poll": d.get("poll"),
                     "media_encuesta": nac["media_encuestas"].get(d.get("poll") or "", None),
                     "previo": d["previo"], "nota": d.get("nota"), "escanos": e,
                     "favorito_en": [c["provincia"] for c in cont if c["favorito"] == b]})
    otras = cand[cand.bloque == OTROS].groupby(["siglas", "denominacion"]).provincia_id.apply(list).reset_index()
    _w("organizaciones.json", {"bloques": orgs, "otras": otras.to_dict("records"),
                               "fuente": candidaturas.BOE_ID, "url": candidaturas.BOE_URL})

    # --- validación
    _w("backtest.json", _limpiar(B))

    # --- encuestas: serie 2026 completa + las usadas
    polls = datos.encuestas("2026")
    keep = ["instituto", "medio", "campo_inicio", "campo_fin", "muestra", "seccion_wiki", "fuente_original",
            "verificacion", "PP", "PSOE", "VOX", "FA", "FV", "SUMAR", "PODEMOS", "SALF", "ERC", "JUNTS", "BILDU",
            "PNV", "BNG", "CCA", "ADELANTE"]
    pl = polls[[c for c in keep if c in polls]].copy()
    pl["campo_inicio"] = pl.campo_inicio.astype(str)
    pl["campo_fin"] = pl.campo_fin.astype(str)
    _w("encuestas.json", _limpiar({"serie": pl.to_dict("records"), "usadas": P["encuestas_usadas"],
                                   "fuente": "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Spanish_general_election",
                                   "ventana_dias": cfg["encuestas"]["ventana_dias"],
                                   "vida_media_dias": cfg["encuestas"]["vida_media_dias"]}))

    # --- Data Quality Center
    dqc = {
        "fuentes": [
            {"fuente": "Candidaturas proclamadas al Congreso", "origen": f"{candidaturas.BOE_ID} (BOE núm. 273, 3-nov-2026)",
             "url": candidaturas.BOE_URL, "tipo": "Oficial", "estado": "Verificada",
             "control": "534 proclamadas y 21 no proclamadas (coincide con el total publicado); 350 escaños; SHA-256 registrado"},
            {"fuente": "Resultados oficiales Congreso 2011–2023 y europeas 2014–2024", "origen": "Ministerio del Interior (Infoelectoral)",
             "url": "https://infoelectoral.interior.gob.es", "tipo": "Oficial", "estado": "Verificada",
             "control": "D'Hondt reproduce los escaños oficiales en las 52 circunscripciones (tests del warehouse)"},
            {"fuente": "Encuestas de intención de voto", "origen": "Wikipedia (en) con enlace a cada publicación original",
             "url": "https://en.wikipedia.org/wiki/Opinion_polling_for_the_2026_Spanish_general_election", "tipo": "Secundaria",
             "estado": "Pendiente de verificación", "control": f"{len(polls)} encuestas 2023–2026; {nac['n_encuestas']} en la ventana de cálculo; cada fila conserva la URL original"},
            {"fuente": "Cartografía provincial", "origen": "INE · secciones censales 2024 (disueltas por provincia)",
             "url": "https://www.ine.es", "tipo": "Oficial", "estado": "Verificada", "control": "52 provincias, 0 huérfanas"},
        ],
        "contiendas": [{"provincia_id": c["provincia_id"], "provincia": c["provincia"], "calidad": c["calidad"],
                        "clase": c["calidad_clase"], "motivos": c["calidad_motivos"]} for c in cont],
        "limitaciones": [
            "No hay encuestas provinciales verificadas: el reparto territorial sale de la implantación previa (swing proporcional).",
            "Frente Amplio, Compromís y Unidad del Pueblo Canario no tienen continuidad legal con Sumar 2023: su implantación usa Sumar 2023 como sustituto geográfico y su incertidumbre provincial se multiplica por 1,5.",
            "Podemos y SALF toman su implantación de las europeas de 2024 (misma formación, otra elección).",
            "Adelante Andalucía no tiene implantación previa cargada: reparto uniforme en sus 8 provincias.",
            "OTROS agrega candidaturas distintas y no recibe escaños en la simulación (Soria ¡Ya!, Teruel Existe, PACMA, etc.).",
            "Las encuestas proceden de una fuente secundaria (Wikipedia) y están pendientes de verificar contra la publicación original.",
        ],
    }
    _w("calidad.json", dqc)

    # --- cartografía (provincias del INE ya simplificadas en el dashboard histórico)
    geo_src = ROOT / "web" / "data" / "geo" / "provincias.geojson"
    (WEB_DATA / "geo").mkdir(parents=True, exist_ok=True)
    g = json.loads(geo_src.read_text(encoding="utf-8"))
    for f in g["features"]:
        f["properties"] = {"id": f["properties"]["id"][-2:]}
    (WEB_DATA / "geo" / "provincias.geojson").write_text(json.dumps(g, separators=(",", ":")), encoding="utf-8")
    shutil.copy(ROOT / "web" / "data" / "geo" / "ccaa.geojson", WEB_DATA / "geo" / "ccaa.geojson")

    # --- tablas para Excel y Power BI
    REPORTS.mkdir(parents=True, exist_ok=True)
    filas_c, filas_b = [], []
    for c in cont:
        filas_c.append({k: c[k] for k in ["provincia_id", "provincia", "ccaa", "escanos", "favorito", "favorito_siglas",
                                          "p_victoria_favorito", "voto_favorito", "voto_favorito_p10", "voto_favorito_p90",
                                          "margen_p50", "margen_p10", "margen_p90", "competitividad", "calidad",
                                          "calidad_clase", "ganador_2023", "voto_ganador_2023", "margen_2023", "escanos_fav"]})
        for x in c["candidaturas"]:
            filas_b.append({"provincia_id": c["provincia_id"], "provincia": c["provincia"], "ccaa": c["ccaa"], **x})
    pd.DataFrame(filas_c).to_csv(REPORTS / "contiendas.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(filas_b).to_csv(REPORTS / "candidaturas.csv", index=False, encoding="utf-8-sig")
    pd.DataFrame(escanos).to_csv(REPORTS / "escanos_nacional.csv", index=False, encoding="utf-8-sig")
    print(f"web29n/data y reports/pronostico_29n actualizados ({len(cont)} contiendas)")
