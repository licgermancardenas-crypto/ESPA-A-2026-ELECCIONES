"""Métricas electorales que no estaban en el warehouse (las demás se leen de gold).

Ya calculadas en gold y reutilizadas: participación, abstención, voto por familia, ENEP, ENPP,
Gallagher, margen, competitividad y volatilidad de Pedersen. Aquí solo se añaden:

- Swing (cambio) de una familia: Δp = p_t − p_t−1, en puntos porcentuales.
- Swing de Butler entre dos fuerzas: ((p_A,t − p_A,t−1) − (p_B,t − p_B,t−1)) / 2.
- Concentración (Herfindahl-Hirschman): HHI = Σ p_i²  (ENEP = 1 / HHI).
- Fragmentación de Rae: F = 1 − Σ p_i².
- Cambio de participación: Δ = participación_t − participación_t−1.
"""

from __future__ import annotations

import numpy as np


def swing(p_t, p_t1):
    return np.asarray(p_t, float) - np.asarray(p_t1, float)


def swing_butler(a_t, a_t1, b_t, b_t1):
    return ((np.asarray(a_t, float) - a_t1) - (np.asarray(b_t, float) - b_t1)) / 2


def hhi(cuotas) -> float:
    p = np.asarray([c for c in cuotas if c is not None and np.isfinite(c)], float)
    return float((p ** 2).sum()) if len(p) else float("nan")


def rae(cuotas) -> float:
    return 1 - hhi(cuotas)
