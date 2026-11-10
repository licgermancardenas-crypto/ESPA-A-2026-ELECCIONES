"""Perfiles de votantes por provincia con MRP (regresión multinivel y postestratificación).

Las encuestas postelectorales del CIS no tienen muestra suficiente para describir a los votantes de cada provincia
(2023: mediana de 135 entrevistas). MRP lo resuelve en cuatro pasos:

1. Marco de postestratificación: Censo anual del INE (tabla 66601), población de nacionalidad española de 18 años
   o más por provincia × sexo × edad × nivel de estudios.
2. Modelo: regresión logística multinomial con penalización L2 sobre los microdatos del CIS. Efectos de sexo, edad,
   estudios, edad×sexo, edad×estudios, comunidad, provincia y comunidad×edad. La penalización hace el papel de los
   efectos aleatorios: una provincia con poca muestra se parece a su comunidad, y una comunidad pequeña al conjunto.
   La fuerza de la penalización se elige por validación cruzada.
3. Postestratificación: probabilidad de cada celda del censo × su población.
4. Calibración: ajuste logístico (raking) para que cada provincia reproduzca exactamente su resultado oficial
   (abstención, voto a cada partido y resto). El modelo decide *quién* vota a cada partido; el escrutinio, *cuántos*.

Incertidumbre: bootstrap de las entrevistas (todo el proceso se repite B veces). Validación: se deja fuera cada
provincia grande, se estima solo con el resto y se compara con la estimación directa de su propia muestra.

    python -m atlas_spain.encuestas.mrp        → data/gold/mrp/*.json y web/data/mrp/*.json
"""
from __future__ import annotations

import hashlib
import json
import sys
import time
import unicodedata
import warnings

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

from atlas_spain import paths

CENSO_CSV = paths.DATA / "landing" / "ine_censo2021" / "t66601.csv"
CENSO_URL = "https://www.ine.es/jaxiT3/files/t/es/csv_bdsc/66601.csv?nocab=1"
SALIDA = paths.DATA / "gold" / "mrp"
WEB = paths.ROOT / "web" / "data" / "mrp"

EDADES = ["18–24", "25–34", "35–49", "50–59", "60–69", "70 y más"]
SEXOS = ["Mujer", "Hombre"]
ESTUDIOS = ["Sin estudios", "Primaria", "Secundaria 1ª etapa", "Secundaria 2ª etapa", "FP", "Superiores"]
DIMS = {"edad": EDADES, "sexo": SEXOS, "estudios": ESTUDIOS}
# Grupos del censo → grupos del modelo. De 15–19 solo cuentan 18 y 19 años: 2/5 del grupo.
EDAD_CENSO = {"De 15 a 19 años": ("18–24", 0.4), "De 20 a 24 años": ("18–24", 1.0), "De 25 a 29 años": ("25–34", 1.0),
              "De 30 a 34 años": ("25–34", 1.0), "De 35 a 39 años": ("35–49", 1.0), "De 40 a 49 años": ("35–49", 1.0),
              "De 50 a 59 años": ("50–59", 1.0), "De 60 a 69 años": ("60–69", 1.0), "De 70 a 79 años": ("70 y más", 1.0),
              "De 80 a 89 años": ("70 y más", 1.0), "90 y más años": ("70 y más", 1.0)}
# Nivel de formación del censo (CNED-2014) → recodificación ESTUDIOS del CIS
EST_CENSO = [("sin estudios", "Sin estudios"), ("educacion primaria", "Primaria"), ("primera etapa", "Secundaria 1ª etapa"),
             ("segunda etapa de educacion secundaria, con orientacion general", "Secundaria 2ª etapa"),
             ("segunda etapa de educacion secundaria con orientacion profesional", "FP"), ("ensenanzas de formacion profesional", "FP"),
             ("grados universitarios", "Superiores"), ("masteres", "Superiores"), ("doctorado", "Superiores")]
MIN_RESPUESTAS = 30   # un partido necesita al menos 30 votantes en la encuesta para modelarse aparte
REJILLA_C = (0.05, 0.15, 0.5, 1.5)
B = 40


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().strip()


def _grupo_edad(edad: pd.Series) -> pd.Series:
    return pd.cut(edad, [17, 24, 34, 49, 59, 69, 120], labels=EDADES).astype(object)


