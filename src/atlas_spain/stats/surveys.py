"""Encuestas: error muestral, efecto de diseño y comparación con la población de referencia.

Solo se calcula a partir de lo PUBLICADO en la ficha técnica. Si un dato no está publicado, el
resultado lo indica; no se supone. El margen de error clásico solo es válido para muestreo
aleatorio simple: muestras por cuotas o paneles online no tienen un error muestral bien definido.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as st


def error_estandar(p: float, n: int, deff: float = 1.0, N: int | None = None) -> float:
    """SE de una proporción con efecto de diseño y corrección por población finita opcional."""
    fpc = (N - n) / (N - 1) if N and N > n else 1.0
    return float(np.sqrt(deff * p * (1 - p) / n * fpc))


def margen_error(n: int, p: float = 0.5, confianza: float = 0.95, deff: float = 1.0, N: int | None = None) -> dict:
    z = st.norm.ppf(0.5 + confianza / 2)
    se = error_estandar(p, n, deff, N)
    return {"n": n, "p": p, "confianza": confianza, "deff": deff, "se": se, "margen": float(z * se),
            "supuesto": "Muestreo aleatorio simple ajustado por el efecto de diseño indicado."}


def kish(pesos) -> dict:
    """Tamaño efectivo y efecto de diseño por ponderación (Kish): n_ef = (Σw)² / Σw²; deff = n / n_ef."""
    w = np.asarray(pesos, float)
    w = w[np.isfinite(w) & (w > 0)]
    if len(w) == 0:
        return {"n": 0}
    nef = w.sum() ** 2 / (w ** 2).sum()
    return {"n": len(w), "n_efectivo": float(nef), "deff": float(len(w) / nef), "cv_pesos": float(w.std() / w.mean())}


def composicion(muestra: dict[str, float], poblacion: dict[str, float], n: int) -> dict:
    """Compara la composición de la muestra con la de la población (bondad de ajuste χ²).

    `muestra`: proporciones (o conteos) por categoría; `poblacion`: proporciones de referencia."""
    cats = [c for c in poblacion if c in muestra]
    m = np.array([muestra[c] for c in cats], float)
    m = m / m.sum()
    p = np.array([poblacion[c] for c in cats], float)
    p = p / p.sum()
    obs, esp = m * n, p * n
    chi2, pv = st.chisquare(obs, esp)
    return {"categorias": cats, "muestra": m.tolist(), "poblacion": p.tolist(), "diferencia_pp": ((m - p) * 100).tolist(),
            "chi2": float(chi2), "p": float(pv), "disimilitud": float(0.5 * np.abs(m - p).sum()),
            "nota": "Índice de disimilitud: proporción de la muestra que habría que redistribuir para igualar la población."}


def ficha_completa(ficha: dict) -> dict:
    """Comprueba qué campos de la ficha técnica están publicados (no se infiere ninguno)."""
    campos = ["instituto", "fecha_campo_inicio", "fecha_campo_fin", "tamano_muestra", "poblacion_objetivo", "ambito",
              "metodo_muestreo", "tecnica_recogida", "ponderacion", "margen_error_publicado", "nivel_confianza", "fuente_url"]
    faltan = [c for c in campos if not ficha.get(c)]
    return {"campos": campos, "faltan": faltan, "completitud": 1 - len(faltan) / len(campos)}
