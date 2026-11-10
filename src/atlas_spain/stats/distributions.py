"""Distribuciones: histograma, densidad (KDE), distribución acumulada y diagrama de caja."""

from __future__ import annotations

import numpy as np
from scipy import stats as st

from atlas_spain.stats.descriptive import limpiar


def histograma(x, intervalos="fd", rango=None, densidad=False) -> dict:
    """`intervalos`: entero o regla de numpy ('fd' Freedman-Diaconis, 'sturges', 'scott', 'auto')."""
    x, _, faltan = limpiar(x)
    if len(x) == 0:
        return {"n": 0, "n_faltantes": faltan, "bordes": [], "conteos": []}
    if isinstance(intervalos, str) and np.ptp(x) == 0:
        intervalos = 1
    bordes = np.histogram_bin_edges(x, bins=intervalos, range=rango)
    if len(bordes) > 201:  # acotar reglas automáticas con colas muy largas
        bordes = np.histogram_bin_edges(x, bins=200, range=rango)
    conteos, bordes = np.histogram(x, bins=bordes, range=rango, density=densidad)
    return {"n": len(x), "n_faltantes": faltan, "bordes": bordes.tolist(),
            "conteos": conteos.tolist(), "regla": intervalos if isinstance(intervalos, str) else "fijo"}


def densidad(x, puntos: int = 200, ancho=None) -> dict:
    """Estimación de densidad por núcleo gaussiano (ancho de banda de Scott salvo que se indique)."""
    x, _, faltan = limpiar(x)
    if len(x) < 3 or np.ptp(x) == 0:
        return {"n": len(x), "n_faltantes": faltan, "x": [], "y": [], "avisos": ["Datos insuficientes para estimar la densidad."]}
    k = st.gaussian_kde(x, bw_method=ancho)
    pad = 0.05 * np.ptp(x)
    grid = np.linspace(x.min() - pad, x.max() + pad, puntos)
    return {"n": len(x), "n_faltantes": faltan, "x": grid.tolist(), "y": k(grid).tolist(), "ancho_banda": float(k.factor)}


def acumulada(x) -> dict:
    """Distribución acumulada empírica (ECDF)."""
    x, _, faltan = limpiar(x)
    xs = np.sort(x)
    return {"n": len(xs), "n_faltantes": faltan, "x": xs.tolist(), "y": (np.arange(1, len(xs) + 1) / max(len(xs), 1)).tolist()}


def caja(x, k: float = 1.5) -> dict:
    """Estadísticos del diagrama de caja de Tukey: bigotes en el último dato dentro de Q1 − k·IQR y Q3 + k·IQR."""
    x, _, faltan = limpiar(x)
    if len(x) == 0:
        return {"n": 0, "n_faltantes": faltan}
    q1, med, q3 = np.percentile(x, [25, 50, 75])
    iqr = q3 - q1
    lo, hi = q1 - k * iqr, q3 + k * iqr
    dentro = x[(x >= lo) & (x <= hi)]
    return {"n": len(x), "n_faltantes": faltan, "q1": float(q1), "mediana": float(med), "q3": float(q3),
            "bigote_inf": float(dentro.min()), "bigote_sup": float(dentro.max()),
            "n_atipicos": int(((x < lo) | (x > hi)).sum()), "k": k}
