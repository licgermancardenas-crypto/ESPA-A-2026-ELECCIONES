"""Modelos de reparto del voto dentro de cada circunscripción.

Todos devuelven un índice η por (provincia, bloque); la proporción esperada es softmax(η) dentro de la
provincia. Orden de complejidad (se elige el más simple salvo mejora clara fuera de muestra):

- persistencia: baseline sin encuestas. p ∝ voto previo del bloque en la provincia.
- swing_proporcional: baseline con encuestas. p ∝ media nacional de encuestas × fuerza relativa previa
  (swing proporcional uniforme). Sin parámetros.
- logit_condicional: logit condicional de McFadden (softmax(Xβ) por provincia) con penalización L2,
  ajustado por máxima verosimilitud fraccional sobre las proporciones observadas.
- jerarquico: logit condicional con desviaciones por comunidad autónoma del coeficiente de la fuerza
  relativa y de las encuestas, encogidas hacia el coeficiente común (pooling parcial = MAP con prior normal).
- gbm: gradient boosting sobre el residuo del swing proporcional (log), centrado por provincia.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from .features import COLS, EPS


def _g(df: pd.DataFrame) -> np.ndarray:
    return pd.factorize(df["eleccion"].astype(str) + "|" + df["provincia_id"].astype(str))[0]


def softmax_grupos(eta: np.ndarray, g: np.ndarray) -> np.ndarray:
    m = pd.Series(eta).groupby(g).transform("max").to_numpy()
    e = np.exp(eta - m)
    return e / pd.Series(e).groupby(g).transform("sum").to_numpy()


def predecir(modelo, df: pd.DataFrame) -> np.ndarray:
    return softmax_grupos(modelo.eta(df), _g(df))


class Persistencia:
    nombre = "persistencia"

    def fit(self, df):
        return self

    def eta(self, df):
        return np.log(df["rel"].to_numpy() * df["prev_nac"].to_numpy() + EPS)


class SwingProporcional:
    nombre = "swing_proporcional"

    def fit(self, df):
        return self

    def eta(self, df):
        return np.log(df["poll"].to_numpy() * np.maximum(df["rel"].to_numpy(), EPS))


class LogitCondicional:
    nombre = "logit_condicional"
    cols_jer = ("l_poll", "l_rel")

    def __init__(self, lam: float = 1.0, lam_ccaa: float | None = None):
        self.lam, self.lam_ccaa = lam, lam_ccaa
        if lam_ccaa is not None:
            self.nombre = "jerarquico"

    def _X(self, df):
        return df[COLS].to_numpy(float)

    def _eta(self, theta, X, idx):
        k = X.shape[1]
        beta = theta[:k]
        eta = X @ beta
        if self.lam_ccaa is not None:
            d = theta[k:].reshape(len(self.ccaa_), len(self.cols_jer))
            j = [COLS.index(c) for c in self.cols_jer]
            ok = idx >= 0
            eta[ok] += np.sum(X[ok][:, j] * d[idx[ok]], axis=1)
        return eta

    def fit(self, df):
        X, s, g = self._X(df), df["s"].to_numpy(float), _g(df)
        self.ccaa_ = sorted(df["ccaa"].unique())
        idx = df["ccaa"].map({c: i for i, c in enumerate(self.ccaa_)}).to_numpy()
        k = X.shape[1]
        n_extra = len(self.ccaa_) * len(self.cols_jer) if self.lam_ccaa is not None else 0
        n_g = g.max() + 1
        # inicio en el swing proporcional (β_poll = β_rel = 1)
        theta0 = np.zeros(k + n_extra)
        theta0[COLS.index("l_poll")] = 1.0
        theta0[COLS.index("l_rel")] = 1.0
        prior = theta0[:k].copy()

        def f(theta):
            eta = self._eta(theta, X, idx)
            m = pd.Series(eta).groupby(g).transform("max").to_numpy()
            e = np.exp(eta - m)
            z = np.bincount(g, e, n_g)[g]
            ll = np.sum(s * (eta - m - np.log(z)))
            pen = 0.5 * self.lam * np.sum((theta[:k] - prior) ** 2)
            if n_extra:
                pen += 0.5 * self.lam_ccaa * np.sum(theta[k:] ** 2)
            return -ll / n_g * 100 + pen

        r = minimize(f, theta0, method="L-BFGS-B")
        self.theta_ = r.x
        self.coef_ = dict(zip(COLS, r.x[:k]))
        return self

    def eta(self, df):
        X = self._X(df)
        idx = df["ccaa"].map({c: i for i, c in enumerate(getattr(self, "ccaa_", []))}).fillna(-1).astype(int).to_numpy()
        return self._eta(self.theta_, X, idx)


class GBM:
    nombre = "gbm"

    def __init__(self, **kw):
        self.kw = kw

    def fit(self, df):
        from sklearn.ensemble import HistGradientBoostingRegressor
        base = SwingProporcional().eta(df)
        y = np.log(df["s"].to_numpy() + EPS) - base
        y = y - pd.Series(y).groupby(_g(df)).transform("mean").to_numpy()
        self.m_ = HistGradientBoostingRegressor(random_state=0, **self.kw).fit(df[COLS + ["rel", "poll"]], y)
        return self

    def eta(self, df):
        return SwingProporcional().eta(df) + self.m_.predict(df[COLS + ["rel", "poll"]])


def catalogo(cfg: dict, lam: float) -> dict:
    m = cfg["modelos"]
    return {
        "persistencia": Persistencia(),
        "swing_proporcional": SwingProporcional(),
        "logit_condicional": LogitCondicional(lam),
        "jerarquico": LogitCondicional(lam, m["jerarquico_lambda_ccaa"]),
        "gbm": GBM(**m["gbm"]),
    }
