"""Correlación: Pearson, Spearman, Kendall, matriz y correlación parcial.

Intervalos de confianza por transformación z de Fisher:
- Pearson:  SE = 1/√(n−3)
- Spearman: SE = √(1,06/(n−3))   (Fieller, Hartley y Pearson, 1957)
- Kendall:  SE = √(0,437/(n−4))  (Fieller et al., 1957)

Advertencias que acompañan a todo resultado: correlación no implica causalidad; con datos
territoriales agregados no se puede inferir el comportamiento de individuos (falacia ecológica);
los territorios vecinos se parecen entre sí (autocorrelación espacial), lo que hace los valores p
optimistas; puede haber variables de confusión.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as st

ADVERTENCIAS = [
    "Una correlación no demuestra causalidad.",
    "Datos agregados por territorio: no describen el comportamiento de personas (falacia ecológica).",
    "Los territorios vecinos se parecen entre sí (autocorrelación espacial): el valor p asume independencia y puede ser optimista.",
    "Puede haber variables de confusión no incluidas.",
]
SE_K = {"pearson": 1.0, "spearman": 1.06}


def _pares(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    return x[ok], y[ok], int((~ok).sum())


def correlacion(x, y, metodo: str = "pearson", confianza: float = 0.95) -> dict:
    x, y, faltan = _pares(x, y)
    n = len(x)
    r = {"metodo": metodo, "n": n, "n_faltantes": faltan, "confianza": confianza, "advertencias": ADVERTENCIAS, "avisos": []}
    if n < 4 or np.ptp(x) == 0 or np.ptp(y) == 0:
        r.update(coef=None, p=None, ic=None)
        r["avisos"].append("Datos insuficientes o sin variación para calcular la correlación.")
        return r
    if metodo == "pearson":
        c, p = st.pearsonr(x, y)
    elif metodo == "spearman":
        c, p = st.spearmanr(x, y)
    elif metodo == "kendall":
        c, p = st.kendalltau(x, y)
    else:
        raise ValueError(metodo)
    c, p = float(c), float(p)
    zc = st.norm.ppf(0.5 + confianza / 2)
    if metodo == "kendall":
        se = np.sqrt(0.437 / (n - 4)) if n > 4 else np.nan
    else:
        se = np.sqrt(SE_K[metodo] / (n - 3))
    zr = np.arctanh(np.clip(c, -0.999999, 0.999999))
    ic = [float(np.tanh(zr - zc * se)), float(np.tanh(zr + zc * se))] if np.isfinite(se) else None
    r.update(coef=c, p=p, ic=ic, r2=c * c if metodo == "pearson" else None)
    if metodo == "pearson":
        b, a = np.polyfit(x, y, 1)
        r["recta"] = {"pendiente": float(b), "ordenada": float(a)}
    r["fuerza"] = _fuerza(c)
    return r


def _fuerza(c: float) -> str:
    a = abs(c)
    return "despreciable" if a < 0.1 else "débil" if a < 0.3 else "moderada" if a < 0.5 else "fuerte" if a < 0.7 else "muy fuerte"


def matriz(variables: dict[str, np.ndarray], metodo: str = "pearson") -> dict:
    """Matriz de correlaciones por pares completos (cada celda usa las observaciones con ambos datos)."""
    nombres = list(variables)
    k = len(nombres)
    m = np.full((k, k), np.nan)
    nn = np.zeros((k, k), int)
    for i in range(k):
        for j in range(i, k):
            if i == j:
                m[i, j] = 1.0
                nn[i, j] = int(np.isfinite(np.asarray(variables[nombres[i]], float)).sum())
                continue
            res = correlacion(variables[nombres[i]], variables[nombres[j]], metodo)
            m[i, j] = m[j, i] = np.nan if res["coef"] is None else res["coef"]
            nn[i, j] = nn[j, i] = res["n"]
    return {"metodo": metodo, "variables": nombres, "coef": [[None if not np.isfinite(v) else float(v) for v in fila] for fila in m],
            "n": nn.tolist(), "advertencias": ADVERTENCIAS}


def parcial(x, y, controles: dict[str, np.ndarray], metodo: str = "pearson") -> dict:
    """Correlación parcial de x e y controlando por `controles` (residuos de MCO; Spearman sobre rangos)."""
    cols = [np.asarray(x, float), np.asarray(y, float)] + [np.asarray(c, float) for c in controles.values()]
    ok = np.all([np.isfinite(c) for c in cols], axis=0)
    cols = [c[ok] for c in cols]
    if metodo == "spearman":
        cols = [st.rankdata(c) for c in cols]
    n, k = len(cols[0]), len(controles)
    if n - k - 3 < 1:
        return {"metodo": metodo, "n": n, "coef": None, "p": None, "avisos": ["Observaciones insuficientes."]}
    Z = np.column_stack([np.ones(n)] + cols[2:])
    rx = cols[0] - Z @ np.linalg.lstsq(Z, cols[0], rcond=None)[0]
    ry = cols[1] - Z @ np.linalg.lstsq(Z, cols[1], rcond=None)[0]
    c = float(np.corrcoef(rx, ry)[0, 1])
    df = n - 2 - k
    t = c * np.sqrt(df / max(1e-12, 1 - c * c))
    p = float(2 * st.t.sf(abs(t), df))
    return {"metodo": metodo, "n": n, "n_faltantes": int((~ok).sum()), "controles": list(controles), "coef": c, "p": p,
            "gl": df, "fuerza": _fuerza(c), "advertencias": ADVERTENCIAS}
