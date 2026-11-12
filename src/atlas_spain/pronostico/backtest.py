"""Backtesting a ciegas (origen móvil) y calibración de la incertidumbre.

Para cada elección objetivo t ∈ {2015, 2016, 2019-A, 2019-N, 2023}:
  - el diseño solo usa resultados de elecciones anteriores a t y encuestas con fin de campo ≤ t − 6 días;
  - los modelos con parámetros se entrenan SOLO con transiciones cuyo objetivo es anterior a t;
  - λ se elige dentro de esas transiciones (validación anidada de origen móvil).
2015 no tiene transiciones previas: allí solo se evalúan los modelos sin parámetros.
La comparación entre modelos usa las elecciones donde todos son evaluables (2016–2023).
"""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from ..paths import DATA
from . import datos, features, modelos, simulacion
from .datos import OTROS

SALIDA = DATA / "gold" / "pronostico_2026"


def _cat(lst: list[pd.DataFrame]) -> pd.DataFrame:
    """concat sin attrs (los attrs guardan tablas de encuestas y pandas no sabe compararlos)."""
    xs = []
    for d in lst:
        x = d.copy()
        x.attrs = {}
        xs.append(x)
    return pd.concat(xs, ignore_index=True)


def disenos() -> list[pd.DataFrame]:
    return [features.diseno_historico(bt) for bt in datos.config()["backtest"]]


