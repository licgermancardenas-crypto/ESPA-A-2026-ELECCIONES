"""Inferencia: contrastes de hipótesis, intervalos de confianza y correcciones múltiples.

Cada contraste devuelve hipótesis nula y alternativa, estadístico, grados de libertad, valor p,
nivel de significación, tamaño del efecto, supuestos e interpretación en lenguaje llano.

Nota sobre datos territoriales: cuando se comparan TODOS los municipios de dos grupos no hay
muestreo; el contraste responde a si la diferencia es grande respecto a la variabilidad interna
(modelo de superpoblación). Se indica en `supuestos`.
"""

from __future__ import annotations

import numpy as np
from scipy import stats as st

from atlas_spain.stats.descriptive import limpiar

SUPERPOBLACION = ("Si los grupos incluyen todos los territorios (no una muestra), el valor p se interpreta "
                  "bajo un modelo de superpoblación: mide si la diferencia supera lo esperable por variabilidad interna.")


def _interpretar(p, alfa, h1):
    if p is None:
        return "No se pudo calcular."
    if p < alfa:
        return f"Con α = {alfa}, se rechaza H₀: los datos son compatibles con {h1}."
    return f"Con α = {alfa}, no se rechaza H₀: no hay evidencia suficiente de que {h1}."


# ─────────── intervalos de confianza ───────────
def ic_media(x, confianza=0.95) -> dict:
    x, _, faltan = limpiar(x)
    n = len(x)
    if n < 2:
        return {"n": n, "media": float(x.mean()) if n else None, "ic": None}
    m, se = x.mean(), x.std(ddof=1) / np.sqrt(n)
    t = st.t.ppf(0.5 + confianza / 2, n - 1)
    return {"n": n, "n_faltantes": faltan, "media": float(m), "se": float(se), "confianza": confianza,
            "ic": [float(m - t * se), float(m + t * se)], "metodo": "t de Student"}


def ic_proporcion(k: int, n: int, confianza=0.95, metodo="wilson") -> dict:
    """Wilson (por defecto, buen comportamiento con p extremos y n pequeño) o Wald."""
    if n <= 0:
        return {"n": n, "p": None, "ic": None}
    p = k / n
    z = st.norm.ppf(0.5 + confianza / 2)
    if metodo == "wald":
        se = np.sqrt(p * (1 - p) / n)
        ic = [p - z * se, p + z * se]
    else:
        den = 1 + z * z / n
        c = (p + z * z / (2 * n)) / den
        h = z * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
        ic = [c - h, c + h]
    return {"n": n, "k": k, "p": p, "confianza": confianza, "ic": [float(max(0, ic[0])), float(min(1, ic[1]))], "metodo": metodo}


def ic_bootstrap(x, estadistico=np.mean, B=2000, confianza=0.95, semilla=0) -> dict:
    """Bootstrap percentil con semilla fija (reproducible)."""
    x, _, faltan = limpiar(x)
    if len(x) < 2:
        return {"n": len(x), "ic": None}
    rng = np.random.default_rng(semilla)
    reps = np.array([estadistico(rng.choice(x, len(x), replace=True)) for _ in range(B)])
    a = (1 - confianza) / 2
    return {"n": len(x), "n_faltantes": faltan, "estimacion": float(estadistico(x)), "B": B, "semilla": semilla,
            "confianza": confianza, "ic": [float(np.quantile(reps, a)), float(np.quantile(reps, 1 - a))],
            "se": float(reps.std(ddof=1)), "metodo": "bootstrap percentil"}


# ─────────── contrastes ───────────
def t_dos_grupos(a, b, alfa=0.05, varianzas_iguales=False, confianza=0.95) -> dict:
    a, _, fa = limpiar(a)
    b, _, fb = limpiar(b)
    r = {"prueba": "t de Welch" if not varianzas_iguales else "t de Student", "alfa": alfa,
         "h0": "las medias de ambos grupos son iguales", "h1": "las medias de ambos grupos difieren",
         "n": [len(a), len(b)], "n_faltantes": fa + fb}
    if len(a) < 2 or len(b) < 2:
        r.update(estadistico=None, p=None, interpretacion="Cada grupo necesita al menos 2 observaciones.")
        return r
    t, p = st.ttest_ind(a, b, equal_var=varianzas_iguales)
    va, vb = a.var(ddof=1), b.var(ddof=1)
    na, nb = len(a), len(b)
    if varianzas_iguales:
        gl = na + nb - 2
        se = np.sqrt(((na - 1) * va + (nb - 1) * vb) / gl * (1 / na + 1 / nb))
    else:
        se = np.sqrt(va / na + vb / nb)
        gl = (va / na + vb / nb) ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    dif = a.mean() - b.mean()
    tc = st.t.ppf(0.5 + confianza / 2, gl)
    sp = np.sqrt(((na - 1) * va + (nb - 1) * vb) / (na + nb - 2))
    d = dif / sp if sp > 0 else None
    g = d * (1 - 3 / (4 * (na + nb) - 9)) if d is not None else None
    r.update(estadistico=float(t), gl=float(gl), p=float(p), medias=[float(a.mean()), float(b.mean())],
             diferencia=float(dif), ic_diferencia=[float(dif - tc * se), float(dif + tc * se)], confianza=confianza,
             efecto={"d_cohen": d and float(d), "g_hedges": g and float(g), "magnitud": _mag_d(g)},
             supuestos=["Observaciones independientes.", "Distribución aproximadamente normal de cada grupo o n grande (TCL).",
                        "Welch no asume varianzas iguales." if not varianzas_iguales else "Varianzas iguales.", SUPERPOBLACION],
             interpretacion=_interpretar(float(p), alfa, "las medias difieren"))
    return r


