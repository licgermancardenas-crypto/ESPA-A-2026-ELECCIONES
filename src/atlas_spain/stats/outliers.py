"""Detección de valores atípicos.

Una anomalía estadística indica que un valor se aleja del patrón del conjunto de referencia.
No implica por sí misma un error, una irregularidad ni un fraude.

Métodos:
- z:               z = (x − x̄) / σ                       umbral habitual |z| > 3
- z modificado:    M = 0,6745 (x − mediana) / MAD          umbral habitual |M| > 3,5 (Iglewicz y Hoaglin)
- IQR:             x < Q1 − k·IQR  o  x > Q3 + k·IQR       k habitual 1,5 (Tukey)
- Isolation Forest (opcional, requiere scikit-learn; solo en local)
"""

from __future__ import annotations

import numpy as np

from atlas_spain.stats.descriptive import limpiar

UMBRAL = {"z": 3.0, "z_modificado": 3.5, "iqr": 1.5}


def puntuar(x, metodo: str = "z_modificado", umbral: float | None = None) -> dict:
    """Devuelve la puntuación de cada observación (NaN donde falta el dato) y la máscara de atípicos."""
    xa = np.asarray(x, dtype=float)
    ok = np.isfinite(xa)
    v = xa[ok]
    u = UMBRAL.get(metodo, 0) if umbral is None else umbral
    score = np.full(len(xa), np.nan)
    ref = {}
    if len(v) < 3:
        return {"score": score, "atipico": np.zeros(len(xa), bool), "referencia": ref, "umbral": u,
                "avisos": ["Menos de 3 observaciones: no se buscan atípicos."]}
    if metodo == "z":
        m, s = v.mean(), v.std(ddof=0)
        ref = {"media": float(m), "desviacion": float(s)}
        score[ok] = (v - m) / s if s > 0 else 0.0
        at = np.abs(score) > u
    elif metodo == "z_modificado":
        med = np.median(v)
        mad = np.median(np.abs(v - med))
        ref = {"mediana": float(med), "mad": float(mad)}
        if mad == 0:  # más de la mitad de los valores iguales: se usa la desviación absoluta media (convención IBM/SPSS)
            meanad = np.mean(np.abs(v - med))
            score[ok] = (v - med) / (1.253314 * meanad) if meanad > 0 else 0.0
            ref["nota"] = "MAD = 0: se usa 1,2533 × desviación absoluta media."
        else:
            score[ok] = 0.6745 * (v - med) / mad
        at = np.abs(score) > u
    elif metodo == "iqr":
        q1, q3 = np.percentile(v, [25, 75])
        iqr = q3 - q1
        lo, hi = q1 - u * iqr, q3 + u * iqr
        ref = {"q1": float(q1), "q3": float(q3), "iqr": float(iqr), "limite_inf": float(lo), "limite_sup": float(hi)}
        # puntuación: distancia al límite en unidades de IQR (0 dentro del rango)
        d = np.where(v < lo, (v - lo), np.where(v > hi, (v - hi), 0.0))
        score[ok] = d / iqr if iqr > 0 else 0.0
        at = (xa < lo) | (xa > hi)
    elif metodo == "isolation_forest":
        from sklearn.ensemble import IsolationForest  # solo disponible en local
        f = IsolationForest(n_estimators=200, contamination="auto", random_state=0).fit(v.reshape(-1, 1))
        score[ok] = -f.score_samples(v.reshape(-1, 1))
        at = np.zeros(len(xa), bool)
        at[ok] = f.predict(v.reshape(-1, 1)) == -1
        ref = {"modelo": "IsolationForest(n_estimators=200, random_state=0)"}
    else:
        raise ValueError(f"Método desconocido: {metodo}")
    at = np.asarray(at) & ok
    return {"score": score, "atipico": at, "referencia": ref, "umbral": u, "avisos": []}


def detectar(ids, valores, metodo: str = "z_modificado", umbral: float | None = None, max_items: int = 200) -> dict:
    """Lista de atípicos ordenada por magnitud, con valor observado, referencia y desviación."""
    x, _, faltan = limpiar(valores)
    r = puntuar(valores, metodo, umbral)
    v = np.asarray(valores, dtype=float)
    centro = float(np.median(x)) if len(x) else None
    idx = np.where(r["atipico"])[0]
    idx = idx[np.argsort(-np.abs(r["score"][idx]))]
    items = [{"id": ids[i], "valor": float(v[i]), "referencia": centro, "desviacion": float(v[i] - centro),
              "score": float(r["score"][i])} for i in idx[:max_items]]
    return {"metodo": metodo, "umbral": r["umbral"], "n": len(x), "n_faltantes": faltan,
            "n_atipicos": int(len(idx)), "referencia": r["referencia"], "items": items, "avisos": r["avisos"]}
