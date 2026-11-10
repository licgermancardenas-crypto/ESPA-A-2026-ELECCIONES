"""Regresión: MCO (simple y múltiple), logística, Poisson, ridge y lasso, con diagnósticos.

Implementación propia con numpy/scipy (validada contra statsmodels y scikit-learn en los tests).
Las regresiones con datos observacionales describen asociaciones condicionales: no prueban causalidad.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as st

ADVERTENCIAS = [
    "Modelo observacional: los coeficientes describen asociaciones condicionales, no efectos causales.",
    "Datos agregados por territorio: no se pueden trasladar a personas (falacia ecológica).",
    "Los residuos de territorios vecinos suelen estar correlacionados (autocorrelación espacial): los errores estándar pueden subestimarse.",
]


def _matriz(y, X: dict[str, np.ndarray], constante=True):
    nombres = list(X)
    cols = [np.asarray(X[k], float) for k in nombres]
    y = np.asarray(y, float)
    ok = np.isfinite(y)
    for c in cols:
        ok &= np.isfinite(c)
    M = np.column_stack(cols)[ok] if cols else np.empty((ok.sum(), 0))
    if constante:
        M = np.column_stack([np.ones(ok.sum()), M])
        nombres = ["constante"] + nombres
    return y[ok], M, nombres, int((~ok).sum()), ok


def _tabla(nombres, beta, se, gl, confianza, dist="t"):
    q = st.t.ppf(0.5 + confianza / 2, gl) if dist == "t" else st.norm.ppf(0.5 + confianza / 2)
    stat = beta / se
    p = 2 * (st.t.sf(np.abs(stat), gl) if dist == "t" else st.norm.sf(np.abs(stat)))
    return [{"variable": n, "coef": float(b), "se": float(s), "estadistico": float(t), "p": float(pp),
             "ic": [float(b - q * s), float(b + q * s)]} for n, b, s, t, pp in zip(nombres, beta, se, stat, p)]


def mco(y, X: dict, robusto: str | None = "HC3", confianza=0.95) -> dict:
    """Mínimos cuadrados ordinarios. `robusto`: None (clásico) o 'HC3' (heterocedasticidad)."""
    y, M, nombres, faltan, ok = _matriz(y, X)
    n, k = M.shape
    r = {"modelo": "MCO", "n": n, "n_faltantes": faltan, "variables": nombres, "advertencias": ADVERTENCIAS, "avisos": []}
    if n <= k + 1:
        r["avisos"].append("Observaciones insuficientes para el número de variables.")
        return r
    XtX_inv = np.linalg.pinv(M.T @ M)
    beta = XtX_inv @ M.T @ y
    yhat = M @ beta
    e = y - yhat
    gl = n - k
    s2 = e @ e / gl
    h = np.einsum("ij,jk,ik->i", M, XtX_inv, M)  # apalancamiento
    if robusto == "HC3":
        w = (e / (1 - np.clip(h, 0, 0.999999))) ** 2
        cov = XtX_inv @ (M.T * w) @ M @ XtX_inv
    else:
        cov = s2 * XtX_inv
    se = np.sqrt(np.diag(cov))
    sst = ((y - y.mean()) ** 2).sum()
    r2 = 1 - (e @ e) / sst if sst > 0 else None
    r2a = 1 - (1 - r2) * (n - 1) / gl if r2 is not None else None
    ll = -n / 2 * (np.log(2 * np.pi) + np.log(e @ e / n) + 1)
    f = ((sst - e @ e) / (k - 1)) / s2 if k > 1 and s2 > 0 else None
    r.update(coeficientes=_tabla(nombres, beta, se, gl, confianza), errores=robusto or "clásicos", confianza=confianza,
             r2=r2 and float(r2), r2_ajustado=r2a and float(r2a), gl_residuos=int(gl),
             f=f and float(f), p_f=float(st.f.sf(f, k - 1, gl)) if f else None,
             aic=float(2 * k - 2 * ll), bic=float(k * np.log(n) - 2 * ll), sigma=float(np.sqrt(s2)),
             diagnosticos=_diagnosticos(M, e, h, s2, nombres))
    r["_beta"], r["_cov"], r["_mask"] = beta, cov, ok
    return r


def _diagnosticos(M, e, h, s2, nombres) -> dict:
    n, k = M.shape
    jb = st.jarque_bera(e)
    dw = float(np.sum(np.diff(e) ** 2) / np.sum(e ** 2))
    # Breusch-Pagan (versión de Koenker): n·R² de e² sobre X
    e2 = e ** 2
    g = np.linalg.lstsq(M, e2, rcond=None)[0]
    r2a = 1 - ((e2 - M @ g) ** 2).sum() / ((e2 - e2.mean()) ** 2).sum()
    bp = n * r2a
    cook = (e ** 2 / (k * s2)) * h / (1 - h) ** 2
    vif = {}
    for j in range(1, k):
        otras = np.delete(M, j, axis=1)
        res = M[:, j] - otras @ np.linalg.lstsq(otras, M[:, j], rcond=None)[0]
        r2j = 1 - (res @ res) / ((M[:, j] - M[:, j].mean()) ** 2).sum()
        vif[nombres[j]] = float(1 / (1 - r2j)) if r2j < 1 else None
    resid = np.sort(e)
    teor = st.norm.ppf((np.arange(1, n + 1) - 0.5) / n) * np.sqrt(s2)
    paso = max(1, n // 400)
    return {
        "jarque_bera": {"estadistico": float(jb.statistic), "p": float(jb.pvalue), "contrasta": "normalidad de los residuos"},
        "breusch_pagan": {"estadistico": float(bp), "gl": k - 1, "p": float(st.chi2.sf(bp, k - 1)), "contrasta": "homocedasticidad"},
        "durbin_watson": {"estadistico": dw, "nota": "≈2 sin autocorrelación de orden 1 (según el orden de las filas)"},
        "vif": vif,
        "cook_max": float(np.nanmax(cook)), "n_influyentes": int((cook > 4 / n).sum()),
        "qq": {"teorico": teor[::paso].tolist(), "observado": resid[::paso].tolist()},
    }


def prediccion(modelo: dict, Xnuevo: dict, confianza=0.95) -> dict:
    """Intervalo de confianza (de la media) y de predicción (de una nueva observación) para MCO."""
    nombres = modelo["variables"]
    x = np.array([1.0] + [float(Xnuevo[k]) for k in nombres[1:]])
    beta, cov = modelo["_beta"], modelo["_cov"]
    yhat = float(x @ beta)
    se_m = float(np.sqrt(x @ cov @ x))
    se_p = float(np.sqrt(se_m ** 2 + modelo["sigma"] ** 2))
    t = st.t.ppf(0.5 + confianza / 2, modelo["gl_residuos"])
    return {"prediccion": yhat, "ic_media": [yhat - t * se_m, yhat + t * se_m], "ic_prediccion": [yhat - t * se_p, yhat + t * se_p],
            "nota": "El intervalo de predicción es más ancho: incluye la variabilidad de una observación individual."}


def _irls(y, M, familia, offset=None, iter_max=100, tol=1e-10):
    n, k = M.shape
    off = np.zeros(n) if offset is None else offset
    beta = np.zeros(k)
    if familia == "poisson":
        beta[0] = np.log(max(y.mean(), 1e-8))
    for it in range(iter_max):
        eta = M @ beta + off
        if familia == "logit":
            mu = 1 / (1 + np.exp(-eta))
            w = np.clip(mu * (1 - mu), 1e-12, None)
        else:
            mu = np.exp(eta)
            w = np.clip(mu, 1e-12, None)
        z = eta - off + (y - mu) / w
        nueva = np.linalg.solve(M.T @ (M * w[:, None]), M.T @ (w * z))
        if np.max(np.abs(nueva - beta)) < tol:
            beta = nueva
            break
        beta = nueva
    eta = M @ beta + off
    mu = 1 / (1 + np.exp(-eta)) if familia == "logit" else np.exp(eta)
    w = mu * (1 - mu) if familia == "logit" else mu
    cov = np.linalg.pinv(M.T @ (M * w[:, None]))
    return beta, cov, mu, it + 1


def logistica(y, X: dict, confianza=0.95) -> dict:
    """Regresión logística (y ∈ {0, 1}). Coeficientes en log-odds y razones de odds."""
    y, M, nombres, faltan, _ = _matriz(y, X)
    r = {"modelo": "Logística", "n": len(y), "n_faltantes": faltan, "variables": nombres, "advertencias": ADVERTENCIAS, "avisos": []}
    if not set(np.unique(y)) <= {0.0, 1.0} or len(np.unique(y)) < 2:
        r["avisos"].append("La variable dependiente debe ser binaria (0/1) con ambos valores presentes.")
        return r
    beta, cov, mu, it = _irls(y, M, "logit")
    ll = float(np.sum(y * np.log(np.clip(mu, 1e-15, 1)) + (1 - y) * np.log(np.clip(1 - mu, 1e-15, 1))))
    p0 = y.mean()
    ll0 = float(len(y) * (p0 * np.log(p0) + (1 - p0) * np.log(1 - p0)))
    tabla = _tabla(nombres, beta, np.sqrt(np.diag(cov)), None, confianza, dist="z")
    for t in tabla:
        t["odds_ratio"] = float(np.exp(t["coef"]))
        t["ic_odds_ratio"] = [float(np.exp(t["ic"][0])), float(np.exp(t["ic"][1]))]
    k = len(beta)
    r.update(coeficientes=tabla, iteraciones=it, log_verosimilitud=ll, pseudo_r2_mcfadden=1 - ll / ll0,
             aic=2 * k - 2 * ll, bic=k * np.log(len(y)) - 2 * ll, confianza=confianza,
             exactitud=float(((mu >= 0.5) == (y == 1)).mean()))
    return r


def poisson(y, X: dict, exposicion=None, confianza=0.95) -> dict:
    """Regresión de Poisson para conteos; `exposicion` entra como offset log(exposición)."""
    nombres_x = dict(X)
    if exposicion is not None:
        nombres_x["__exp"] = exposicion
    y, M, nombres, faltan, ok = _matriz(y, nombres_x)
    off = None
    if exposicion is not None:
        off = np.log(M[:, -1])
        M, nombres = M[:, :-1], nombres[:-1]
    r = {"modelo": "Poisson", "n": len(y), "n_faltantes": faltan, "variables": nombres, "advertencias": ADVERTENCIAS, "avisos": []}
    if (y < 0).any():
        r["avisos"].append("La variable dependiente debe ser un conteo no negativo.")
        return r
    beta, cov, mu, it = _irls(y, M, "poisson", off)
    disp = float(np.sum((y - mu) ** 2 / mu) / (len(y) - len(beta)))
    tabla = _tabla(nombres, beta, np.sqrt(np.diag(cov)), None, confianza, dist="z")
    for t in tabla:
        t["razon_tasas"] = float(np.exp(t["coef"]))
    if disp > 1.5:
        r["avisos"].append(f"Sobredispersión (φ = {disp:.1f}): los errores estándar de Poisson son optimistas.")
    r.update(coeficientes=tabla, iteraciones=it, dispersion=disp, confianza=confianza)
    return r


def penalizada(y, X: dict, tipo="ridge", alfa=1.0, iter_max=5000, tol=1e-8) -> dict:
    """Ridge o lasso sobre variables estandarizadas (coeficientes en escala original y estandarizada).

    Objetivo (convención de scikit-learn): ridge ‖y − Xβ‖² + α‖β‖²; lasso (1/2n)‖y − Xβ‖² + α‖β‖₁."""
    y, M, nombres, faltan, _ = _matriz(y, X, constante=False)
    n, k = M.shape
    mu, sd = M.mean(0), M.std(0)
    sd[sd == 0] = 1
    Z = (M - mu) / sd
    yc = y - y.mean()
    if tipo == "ridge":
        b = np.linalg.solve(Z.T @ Z + alfa * np.eye(k), Z.T @ yc)
    else:  # lasso: descenso por coordenadas
        b = np.zeros(k)
        cn = (Z ** 2).sum(0) / n
        for _ in range(iter_max):
            viejo = b.copy()
            for j in range(k):
                rj = yc - Z @ b + Z[:, j] * b[j]
                rho = Z[:, j] @ rj / n
                b[j] = np.sign(rho) * max(abs(rho) - alfa, 0) / cn[j]
            if np.max(np.abs(b - viejo)) < tol:
                break
    orig = b / sd
    inter = y.mean() - orig @ mu
    e = y - (M @ orig + inter)
    r2 = 1 - (e @ e) / ((y - y.mean()) ** 2).sum()
    return {"modelo": tipo.capitalize(), "alfa": alfa, "n": n, "n_faltantes": faltan, "r2": float(r2),
            "coeficientes": [{"variable": "constante", "coef": float(inter), "coef_estandarizado": None}] +
                            [{"variable": nm, "coef": float(o), "coef_estandarizado": float(s)} for nm, o, s in zip(nombres, orig, b)],
            "nota": "Sin errores estándar: la penalización sesga los coeficientes a propósito para mejorar la predicción.",
            "advertencias": ADVERTENCIAS}


def limpiar_salida(modelo: dict) -> dict:
    """Quita los campos internos (arrays) antes de serializar."""
    return {k: v for k, v in modelo.items() if not k.startswith("_")}
