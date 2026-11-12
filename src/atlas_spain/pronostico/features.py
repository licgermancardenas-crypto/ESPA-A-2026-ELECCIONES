"""Matriz de diseño (contienda x bloque) para el backtesting y para 2026.

Variables por bloque k en la provincia p:
  l_poll      log de la media nacional de encuestas del bloque (corte sin fuga)
  l_rel       log de la fuerza relativa previa: voto previo en p / voto previo nacional
  no_legal    1 si la implantación previa es un sustituto geográfico o viene de otra elección
  l_rel_nl    l_rel * no_legal (permite encoger la implantación cuando no es continuidad legal)
  ninguno     1 si no hay implantación previa (fuerza relativa uniforme en sus provincias)
  otros       1 para el agregado OTROS
  l_poll_esc  l_poll * log(escaños de p): voto útil en circunscripciones pequeñas
y el objetivo `s` (proporción observada; NaN en 2026).
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pandas as pd

from . import datos
from .datos import OTROS

# Metadatos de cada diseño (encuestas usadas, medias), por id de elección. No se guardan como
# atributos del DataFrame porque pandas los propaga y compara en cada concat.
META: dict[str, dict] = {}

COLS = ["l_poll", "l_rel", "l_rel_nl", "ninguno", "otros", "l_poll_esc"]
EPS = 0.002

# Comunidad autónoma (código INE) de cada provincia, para el modelo jerárquico
CCAA = {
    "04": "01", "11": "01", "14": "01", "18": "01", "21": "01", "23": "01", "29": "01", "41": "01",
    "22": "02", "44": "02", "50": "02", "33": "03", "07": "04", "35": "05", "38": "05", "39": "06",
    "05": "07", "09": "07", "24": "07", "34": "07", "37": "07", "40": "07", "42": "07", "47": "07", "49": "07",
    "02": "08", "13": "08", "16": "08", "19": "08", "45": "08", "08": "09", "17": "09", "25": "09", "43": "09",
    "03": "10", "12": "10", "46": "10", "06": "11", "10": "11", "15": "12", "27": "12", "32": "12", "36": "12",
    "28": "13", "30": "14", "31": "15", "01": "16", "20": "16", "48": "16", "26": "17", "51": "18", "52": "19",
}


def _previo(eleccion: str, familias: list[str]) -> tuple[pd.Series, float]:
    """Proporción provincial y nacional de la suma de `familias` en `eleccion`."""
    r = datos.resultados(eleccion)
    tot = r.groupby("provincia_id").votos.sum()
    v = r[r.familia.isin(familias)].groupby("provincia_id").votos.sum().reindex(tot.index, fill_value=0.0)
    return v / tot, float(v.sum() / tot.sum())


def _fila(prov, bloque, poll, rel, tipo, esc, s=np.nan, **extra):
    l_rel = float(np.log(max(rel, EPS)))
    nl = 1.0 if tipo in ("sustituto", "europeas") else 0.0
    lp = float(np.log(max(poll, EPS)))
    return {"provincia_id": prov, "bloque": bloque, "poll": poll, "rel": rel, "tipo_previo": tipo,
            "l_poll": lp, "l_rel": l_rel, "l_rel_nl": l_rel * nl, "ninguno": float(tipo == "ninguno"),
            "otros": float(bloque == OTROS), "l_poll_esc": lp * np.log(esc), "escanos": esc, "s": s, **extra}


def _rel_ninguno(provs_corre: list[str], validos_prev: pd.Series) -> float:
    """Fuerza relativa uniforme: votos nacionales / votos de las provincias donde concurre."""
    return float(validos_prev.sum() / validos_prev.reindex(provs_corre).sum())


# ------------------------------------------------------------------------------- histórico

def diseno_historico(bt: dict) -> pd.DataFrame:
    """Diseño de una transición previa -> objetivo con encuestas cortadas antes de la veda."""
    cfg = datos.config()
    corte = date.fromisoformat(bt["fecha"]) - timedelta(days=cfg["encuestas"]["corte_previo_eleccion_dias"])
    media, usadas = datos.media_encuestas(datos.encuestas(bt["pagina"]), bt["polls"], corte)
    obj = datos.resultados(bt["objetivo"])
    tot_obj = obj.groupby("provincia_id").votos.sum()
    esc = obj.groupby("provincia_id").escanos.sum()
    validos_prev = datos.votos_validos(bt["previa"])
    fus, sus = bt.get("fusiones", {}), bt.get("sustitutos", {})
    nuevos = set(bt.get("nuevos_desde_europeas", []))
    unidades = {}
    for col, fams in bt["polls"].items():
        if col not in media or media[col] <= 0:
            continue
        clave = fams[0]
        if clave in unidades:          # dos columnas de Wikipedia para la misma familia (renombrado)
            continue
        fam_prev = fus.get(clave) or sus.get(clave) or fams
        prov_prev, nac_prev = _previo(bt["previa"], fam_prev)
        tipo = "sustituto" if clave in sus else "legal"
        if nac_prev == 0 and clave in nuevos and bt.get("europeas"):
            prov_prev, nac_prev = _previo(bt["europeas"], fams)
            tipo = "europeas"
        v = obj[obj.familia.isin(fams)].groupby("provincia_id").votos.sum()
        unidades[clave] = dict(poll=media[col], prov_prev=prov_prev, nac_prev=nac_prev, tipo=tipo,
                               v=v, fams=fams)
    poll_otros = max(1.0 - sum(u["poll"] for u in unidades.values()), 0.005)
    fams_unidades = {f for u in unidades.values() for f in u["fams"]} | \
                    {f for k in unidades for f in (fus.get(k) or sus.get(k) or [])}
    prev = datos.resultados(bt["previa"])
    otros_prev = prev[~prev.familia.isin(fams_unidades)]
    otros_prov = otros_prev.groupby("provincia_id").votos.sum().reindex(validos_prev.index, fill_value=0) / validos_prev
    otros_nac = float(otros_prev.votos.sum() / validos_prev.sum())
    filas = []
    for p in tot_obj.index:
        usados = 0.0
        for k, u in unidades.items():
            vp = float(u["v"].get(p, 0.0))
            if vp <= 0:
                continue                 # no concurre en p
            usados += vp
            if u["nac_prev"] > 0:
                rel, tipo = float(u["prov_prev"].get(p, 0.0)) / u["nac_prev"], u["tipo"]
            else:
                provs = [q for q in tot_obj.index if float(u["v"].get(q, 0.0)) > 0]
                rel, tipo = _rel_ninguno(provs, validos_prev), "ninguno"
            filas.append(_fila(p, k, u["poll"], rel, tipo, esc[p], vp / tot_obj[p], prev_nac=u["nac_prev"] or 0.005))
        resto = tot_obj[p] - usados
        filas.append(_fila(p, OTROS, poll_otros, float(otros_prov.get(p, 0.0)) / otros_nac, "legal",
                           esc[p], resto / tot_obj[p], prev_nac=otros_nac))
    df = pd.DataFrame(filas)
    df["eleccion"] = bt["objetivo"]
    df["ccaa"] = df.provincia_id.map(CCAA)
    META[bt["objetivo"]] = {"encuestas_usadas": usadas, "media": media}
    return df


# ---------------------------------------------------------------------------------- 2026

def media_2026(corte: date) -> tuple[dict, pd.DataFrame]:
    """Media de encuestas 2026 por bloque. FA y FV (Compromís) a veces se publican como suma conjunta:
    se promedia la suma FA+FV y se reparte con la proporción media de las encuestas que las separan."""
    polls = datos.encuestas("2026")
    polls = polls[polls.seccion_wiki.str.contains("with Broad Front")].copy()
    fa = polls["FA"].fillna(0) + polls["FV"].fillna(0)
    polls["FA_FV"] = fa.where(polls["FA"].notna())
    sep = polls[polls["FV"].notna() & polls["FA"].notna()]
    cols = {c: [c] for c in ["PP", "PSOE", "VOX", "FA_FV", "PODEMOS", "SALF", "ERC", "JUNTS", "BILDU",
                             "PNV", "BNG", "CCA", "ADELANTE"]}
    media, usadas = datos.media_encuestas(polls, cols, corte)
    sep_c = datos.seleccionar_encuestas(sep, corte)
    if len(sep_c) and "FA_FV" in media:
        r_fv = float((sep_c["FV"] / (sep_c["FA"] + sep_c["FV"])).mean())
    else:
        r_fv = 0.0
    media["FV"] = media["FA_FV"] * r_fv
    media["FA"] = media.pop("FA_FV") * (1 - r_fv)
    media["_ratio_fv"] = r_fv
    return media, usadas


def diseno_2026(corte: date) -> tuple[pd.DataFrame, dict]:
    from . import candidaturas
    cfg = datos.config()
    media, usadas = media_2026(corte)
    cand = candidaturas.cargar()
    cand = cand[cand.proclamada].copy()
    inv = {s: b for b, d in cfg["bloques"].items() for s in d["siglas"]}
    cand["bloque"] = cand.siglas.map(inv).fillna(OTROS)
    esc = cand.groupby("provincia_id").n_titulares.max()      # titulares = escaños de la circunscripción
    validos_prev = datos.votos_validos("02-202307")
    # Implantación de cada bloque. La fuerza relativa se mide contra el voto previo nacional de la
    # COLUMNA de encuesta que lo mueve, contando cada bloque solo en las provincias donde concurre en
    # 2026 (así una coalición regional o un sustituto geográfico no se diluye en todo el país).
    impl, base_col = {}, {}
    provs_b = cand.groupby("bloque").provincia_id.apply(set).to_dict()
    for b, d in cfg["bloques"].items():
        pv = d["previo"]
        if pv["tipo"] == "ninguno" or b not in provs_b:
            impl[b] = None
            continue
        r = datos.resultados(pv["eleccion"])
        tot = r.groupby("provincia_id").votos.sum()
        v = r[r.familia.isin(pv["familias"])].groupby("provincia_id").votos.sum().reindex(tot.index, fill_value=0.0)
        impl[b] = (v / tot, None)
        col = d["poll"]
        base_col[col] = base_col.get(col, 0.0) + float(v.reindex(sorted(provs_b[b])).sum() / tot.sum())
    for b, d in cfg["bloques"].items():
        if impl.get(b) is not None:
            impl[b] = (impl[b][0], base_col[d["poll"]])
    poll_bloque = {}
    for b, d in cfg["bloques"].items():
        poll_bloque[b] = media.get(d["poll"]) if d["poll"] else None
    # bloques sin columna de encuesta: su previo nacional (2023) entra en OTROS
    con_poll = {b for b, v in poll_bloque.items() if v}
    # los bloques que comparten columna (PP / UPN_PP, BILDU / BILDU_ERC, FA / UPC) comparten la media
    poll_otros = max(1.0 - sum(v for k, v in media.items() if not k.startswith("_")), 0.005)
    familias_con_bloque = {f for b in con_poll for f in cfg["bloques"][b]["previo"].get("familias", [])}
    prev = datos.resultados("02-202307")
    otros_prev = prev[~prev.familia.isin(familias_con_bloque)]
    otros_prov = otros_prev.groupby("provincia_id").votos.sum().reindex(validos_prev.index, fill_value=0) / validos_prev
    otros_nac = float(otros_prev.votos.sum() / validos_prev.sum())
    filas = []
    for p, g in cand.groupby("provincia_id"):
        for b in sorted(set(g.bloque)):
            if b == OTROS or b not in con_poll:
                continue
            tipo_cfg = cfg["bloques"][b]["previo"]["tipo"]
            if impl[b] is None:
                provs = sorted(cand.loc[cand.bloque == b, "provincia_id"].unique())
                rel, tipo = _rel_ninguno(provs, validos_prev), "ninguno"
            else:
                prov_prev, nac_prev = impl[b]
                tipo = "europeas" if (tipo_cfg == "legal" and cfg["bloques"][b]["previo"]["eleccion"].startswith("07")) \
                    else tipo_cfg
                rel = float(prov_prev.get(p, 0.0)) / nac_prev if nac_prev > 0 else 1.0
            fila = g[g.bloque == b].iloc[0]
            pn = impl[b][1] if impl[b] is not None else 0.005
            filas.append(_fila(p, b, poll_bloque[b], rel, tipo, esc[p], prev_nac=pn, siglas=fila.siglas,
                               denominacion=fila.denominacion, cabeza_lista=fila.cabeza_lista))
        filas.append(_fila(p, OTROS, poll_otros, float(otros_prov.get(p, 0.0)) / otros_nac, "legal", esc[p],
                           prev_nac=otros_nac, siglas=OTROS, denominacion="Otras candidaturas",
                           cabeza_lista=None))
    df = pd.DataFrame(filas)
    df["eleccion"] = cfg["eleccion_objetivo"]["id"]
    df["ccaa"] = df.provincia_id.map(CCAA)
    df["poll_clave"] = df.bloque.map(lambda b: cfg["bloques"].get(b, {}).get("poll") or b)
    META[cfg["eleccion_objetivo"]["id"]] = {"encuestas_usadas": usadas, "media": media}
    return df, media
