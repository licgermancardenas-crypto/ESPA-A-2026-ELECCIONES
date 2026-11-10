"""Validación del motor estadístico contra implementaciones de referencia y casos extremos."""

import numpy as np
import pytest

from atlas_spain.stats import correlation as cor
from atlas_spain.stats import descriptive as d
from atlas_spain.stats import distributions as dist
from atlas_spain.stats import electoral as el
from atlas_spain.stats import inference as inf
from atlas_spain.stats import outliers as out
from atlas_spain.stats import regression as reg
from atlas_spain.stats import spatial as sp
from atlas_spain.stats import surveys as sv

RNG = np.random.default_rng(42)


# ─────────── descriptiva ───────────
def test_describir_formulas_basicas():
    x = [2, 4, 4, 4, 5, 5, 7, 9]
    r = d.describir(x)
    assert r["media"] == 5
    assert r["varianza_poblacional"] == pytest.approx(4.0)       # Σ(x−x̄)²/n = 32/8
    assert r["varianza_muestral"] == pytest.approx(32 / 7)        # /(n−1)
    assert r["desviacion_poblacional"] == pytest.approx(2.0)
    assert r["mediana"] == 4.5
    assert r["iqr"] == pytest.approx(np.percentile(x, 75) - np.percentile(x, 25))


def test_media_ponderada_es_agregado():
    # participación de dos municipios: 50 % de 100 electores y 90 % de 900 → agregado 86 %
    r = d.describir([0.5, 0.9], w=[100, 900])
    assert r["media"] == pytest.approx(0.7)
    assert r["media_ponderada"] == pytest.approx((50 + 810) / 1000)


def test_faltantes_y_pesos_invalidos():
    r = d.describir([1, np.nan, 3, np.inf], w=[1, 1, 0, 1])
    assert r["n"] == 1 and r["n_faltantes"] == 3


def test_sin_datos_no_revienta():
    r = d.describir([np.nan])
    assert r["n"] == 0 and r["avisos"]
    assert d.media([]) is None


def test_muestra_pequena_avisa():
    assert any("Pocas" in a for a in d.describir([1, 2, 3])["avisos"])


def test_cuantil_ponderado_con_pesos_iguales_aproxima_mediana():
    x = RNG.normal(size=1001)
    assert d.cuantil_ponderado(x, np.ones_like(x), 0.5) == pytest.approx(np.median(x), abs=1e-2)


def test_media_movil():
    m = d.media_movil([1, 2, 3, 4], 2)
    assert np.isnan(m[0]) and list(m[1:]) == [1.5, 2.5, 3.5]


def test_posicion():
    p = d.posicion(10, [1, 2, 3, 10])
    assert p["percentil"] > 80 and p["z"] > 0


# ─────────── distribuciones ───────────
def test_histograma_cuenta_todo():
    x = RNG.normal(size=500)
    h = dist.histograma(x, "fd")
    assert sum(h["conteos"]) == 500


def test_histograma_constante():
    h = dist.histograma([3, 3, 3])
    assert sum(h["conteos"]) == 3


def test_caja_tukey():
    c = dist.caja([1, 2, 3, 4, 100])
    assert c["n_atipicos"] == 1 and c["bigote_sup"] == 4


def test_densidad_integra_uno():
    x = RNG.normal(size=400)
    k = dist.densidad(x, puntos=400)
    assert np.trapezoid(k["y"], k["x"]) == pytest.approx(1, abs=0.03)


# ─────────── atípicos ───────────
def test_atipicos_z_modificado_y_iqr():
    x = np.r_[RNG.normal(50, 2, 200), 120]
    for m in ("z", "z_modificado", "iqr"):
        r = out.detectar(list(range(len(x))), x, m)
        assert r["items"][0]["id"] == 200, m


def test_mad_cero_no_divide_por_cero():
    r = out.puntuar([5, 5, 5, 5, 5, 9], "z_modificado")
    assert np.isfinite(r["score"]).all()


def test_isolation_forest_opcional():
    pytest.importorskip("sklearn")
    x = np.r_[RNG.normal(0, 1, 300), 15]
    r = out.puntuar(x, "isolation_forest")
    assert r["atipico"][-1]


# ─────────── correlación ───────────
def test_correlaciones_contra_scipy():
    from scipy import stats as st
    x = RNG.normal(size=200)
    y = 0.5 * x + RNG.normal(size=200)
    for m, f in (("pearson", st.pearsonr), ("spearman", st.spearmanr), ("kendall", st.kendalltau)):
        r = cor.correlacion(x, y, m)
        assert r["coef"] == pytest.approx(f(x, y)[0])
        assert r["ic"][0] < r["coef"] < r["ic"][1]


def test_ic_pearson_contra_scipy():
    from scipy import stats as st
    x = RNG.normal(size=80)
    y = x + RNG.normal(size=80)
    ci = st.pearsonr(x, y).confidence_interval(0.95)
    r = cor.correlacion(x, y)
    assert r["ic"] == pytest.approx([ci.low, ci.high], abs=1e-6)