def _metricas(df: pd.DataFrame, pred: np.ndarray) -> dict:
    d = df.assign(pred=pred)
    ce = -(d.s * np.log(np.clip(d.pred, 1e-9, 1))).groupby(d.provincia_id).sum()
    ent = -(d.s * np.log(np.clip(d.s, 1e-9, 1))).groupby(d.provincia_id).sum()
    sin = d[d.bloque != OTROS]
    gana_obs = sin.loc[sin.groupby("provincia_id").s.idxmax(), ["provincia_id", "bloque"]].set_index("provincia_id").bloque
    gana_pre = sin.loc[sin.groupby("provincia_id").pred.idxmax(), ["provincia_id", "bloque"]].set_index("provincia_id").bloque
    # escaños con la proporción esperada (determinista)
    esc_pred, esc_obs = {}, {}
    for p, g in d.groupby("provincia_id"):
        el = (g.bloque != OTROS).to_numpy()
        e1 = simulacion.dhondt(g.pred.to_numpy()[None, :], int(g.escanos.iloc[0]), el)[0]
        e2 = simulacion.dhondt(g.s.to_numpy()[None, :], int(g.escanos.iloc[0]), el)[0]
        for b, a, o in zip(g.bloque, e1, e2):
            esc_pred[b] = esc_pred.get(b, 0) + int(a)
            esc_obs[b] = esc_obs.get(b, 0) + int(o)
    return {
        "kl": float((ce - ent).mean()),                    # divergencia KL media por provincia
        "mae_pp": float((d.pred - d.s).abs().mean() * 100),
        "acierto_ganador": float((gana_obs == gana_pre.reindex(gana_obs.index)).mean()),
        "error_escanos": int(sum(abs(esc_pred.get(b, 0) - esc_obs.get(b, 0)) for b in esc_obs) // 2),
    }


def _elegir_lambda(train: list[pd.DataFrame], cfg: dict) -> float:
    if len(train) < 2:
        return 1.0
    mejor, lam_m = np.inf, 1.0
    for lam in cfg["modelos"]["ridge_lambda"]:
        kls = []
        for j in range(1, len(train)):
            m = modelos.LogitCondicional(lam).fit(_cat(train[:j]))
            kls.append(_metricas(train[j], modelos.predecir(m, train[j]))["kl"])
        if np.mean(kls) < mejor:
            mejor, lam_m = float(np.mean(kls)), lam
    return lam_m


def error_encuestas(df: pd.DataFrame) -> pd.Series:
    """Error nacional (escala log) de la media de encuestas por bloque: log(resultado / encuesta)."""
    v = df.assign(votos=df.s)
    tot = datos.votos_validos(df.eleccion.iloc[0])
    nac = (df.s * df.provincia_id.map(tot)).groupby(df.bloque).sum() / tot.sum()
    poll = df.groupby("bloque").poll.first()
    ok = (poll >= 0.01) & (nac > 0)
    return np.log(nac[ok] / poll[ok])


def ejecutar(n_sims_cal: int = 2000) -> dict:
    cfg = datos.config()
    D = disenos()
    nombres = cfg["modelos"]["orden_complejidad"]
    filas, preds = [], {}
    for i, df in enumerate(D):
        train = D[:i]
        lam = _elegir_lambda(train, cfg)
        cat = modelos.catalogo(cfg, lam)
        for nom in nombres:
            m = cat[nom]
            if nom not in ("persistencia", "swing_proporcional"):
                if not train:
                    continue
                m.fit(_cat(train))
            pr = modelos.predecir(m, df)
            preds[(i, nom)] = pr
            filas.append({"eleccion": df.eleccion.iloc[0], "modelo": nom, "lambda": lam, **_metricas(df, pr)})
    tabla = pd.DataFrame(filas)
    comunes = tabla[tabla.eleccion != D[0].eleccion.iloc[0]]
    resumen = comunes.groupby("modelo")[["kl", "mae_pp", "acierto_ganador", "error_escanos"]].mean() \
        .reindex(nombres)
    best = resumen.kl.min()
    tol = cfg["modelos"]["tolerancia_logloss"]
    elegido = next(n for n in nombres if resumen.loc[n, "kl"] <= best + tol)

    # --- calibración de σ (con el modelo elegido, en las elecciones 2016–2023, origen móvil)
    errs = [error_encuestas(df) for df in D]
    rng = np.random.default_rng(cfg["simulacion"]["semilla"])
    cal = []
    for sn in cfg["simulacion"]["sigma_nac_rejilla"]:
        for sp in cfg["simulacion"]["sigma_prov_rejilla"]:
            lls, cobs, cob_esc = [], [], []
            for i, df in enumerate(D[1:], start=1):
                pr = preds[(i, elegido)]
                eta = np.log(np.clip(pr, 1e-9, 1))
                sims = simulacion.simular(df, eta, sn, sp, n_sims_cal, rng, cfg)
                esc = simulacion.escanos_sim(df, sims, cfg["eleccion_objetivo"]["barrera"])
                tot_esc = {}
                for p, idx in df.groupby("provincia_id", sort=False).indices.items():
                    sub = df.iloc[idx]
                    sh = sims[p]
                    q10, q90 = np.quantile(sh, [0.1, 0.9], axis=0)
                    cobs.extend(((sub.s.to_numpy() >= q10) & (sub.s.to_numpy() <= q90)).tolist())
                    mask = (sub.bloque != OTROS).to_numpy()
                    gana = np.bincount(np.where(mask[None, :], sh, -1).argmax(1), minlength=len(idx)) / len(sh)
                    obs = int(np.where(mask, sub.s.to_numpy(), -1).argmax())
                    lls.append(np.log(max(gana[obs], 1e-3)))
                    for b, col in zip(sub.bloque, esc[p].T):
                        tot_esc.setdefault(b, 0)
                        tot_esc[b] = tot_esc[b] + col
                # cobertura del 80 % de escaños nacionales por bloque
                obs_esc = df.groupby("bloque").apply(lambda g: 0).to_dict()
                for p, g in df.groupby("provincia_id"):
                    el = (g.bloque != OTROS).to_numpy()
                    e2 = simulacion.dhondt(g.s.to_numpy()[None, :], int(g.escanos.iloc[0]), el)[0]
                    for b, o in zip(g.bloque, e2):
                        obs_esc[b] += int(o)
                for b, v in tot_esc.items():
                    if b == OTROS:
                        continue
                    lo, hi = np.quantile(v, [0.1, 0.9])
                    cob_esc.append(lo <= obs_esc[b] <= hi)
            cal.append({"sigma_nac": sn, "sigma_prov": sp, "logscore_ganador": float(np.mean(lls)),
                        "cobertura80_voto": float(np.mean(cobs)), "cobertura80_escanos": float(np.mean(cob_esc))})
    cal = pd.DataFrame(cal)
    cal["objetivo"] = -cal.logscore_ganador + (cal.cobertura80_voto - 0.8).abs() + (cal.cobertura80_escanos - 0.8).abs()
    sel = cal.loc[cal.objetivo.idxmin()]
    err_all = pd.concat(errs)
    res = {
        "modelo_seleccionado": elegido,
        "criterio": f"el modelo más simple con KL ≤ mejor + {tol} (media 2016–2023, origen móvil)",
        "tabla": tabla.round(4).to_dict("records"),
        "resumen": resumen.round(4).reset_index().to_dict("records"),
        "calibracion": cal.round(4).to_dict("records"),
        "sigma_nac": float(sel.sigma_nac), "sigma_prov": float(sel.sigma_prov),
        "sigma_nac_empirico": float(np.sqrt(np.mean(err_all ** 2))),
        "error_encuestas": [{"eleccion": D[i].eleccion.iloc[0], "bloque": b, "error_log": round(float(v), 4)}
                            for i, e in enumerate(errs) for b, v in e.items()],
        "encuestas_usadas": {D[i].eleccion.iloc[0]: int(len(features.META[D[i].eleccion.iloc[0]]["encuestas_usadas"])) for i in range(len(D))},
        "calibracion_sel": {k: float(sel[k]) for k in ["logscore_ganador", "cobertura80_voto", "cobertura80_escanos"]},
    }
    SALIDA.mkdir(parents=True, exist_ok=True)
    (SALIDA / "backtest.json").write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return res
