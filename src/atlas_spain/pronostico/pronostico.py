"""Pronóstico 29-N-2026: 52 circunscripciones del Congreso.

Por contienda: favorito, probabilidad de victoria (más votos), % de voto con intervalo 80 %, margen,
competitividad, escaños esperados por bloque, escenarios y calidad del dato. A nivel nacional:
distribución de escaños por bloque y probabilidades de mayorías.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from . import backtest, datos, features, modelos, simulacion
from .datos import OTROS

SALIDA = backtest.SALIDA

NOMBRES_CCAA = {
    "01": "Andalucía", "02": "Aragón", "03": "Asturias", "04": "Illes Balears", "05": "Canarias",
    "06": "Cantabria", "07": "Castilla y León", "08": "Castilla-La Mancha", "09": "Cataluña",
    "10": "Comunitat Valenciana", "11": "Extremadura", "12": "Galicia", "13": "Comunidad de Madrid",
    "14": "Región de Murcia", "15": "Navarra", "16": "País Vasco", "17": "La Rioja", "18": "Ceuta", "19": "Melilla",
}


def _nombres_provincia() -> dict:
    import duckdb
    from ..paths import WAREHOUSE
    con = duckdb.connect(str(WAREHOUSE), read_only=True)
    try:
        d = con.sql("select right(geo_id,2) id, geo_name as name from gold.dim_geography "
                    "where geo_type='provincia' and valid_to is null").df()
    finally:
        con.close()
    return dict(zip(d.id, d.name))


def competitividad(p: float, margen: float, cfg: dict) -> str:
    for c in cfg["competitividad"]:
        if p < c["p_max"] or margen < c["margen_max"]:
            return c["clase"]
    return cfg["competitividad"][-1]["clase"]


def calidad(sub: pd.DataFrame, n_encuestas: int, cfg: dict) -> tuple[int, str, list[str]]:
    """Puntuación 0-100 de la calidad del dato de una contienda (reglas fijas, documentadas)."""
    motivos = ["Nómina oficial (BOE-A-2026-23103): 30/30"]
    pts = 30
    e = round(25 * min(n_encuestas / 15, 1))
    pts += e
    motivos.append(f"Encuestas nacionales en la ventana de 21 días: {n_encuestas} → {e}/25")
    peso_legal = float(sub.loc[sub.tipo_previo == "legal", "media"].sum() / sub["media"].sum())
    l = round(25 * peso_legal)
    pts += l
    motivos.append(f"Voto pronosticado con continuidad legal desde 2023: {peso_legal:.0%} → {l}/25")
    motivos.append("Encuestas provinciales verificadas: ninguna cargada → 0/20")
    q = cfg["calidad"]
    clase = "Alta" if pts >= q["alta_min"] else "Media" if pts >= q["media_min"] else "Baja"
    return pts, clase, motivos


def ejecutar(corte: date | None = None, n_sims: int | None = None) -> dict:
    cfg = datos.config()
    corte = corte or min(date.today(), date.fromisoformat(cfg["eleccion_objetivo"]["veda_desde"]))
    n_sims = n_sims or cfg["simulacion"]["n_sims"]
    bt_path = SALIDA / "backtest.json"
    bt = json.loads(bt_path.read_text(encoding="utf-8")) if bt_path.exists() else backtest.ejecutar()
    df, media = features.diseno_2026(corte)
    usadas = features.META[cfg["eleccion_objetivo"]["id"]]["encuestas_usadas"]
    nombre = bt["modelo_seleccionado"]
    m = modelos.catalogo(cfg, 1.0)[nombre]
    if nombre not in ("persistencia", "swing_proporcional"):
        m.fit(backtest._cat(backtest.disenos()))
    eta = m.eta(df)
    df["pred"] = modelos.softmax_grupos(eta, pd.factorize(df.provincia_id)[0])
    rng = np.random.default_rng(cfg["simulacion"]["semilla"])
    sims = simulacion.simular(df, eta, bt["sigma_nac"], bt["sigma_prov"], n_sims, rng, cfg)
    esc = simulacion.escanos_sim(df, sims, cfg["eleccion_objetivo"]["barrera"])
    nprov = _nombres_provincia()

    # --- nacional: escaños por bloque (sumando bloques que comparten columna de encuesta para el titular)
    bloques = sorted(set(df.bloque) - {OTROS})
    tot = {b: np.zeros(n_sims, dtype=np.int32) for b in bloques}
    for p, idx in df.groupby("provincia_id", sort=False).indices.items():
        for b, col in zip(df.bloque.iloc[idx], esc[p].T):
            if b != OTROS:
                tot[b] += col
    pp_total = tot["PP"] + tot.get("UPN_PP", 0)
    psoe = tot["PSOE"]
    vox = tot["VOX"]
    nacional = {
        "escanos": {b: {"media": float(v.mean()), "p10": int(np.quantile(v, .1)), "p50": int(np.median(v)),
                        "p90": int(np.quantile(v, .9))} for b, v in tot.items()},
        "p_pp_primero": float(np.mean(pp_total > psoe)),
        "p_psoe_primero": float(np.mean(psoe > pp_total)),
        "p_mayoria_pp_vox": float(np.mean(pp_total + vox >= 176)),
        "p_mayoria_absoluta_pp": float(np.mean(pp_total >= 176)),
        "dist_pp_vox": np.bincount(pp_total + vox, minlength=351).tolist(),
        "media_encuestas": {k: v for k, v in media.items() if not k.startswith("_")},
        "ratio_fv_en_fa_fv": media.get("_ratio_fv"),
        "n_encuestas": int(len(usadas)),
        "corte": corte.isoformat(),
    }
    # escenarios nacionales: terciles extremos del margen PP-PSOE en escaños
    marg = pp_total - psoe
    lo, hi = np.quantile(marg, [0.2, 0.8])
    esc_sel = {"Base (mediana)": np.ones(n_sims, bool),
               "Favorable al PSOE (20 % inferior del margen PP–PSOE)": marg <= lo,
               "Favorable al PP (20 % superior del margen PP–PSOE)": marg >= hi}

    # --- contiendas
    contiendas = []
    n_enc = int(len(usadas))
    for p, idx in df.groupby("provincia_id", sort=False).indices.items():
        sub = df.iloc[idx].copy()
        sh = sims[p]
        mask = (sub.bloque != OTROS).to_numpy()
        shm = np.where(mask[None, :], sh, -1.0)
        gana = np.bincount(shm.argmax(1), minlength=len(idx)) / n_sims
        q = np.quantile(sh, [0.1, 0.5, 0.9], axis=0)
        fav = int(np.argmax(gana))
        orden = np.sort(shm, axis=1)
        mf = sh[:, fav] - np.max(np.delete(shm, fav, axis=1), axis=1)
        sub["media"] = sh.mean(0)
        sub["p10"], sub["p50"], sub["p90"] = q
        sub["p_victoria"] = gana
        sub["escanos_media"] = esc[p].mean(0)
        sub["escanos_p10"] = np.quantile(esc[p], .1, axis=0)
        sub["escanos_p90"] = np.quantile(esc[p], .9, axis=0)
        sub["p_al_menos_1"] = (esc[p] > 0).mean(0)
        pts, clase, motivos = calidad(sub, n_enc, cfg)
        escen = []
        for nom, sel in esc_sel.items():
            g2 = np.bincount(shm[sel].argmax(1), minlength=len(idx)) / sel.sum()
            escen.append({"escenario": nom,
                          "ganador": sub.bloque.iloc[int(np.argmax(g2))],
                          "voto": {b: round(float(v), 4) for b, v in zip(sub.bloque, sh[sel].mean(0))},
                          "escanos": {b: round(float(v), 2) for b, v in zip(sub.bloque, esc[p][sel].mean(0))}})
        margen = float(np.median(mf))
        contiendas.append({
            "provincia_id": p, "provincia": nprov.get(p, p), "ccaa_id": features.CCAA[p],
            "ccaa": NOMBRES_CCAA[features.CCAA[p]], "escanos": int(sub.escanos.iloc[0]),
            "favorito": sub.bloque.iloc[fav], "favorito_siglas": sub.siglas.iloc[fav],
            "p_victoria_favorito": float(gana[fav]),
            "voto_favorito": float(sub.media.iloc[fav]), "voto_favorito_p10": float(q[0][fav]),
            "voto_favorito_p90": float(q[2][fav]),
            "margen_p50": margen, "margen_p10": float(np.quantile(mf, .1)), "margen_p90": float(np.quantile(mf, .9)),
            "competitividad": competitividad(float(gana[fav]), abs(margen), cfg),
            "calidad": pts, "calidad_clase": clase, "calidad_motivos": motivos,
            "candidaturas": sub[["bloque", "siglas", "denominacion", "cabeza_lista", "tipo_previo", "pred", "media",
                                 "p10", "p50", "p90", "p_victoria", "escanos_media", "escanos_p10", "escanos_p90",
                                 "p_al_menos_1"]].round(4).to_dict("records"),
            "escenarios": escen,
        })
    res = {"eleccion": cfg["eleccion_objetivo"], "modelo": nombre, "sigma_nac": bt["sigma_nac"],
           "sigma_prov": bt["sigma_prov"], "n_sims": n_sims, "nacional": nacional, "contiendas": contiendas,
           "encuestas_usadas": usadas.assign(campo_inicio=usadas.campo_inicio.astype(str),
                                             campo_fin=usadas.campo_fin.astype(str))
           .drop(columns=[c for c in usadas.columns if c.startswith("esc_")]).to_dict("records")}
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "pronostico.json").write_text(json.dumps(res, ensure_ascii=False, default=float), encoding="utf-8")
    return res