def test_correlacion_sin_variacion():
    assert cor.correlacion([1, 1, 1, 1, 1], [1, 2, 3, 4, 5])["coef"] is None


def test_parcial_contra_pingouin_equivalente():
    # z causa x e y: la correlación parcial controlando z debe ser ≈ 0
    z = RNG.normal(size=2000)
    x = z + RNG.normal(size=2000) * 0.5
    y = z + RNG.normal(size=2000) * 0.5
    assert abs(cor.parcial(x, y, {"z": z})["coef"]) < 0.06
    assert cor.correlacion(x, y)["coef"] > 0.7


def test_matriz_simetrica():
    m = cor.matriz({"a": RNG.normal(size=50), "b": RNG.normal(size=50), "c": RNG.normal(size=50)})
    c = np.array(m["coef"], float)
    assert np.allclose(c, c.T) and np.allclose(np.diag(c), 1)


# ─────────── inferencia ───────────
def test_welch_contra_scipy_y_statsmodels():
    from scipy import stats as st
    a, b = RNG.normal(0, 1, 40), RNG.normal(0.6, 2, 55)
    r = inf.t_dos_grupos(a, b)
    t = st.ttest_ind(a, b, equal_var=False)
    assert r["estadistico"] == pytest.approx(t.statistic) and r["p"] == pytest.approx(t.pvalue)
    ci = t.confidence_interval(0.95)
    assert r["ic_diferencia"] == pytest.approx([ci.low, ci.high])


def test_ic_media_y_bootstrap():
    x = RNG.normal(10, 2, 100)
    r = inf.ic_media(x)
    b = inf.ic_bootstrap(x, B=3000)
    assert r["ic"][0] < 10 < r["ic"][1]
    assert b["ic"] == pytest.approx(r["ic"], abs=0.15)
    assert inf.ic_bootstrap(x, B=500)["ic"] == inf.ic_bootstrap(x, B=500)["ic"]  # semilla fija


def test_wilson_contra_statsmodels():
    sm = pytest.importorskip("statsmodels.stats.proportion")
    lo, hi = sm.proportion_confint(7, 40, method="wilson")
    assert inf.ic_proporcion(7, 40)["ic"] == pytest.approx([lo, hi])


def test_proporciones_contra_statsmodels():
    sm = pytest.importorskip("statsmodels.stats.proportion")
    z, p = sm.proportions_ztest([45, 60], [100, 100])
    r = inf.proporciones(45, 100, 60, 100)
    assert r["estadistico"] == pytest.approx(z) and r["p"] == pytest.approx(p)


def test_anova_y_kruskal():
    from scipy import stats as st
    g = {"a": RNG.normal(0, 1, 30), "b": RNG.normal(0.5, 1, 30), "c": RNG.normal(1, 1, 30)}
    assert inf.anova(g)["p"] == pytest.approx(st.f_oneway(*g.values()).pvalue)
    assert inf.kruskal(g)["p"] == pytest.approx(st.kruskal(*g.values()).pvalue)


def test_chi2_y_contingencia():
    r = inf.chi_cuadrado([[20, 30], [30, 20]])
    assert r["gl"] == 1 and 0 < r["p"] < 0.1
    c = inf.contingencia(["a", "a", "b", "b"], ["x", "y", "x", "x"])
    assert c["denominadores"]["columnas"] == [3, 1]
    assert c["condicional_fila_dado_columna"][0][0] == pytest.approx(1 / 3)


def test_ajuste_p_contra_statsmodels():
    mt = pytest.importorskip("statsmodels.stats.multitest")
    p = [0.01, 0.04, 0.03, 0.2, 0.005]
    for m, ref in (("holm", "holm"), ("bh", "fdr_bh")):
        assert inf.ajustar_p(p, m) == pytest.approx(list(mt.multipletests(p, method=ref)[1]))


def test_bayes():
    assert inf.bayes(0.9, 0.1, 0.18) == pytest.approx(0.5)


# ─────────── regresión ───────────
def _datos(n=300):
    x1, x2 = RNG.normal(size=n), RNG.normal(size=n)
    y = 1 + 2 * x1 - 0.5 * x2 + RNG.normal(size=n) * (1 + 0.5 * np.abs(x1))
    return y, {"x1": x1, "x2": x2}


def test_mco_contra_statsmodels_hc3_y_clasico():
    sm = pytest.importorskip("statsmodels.api")
    y, X = _datos()
    M = sm.add_constant(np.column_stack([X["x1"], X["x2"]]))
    for cov, rob in (("HC3", "HC3"), ("nonrobust", None)):
        ref = sm.OLS(y, M).fit(cov_type=cov)
        r = reg.mco(y, X, robusto=rob)
        assert [c["coef"] for c in r["coeficientes"]] == pytest.approx(list(ref.params))
        assert [c["se"] for c in r["coeficientes"]] == pytest.approx(list(ref.bse))
    assert r["r2"] == pytest.approx(ref.rsquared) and r["aic"] == pytest.approx(ref.aic)


