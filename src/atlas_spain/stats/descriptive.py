"""Estadística descriptiva: media, mediana, cuantiles, varianza, desviación estándar.

Definiciones (documentadas también en la interfaz):
- Media aritmética: x̄ = Σx / n.
- Media ponderada: x̄_w = Σ w·x / Σ w. El peso debe ser la magnitud que da sentido al promedio
  (p. ej. participación ponderada por censo = participación agregada del conjunto).
- Varianza poblacional: σ² = Σ(x − x̄)² / n. Describe el conjunto observado completo (p. ej. todos
  los municipios de una provincia: no son una muestra).
- Varianza muestral: s² = Σ(x − x̄)² / (n − 1). Estima la varianza de una población mayor.
- Varianza ponderada (de frecuencias): Σ w(x − x̄_w)² / Σ w.
- Cuantiles: interpolación lineal (tipo 7 de Hyndman-Fan, el de R y numpy por defecto).
- Cuantiles ponderados: interpolación sobre la distribución acumulada de pesos (punto medio).
- Asimetría y curtosis: estimadores corregidos por sesgo (Fisher-Pearson ajustado; exceso de curtosis).
"""

from __future__ import annotations

import numpy as np
from scipy import stats as st


def limpiar(x, w=None):
    """Convierte a float y descarta NaN/inf (y pesos no positivos o faltantes)."""
    x = np.asarray(x, dtype=float)
    ok = np.isfinite(x)
    if w is not None:
        w = np.asarray(w, dtype=float)
        ok &= np.isfinite(w) & (w > 0)
        return x[ok], w[ok], int((~ok).sum())
    return x[ok], None, int((~ok).sum())


def media(x, w=None) -> float | None:
    x, w, _ = limpiar(x, w)
    if len(x) == 0:
        return None
    return float(np.average(x, weights=w))


def cuantil_ponderado(x, w, q):
    x, w, _ = limpiar(x, w)
    if len(x) == 0:
        return None
    o = np.argsort(x)
    x, w = x[o], w[o]
    acum = (np.cumsum(w) - 0.5 * w) / w.sum()
    return float(np.interp(q, acum, x))


def media_movil(serie, ventana: int):
    """Media móvil simple centrada a la derecha (incluye el período actual y los ventana−1 anteriores)."""
    s = np.asarray(serie, dtype=float)
    out = np.full(len(s), np.nan)
    for i in range(ventana - 1, len(s)):
        v = s[i - ventana + 1:i + 1]
        if np.isfinite(v).all():
            out[i] = v.mean()
    return out


def describir(x, w=None) -> dict:
    """Resumen completo de una variable. Con `w`, añade media/mediana/varianza ponderadas."""
    x, w, faltan = limpiar(x, w)
    n = len(x)
    r = {"n": n, "n_faltantes": faltan, "avisos": []}
    if n == 0:
        r["avisos"].append("Sin observaciones válidas.")
        return r
    q = np.percentile(x, [1, 5, 10, 25, 50, 75, 90, 95, 99])
    r.update({
        "media": float(x.mean()), "mediana": float(q[4]), "minimo": float(x.min()), "maximo": float(x.max()),
        "rango": float(x.max() - x.min()), "q1": float(q[3]), "q3": float(q[5]), "iqr": float(q[5] - q[3]),
        "percentiles": {p: float(v) for p, v in zip((1, 5, 10, 25, 50, 75, 90, 95, 99), q)},
        "varianza_poblacional": float(x.var(ddof=0)), "desviacion_poblacional": float(x.std(ddof=0)),
        "varianza_muestral": float(x.var(ddof=1)) if n > 1 else None,
        "desviacion_muestral": float(x.std(ddof=1)) if n > 1 else None,
        "suma": float(x.sum()),
    })
    r["coef_variacion"] = float(r["desviacion_poblacional"] / abs(r["media"])) if r["media"] else None
    r["asimetria"] = float(st.skew(x, bias=False)) if n > 2 and x.std() > 0 else None
    r["curtosis"] = float(st.kurtosis(x, bias=False)) if n > 3 and x.std() > 0 else None
    r["media_menos_mediana"] = r["media"] - r["mediana"]
    if n < 30:
        r["avisos"].append(f"Pocas observaciones (n = {n}): los cuantiles y la forma de la distribución son inestables.")
    if w is not None:
        mw = float(np.average(x, weights=w))
        r.update({
            "media_ponderada": mw,
            "mediana_ponderada": cuantil_ponderado(x, w, 0.5),
            "varianza_ponderada": float(np.average((x - mw) ** 2, weights=w)),
            "suma_pesos": float(w.sum()),
        })
        r["desviacion_ponderada"] = float(np.sqrt(r["varianza_ponderada"]))
    return r


def posicion(valor: float, x) -> dict:
    """Dónde cae un valor dentro de una distribución: percentil, z y desviación respecto a media y mediana."""
    x, _, _ = limpiar(x)
    if len(x) == 0 or valor is None or not np.isfinite(valor):
        return {"n": len(x)}
    sd = x.std(ddof=0)
    return {
        "n": len(x), "valor": float(valor),
        "percentil": float(st.percentileofscore(x, valor, kind="mean")),
        "media": float(x.mean()), "mediana": float(np.median(x)),
        "desvio_media": float(valor - x.mean()), "desvio_mediana": float(valor - np.median(x)),
        "z": float((valor - x.mean()) / sd) if sd > 0 else None,
    }
