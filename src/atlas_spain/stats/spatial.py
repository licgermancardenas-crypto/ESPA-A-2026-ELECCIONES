"""Estadística espacial: I de Moran global y local (LISA) con inferencia por permutaciones.

Pesos: contigüidad (reina) entre municipios de la geografía vigente, estandarizados por filas.
Los vecinos se precalculan una vez con libpysal (local) y se guardan como listas; el cálculo de
Moran usa solo numpy, por eso funciona también en la función publicada.

I global = (n / S0) · Σ_i Σ_j w_ij z_i z_j / Σ_i z_i²           (con filas estandarizadas S0 = n)
I_i local = (z_i / m2) · Σ_j w_ij z_j,   m2 = Σ z_i² / (n − 1)   (convención de PySAL/esda)
Cuadrantes LISA: Alto-Alto, Bajo-Bajo, Alto-Bajo, Bajo-Alto (según z_i y su retardo espacial).
"""

from __future__ import annotations

import numpy as np


def _filas(vecinos: list[list[int]], validos: np.ndarray):
    """Vecinos restringidos a observaciones válidas, reindexados, y matriz W dispersa estandarizada por filas."""
    from scipy import sparse
    nuevo = -np.ones(len(vecinos), int)
    idx = np.where(validos)[0]
    nuevo[idx] = np.arange(len(idx))
    out, filas_i, cols = [], [], []
    for r, i in enumerate(idx):
        v = np.array([nuevo[j] for j in vecinos[i] if validos[j]], int)
        out.append(v)
        filas_i.extend([r] * len(v))
        cols.extend(v.tolist())
    k = np.array([len(v) for v in out], float)
    datos = np.repeat(np.where(k > 0, 1 / np.maximum(k, 1), 0), k.astype(int))
    W = sparse.csr_matrix((datos, (filas_i, cols)), shape=(len(idx), len(idx)))
    return out, W


def _retardo(z, W):
    return W @ z


def moran_global(valores, vecinos: list[list[int]], permutaciones: int = 999, semilla: int = 0) -> dict:
    x = np.asarray(valores, float)
    ok = np.isfinite(x)
    filas, W = _filas(vecinos, ok)
    con = np.array([len(v) > 0 for v in filas])
    z = x[ok] - x[ok].mean()
    n = len(z)
    if n < 10 or (z ** 2).sum() == 0:
        return {"n": n, "I": None, "avisos": ["Observaciones insuficientes o sin variación."]}
    lag = _retardo(z, W)
    s0 = con.sum()
    I = float((n / s0) * (z * lag)[con].sum() / (z ** 2).sum())
    rng = np.random.default_rng(semilla)
    sim = np.empty(permutaciones)
    for k in range(permutaciones):
        zp = rng.permutation(z)
        sim[k] = (n / s0) * (zp * _retardo(zp, W))[con].sum() / (zp ** 2).sum()
    p = float((1 + (np.abs(sim - sim.mean()) >= abs(I - sim.mean())).sum()) / (permutaciones + 1))
    return {"n": n, "n_faltantes": int((~ok).sum()), "n_aislados": int((~con).sum()), "I": I, "esperanza": -1 / (n - 1),
            "p_permutacion": p, "permutaciones": permutaciones, "semilla": semilla,
            "z": float((I - sim.mean()) / sim.std()) if sim.std() > 0 else None,
            "interpretacion": ("Valores parecidos tienden a agruparse en el espacio." if I > 0 else
                               "Valores distintos tienden a ser vecinos.") + (" (significativo)" if p < 0.05 else " (no significativo)")}


def moran_local(valores, vecinos: list[list[int]], permutaciones: int = 499, alfa: float = 0.05, semilla: int = 0) -> dict:
    """LISA con permutación condicional (se fija i y se permutan los demás valores)."""
    x = np.asarray(valores, float)
    ok = np.isfinite(x)
    filas, W = _filas(vecinos, ok)
    z = x[ok] - x[ok].mean()
    n = len(z)
    m2 = (z ** 2).sum() / (n - 1)
    lag = _retardo(z, W)
    Ii = z * lag / m2
    rng = np.random.default_rng(semilla)
    p = np.ones(n)
    k = np.array([len(v) for v in filas])
    if k.max() > 0:
        # como esda: una matriz de índices aleatorios (sin reemplazo sobre las n−1 posiciones distintas de i)
        # compartida por todos los i; se salta la posición i desplazando los índices ≥ i
        R = np.array([rng.choice(n - 1, k.max(), replace=False) for _ in range(permutaciones)])
        for kk in np.unique(k[k > 0]):
            sel = np.where(k == kk)[0]
            Rk = R[:, :kk]
            for c in range(0, len(sel), 256):
                ii = sel[c:c + 256]
                adj = Rk[None, :, :] + (Rk[None, :, :] >= ii[:, None, None])
                sims = z[adj].mean(axis=2) * z[ii][:, None] / m2
                obs = Ii[ii][:, None]
                med = np.median(sims, axis=1, keepdims=True)
                mayor = np.where(obs >= med, (sims >= obs).sum(1, keepdims=True), (sims <= obs).sum(1, keepdims=True))
                p[ii] = (mayor[:, 0] + 1) / (permutaciones + 1)
    cuad = np.where(z > 0, np.where(lag > 0, "Alto-Alto", "Alto-Bajo"), np.where(lag > 0, "Bajo-Alto", "Bajo-Bajo"))
    cuad = np.where(p < alfa, cuad, "No significativo")
    salida = np.full(len(x), None, dtype=object)
    salida[ok] = cuad
    Iout = np.full(len(x), np.nan)
    Iout[ok] = Ii
    pout = np.full(len(x), np.nan)
    pout[ok] = p
    resumen = {c: int((cuad == c).sum()) for c in ("Alto-Alto", "Bajo-Bajo", "Alto-Bajo", "Bajo-Alto", "No significativo")}
    return {"n": n, "alfa": alfa, "permutaciones": permutaciones, "semilla": semilla, "I": Iout, "p": pout, "cuadrante": salida,
            "resumen": resumen,
            "nota": "Con miles de pruebas simultáneas, algunos territorios aparecen significativos por azar (≈ α·n)."}