# ───────────────────────── marco censal ─────────────────────────
def marco(anio: int) -> pd.DataFrame:
    """Españoles de 18+ por provincia × sexo × edad × estudios (Censo anual del INE, tabla 66601)."""
    df = pd.read_csv(CENSO_CSV, sep=";", dtype=str, encoding="utf-8-sig")
    df.columns = ["nac", "ccaa", "prov", "sexo", "edad", "nacionalidad", "estudios", "periodo", "total"]
    df = df[df.prov.notna() & df.sexo.isin(["Hombres", "Mujeres"]) & (df.nacionalidad == "Española")
            & (df.periodo == str(anio)) & df.edad.isin(EDAD_CENSO) & (df.estudios != "Total")].copy()
    est = {}
    for e in df.estudios.unique():
        n = _norm(e)
        est[e] = next((v for k, v in EST_CENSO if n.startswith(k)), None)
    if any(v is None for v in est.values()):
        raise ValueError(f"niveles de estudios sin mapear: {[k for k, v in est.items() if v is None]}")
    df["n"] = df.total.str.replace(".", "", regex=False).astype(float) * df.edad.map(lambda e: EDAD_CENSO[e][1])
    df["prov"] = df.prov.str[:2]
    df["ccaa"] = df.ccaa.str[:2]
    df["edad"] = df.edad.map(lambda e: EDAD_CENSO[e][0])
    df["sexo"] = df.sexo.map({"Hombres": "Hombre", "Mujeres": "Mujer"})
    df["estudios"] = df.estudios.map(est)
    m = df.groupby(["ccaa", "prov", "sexo", "edad", "estudios"], as_index=False).n.sum()
    if m.prov.nunique() != 52:
        raise ValueError(f"el marco tiene {m.prov.nunique()} provincias (se esperaban 52)")
    return m


# ───────────────────────── objetivos oficiales ─────────────────────────
def objetivos(P, eleccion: str, categorias: list[str]) -> dict[str, np.ndarray]:
    """Reparto oficial del electorado de cada provincia entre las categorías del modelo (suma 1)."""
    N = P.nivel("provincia")
    part = P.serie("provincia", "participacion", eleccion)
    blanco = np.nan_to_num(P.serie("provincia", "voto_blanco", eleccion))
    nulo = np.nan_to_num(P.serie("provincia", "voto_nulo", eleccion))
    fams = P.categorias("provincia", "voto_familia", eleccion)
    share = {f: np.nan_to_num(P.serie("provincia", "voto_familia", eleccion, f)) for f in fams}
    out = {}
    for i, gid in enumerate(N["ids"]):
        cand = part[i] * (1 - nulo[i]) * (1 - blanco[i])
        t = np.zeros(len(categorias))
        for j, c in enumerate(categorias):
            if c == "Abstención":
                t[j] = 1 - part[i]
            elif c != "Otros":
                t[j] = cand * share.get(c, np.zeros(len(N["ids"])))[i]
        t[categorias.index("Otros")] = max(0.0, 1 - t.sum())
        out[gid[-2:]] = t / t.sum()
    return out


# ───────────────────────── diseño del modelo ─────────────────────────
def _x(df: pd.DataFrame, columnas: list[str] | None = None) -> tuple[np.ndarray, list[str]]:
    f = pd.DataFrame({
        "sexo": df.sexo, "edad": df.edad, "estudios": df.estudios,
        "edad_sexo": df.edad + "|" + df.sexo, "edad_estudios": df.edad + "|" + df.estudios,
        "ccaa": df.ccaa, "prov": df.prov, "ccaa_edad": df.ccaa + "|" + df.edad,
    })
    X = pd.get_dummies(f, prefix_sep="=", dtype=np.float32)
    if columnas is not None:
        X = X.reindex(columns=columnas, fill_value=0.0)
    return X.to_numpy(), list(X.columns)


def _ajustar(X, y, C, pesos=None):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return LogisticRegression(C=C, max_iter=400, tol=1e-5).fit(X, y, sample_weight=pesos)


def _proba(modelo, X, clases):
    p = np.zeros((X.shape[0], len(clases)))
    p[:, [clases.index(c) for c in modelo.classes_]] = modelo.predict_proba(X)
    return p


def calibrar(n: np.ndarray, p: np.ndarray, t: np.ndarray, iteraciones: int = 1000) -> np.ndarray:
    """Raking de las probabilidades de las celdas para que el total de la provincia sea `t` (ajuste logístico)."""
    p = np.clip(p, 1e-9, None)
    p = p / p.sum(1, keepdims=True)
    for _ in range(iteraciones):
        s = (n[:, None] * p).sum(0) / n.sum()
        if np.abs(s - t).max() < 1e-8:
            break
        p = p * np.divide(t, s, out=np.zeros_like(t), where=s > 0)
        p = p / p.sum(1, keepdims=True)
    return p


