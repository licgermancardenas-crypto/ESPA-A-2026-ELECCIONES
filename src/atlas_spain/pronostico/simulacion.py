"""Simulación Monte Carlo del voto y del reparto de escaños.

η_sim(p,k) = η(p,k) + σ_nac·Z_k + σ_prov·f_k·Z_(p,k)
  Z_k      error nacional del bloque (común a todas sus provincias: error de la media de encuestas)
  Z_(p,k)  error provincial independiente
  f_k      1; × factor_sustituto si la implantación no es continuidad legal; × factor_nuevo si no hay
Proporciones = softmax por provincia. Escaños: D'Hondt por circunscripción con barrera del 3 % (art. 163
LOREG). OTROS es un agregado de candidaturas distintas: no recibe escaños en la simulación.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .datos import OTROS


def factores(df: pd.DataFrame, cfg: dict) -> np.ndarray:
    s = cfg["simulacion"]
    f = np.ones(len(df))
    f[df["tipo_previo"].isin(["sustituto", "europeas"]).to_numpy()] = s["factor_sustituto"]
    f[(df["tipo_previo"] == "ninguno").to_numpy()] = s["factor_nuevo"]
    return f


def simular(df: pd.DataFrame, eta: np.ndarray, sigma_nac: float, sigma_prov: float, n: int,
            rng: np.random.Generator, cfg: dict) -> dict[str, np.ndarray]:
    """Devuelve {provincia_id: matriz (n, k_p)} de proporciones simuladas, en el orden de `df`."""
    claves = df["poll_clave"] if "poll_clave" in df else df["bloque"]
    uniq, cod = np.unique(claves.to_numpy(), return_inverse=True)
    z_nac = rng.standard_normal((n, len(uniq)))
    f = factores(df, cfg)
    out = {}
    for p, idx in df.groupby("provincia_id", sort=False).indices.items():
        x = eta[idx][None, :] + sigma_nac * z_nac[:, cod[idx]] + \
            sigma_prov * f[idx][None, :] * rng.standard_normal((n, len(idx)))
        x -= x.max(1, keepdims=True)
        e = np.exp(x)
        out[p] = e / e.sum(1, keepdims=True)
    return out


def dhondt(sh: np.ndarray, escanos: int, elegible: np.ndarray, barrera: float = 0.03) -> np.ndarray:
    """Escaños (n, k) por D'Hondt para cada simulación. `elegible`: máscara de bloques que pueden obtener
    escaño (OTROS no). Desempate por mayor voto (equivale al criterio de la LOREG en la práctica)."""
    n, k = sh.shape
    v = np.where((sh >= barrera) & elegible[None, :], sh, 0.0)
    div = np.arange(1, escanos + 1)
    q = (v[:, :, None] / div[None, None, :]).reshape(n, k * escanos)
    top = np.argpartition(-q, escanos - 1, axis=1)[:, :escanos]
    partido = top // escanos
    res = np.zeros((n, k), dtype=np.int16)
    np.add.at(res, (np.repeat(np.arange(n), escanos), partido.ravel()), 1)
    return res


def escanos_sim(df: pd.DataFrame, sims: dict[str, np.ndarray], barrera: float) -> dict[str, np.ndarray]:
    out = {}
    for p, idx in df.groupby("provincia_id", sort=False).indices.items():
        sub = df.iloc[idx]
        eleg = (sub["bloque"] != OTROS).to_numpy()
        out[p] = dhondt(sims[p], int(sub["escanos"].iloc[0]), eleg, barrera)
    return out


def resumen_provincia(sh: np.ndarray) -> dict:
    n, k = sh.shape
    gana = np.bincount(sh.argmax(1), minlength=k) / n
    q = np.quantile(sh, [0.1, 0.5, 0.9], axis=0)
    fav = int(np.argmax(gana))
    otros = np.delete(sh, fav, axis=1)
    mf = sh[:, fav] - (otros.max(1) if k > 1 else 0)
    return {"p_victoria": gana, "media": sh.mean(0), "p10": q[0], "p50": q[1], "p90": q[2], "favorito": fav,
            "margen_p50": float(np.median(mf)), "margen_p10": float(np.quantile(mf, 0.1)),
            "margen_p90": float(np.quantile(mf, 0.9))}
