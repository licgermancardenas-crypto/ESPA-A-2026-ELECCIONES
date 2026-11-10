"""Servicio estadístico: traduce peticiones territoriales en llamadas al motor y registra cada ejecución.

Petición: {"metodo": "...", "params": {...}}. Una variable se describe con un "spec":
    {"variable": "participacion", "periodo": "02-202307"}
    {"variable": "voto_familia", "categoria": "PP", "periodo": "02-202307"}
    {"variable": "participacion", "periodo": "02-202307", "base": "02-201911"}   → cambio (t − base)
    {"variable": "ganador", "periodo": "02-202307"}                               → familia más votada (categórica)
Ámbito: {"nivel": "municipio", "dentro": "ES-CA-01"}  (dentro: ES, una comunidad o una provincia).
Peso: "ninguno" | "poblacion" | "censo" | "votos_validos".

Todas las respuestas incluyen `ejecucion`: método, versión del motor, huella del panel, parámetros,
n, faltantes, duración y fecha. Ese registro se guarda en data/ops/stat_runs.jsonl en local.
"""

from __future__ import annotations

import json
import re
import time
import uuid
from datetime import datetime, timezone

import numpy as np

from atlas_spain.stats import VERSION
from atlas_spain.stats import correlation as cor
from atlas_spain.stats import descriptive as desc
from atlas_spain.stats import distributions as dist
from atlas_spain.stats import inference as inf
from atlas_spain.stats import outliers as out
from atlas_spain.stats import regression as reg
from atlas_spain.stats import spatial as sp

LIMITES = {"max_x": 8, "max_permutaciones": 999, "max_bootstrap": 5000, "max_puntos": 4000, "max_grupos": 20}
PESOS = {"ninguno": None, "poblacion": "poblacion", "censo": "censo", "votos_validos": "votos_validos"}


class ErrorPeticion(ValueError):
    pass


def _json(o):
    """Convierte arrays y NaN a tipos serializables (NaN → None)."""
    if isinstance(o, dict):
        return {k: _json(v) for k, v in o.items() if not str(k).startswith("_")}
    if isinstance(o, (list, tuple)):
        return [_json(v) for v in o]
    if isinstance(o, np.ndarray):
        return _json(o.tolist())
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