def _resumen(fr: pd.DataFrame, pr: np.ndarray, unidades: dict[str, np.ndarray]) -> np.ndarray:
    """Para cada unidad: votos por categoría de cada dimensión → [unidad, clase, columna] (columnas = todas las categorías)."""
    votos = fr.n.to_numpy()[:, None] * pr
    cols = [(d, c) for d, cs in DIMS.items() for c in cs]
    out = np.zeros((len(unidades), pr.shape[1], len(cols) + 1))
    pob = np.zeros((len(unidades), len(cols) + 1))
    mascaras = [(fr[{"edad": "edad", "sexo": "sexo", "estudios": "estudios"}[d]] == c).to_numpy() for d, c in cols]
    for u, (_, filas) in enumerate(unidades.items()):
        for k, m in enumerate(mascaras):
            mm = m & filas
            out[u, :, k] = votos[mm].sum(0)
            pob[u, k] = fr.n.to_numpy()[mm].sum()
        out[u, :, -1] = votos[filas].sum(0)
        pob[u, -1] = fr.n.to_numpy()[filas].sum()
    return out, pob


def _estadisticos(votos: np.ndarray, pob: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """composición (P(categoría | partido)) y conducta (P(partido | categoría)) por unidad."""
    comp = np.zeros_like(votos[..., :-1])
    i = 0
    for cs in DIMS.values():
        sl = slice(i, i + len(cs))
        tot = votos[..., sl].sum(-1, keepdims=True)
        comp[..., sl] = np.divide(votos[..., sl], tot, out=np.zeros_like(votos[..., sl]), where=tot > 0)
        i += len(cs)
    cond = np.divide(votos[..., :-1], pob[:, None, :-1], out=np.zeros_like(votos[..., :-1]), where=pob[:, None, :-1] > 0)
    return comp, cond


# ───────────────────────── estimación por elección ─────────────────────────
def preparar(enc: pd.DataFrame, P, eleccion: str):
    d = enc[enc.eleccion == eleccion].copy()
    d["edad"] = _grupo_edad(d.edad)
    d = d.dropna(subset=["voto", "sexo", "edad", "estudios", "prov"])
    d = d[d.voto != "Nuevos votantes"]
    oficiales = set(P.categorias("provincia", "voto_familia", eleccion))
    d["y"] = d.voto.where(d.voto.isin(oficiales | {"Abstención"}), "Otros")
    cuenta = d.y.value_counts()
    d["y"] = d.y.where(d.y.isin(cuenta[cuenta >= MIN_RESPUESTAS].index) | (d.y == "Abstención"), "Otros")
    orden = ["Abstención"] + [c for c in d.y.value_counts().index if c not in ("Abstención", "Otros")] + ["Otros"]
    prov_ccaa = enc.dropna(subset=["prov", "ccaa"]).groupby("prov").ccaa.agg(lambda s: s.mode().iloc[0])
    d["ccaa"] = d.prov.map(prov_ccaa)
    return d.reset_index(drop=True), orden


def elegir_c(X, y) -> tuple[float, dict]:
    cv = StratifiedKFold(5, shuffle=True, random_state=7)
    res = {}
    for C in REJILLA_C:
        ll = []
        for tr, te in cv.split(X, y):
            m = _ajustar(X[tr], y[tr], C)
            p = np.clip(m.predict_proba(X[te]), 1e-12, 1)
            idx = np.searchsorted(m.classes_, y[te])
            ll.append(-np.log(p[np.arange(len(te)), idx]).mean())
        res[C] = float(np.mean(ll))
    return min(res, key=res.get), res


def estimar(enc: pd.DataFrame, P, eleccion: str, b: int = B, semilla: int = 11) -> dict:
    t0 = time.time()
    d, clases = preparar(enc, P, eleccion)
    anio = 2023 if eleccion >= "02-2023" else 2021
    fr = marco(anio)
    obj = objetivos(P, eleccion, clases)
    X, cols = _x(d)
    Xf, _ = _x(fr, cols)
    y = d.y.to_numpy()
    C, cv = elegir_c(X, y)
    provs = sorted(fr.prov.unique())
    nprov = len(provs)
    ccaas = sorted(fr.ccaa.unique())
    unidades = {**{p: (fr.prov == p).to_numpy() for p in provs}, **{"CA" + c: (fr.ccaa == c).to_numpy() for c in ccaas},
                "ES": np.ones(len(fr), bool)}

    def una(Xtr, ytr):
        m = _ajustar(Xtr, ytr, C)
        pr = _proba(m, Xf, clases)
        for p in provs:
            f = (fr.prov == p).to_numpy()
            pr[f] = calibrar(fr.n.to_numpy()[f], pr[f], obj[p])
        return _resumen(fr, pr, unidades)

    votos, pob = una(X, y)
    rng = np.random.default_rng(semilla)
    rep = []
    for _ in range(b):
        i = rng.integers(0, len(d), len(d))
        rep.append(una(X[i], y[i])[0])
    rep = np.stack(rep)
    comp, cond = _estadisticos(votos, pob)
    rc, rd = zip(*(_estadisticos(r, pob) for r in rep))
    rc, rd = np.stack(rc), np.stack(rd)
    lo_c, hi_c = np.quantile(rc, [0.025, 0.975], axis=0)
    lo_d, hi_d = np.quantile(rd, [0.025, 0.975], axis=0)

    nombres = dict(zip(P.nivel("provincia")["ids"], P.nivel("provincia")["nombres"]))
    nombres |= dict(zip(P.nivel("ccaa")["ids"], P.nivel("ccaa")["nombres"]))
    n_muestra = d.prov.value_counts()
    n_ccaa = d.ccaa.value_counts()
    r = lambda a: np.round(a * 100, 1).tolist()
    salida = []
    for u, clave in enumerate(unidades):
        if clave == "ES":
            gid, nivel, n = "ES", "pais", len(d)
        elif clave.startswith("CA"):
            gid, nivel, n = "ES-CA-" + clave[2:], "ccaa", int(n_ccaa.get(clave[2:], 0))
        else:
            gid, nivel, n = "ES-PR-" + clave, "provincia", int(n_muestra.get(clave, 0))
        tot = votos[u, :, -1]
        salida.append({"id": gid, "nombre": nombres.get(gid, "España"), "nivel": nivel, "n_muestra": n,
                       "poblacion": int(round(pob[u, -1])), "voto": r(tot / tot.sum()),
                       "comp": [[r(comp[u, j]), r(lo_c[u, j]), r(hi_c[u, j])] for j in range(len(clases))],
                       "conducta": [[r(cond[u, j]), r(lo_d[u, j]), r(hi_d[u, j])] for j in range(len(clases))]})
    est = enc.loc[enc.eleccion == eleccion, "estudio"].iloc[0]
    print(f"  {eleccion}: n={len(d):,}  clases={len(clases)}  C={C}  {time.time() - t0:.0f}s", flush=True)
    return {"eleccion": eleccion, "estudio": est, "censo_anio": anio, "partidos": clases,
            "dims": DIMS, "n": int(len(d)), "C": C, "cv_logloss": cv, "bootstrap": b,
            "columnas": [f"{dd}|{c}" for dd, cs in DIMS.items() for c in cs], "unidades": salida}


# ───────────────────────── validación: provincia fuera ─────────────────────────
def _directa(d: pd.DataFrame, t: np.ndarray, clases: list[str], fr: pd.DataFrame | None = None) -> np.ndarray:
    """Composición por edad de cada clase en una submuestra. Pesos por raking a tres márgenes: resultado oficial (`t`)
    y, si se da el marco `fr`, la edad y los estudios del censo. Así la estimación directa no arrastra el sesgo de
    estudios de la encuesta (la telefónica de 2023 tiene un 46 % de universitarios frente al 25 % del censo)."""
    w = np.ones(len(d))
    margenes = [(d.y.to_numpy(), dict(zip(clases, t)))]
    if fr is not None:
        for col, cf in (("edad", "edad"), ("estudios", "estudios")):
            tot = fr.groupby(cf).n.sum()
            margenes.append((d[col].to_numpy(), (tot / tot.sum()).to_dict()))
    for _ in range(100):
        for v, obj in margenes:
            for k, objetivo in obj.items():
                m = v == k
                s = w[m].sum() / w.sum()
                if m.any() and s > 0:
                    w[m] *= objetivo / s
    out = np.full((len(clases), len(EDADES)), np.nan)
    ed = d.edad.to_numpy()
    for j, c in enumerate(clases):
        m = d.y.to_numpy() == c
        if m.sum() >= 30:
            tot = w[m].sum()
            out[j] = [w[m & (ed == e)].sum() / tot for e in EDADES]
    return out


def validar(enc: pd.DataFrame, P, eleccion: str, C: float, minimo: int = 300) -> dict:
    d, clases = preparar(enc, P, eleccion)
    fr = marco(2023 if eleccion >= "02-2023" else 2021)
    obj = objetivos(P, eleccion, clases)
    X, cols = _x(d)
    Xf, _ = _x(fr, cols)
    y = d.y.to_numpy()
    filas = []
    for p, n in d.prov.value_counts().items():
        if n < minimo:
            continue
        fuera = (d.prov == p).to_numpy()
        m = _ajustar(X[~fuera], y[~fuera], C)
        f = (fr.prov == p).to_numpy()
        pr = calibrar(fr.n.to_numpy()[f], _proba(m, Xf[f], clases), obj[p])
        votos = fr.n.to_numpy()[f][:, None] * pr
        mrp = np.stack([[votos[(fr.edad[f] == e).to_numpy(), j].sum() for e in EDADES] for j in range(len(clases))])
        mrp = mrp / mrp.sum(1, keepdims=True)
        dire = _directa(d[fuera], obj[p], clases, fr[fr.prov == p])
        # referencia justa: perfil nacional de cada partido calculado SIN la provincia evaluada
        resto = d[~fuera]
        nac = _directa(resto, np.bincount([clases.index(c) for c in resto.y], minlength=len(clases)) / len(resto), clases, fr[fr.prov != p])
        for j, c in enumerate(clases):
            if c in ("Otros",) or np.isnan(dire[j]).any() or np.isnan(nac[j]).any():
                continue
            filas.append({"prov": p, "partido": c, "n_partido": int((d[fuera].y == c).sum()),
                          "error_mrp": float(np.abs(mrp[j] - dire[j]).mean() * 100),
                          "error_nacional": float(np.abs(nac[j] - dire[j]).mean() * 100)})
    df = pd.DataFrame(filas)
    return {"eleccion": eleccion, "minimo_entrevistas": minimo, "provincias": sorted(df.prov.unique().tolist()),
            "comparaciones": len(df), "error_medio_mrp": round(df.error_mrp.mean(), 2),
            "error_medio_nacional": round(df.error_nacional.mean(), 2),
            "mejora_en": int((df.error_mrp < df.error_nacional).sum()),
            "detalle": df.round(2).to_dict("records")}


def construir(elecciones: list[str] | None = None, b: int = B) -> None:
    from atlas_spain.stats.panel import Panel
    P = Panel(paths.DATA / "gold" / "stat_panel.npz")
    enc = pd.read_parquet(paths.DATA / "gold" / "cis_postelectorales.parquet")
    elecciones = elecciones or sorted(enc.eleccion.unique())
    SALIDA.mkdir(parents=True, exist_ok=True)
    WEB.mkdir(parents=True, exist_ok=True)
    indice = {"metodo": __doc__.split("\n\n")[0], "fuente_marco": {"tabla": "INE 66601", "url": CENSO_URL,
              "sha256": hashlib.sha256(CENSO_CSV.read_bytes()).hexdigest()}, "elecciones": {}}
    ces = {}
    for el in elecciones:
        r = estimar(enc, P, el, b)
        ces[el] = r["C"]
        texto = json.dumps(r, ensure_ascii=False, separators=(",", ":"))
        (SALIDA / f"{el}.json").write_text(texto, encoding="utf-8")
        (WEB / f"{el}.json").write_text(texto, encoding="utf-8")
        indice["elecciones"][el] = {"estudio": r["estudio"], "n": r["n"], "censo_anio": r["censo_anio"], "C": r["C"],
                                    "partidos": r["partidos"], "bootstrap": b}
    print("  validación (provincia fuera)…", flush=True)
    indice["validacion"] = [validar(enc, P, el, ces[el]) for el in elecciones if el >= "02-2019"]
    for v in indice["validacion"]:
        print(f"    {v['eleccion']}: {len(v['provincias'])} provincias, error medio MRP {v['error_medio_mrp']} pp "
              f"vs {v['error_medio_nacional']} pp con la composición nacional; mejora en {v['mejora_en']}/{v['comparaciones']}")
    texto = json.dumps(indice, ensure_ascii=False, indent=1)
    (SALIDA / "indice.json").write_text(texto, encoding="utf-8")
    (WEB / "indice.json").write_text(texto, encoding="utf-8")


if __name__ == "__main__":
    construir(sys.argv[1:] or None)