def _mag_d(d):
    if d is None:
        return None
    a = abs(d)
    return "despreciable" if a < 0.2 else "pequeño" if a < 0.5 else "mediano" if a < 0.8 else "grande"


def mann_whitney(a, b, alfa=0.05) -> dict:
    a, _, fa = limpiar(a)
    b, _, fb = limpiar(b)
    r = {"prueba": "U de Mann-Whitney", "alfa": alfa, "n": [len(a), len(b)], "n_faltantes": fa + fb,
         "h0": "las distribuciones de ambos grupos son iguales",
         "h1": "un grupo tiende a tomar valores mayores que el otro"}
    if len(a) < 1 or len(b) < 1:
        r.update(estadistico=None, p=None)
        return r
    u, p = st.mannwhitneyu(a, b, alternative="two-sided")
    rb = 1 - 2 * u / (len(a) * len(b))  # correlación biserial de rangos (signo: grupo b mayor > 0)
    r.update(estadistico=float(u), p=float(p), medianas=[float(np.median(a)), float(np.median(b))],
             efecto={"r_biserial_rangos": float(-rb)}, supuestos=["Observaciones independientes.", "No asume normalidad.", SUPERPOBLACION],
             interpretacion=_interpretar(float(p), alfa, "un grupo tiende a valores mayores"))
    return r


def anova(grupos: dict[str, np.ndarray], alfa=0.05) -> dict:
    gs = {k: limpiar(v)[0] for k, v in grupos.items()}
    gs = {k: v for k, v in gs.items() if len(v) >= 2}
    r = {"prueba": "ANOVA de un factor", "alfa": alfa, "grupos": list(gs), "n": [len(v) for v in gs.values()],
         "h0": "todas las medias de grupo son iguales", "h1": "al menos una media de grupo difiere"}
    if len(gs) < 2:
        r.update(estadistico=None, p=None, interpretacion="Se necesitan al menos 2 grupos con 2 observaciones.")
        return r
    f, p = st.f_oneway(*gs.values())
    todo = np.concatenate(list(gs.values()))
    ssb = sum(len(v) * (v.mean() - todo.mean()) ** 2 for v in gs.values())
    sst = ((todo - todo.mean()) ** 2).sum()
    k, N = len(gs), len(todo)
    lev = st.levene(*gs.values())
    r.update(estadistico=float(f), gl=[k - 1, N - k], p=float(p), medias={g: float(v.mean()) for g, v in gs.items()},
             efecto={"eta2": float(ssb / sst) if sst > 0 else None},
             levene={"estadistico": float(lev.statistic), "p": float(lev.pvalue)},
             supuestos=["Observaciones independientes.", "Normalidad aproximada dentro de cada grupo.",
                        "Varianzas homogéneas (ver prueba de Levene; si p < 0,05 usar Kruskal-Wallis).", SUPERPOBLACION],
             interpretacion=_interpretar(float(p), alfa, "al menos una media difiere"))
    return r


def kruskal(grupos: dict[str, np.ndarray], alfa=0.05) -> dict:
    gs = {k: limpiar(v)[0] for k, v in grupos.items()}
    gs = {k: v for k, v in gs.items() if len(v) >= 1}
    r = {"prueba": "H de Kruskal-Wallis", "alfa": alfa, "grupos": list(gs), "n": [len(v) for v in gs.values()],
         "h0": "todas las distribuciones de grupo son iguales", "h1": "al menos un grupo tiende a valores distintos"}
    if len(gs) < 2:
        r.update(estadistico=None, p=None)
        return r
    h, p = st.kruskal(*gs.values())
    N = sum(len(v) for v in gs.values())
    r.update(estadistico=float(h), gl=len(gs) - 1, p=float(p), medianas={g: float(np.median(v)) for g, v in gs.items()},
             efecto={"epsilon2": float(h / ((N * N - 1) / (N + 1)))}, supuestos=["Observaciones independientes.", "No asume normalidad.", SUPERPOBLACION],
             interpretacion=_interpretar(float(p), alfa, "al menos un grupo difiere"))
    return r


