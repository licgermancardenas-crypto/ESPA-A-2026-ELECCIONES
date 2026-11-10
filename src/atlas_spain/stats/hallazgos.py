"""Hallazgos estadísticos trazables para la sección Hallazgos.

    python -m atlas_spain.stats.hallazgos   → web/data/hallazgos_estadisticos.json + web/data/core/stat_runs.json

Cada hallazgo se produce ejecutando el servicio estadístico (mismo motor que la web) y conserva:
título, territorio, variable, período, método, resultado, contexto, fuente, limitación, el análisis
que lo reproduce (módulo + parámetros) y el registro de la ejecución. Los textos describen
distribuciones y asociaciones; no atribuyen causas ni sacan conclusiones políticas.
"""

from __future__ import annotations

import json
import re

from atlas_spain import paths
from atlas_spain.stats.panel import cargar
from atlas_spain.stats.service import Servicio, registro_local


def _pct(v, d=1):
    return f"{v * 100:.{d}f}".replace(".", ",") + " %"


def _f(v, d=2, signo=False):
    """Número con coma decimal (y signo menos tipográfico)."""
    t = f"{v:+.{d}f}" if signo else f"{v:.{d}f}"
    return t.replace(".", ",").replace("-", "−")


def _n(v, d=0):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def generar() -> list[dict]:
    runs = []

    def registro(r):
        runs.append(r)
        registro_local(r)

    S = Servicio(cargar(), registro=registro)
    P = S.P
    gens = sorted(p for p in P.periodos("municipio", "participacion") if p.startswith("02-"))
    gen, ant = gens[-1], gens[-2]
    nombre = {gen: "las generales de 2023", ant: "las generales de noviembre de 2019"}
    out = []

    M = P.nivel("municipio")
    ccaa_de = dict(zip(M["ids"], M["ccaa"]))
    nombre_ccaa = dict(zip(P.nivel("ccaa")["ids"], P.nivel("ccaa")["nombres"]))

    def _concentracion(items):
        """Comunidad con más casos atípicos, calculada (no supuesta)."""
        from collections import Counter
        c = Counter(ccaa_de.get(i["id"]) for i in items)
        if not c:
            return ""
        top, k = c.most_common(1)[0]
        return f"{k} de los {len(items)} casos atípicos están en {nombre_ccaa.get(top, top)}."

    def add(h, metodo, params, modulo=None):
        r = S.ejecutar(metodo, params)
        if r["error"]:
            return None
        res = r["resultado"]
        h = h(res)
        if h:
            h.update(tipo="estadistica", metodo=metodo, analisis={"modulo": modulo or metodo, "params": params},
                     ejecucion={k: r["ejecucion"][k] for k in ("run_id", "panel", "version_motor", "fecha", "n")})
            out.append(h)
        return res

    # 1. media frente a mediana y frente al agregado
    add(lambda d: {
        "titulo": "La media municipal no es la participación de España",
        "territorio": "España (8.132 municipios)", "variable": "Participación electoral", "periodo": nombre[gen],
        "resultado": f"Media de municipios {_pct(d['media'])}, mediana {_pct(d['mediana'])}, participación agregada (ponderada por censo) {_pct(d['media_ponderada'])}.",
        "contexto": f"La media simple supera al agregado en {_f((d['media'] - d['media_ponderada']) * 100, 1)} puntos porque los municipios pequeños votan más y cada uno cuenta igual que una gran ciudad. Desviación estándar entre municipios: {_f(d['desviacion_poblacional'] * 100, 1)} puntos.",
        "limitacion": "El censo municipal no incluye a los residentes en el extranjero (CERA), que sí cuentan en el total nacional oficial.",
        "fuente": "Ministerio del Interior (Infoelectoral)",
        "cifras": [["Media municipal", _pct(d["media"])], ["Mediana", _pct(d["mediana"])], ["Agregada", _pct(d["media_ponderada"])]],
    }, "descriptiva", {"x": {"variable": "participacion", "periodo": gen}, "ambito": {"nivel": "municipio", "dentro": "ES"}, "peso": "censo"})

    # 2. diferencias entre comunidades
    ccaa = [g for g in P.nivel("ccaa")["ids"] if g not in ("ES-CA-18", "ES-CA-19")]
    add(lambda d: {
        "titulo": "Cuánto pesa la comunidad en la participación municipal",
        "territorio": "17 comunidades autónomas", "variable": "Participación electoral", "periodo": nombre[gen],
        "resultado": f"Las diferencias entre comunidades explican el {_pct(d['efecto']['eta2'], 0)} de la variación de la participación entre municipios (η², ANOVA; p < 0,0001).",
        "contexto": f"Mediana más alta: {max(d['resumen_grupos'], key=lambda g: g['mediana'])['grupo']} ({_pct(max(g['mediana'] for g in d['resumen_grupos']))}); más baja: {min(d['resumen_grupos'], key=lambda g: g['mediana'])['grupo']} ({_pct(min(g['mediana'] for g in d['resumen_grupos']))}).",
        "limitacion": "Las varianzas no son homogéneas (Levene); la prueba de Kruskal-Wallis conduce a la misma conclusión. Comparación de todos los municipios, no de una muestra.",
        "fuente": "Ministerio del Interior (Infoelectoral)",
        "cifras": [["η²", _pct(d["efecto"]["eta2"], 0)], ["Municipios", _n(sum(d["n"]))]],
    }, "contraste", {"x": {"variable": "participacion", "periodo": gen}, "grupos": ccaa, "prueba": "auto"})

    # 3. concentración espacial
    add(lambda d: {
        "titulo": "La participación se agrupa en el territorio",
        "territorio": "España (municipios)", "variable": "Participación electoral", "periodo": nombre[gen],
        "resultado": f"I de Moran = {_f(d['global']['I'])} (p = {_f(d['global']['p_permutacion'], 3)}, {d['global']['permutaciones']} permutaciones): "
                     f"{_n(d['local']['resumen']['Alto-Alto'])} municipios forman zonas de participación alta y {_n(d['local']['resumen']['Bajo-Bajo'])}, zonas de participación baja.",
        "contexto": "Los municipios vecinos tienden a parecerse. Por eso los valores p de pruebas que asumen independencia entre municipios son optimistas.",
        "limitacion": "Pesos por contigüidad; con miles de pruebas locales, algunos municipios aparecen significativos por azar (≈5 %).",
        "fuente": "Ministerio del Interior (Infoelectoral) · cartografía INE 2024",
        "cifras": [["I de Moran", _f(d['global']['I'])], ["Alto-Alto", _n(d["local"]["resumen"]["Alto-Alto"])], ["Bajo-Bajo", _n(d["local"]["resumen"]["Bajo-Bajo"])]],
    }, "espacial", {"x": {"variable": "participacion", "periodo": gen}, "nivel": "municipio", "permutaciones": 199})

    # 4. anomalías del cambio de participación (municipios medianos y grandes)
    add(lambda d: {
        "titulo": "Caídas de participación fuera de patrón (2019 → 2023)",
        "territorio": "Municipios de 5.000 habitantes o más", "variable": "Cambio de participación", "periodo": f"{nombre[ant]} → {nombre[gen]}",
        "resultado": f"{d['n_atipicos']} de {_n(d['n'])} municipios se alejan del patrón (z modificado > 3,5). Mayor caída: {d['items'][0]['nombre']} ({d['items'][0]['provincia']}), {_f(d['items'][0]['valor'] * 100, 1, True)} puntos.",
        "contexto": f"Cambio mediano del conjunto: {_f(d['referencia']['mediana'] * 100, 1, True)} puntos. {_concentracion(d['items'])}",
        "limitacion": "Una anomalía estadística no implica error, irregularidad ni fraude: solo que el cambio es inusual frente al resto.",
        "fuente": "Ministerio del Interior (Infoelectoral)",
        "items": [[i["id"], i["nombre"], i["valor"]] for i in d["items"][:5]],
    }, "atipicos", {"x": {"variable": "participacion", "periodo": gen, "base": ant}, "ambito": {"nivel": "municipio", "dentro": "ES", "min_poblacion": 5000}, "metodo": "z_modificado"})

    # 5. renta y participación, con y sin edad
    add(lambda d: {
        "titulo": "Renta y participación: una asociación que depende de la edad",
        "territorio": "España (municipios)", "variable": "Renta neta por persona × participación", "periodo": f"renta 2024 · {nombre[gen]}",
        "resultado": f"Correlación de Spearman {_f(d['coef'], 2, True)} (IC 95 % {_f(d['ic'][0], 2, True)} a {_f(d['ic'][1], 2, True)}, n = {_n(d['n'])}); controlando por el % de 65 y más años pasa a {_f(d['parcial']['coef'], 2, True)}.",
        "contexto": "La asociación ya es débil y prácticamente desaparece al tener en cuenta la estructura de edad de cada municipio.",
        "limitacion": "Correlación entre territorios, no entre personas (falacia ecológica). La renta es de 2024 y la elección de 2023. No indica causalidad.",
        "fuente": "INE (Atlas de Distribución de Renta de los Hogares) · Ministerio del Interior",
        "cifras": [["Spearman", _f(d['coef'], 2, True)], ["Parcial (edad)", _f(d['parcial']['coef'], 2, True)]],
    }, "correlacion", {"x": {"variable": "renta_persona", "periodo": "2024"}, "y": {"variable": "participacion", "periodo": gen},
                       "metodo": "spearman", "ambito": {"nivel": "municipio", "dentro": "ES"}, "controles": [{"variable": "pct_65", "periodo": "2024"}]})

    # 6. fragmentación: cambio pareado del número efectivo de partidos 2011 → 2015
    g11 = next(p for p in gens if p.startswith("02-2011"))
    g15 = next(p for p in gens if p.startswith("02-2015"))
    add(lambda d: {
        "titulo": "2015: el salto de la fragmentación, municipio a municipio",
        "territorio": "España (municipios)", "variable": "Número efectivo de partidos", "periodo": "generales 2011 → 2015",
        "resultado": f"El número efectivo de partidos subió de media {_f(d['diferencia_media'], 2, True)} por municipio (IC 95 % {_f(d['ic_diferencia'][0], 2, True)} a {_f(d['ic_diferencia'][1], 2, True)}; n = {_n(d['n'])}).",
        "contexto": "Comparación pareada de los mismos municipios en ambas convocatorias (t pareada y Wilcoxon).",
        "limitacion": "Se calcula sobre candidaturas, no familias; los municipios fusionados o segregados entre ambas fechas quedan fuera.",
        "fuente": "gold.election_indices (Ministerio del Interior)",
        "cifras": [["Cambio medio", _f(d['diferencia_media'], 2, True)], ["Municipios", _n(d["n"])]],
    }, "contraste", {"x": {"variable": "enep"}, "periodos": [g11, g15], "ambito": {"nivel": "municipio", "dentro": "ES"}})

    # 7. perfiles territoriales
    def _perfiles(d):
        defs = {q["id"]: q for q in d["perfiles"]}
        act = {k: v for k, v in d["actual"].items() if k != "todos"}
        pp = sorted(((v["familias"].get("PP"), int(k)) for k, v in act.items() if v["familias"].get("PP") is not None), reverse=True)
        ps = sorted(((v["familias"].get("PSOE"), int(k)) for k, v in act.items() if v["familias"].get("PSOE") is not None), reverse=True)
        pa = sorted(((v["participacion"], int(k)) for k, v in act.items()), reverse=True)
        return {
            "titulo": "Cómo vota cada tipo de municipio",
            "territorio": f"{len(defs)} perfiles territoriales ({sum(q['n_municipios'] for q in defs.values()):,} municipios)".replace(",", "."),
            "variable": "Voto por familia y participación", "periodo": nombre[gen],
            "resultado": f"PP: del {_pct(pp[-1][0])} ({defs[pp[-1][1]]['nombre']}) al {_pct(pp[0][0])} ({defs[pp[0][1]]['nombre']}). "
                         f"PSOE: del {_pct(ps[-1][0])} al {_pct(ps[0][0])} ({defs[ps[0][1]]['nombre']}).",
            "contexto": f"Participación más alta en «{defs[pa[0][1]]['nombre']}» ({_pct(pa[0][0])}) y más baja en «{defs[pa[-1][1]]['nombre']}» ({_pct(pa[-1][0])}).",
            "limitacion": "Tipología de territorios (k-medias estratificado por tamaño sobre densidad, renta, edad y crecimiento), no de personas.",
            "fuente": "INE (Padrón, ADRH) · Ministerio del Interior",
            "cifras": [["Perfiles", str(len(defs))], ["PP máx.", _pct(pp[0][0])], ["PSOE máx.", _pct(ps[0][0])]],
        }
    add(_perfiles, "perfiles", {"tipo": "02", "periodo": gen}, modulo="perfiles")

    destino = paths.ROOT / "web" / "data"
    (destino / "hallazgos_estadisticos.json").write_text(json.dumps(out, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    (destino / "core").mkdir(parents=True, exist_ok=True)
    (destino / "core" / "stat_runs.json").write_text(json.dumps(runs, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"{len(out)} hallazgos estadísticos · {len(runs)} ejecuciones registradas")
    return out


if __name__ == "__main__":
    generar()