class Servicio:
    def __init__(self, panel, registro=None):
        self.P = panel
        self.registro = registro  # callable(dict) para guardar la ejecución

    # ─────────── resolución de variables y ámbitos ───────────
    def _ambito(self, ambito: dict | None):
        ambito = ambito or {}
        nivel = ambito.get("nivel", "municipio")
        if nivel not in self.P.M:
            raise ErrorPeticion(f"Nivel desconocido: {nivel}")
        N = self.P.nivel(nivel)
        dentro = ambito.get("dentro") or "ES"
        n = len(N["ids"])
        if dentro == "ES":
            mask = np.ones(n, bool)
        elif dentro.startswith("ES-CA-"):
            mask = np.array([c == dentro for c in N["ccaa"]])
        elif dentro.startswith("ES-PR-"):
            mask = np.array([p == dentro for p in N["provincia"]])
        else:
            raise ErrorPeticion(f"Ámbito no válido: {dentro}")
        minimo = ambito.get("min_poblacion")
        if minimo:  # excluye territorios pequeños, donde unas pocas personas mueven mucho los porcentajes
            pob = self.P.serie(nivel, "poblacion", "2025")
            mask &= np.nan_to_num(pob, nan=0) >= float(minimo)
        if not mask.any():
            raise ErrorPeticion(f"Sin territorios de nivel {nivel} dentro de {dentro}")
        return nivel, mask, dentro

    def _valores(self, nivel, spec: dict) -> np.ndarray:
        v, p, c = spec.get("variable"), spec.get("periodo"), spec.get("categoria")
        if v == "ganador":
            return self._ganador(nivel, p)
        if v == "perfil":
            return self._perfil(nivel)
        if v not in self.P.catalogo:
            raise ErrorPeticion(f"Variable desconocida: {v}")
        x = self.P.serie(nivel, v, p, c)
        if x is None:
            raise ErrorPeticion(f"Sin datos de {v}{' / ' + c if c else ''} en {p} a nivel {nivel}")
        if spec.get("base"):
            b = self.P.serie(nivel, v, spec["base"], c)
            if b is None:
                raise ErrorPeticion(f"Sin datos de {v} en {spec['base']}")
            x = x - b
        if spec.get("log"):
            with np.errstate(divide="ignore", invalid="ignore"):
                x = np.where(x > 0, np.log(x), np.nan)
        return x

    def _perfil(self, nivel):
        if nivel != "municipio" or "perfiles" not in self.P.meta:
            raise ErrorPeticion("Los perfiles territoriales solo existen a nivel municipal.")
        cod = self.P.serie("municipio", "perfil", "2025")
        nombres = {p["id"]: p["nombre"] for p in self.P.meta["perfiles"]["perfiles"]}
        return np.array([nombres.get(int(c)) if np.isfinite(c) else None for c in cod], dtype=object)

    def _ganador(self, nivel, periodo):
        fams = self.P.categorias(nivel, "voto_familia", periodo)
        if not fams:
            raise ErrorPeticion(f"Sin resultados por familia en {periodo}")
        M = np.vstack([self.P.serie(nivel, "voto_familia", periodo, f) for f in fams])
        M = np.where(np.isfinite(M), M, -1)
        idx = M.argmax(0)
        g = np.array([fams[i] for i in idx], dtype=object)
        g[M.max(0) < 0] = None
        return g

    def _peso(self, nivel, spec, peso):
        clave = PESOS.get(peso or "ninguno", "x")
        if clave == "x":
            raise ErrorPeticion(f"Peso no válido: {peso}")
        if clave is None:
            return None
        p = spec.get("periodo", "")
        if clave == "poblacion":
            anyo = p[3:7] if "-" in p and len(p) == 9 else (p[-4:] if p[-4:].isdigit() else "2025")
            disp = self.P.periodos(nivel, "poblacion")
            anyo = min(disp, key=lambda a: abs(int(a) - int(anyo))) if disp else None
            return self.P.serie(nivel, "poblacion", anyo) if anyo else None
        w = self.P.serie(nivel, clave, p)
        if w is None:
            raise ErrorPeticion(f"El peso «{peso}» no existe para el período {p} (solo convocatorias electorales).")
        return w

    def _etiqueta(self, spec):
        cat = self.P.catalogo.get(spec.get("variable"), {})
        nombre = cat.get("nombre", spec.get("variable"))
        if spec.get("categoria"):
            nombre += f" · {spec['categoria']}"
        per = spec.get("periodo", "")
        if spec.get("log"):
            nombre = f"log {nombre}"
        return nombre + (f" ({spec['base']} → {per})" if spec.get("base") else f" ({per})")

    # ─────────── métodos ───────────
    def m_catalogo(self, params):
        out_ = []
        for v, meta in self.P.catalogo.items():
            niveles = {n: self.P.periodos(n, v) or ([] if v != "voto_familia" else sorted({k.split('|')[2] for k in self.P.claves[n] if k.startswith('voto_familia|')}))
                       for n in ("municipio", "provincia", "ccaa")}
            out_.append({**meta, "periodos": niveles})
        out_.append({"variable": "ganador", "nombre": "Familia más votada", "unidad": "categoría", "tipo": "electoral",
                     "definicion": "Familia política con mayor porcentaje de voto en el territorio", "formula": "argmax p_f",
                     "fuente": "gold.results_by_family", "periodos": {n: sorted({k.split('|')[2] for k in self.P.claves[n] if k.startswith('voto_familia|')}) for n in ("municipio", "provincia", "ccaa")}})
        if "perfiles" in self.P.meta:
            out_.append({"variable": "perfil", "nombre": "Perfil territorial", "unidad": "categoría", "tipo": "demografia",
                         "definicion": "Tipología del municipio por tamaño, densidad, renta, edad y crecimiento", "formula": "k-medias estratificado",
                         "fuente": "atlas_spain.stats.perfiles (INE)", "limitaciones": "Describe territorios, no personas.",
                         "periodos": {"municipio": ["2025"], "provincia": [], "ccaa": []}})
        return {"variables": out_, "panel": self.P.huella, "niveles": {n: len(self.P.nivel(n)["ids"]) for n in self.P.M}}

    def m_familias(self, params):
        nivel = params.get("nivel", "municipio")
        return {"familias": self.P.categorias(nivel, "voto_familia", params.get("periodo"))}

    def m_resumen(self, params):
        n_series = {n: int(self.P.M[n].shape[0]) for n in self.P.M}
        obs = {n: int(np.isfinite(self.P.M[n]).sum()) for n in self.P.M}
        periodos = sorted({k.split("|")[2] for k in self.P.claves["municipio"]})
        elec = [p for p in periodos if re.fullmatch(r"\d\d-\d{6}", p)]
        return {"panel": self.P.huella, "version_motor": VERSION, "variables": len(self.P.catalogo), "series": n_series,
                "observaciones": obs, "territorios": {n: len(self.P.nivel(n)["ids"]) for n in self.P.M},
                "convocatorias": len(elec), "primera": elec[0] if elec else None, "ultima": elec[-1] if elec else None,
                "metodos": sorted(m[2:] for m in dir(self) if m.startswith("m_"))}

    def m_descriptiva(self, params):
        spec = params["x"]
        nivel, mask, dentro = self._ambito(params.get("ambito"))
        x = self._valores(nivel, spec)[mask]
        w = self._peso(nivel, spec, params.get("peso"))
        w = w[mask] if w is not None else None
        r = desc.describir(x, w)
        r["etiqueta"] = self._etiqueta(spec)
        r["histograma"] = dist.histograma(x, params.get("intervalos", "fd"))
        r["caja"] = dist.caja(x)
        r["densidad"] = dist.densidad(x, 160)
        r["peso"] = params.get("peso") or "ninguno"
        # desglose por grupo (comunidad dentro de España; provincia dentro de una comunidad)
        agrupar = params.get("agrupar") or ("ccaa" if dentro == "ES" else "provincia" if dentro.startswith("ES-CA-") else None)
        if agrupar and nivel == "municipio":
            N = self.P.nivel(nivel)
            col = np.array(N[agrupar], dtype=object)[mask]
            nombres = self._nombres_padre(agrupar)
            grupos = []
            for g in sorted(set(c for c in col if c)):
                xi = x[col == g]
                wi = w[col == g] if w is not None else None
                d = desc.describir(xi, wi)
                if d["n"]:
                    grupos.append({"id": g, "nombre": nombres.get(g, g), "n": d["n"], "media": d["media"], "mediana": d["mediana"],
                                   "q1": d["q1"], "q3": d["q3"], "desviacion": d["desviacion_poblacional"], "minimo": d["minimo"],
                                   "maximo": d["maximo"], "media_ponderada": d.get("media_ponderada")})
            r["grupos"] = grupos
            r["agrupacion"] = agrupar
        return r

    def _nombres_padre(self, nivel_padre):
        N = self.P.nivel("provincia" if nivel_padre == "provincia" else "ccaa")
        return dict(zip(N["ids"], N["nombres"]))

    def m_atipicos(self, params):
        spec = params["x"]
        nivel, mask, _ = self._ambito(params.get("ambito"))
        N = self.P.nivel(nivel)
        x = self._valores(nivel, spec)
        ids = np.array(N["ids"])[mask].tolist()
        r = out.detectar(ids, x[mask], params.get("metodo", "z_modificado"), params.get("umbral"))
        nom = dict(zip(N["ids"], N["nombres"]))
        prov = dict(zip(N["ids"], N["provincia"]))
        pn = self._nombres_padre("provincia")
        for it in r["items"]:
            it["nombre"] = nom[it["id"]]
            it["provincia"] = pn.get(prov.get(it["id"]), "")
        r["etiqueta"] = self._etiqueta(spec)
        r["periodo"] = spec.get("periodo")
        r["aviso"] = "Una anomalía estadística no implica un error, una irregularidad ni un fraude."
        return r

    def m_historia(self, params):
        """Serie de una variable para un territorio frente a la mediana y el rango intercuartílico de su ámbito."""
        geo_id, v, cat = params["geo_id"], params["variable"], params.get("categoria")
        nivel = {"MU": "municipio", "PR": "provincia", "CA": "ccaa"}.get(geo_id.split("-")[1] if "-" in geo_id else "", "pais")
        N = self.P.nivel(nivel)
        if geo_id not in N["ids"]:
            raise ErrorPeticion(f"Territorio desconocido: {geo_id}")
        i = N["ids"].index(geo_id)
        tipo = params.get("tipo")  # p. ej. "02" para generales
        filas = []
        for per in self.P.periodos(nivel, v, cat):
            if tipo and not per.startswith(tipo + "-"):
                continue
            x = self.P.serie(nivel, v, per, cat)
            ref = x[np.array([p == N["provincia"][i] for p in N["provincia"]])] if nivel == "municipio" else x
            q = np.nanpercentile(ref, [25, 50, 75]) if np.isfinite(ref).any() else [None] * 3
            filas.append({"periodo": per, "valor": x[i], "q1": q[0], "mediana": q[1], "q3": q[2], "mediana_nacional": float(np.nanmedian(x))})
        return {"geo_id": geo_id, "variable": v, "categoria": cat, "serie": filas,
                "referencia": "provincia" if nivel == "municipio" else "nivel completo"}

    def m_posicion(self, params):
        """Posición de un territorio en la distribución de su provincia y de España, para varias variables."""
        geo_id = params["geo_id"]
        nivel = {"MU": "municipio", "PR": "provincia", "CA": "ccaa"}[geo_id.split("-")[1]]
        N = self.P.nivel(nivel)
        if geo_id not in N["ids"]:
            raise ErrorPeticion(f"Territorio desconocido: {geo_id}")
        i = N["ids"].index(geo_id)
        prov = np.array([p == N["provincia"][i] for p in N["provincia"]]) if nivel == "municipio" else None
        filas = []
        for spec in params["specs"]:
            try:
                x = self._valores(nivel, spec)
            except ErrorPeticion:
                continue
            if not np.isfinite(x[i]):
                continue
            fila = {"spec": spec, "etiqueta": self._etiqueta(spec), "unidad": self.P.catalogo.get(spec["variable"], {}).get("unidad"),
                    "espana": desc.posicion(x[i], x)}
            if prov is not None:
                fila["provincia"] = desc.posicion(x[i], x[prov])
            mz = out.puntuar(x if prov is None else np.where(prov, x, np.nan), "z_modificado")
            fila["z_modificado"] = mz["score"][i]
            fila["atipico"] = bool(mz["atipico"][i])
            filas.append(fila)
        perfil = None
        if nivel == "municipio" and "perfiles" in self.P.meta:
            c = self.P.serie("municipio", "perfil", "2025")[i]
            if np.isfinite(c):
                q = self.P.meta["perfiles"]["perfiles"][int(c)]
                perfil = {"id": q["id"], "nombre": q["nombre"], "color": q["color"]}
        return {"geo_id": geo_id, "nombre": N["nombres"][i], "nivel": nivel, "filas": filas, "perfil": perfil}

    def m_correlacion(self, params):
        nivel, mask, _ = self._ambito(params.get("ambito"))
        x = self._valores(nivel, params["x"])[mask]
        y = self._valores(nivel, params["y"])[mask]
        metodo = params.get("metodo", "pearson")
        r = cor.correlacion(x, y, metodo, params.get("confianza", 0.95))
        N = self.P.nivel(nivel)
        ids = np.array(N["ids"])[mask]
        nom = np.array(N["nombres"])[mask]
        ok = np.isfinite(x) & np.isfinite(y)
        idx = np.where(ok)[0]
        if len(idx) > LIMITES["max_puntos"]:
            idx = np.sort(np.random.default_rng(0).choice(idx, LIMITES["max_puntos"], replace=False))
            r["puntos_muestreados"] = True
        r["puntos"] = [[float(x[i]), float(y[i]), ids[i], nom[i]] for i in idx]
        r["etiquetas"] = [self._etiqueta(params["x"]), self._etiqueta(params["y"])]
        if params.get("controles"):
            ctrl = {self._etiqueta(c): self._valores(nivel, c)[mask] for c in params["controles"][:LIMITES["max_x"]]}
            r["parcial"] = cor.parcial(x, y, ctrl, "spearman" if metodo == "spearman" else "pearson")
        return r

    def m_matriz(self, params):
        nivel, mask, _ = self._ambito(params.get("ambito"))
        vs = {self._etiqueta(s): self._valores(nivel, s)[mask] for s in params["specs"][:12]}
        return cor.matriz(vs, params.get("metodo", "pearson"))

    def m_contraste(self, params):
        """Compara una variable entre grupos de territorios (ámbitos) o entre dos períodos (pareado)."""
        spec = params["x"]
        prueba = params.get("prueba", "auto")
        alfa = params.get("alfa", 0.05)
        if params.get("periodos"):  # mismos territorios, dos convocatorias → diferencias pareadas
            nivel, mask, _ = self._ambito(params.get("ambito"))
            a = self._valores(nivel, {**spec, "periodo": params["periodos"][0]})[mask]
            b = self._valores(nivel, {**spec, "periodo": params["periodos"][1]})[mask]
            from scipy import stats as st
            ok = np.isfinite(a) & np.isfinite(b)
            d = b[ok] - a[ok]
            t = st.ttest_rel(b[ok], a[ok]) if len(d) > 1 else None
            w = st.wilcoxon(d) if len(d) > 1 and np.any(d != 0) else None
            return {"prueba": "t pareada y Wilcoxon de rangos con signo", "n": int(ok.sum()), "alfa": alfa,
                    "h0": "el cambio medio entre convocatorias es cero", "h1": "hay un cambio sistemático",
                    "diferencia_media": float(d.mean()) if len(d) else None, "ic_diferencia": inf.ic_media(d)["ic"],
                    "t": t and {"estadistico": float(t.statistic), "p": float(t.pvalue)},
                    "wilcoxon": w and {"estadistico": float(w.statistic), "p": float(w.pvalue)},
                    "efecto": {"dz": float(d.mean() / d.std(ddof=1)) if len(d) > 1 and d.std(ddof=1) > 0 else None},
                    "supuestos": ["Mismos territorios en ambas convocatorias.", inf.SUPERPOBLACION]}
        grupos = params["grupos"][:LIMITES["max_grupos"]]
        datos, nombres = {}, {}
        for g in grupos:
            nivel, mask, dentro = self._ambito({"nivel": params.get("nivel", "municipio"), "dentro": g})
            datos[g] = self._valores(nivel, spec)[mask]
        nom = {**self._nombres_padre("provincia"), **self._nombres_padre("ccaa"), "ES": "España"}
        if len(datos) == 2:
            a, b = datos.values()
            r = inf.mann_whitney(a, b, alfa) if prueba == "mann_whitney" else inf.t_dos_grupos(a, b, alfa)
        else:
            r = inf.kruskal(datos, alfa) if prueba == "kruskal" else inf.anova(datos, alfa)
            if len(datos) > 2:  # comparaciones por pares con corrección de Holm
                pares, ps = [], []
                ks = list(datos)
                for i in range(len(ks)):
                    for j in range(i + 1, len(ks)):
                        t = inf.t_dos_grupos(datos[ks[i]], datos[ks[j]], alfa)
                        if t["p"] is not None:
                            pares.append([nom.get(ks[i], ks[i]), nom.get(ks[j], ks[j]), t["diferencia"], t["p"]])
                            ps.append(t["p"])
                adj = inf.ajustar_p(ps, params.get("correccion", "holm")) if ps else []
                r["pares"] = [{"a": a_, "b": b_, "diferencia": d_, "p": p_, "p_ajustado": q} for (a_, b_, d_, p_), q in zip(pares, adj)]
                r["correccion"] = params.get("correccion", "holm")
        r["grupos_nombres"] = [nom.get(g, g) for g in datos]
        r["resumen_grupos"] = [{"grupo": nom.get(g, g), **{k: desc.describir(v).get(k) for k in ("n", "media", "mediana", "desviacion_muestral")}}
                               for g, v in datos.items()]
        r["etiqueta"] = self._etiqueta(spec)
        return r

    def m_regresion(self, params):
        nivel, mask, _ = self._ambito(params.get("ambito"))
        tipo = params.get("tipo", "mco")
        y = self._valores(nivel, params["y"])[mask].astype(float)
        X = {self._etiqueta(s): self._valores(nivel, s)[mask].astype(float) for s in params["x"][:LIMITES["max_x"]]}
        if not X:
            raise ErrorPeticion("Se necesita al menos una variable explicativa.")
        if tipo == "mco":
            r = reg.mco(y, X, robusto="HC3" if params.get("robusto", True) else None)
            if "_mask" in r:  # β estandarizado: cambio en desviaciones estándar de Y por una desviación estándar de X
                m = r["_mask"]
                sy = np.std(y[m])
                for c in r["coeficientes"][1:]:
                    sx = np.std(X[c["variable"]][m])
                    c["beta_std"] = float(c["coef"] * sx / sy) if sy > 0 else None
        elif tipo == "logistica":
            umbral = params.get("umbral")
            if umbral is None:
                raise ErrorPeticion("La regresión logística necesita un umbral para convertir la variable dependiente en 0/1.")
            yb = np.where(np.isfinite(y), (y > umbral).astype(float), np.nan)
            r = reg.logistica(yb, X)
            r["binarizacion"] = f"y = 1 si {self._etiqueta(params['y'])} > {umbral}"
        elif tipo == "poisson":
            r = reg.poisson(np.round(y), X)
        elif tipo in ("ridge", "lasso"):
            r = reg.penalizada(y, X, tipo, float(params.get("alfa", 1.0)))
        else:
            raise ErrorPeticion(f"Tipo de regresión no válido: {tipo}")
        r["dependiente"] = self._etiqueta(params["y"])
        return reg.limpiar_salida(r)

    def m_espacial(self, params):
        spec = params["x"]
        nivel = params.get("nivel", "municipio")
        if nivel not in self.P.vecinos:
            raise ErrorPeticion("Estadística espacial disponible para municipios y provincias.")
        x = self._valores(nivel, spec)
        perm = min(int(params.get("permutaciones", 199)), LIMITES["max_permutaciones"])
        g = sp.moran_global(x, self.P.vecinos[nivel], perm)
        r = {"global": g, "etiqueta": self._etiqueta(spec), "pesos": "contigüidad tipo reina, estandarizados por filas"}
        if params.get("local", True):
            loc = sp.moran_local(x, self.P.vecinos[nivel], min(perm, 499), params.get("alfa", 0.05))
            N = self.P.nivel(nivel)
            r["local"] = {"resumen": loc["resumen"], "nota": loc["nota"],
                          "cuadrantes": {i: c for i, c in zip(N["ids"], loc["cuadrante"]) if c and c != "No significativo"}}
        return r

    def m_probabilidad(self, params):
        """Tabla de contingencia entre dos variables categóricas (o numéricas discretizadas por cuantiles)."""
        nivel, mask, _ = self._ambito(params.get("ambito"))
        cols = []
        for spec in (params["a"], params["b"]):
            v = self._valores(nivel, spec)[mask]
            if v.dtype != object:
                k = int(spec.get("cuantiles", 3))
                cortes = np.nanpercentile(v.astype(float), np.linspace(0, 100, k + 1)[1:-1])
                lab = np.array([f"Q{int(np.searchsorted(cortes, val, side='right')) + 1}" if np.isfinite(val) else None for val in v.astype(float)], dtype=object)
                v = lab
            cols.append(v)
        c = inf.contingencia(cols[0], cols[1])
        c["chi2"] = inf.chi_cuadrado(c["conteos"])
        c["etiquetas"] = [self._etiqueta(params["a"]), self._etiqueta(params["b"])]
        c["nota"] = ("Las probabilidades se calculan sobre territorios (cada municipio cuenta una vez), no sobre personas. "
                     "Los denominadores están en `denominadores`.")
        return c

    def m_comparar_distribucion(self, params):
        """Misma variable en dos convocatorias (o dos ámbitos): histogramas sobre bordes comunes y resumen."""
        nivel, mask, _ = self._ambito(params.get("ambito"))
        specs = params["specs"][:4]
        vals = [self._valores(nivel, s)[mask].astype(float) for s in specs]
        todo = np.concatenate([v[np.isfinite(v)] for v in vals])
        bordes = np.histogram_bin_edges(todo, bins=params.get("intervalos", 40))
        return {"bordes": bordes.tolist(), "series": [
            {"etiqueta": self._etiqueta(s), "conteos": np.histogram(v[np.isfinite(v)], bordes)[0].tolist(),
             **{k: desc.describir(v).get(k) for k in ("n", "media", "mediana", "desviacion_poblacional", "iqr")}}
            for s, v in zip(specs, vals)]}

    def m_perfiles(self, params):
        """Perfiles territoriales y su comportamiento electoral agregado.

        Voto de un perfil = Σ votos de la familia / Σ votos a candidaturas de sus municipios
        (votos a candidaturas = votos válidos × (1 − voto en blanco)). Participación = Σ votantes / Σ censo."""
        if "perfiles" not in self.P.meta:
            raise ErrorPeticion("Perfiles territoriales no calculados (python -m atlas_spain.stats.perfiles).")
        meta = self.P.meta["perfiles"]
        defs = meta["perfiles"]
        cod = self.P.serie("municipio", "perfil", "2025")
        nivel = "municipio"
        tipo = params.get("tipo", "02")
        elecs = [p for p in self.P.periodos(nivel, "participacion") if p.startswith(tipo + "-")]
        periodo = params.get("periodo") or elecs[-1]
        grupos = [(d["id"], cod == d["id"]) for d in defs] + [("todos", np.isfinite(cod))]

        def agregados(per):
            vv = self.P.serie(nivel, "votos_validos", per)
            bl = self.P.serie(nivel, "voto_blanco", per)
            cand = np.nan_to_num(vv) * (1 - np.nan_to_num(bl))
            censo, votantes = self.P.serie(nivel, "censo", per), self.P.serie(nivel, "votantes", per)
            fams = self.P.categorias(nivel, "voto_familia", per)
            res = {}
            for gid, m in grupos:
                den = cand[m].sum()
                fam = {}
                for f in fams:
                    sh = self.P.serie(nivel, "voto_familia", per, f)
                    fam[f] = float(np.nansum(np.nan_to_num(sh[m]) * cand[m]) / den) if den > 0 else None
                part = float(np.nansum(votantes[m]) / np.nansum(censo[m])) if np.nansum(censo[m]) > 0 else None
                res[gid] = {"participacion": part, "familias": dict(sorted(fam.items(), key=lambda kv: -(kv[1] or 0))),
                            "municipios_con_datos": int((m & np.isfinite(vv)).sum())}
            return res

        actual = agregados(periodo)
        serie = {per: agregados(per) for per in elecs} if params.get("evolucion", True) else {}
        r = {"metodo": meta["metodo"], "variables": meta["variables"], "limitaciones": meta["limitaciones"], "sin_perfil": meta["sin_perfil"],
             "perfiles": defs, "periodo": periodo, "actual": actual, "evolucion": serie,
             "formula": "Voto del perfil = Σ votos de la familia / Σ votos a candidaturas; participación = Σ votantes / Σ censo",
             "advertencias": ["Perfiles de territorios, no de personas: que un tipo de municipio vote más a un partido no significa que sus habitantes de un perfil concreto lo hagan (falacia ecológica).",
                              "Municipios con el código vigente (2024); los que se fusionaron o segregaron cuentan solo en las convocatorias en que existen con ese código."]}
        if params.get("asignacion"):
            N = self.P.nivel(nivel)
            r["asignacion"] = {i: int(c) for i, c in zip(N["ids"], cod) if np.isfinite(c)}
        return r

    # ─────────── votantes (microdatos del CIS) ───────────
    _DIMS = {"sexo": "Sexo", "grupo_edad": "Edad", "estudios": "Estudios", "sitlab": "Situación laboral",
             "grupo_ideologia": "Ideología (1–10)", "tamuni": "Tamaño de municipio", "ccaa": "Comunidad autónoma"}
    _ORDEN = {"grupo_edad": ["18–24", "25–34", "35–44", "45–54", "55–64", "65 y más"],
              "estudios": ["Sin estudios", "Primaria", "Secundaria 1ª etapa", "Secundaria 2ª etapa", "FP", "Superiores"],
              "grupo_ideologia": ["Izquierda (1–2)", "Centro-izquierda (3–4)", "Centro (5–6)", "Centro-derecha (7–8)", "Derecha (9–10)"],
              "tamuni": ["≤ 2.000", "2.001–10.000", "10.001–50.000", "50.001–100.000", "100.001–400.000", "400.001–1.000.000", "> 1.000.000"]}
    _NO_PARTIDO = ("Abstención", "Blanco o nulo", "Nuevos votantes")

    def _encuesta(self, eleccion):
        E = self.P.encuesta
        if E is None:
            raise ErrorPeticion("Microdatos del CIS no cargados (python -m atlas_spain.encuestas.cis).")
        elecs = sorted({e for e in E["eleccion"] if e})
        eleccion = eleccion or elecs[-1]
        if eleccion not in elecs:
            raise ErrorPeticion(f"Sin encuesta postelectoral para {eleccion}. Disponibles: {', '.join(elecs)}")
        m = E["eleccion"] == eleccion
        est = next(k for k, v in self.P.meta["encuestas"]["estudios"].items() if v["eleccion"] == eleccion)
        return {k: v[m] for k, v in E.items()}, est, elecs

    def _pesos(self, d, eleccion, ajuste):
        """Pesos del CIS; con ajuste «resultado_oficial», recalibrados para que el voto declarado a candidaturas
        reproduzca el resultado oficial por familia (abstención y blanco/nulo no se ajustan)."""
        w = d["peso"].copy()
        info = {"ajuste": ajuste or "ninguno"}
        if ajuste != "resultado_oficial":
            return w, info
        voto = d["voto"]
        partido = np.array([v is not None and v not in self._NO_PARTIDO for v in voto])
        decl = {}
        for v, wi in zip(voto[partido], w[partido]):
            decl[v] = decl.get(v, 0) + wi
        tot = sum(decl.values())
        ofi = {f: self.P.serie("pais", "voto_familia", eleccion, f)[0] for f in self.P.categorias("pais", "voto_familia", eleccion)}
        ofi = {f: float(v) for f, v in ofi.items() if np.isfinite(v)}
        comunes = [f for f in decl if f in ofi and f != "Otros"]
        otros_ofi = 1 - sum(ofi[f] for f in comunes)
        otros_decl = sum(decl[f] for f in decl if f not in comunes) / tot
        factor = {f: ofi[f] / (decl[f] / tot) for f in comunes}
        for f in decl:
            if f not in comunes:
                factor[f] = otros_ofi / otros_decl if otros_decl > 0 else 1.0
        w = np.array([wi * factor.get(v, 1.0) if p else wi for wi, v, p in zip(w, voto, partido)])
        info["factores"] = {k: round(v, 3) for k, v in sorted(factor.items(), key=lambda kv: -decl.get(kv[0], 0))}
        return w, info

    @staticmethod
    def _prop(w, mask_num, mask_den, conf=0.95):
        """Proporción ponderada con IC de Wilson sobre el tamaño efectivo de Kish."""
        from scipy import stats as st
        wd = w[mask_den]
        if wd.sum() <= 0:
            return None
        p = w[mask_den & mask_num].sum() / wd.sum()
        neff = wd.sum() ** 2 / (wd ** 2).sum()
        z = st.norm.ppf(0.5 + conf / 2)
        den = 1 + z * z / neff
        c = (p + z * z / (2 * neff)) / den
        h = z * np.sqrt(p * (1 - p) / neff + z * z / (4 * neff * neff)) / den
        return {"p": float(p), "ic": [float(max(0, c - h)), float(min(1, c + h))], "n": int(mask_den.sum()), "n_ef": float(neff)}

    def _orden(self, dim, valores):
        o = self._ORDEN.get(dim)
        if dim == "ccaa":
            nom = dict(zip(self.P.nivel("ccaa")["ids"], self.P.nivel("ccaa")["nombres"]))
            return sorted(valores, key=lambda c: nom.get(f"ES-CA-{c}", c)), {c: nom.get(f"ES-CA-{c}", c) for c in valores}
        return ([x for x in o if x in valores] if o else sorted(valores)), {c: c for c in valores}

    def m_votantes(self, params):
        """Perfiles de votantes con microdatos del CIS.

        vista «perfil»: composición de los votantes de cada partido por la dimensión, P(grupo | voto).
        vista «grupo»: voto de cada grupo social, P(voto | grupo).
        vista «ideologia»: media de autoubicación (1–10) por partido con IC."""
        d, est, elecs = self._encuesta(params.get("eleccion"))
        eleccion = d["eleccion"][0]
        w, ajuste = self._pesos(d, eleccion, params.get("ajuste", "resultado_oficial"))
        voto = d["voto"]
        valido = np.array([v is not None for v in voto])
        # partidos a mostrar: los de mayor voto ponderado + abstención
        tot = {}
        for v, wi in zip(voto[valido], w[valido]):
            tot[v] = tot.get(v, 0) + wi
        n_part = int(params.get("partidos", 7))
        partidos = [p for p, _ in sorted(tot.items(), key=lambda kv: -kv[1]) if p not in self._NO_PARTIDO and p != "Otros"][:n_part]
        if params.get("abstencion", True) and "Abstención" in tot:
            partidos.append("Abstención")
        vista = params.get("vista", "perfil")
        dim = params.get("dimension", "grupo_edad")
        meta_est = self.P.meta["encuestas"]["estudios"][est]
        r = {"estudio": est, "eleccion": eleccion, "elecciones": elecs, "titulo": meta_est["titulo"], "modo": meta_est["modo"],
             "campo": meta_est["campo"], "url": meta_est["url"], "n": int(len(voto)), "n_voto": int(valido.sum()), "ajuste": ajuste,
             "partidos": partidos, "vista": vista, "dimension": dim, "dimension_nombre": self._DIMS.get(dim, dim),
             # partidos: % del voto a candidaturas; abstención: % de quienes declaran qué hicieron
             "shares": {p: float(tot.get(p, 0) / (sum(v for k, v in tot.items() if k not in self._NO_PARTIDO) if p not in self._NO_PARTIDO
                                                  else sum(v for k, v in tot.items() if k != "Nuevos votantes")))
                        for p in partidos},
             "advertencias": ["Voto declarado (recuerdo) en una encuesta posterior a la elección: suele sobrerrepresentar al ganador y a la participación.",
                              "Intervalos de confianza de Wilson sobre el tamaño efectivo de Kish (ponderación); no incluyen el efecto de conglomerados del muestreo.",
                              "Grupos con pocos casos (n < 50) tienen intervalos muy amplios: interpretar con cautela."]}
        if meta_est["modo"].startswith("telef"):
            r["advertencias"].append("Encuesta telefónica (CATI): el modo de entrevista difiere de las ediciones presenciales anteriores.")
        if vista == "ideologia":
            ide = d["ideologia"]
            filas = []
            for p in partidos:
                m = (voto == p) & np.isfinite(ide)
                if m.sum() < 2:
                    continue
                wi, x = w[m], ide[m]
                mu = np.average(x, weights=wi)
                var = np.average((x - mu) ** 2, weights=wi)
                neff = wi.sum() ** 2 / (wi ** 2).sum()
                se = np.sqrt(var / neff)
                hist = [float(wi[x == k].sum() / wi.sum()) for k in range(1, 11)]
                filas.append({"partido": p, "media": float(mu), "ic": [float(mu - 1.96 * se), float(mu + 1.96 * se)], "desviacion": float(np.sqrt(var)),
                              "n": int(m.sum()), "distribucion": hist, "sin_respuesta": float(1 - m.sum() / max(1, (voto == p).sum()))})
            m = np.isfinite(ide)
            r["ideologia"] = filas
            r["media_total"] = float(np.average(ide[m], weights=w[m]))
            return r
        if dim not in self._DIMS:
            raise ErrorPeticion(f"Dimensión no válida: {dim}")
        g = d[dim]
        cats, nombres = self._orden(dim, sorted({c for c in g if c is not None}))
        tabla = []
        if vista == "perfil":
            for p in partidos:
                den = (voto == p) & np.array([c is not None for c in g])
                tabla.append({"fila": p, "celdas": [self._prop(w, g == c, den) for c in cats], "n": int(den.sum())})
            den = valido & np.array([c is not None for c in g])
            tabla.append({"fila": "Total (votantes y abstencionistas con respuesta)", "celdas": [self._prop(w, g == c, den) for c in cats], "n": int(den.sum())})
        else:
            for c in cats:
                den = valido & (g == c)
                tabla.append({"fila": nombres[c], "celdas": [self._prop(w, voto == p, den) for p in partidos], "n": int(den.sum())})
        r.update(categorias=[nombres[c] for c in cats], tabla=tabla)
        return r

    def m_trasvases(self, params):
        """Matriz de trasvases declarados: voto en la elección anterior → voto en la elección del estudio."""
        d, est, elecs = self._encuesta(params.get("eleccion"))
        eleccion = d["eleccion"][0]
        w, ajuste = self._pesos(d, eleccion, params.get("ajuste", "resultado_oficial"))
        a, b = d["voto_anterior"], d["voto"]
        ok = np.array([x is not None and y is not None for x, y in zip(a, b)])
        tot_a, tot_b = {}, {}
        for x, y, wi in zip(a[ok], b[ok], w[ok]):
            tot_a[x] = tot_a.get(x, 0) + wi
            tot_b[y] = tot_b.get(y, 0) + wi
        k = int(params.get("partidos", 8))
        top = lambda t: [p for p, _ in sorted(t.items(), key=lambda kv: -kv[1]) if p not in ("Otros",)][:k]
        filas, cols = top(tot_a), top(tot_b)
        M = np.zeros((len(filas), len(cols)))
        for x, y, wi in zip(a[ok], b[ok], w[ok]):
            if x in filas and y in cols:
                M[filas.index(x), cols.index(y)] += wi
        total = w[ok].sum()
        meta_est = self.P.meta["encuestas"]["estudios"][est]
        return {"estudio": est, "eleccion": eleccion, "anterior": d["eleccion_anterior"][0], "elecciones": elecs, "titulo": meta_est["titulo"],
                "ajuste": ajuste, "origen": filas, "destino": cols, "n": int(ok.sum()),
                "flujo": (M / total).tolist(),
                "destino_de_origen": (M / np.maximum(M.sum(1, keepdims=True), 1e-12)).tolist(),
                "origen_de_destino": (M / np.maximum(M.sum(0, keepdims=True), 1e-12)).tolist(),
                "advertencias": ["Trasvases declarados por los propios entrevistados (recuerdo de las dos elecciones): el recuerdo de la elección anterior es menos fiable.",
                                 "«Nuevos votantes»: no tenían edad para votar en la elección anterior. Se excluyen quienes no recuerdan o no contestan.",
                                 "Las filas y columnas muestran los principales partidos; el resto queda fuera de la matriz."]}

    def m_votantes_evolucion(self, params):
        """Evolución del perfil de los votantes de una familia en todas las encuestas postelectorales."""
        familia, dim = params.get("familia", "PSOE"), params.get("dimension", "grupo_edad")
        if dim not in self._DIMS:
            raise ErrorPeticion(f"Dimensión no válida: {dim}")
        E = self.P.encuesta
        if E is None:
            raise ErrorPeticion("Microdatos del CIS no cargados.")
        elecs = sorted({e for e in E["eleccion"] if e})
        cats, nombres = self._orden(dim, sorted({c for c in E[dim] if c is not None}))
        serie = []
        for el in elecs:
            d, est, _ = self._encuesta(el)
            w, _ = self._pesos(d, el, params.get("ajuste", "resultado_oficial"))
            den = (d["voto"] == familia) & np.array([c is not None for c in d[dim]])
            if den.sum() < 20:
                serie.append({"eleccion": el, "n": int(den.sum()), "celdas": None})
                continue
            serie.append({"eleccion": el, "n": int(den.sum()), "celdas": [self._prop(w, d[dim] == c, den) for c in cats]})
        return {"familia": familia, "dimension": dim, "dimension_nombre": self._DIMS[dim], "categorias": [nombres[c] for c in cats], "serie": serie,
                "advertencias": ["Cada punto es una encuesta distinta; 2023 es telefónica y las demás presenciales.",
                                 "Las familias siguen la tabla de Atlas (p. ej., Sumar en 2023 y Podemos y confluencias antes)."]}

    def m_validacion_cis(self, params):
        """Voto declarado frente a resultado oficial, por convocatoria (sesgo de recuerdo)."""
        E = self.P.encuesta
        if E is None:
            raise ErrorPeticion("Microdatos del CIS no cargados.")
        out = []
        for el in sorted({e for e in E["eleccion"] if e}):
            d, est, _ = self._encuesta(el)
            w = d["peso"]
            voto = d["voto"]
            partido = np.array([v is not None and v not in self._NO_PARTIDO for v in voto])
            decl = {}
            for v, wi in zip(voto[partido], w[partido]):
                decl[v] = decl.get(v, 0) + wi
            tot = sum(decl.values())
            filas = []
            for f in sorted(decl, key=lambda f: -decl[f])[:8]:
                o = self.P.serie("pais", "voto_familia", el, f)
                filas.append({"familia": f, "declarado": decl[f] / tot, "oficial": float(o[0]) if o is not None and np.isfinite(o[0]) else None})
            valido = np.array([v is not None and v != "Nuevos votantes" for v in voto])
            part_decl = float(w[valido & (voto != "Abstención")].sum() / w[valido].sum())
            part_ofi = float(self.P.serie("pais", "participacion", el)[0])
            out.append({"eleccion": el, "estudio": est, "filas": filas, "participacion_declarada": part_decl, "participacion_oficial": part_ofi,
                        "error_medio": float(np.mean([abs(x["declarado"] - x["oficial"]) for x in filas if x["oficial"] is not None]))})
        return {"convocatorias": out, "nota": "Diferencias habituales en encuestas postelectorales; el ajuste «resultado oficial» las corrige recalibrando los pesos.",
                "advertencias": ["La participación oficial incluye el voto exterior (CERA); la encuesta, solo residentes en España."]}

    def m_encuesta(self, params):
        """Evaluación metodológica de una encuesta a partir de su ficha técnica publicada."""
        from atlas_spain.stats import surveys as sv
        r = {}
        if params.get("n"):
            r["margen"] = sv.margen_error(int(params["n"]), float(params.get("p", 0.5)), float(params.get("confianza", 0.95)),
                                          float(params.get("deff", 1.0)), params.get("N"))
        if params.get("pesos"):
            r["kish"] = sv.kish(params["pesos"])
        if params.get("muestra"):
            ref = params.get("poblacion") or self.m_referencia({})["proporciones"]
            r["composicion"] = sv.composicion(params["muestra"], ref, int(params.get("n") or 1000))
        if params.get("ficha"):
            r["ficha"] = sv.ficha_completa(params["ficha"])
        r["advertencias"] = ["El margen de error clásico solo es válido con muestreo aleatorio; en cuotas o paneles online no está bien definido.",
                             "No se comparan encuestas con poblaciones objetivo, fechas o métodos distintos sin advertirlo."]
        return r

    def m_referencia(self, params):
        """Distribución de la población por comunidad autónoma (Padrón 2025): referencia para evaluar muestras."""
        N = self.P.nivel("ccaa")
        pob = self.P.serie("ccaa", "poblacion", params.get("anyo", "2025"))
        tot = np.nansum(pob)
        return {"fuente": "INE, Padrón continuo", "anyo": params.get("anyo", "2025"),
                "proporciones": {n: float(v / tot) for n, v in zip(N["nombres"], pob) if np.isfinite(v)}}

    # ─────────── ejecución ───────────
    def ejecutar(self, metodo: str, params: dict) -> dict:
        f = getattr(self, f"m_{metodo}", None) if re.fullmatch(r"[a-z_]{1,40}", str(metodo)) else None
        t0 = time.perf_counter()
        estado, error, resultado = "ok", None, None
        try:
            if f is None:
                raise ErrorPeticion(f"Método desconocido: {metodo}")
            if not isinstance(params, dict):
                raise ErrorPeticion("Los parámetros deben ser un objeto JSON.")
            resultado = _json(f(params or {}))
        except (ErrorPeticion, KeyError, TypeError) as e:
            estado, error = "error_peticion", (str(e) if isinstance(e, ErrorPeticion) else f"Petición incompleta: falta o sobra {e}")
        except Exception as e:  # noqa: BLE001 — se registra y se devuelve como error
            estado, error = "error", f"{type(e).__name__}: {e}"
        run = {"run_id": uuid.uuid4().hex[:12], "metodo": metodo, "version_motor": VERSION, "panel": self.P.huella,
               "parametros": params, "estado": estado, "error": error,
               "n": (resultado or {}).get("n") if isinstance((resultado or {}).get("n"), int) else None,
               "n_faltantes": (resultado or {}).get("n_faltantes"),
               "duracion_ms": round((time.perf_counter() - t0) * 1000, 1),
               "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds")}
        if self.registro and metodo not in ("catalogo", "familias", "resumen"):
            try:
                self.registro(run)
            except Exception:  # noqa: BLE001 — el registro nunca rompe la respuesta
                pass
        return {"resultado": resultado, "ejecucion": run, "error": error}


def registro_local(run: dict) -> None:
    from atlas_spain import paths
    f = paths.DATA / "ops" / "stat_runs.jsonl"
    f.parent.mkdir(parents=True, exist_ok=True)
    with open(f, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(run, ensure_ascii=False, default=str) + "\n")