def test_intervalo_prediccion_mas_ancho():
    y, X = _datos()
    m = reg.mco(y, X, robusto=None)
    p = reg.prediccion(m, {"x1": 0.5, "x2": 0})
    assert (p["ic_prediccion"][1] - p["ic_prediccion"][0]) > (p["ic_media"][1] - p["ic_media"][0])


def test_logistica_contra_statsmodels():
    sm = pytest.importorskip("statsmodels.api")
    x = RNG.normal(size=500)
    y = (RNG.random(500) < 1 / (1 + np.exp(-(0.3 + 1.2 * x)))).astype(float)
    ref = sm.Logit(y, sm.add_constant(x)).fit(disp=0)
    r = reg.logistica(y, {"x": x})
    assert [c["coef"] for c in r["coeficientes"]] == pytest.approx(list(ref.params), rel=1e-6)
    assert [c["se"] for c in r["coeficientes"]] == pytest.approx(list(ref.bse), rel=1e-5)


def test_poisson_contra_statsmodels():
    sm = pytest.importorskip("statsmodels.api")
    x = RNG.normal(size=400)
    expo = RNG.uniform(50, 500, 400)
    y = RNG.poisson(expo * np.exp(-3 + 0.4 * x))
    ref = sm.GLM(y, sm.add_constant(x), family=sm.families.Poisson(), offset=np.log(expo)).fit()
    r = reg.poisson(y, {"x": x}, exposicion=expo)
    assert [c["coef"] for c in r["coeficientes"]] == pytest.approx(list(ref.params), rel=1e-6)


def test_ridge_y_lasso_contra_sklearn():
    lm = pytest.importorskip("sklearn.linear_model")
    y, X = _datos()
    Z = np.column_stack([X["x1"], X["x2"]])
    Zs = (Z - Z.mean(0)) / Z.std(0)
    for tipo, alfa, modelo in (("ridge", 5.0, lm.Ridge(alpha=5.0)), ("lasso", 0.1, lm.Lasso(alpha=0.1))):
        modelo.fit(Zs, y)
        r = reg.penalizada(y, X, tipo, alfa)
        assert [c["coef_estandarizado"] for c in r["coeficientes"][1:]] == pytest.approx(list(modelo.coef_), abs=1e-5)


def test_regresion_datos_insuficientes():
    assert reg.mco([1, 2], {"x": [1, 2]})["avisos"]


# ─────────── encuestas ───────────
def test_margen_error_clasico():
    assert sv.margen_error(1000)["margen"] == pytest.approx(0.031, abs=5e-4)  # ±3,1 % para n=1000


def test_kish():
    assert sv.kish([1, 1, 1, 1])["deff"] == pytest.approx(1)
    assert sv.kish([1, 3])["n_efectivo"] == pytest.approx(16 / 10)


def test_composicion_y_ficha():
    c = sv.composicion({"H": 0.6, "M": 0.4}, {"H": 0.49, "M": 0.51}, 1000)
    assert c["p"] < 0.001 and c["disimilitud"] == pytest.approx(0.11)
    assert "tamano_muestra" in sv.ficha_completa({"instituto": "X"})["faltan"]


# ─────────── electoral ───────────
def test_metricas_electorales():
    assert el.hhi([0.5, 0.5]) == 0.5 and el.rae([0.5, 0.5]) == 0.5
    assert el.swing_butler(0.4, 0.3, 0.3, 0.4) == pytest.approx(0.1)


# ─────────── espacial ───────────
def _rejilla(k):
    vec = []
    for i in range(k):
        for j in range(k):
            vec.append([(i + di) * k + (j + dj) for di in (-1, 0, 1) for dj in (-1, 0, 1)
                        if (di or dj) and 0 <= i + di < k and 0 <= j + dj < k])
    return vec


def test_moran_contra_esda():
    esda = pytest.importorskip("esda")
    libpysal = pytest.importorskip("libpysal")
    k = 12
    vec = _rejilla(k)
    x = np.array([i // k + j % k for i, j in zip(range(k * k), range(k * k))], float) + RNG.normal(size=k * k)
    w = libpysal.weights.W({i: v for i, v in enumerate(vec)})
    w.transform = "r"
    ref = esda.Moran(x, w, permutations=0)
    r = sp.moran_global(x, vec, permutaciones=99)
    assert r["I"] == pytest.approx(ref.I) and r["p_permutacion"] < 0.05
    loc = sp.moran_local(x, vec, permutaciones=99)
    ref_l = esda.Moran_Local(x, w, permutations=0)
    assert np.nanmax(np.abs(loc["I"] - ref_l.Is)) < 1e-9


def test_moran_aleatorio_no_significativo():
    vec = _rejilla(15)
    x = np.random.default_rng(7).normal(size=225)
    assert sp.moran_global(x, vec, permutaciones=199)["p_permutacion"] > 0.05