def proporciones(k1: int, n1: int, k2: int, n2: int, alfa=0.05, confianza=0.95) -> dict:
    """Prueba z de dos proporciones (H₀ con proporción combinada) e IC de Wald para la diferencia."""
    r = {"prueba": "z de dos proporciones", "alfa": alfa, "n": [n1, n2],
         "h0": "las dos proporciones son iguales", "h1": "las dos proporciones difieren"}
    if min(n1, n2) <= 0:
        r.update(estadistico=None, p=None)
        return r
    p1, p2 = k1 / n1, k2 / n2
    pc = (k1 + k2) / (n1 + n2)
    se0 = np.sqrt(pc * (1 - pc) * (1 / n1 + 1 / n2))
    z = (p1 - p2) / se0 if se0 > 0 else 0.0
    p = float(2 * st.norm.sf(abs(z)))
    se = np.sqrt(p1 * (1 - p1) / n1 + p2 * (1 - p2) / n2)
    zc = st.norm.ppf(0.5 + confianza / 2)
    h = 2 * np.arcsin(np.sqrt(p1)) - 2 * np.arcsin(np.sqrt(p2))
    r.update(estadistico=float(z), p=p, proporciones=[p1, p2], diferencia=p1 - p2,
             ic_diferencia=[float(p1 - p2 - zc * se), float(p1 - p2 + zc * se)], confianza=confianza,
             efecto={"h_cohen": float(h)}, supuestos=["Muestras aleatorias independientes.", "n·p y n·(1−p) ≥ 5 en ambos grupos."],
             interpretacion=_interpretar(p, alfa, "las proporciones difieren"))
    return r


def chi_cuadrado(tabla, alfa=0.05) -> dict:
    """Independencia en una tabla de contingencia (conteos). Incluye V de Cramér y frecuencias esperadas."""
    t = np.asarray(tabla, float)
    r = {"prueba": "χ² de independencia", "alfa": alfa,
         "h0": "las dos variables categóricas son independientes", "h1": "las variables están asociadas"}
    if t.ndim != 2 or min(t.shape) < 2 or t.sum() == 0:
        r.update(estadistico=None, p=None)
        return r
    chi2, p, gl, esp = st.chi2_contingency(t, correction=False)
    n = t.sum()
    v = np.sqrt(chi2 / (n * (min(t.shape) - 1)))
    bajas = float((esp < 5).mean())
    r.update(estadistico=float(chi2), gl=int(gl), p=float(p), n=int(n), esperadas=esp.tolist(),
             efecto={"v_cramer": float(v)},
             supuestos=["Conteos de unidades independientes.", f"Frecuencias esperadas ≥ 5 (celdas por debajo: {bajas:.0%})."],
             interpretacion=_interpretar(float(p), alfa, "las variables están asociadas"))
    return r


def contingencia(a, b) -> dict:
    """Tabla de contingencia con probabilidades conjunta, marginales y condicionales.

    P(A=a | B=b) = P(A=a, B=b) / P(B=b). Siempre se informan los denominadores."""
    a, b = np.asarray(a, dtype=object), np.asarray(b, dtype=object)
    ok = np.array([x is not None and y is not None for x, y in zip(a, b)])
    a, b = a[ok], b[ok]
    fa, fb = sorted(set(a)), sorted(set(b))
    t = np.array([[np.sum((a == x) & (b == y)) for y in fb] for x in fa], float)
    n = t.sum()
    return {"filas": fa, "columnas": fb, "n": int(n), "conteos": t.astype(int).tolist(),
            "conjunta": (t / n).tolist() if n else None,
            "marginal_filas": (t.sum(1) / n).tolist() if n else None,
            "marginal_columnas": (t.sum(0) / n).tolist() if n else None,
            "condicional_fila_dado_columna": (t / np.where(t.sum(0) == 0, np.nan, t.sum(0))).tolist(),
            "condicional_columna_dado_fila": (t / np.where(t.sum(1, keepdims=True) == 0, np.nan, t.sum(1, keepdims=True))).tolist(),
            "denominadores": {"filas": t.sum(1).astype(int).tolist(), "columnas": t.sum(0).astype(int).tolist()}}


def bayes(p_b_dado_a: float, p_a: float, p_b: float) -> float | None:
    """P(A|B) = P(B|A)·P(A) / P(B)."""
    return None if not p_b else p_b_dado_a * p_a / p_b


def ajustar_p(ps, metodo: str = "holm") -> list:
    """Corrección por comparaciones múltiples: 'holm' (controla FWER) o 'bh' (Benjamini-Hochberg, FDR)."""
    p = np.asarray(ps, float)
    m = len(p)
    o = np.argsort(p)
    adj = np.empty(m)
    if metodo == "holm":
        acum = 0.0
        for rank, i in enumerate(o):
            acum = max(acum, (m - rank) * p[i])
            adj[i] = min(1.0, acum)
    elif metodo == "bh":
        prev = 1.0
        for rank in range(m - 1, -1, -1):
            i = o[rank]
            prev = min(prev, p[i] * m / (rank + 1))
            adj[i] = min(1.0, prev)
    else:
        raise ValueError(metodo)
    return adj.tolist()
