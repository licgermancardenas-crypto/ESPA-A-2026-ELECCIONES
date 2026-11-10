"""Perfiles territoriales: tipología de municipios según sus características (no de personas).

    python -m atlas_spain.stats.perfiles    → data/gold/perfiles_territoriales.json (+ reexporta el panel)

Diseño (estratificado, habitual en geografía electoral):
1. Tres estratos por tamaño (Padrón 2025): < 5.000, 5.000–50.000 y ≥ 50.000 habitantes. Sin estratos,
   la mayoría de municipios pequeños domina la agrupación y el 80–90 % de la población queda en un
   solo grupo urbano, inútil para analizar el voto.
2. Dentro de cada estrato, k-medias sobre variables estandarizadas: log densidad, renta neta por
   persona (2024), % de 65 y más (2024) y variación de población 2015–2025, recortadas a los
   percentiles 1–99. k ∈ {2, 3, 4} se elige por el coeficiente de silueta (grupos de al menos el 5 %).
3. El nombre de cada perfil se construye con reglas a partir de su centroide (las dos diferencias más
   marcadas respecto a la mediana del estrato); no se escriben a mano.

Limitaciones: describe territorios, no personas; renta y edad son de 2024 (un único año); los
municipios sin renta publicada (≈ 1 %) quedan sin perfil.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

from atlas_spain import paths

ESTRATOS = [("rural", "Municipios rurales", 0, 5_000), ("intermedio", "Municipios intermedios", 5_000, 50_000),
            ("urbano", "Ciudades", 50_000, float("inf"))]
VARS = [("densidad", "2025", True, "densidad"), ("renta_persona", "2024", False, "renta"),
        ("pct_65", "2024", False, "edad"), ("var_poblacion", "2015-2025", False, "crecimiento")]
DESCRIPTORES = {"renta": ("renta alta", "renta baja"), "edad": ("envejecidos", "jóvenes"),
                "crecimiento": ("en crecimiento", "en declive"), "densidad": ("densos", "dispersos")}
# paleta categórica: rural en tierras, intermedio en azules, ciudades en colores vivos (se asigna en orden de estrato)
COLORES = ["#a07a45", "#d9b44a", "#2f6fd6", "#7fb2e5", "#c40bff", "#ff6b9a", "#36c5c5", "#5cc46a", "#f0b54a", "#c25a00", "#a08fc2", "#ffd36b"]


def _silueta(Z, lab):
    from sklearn.metrics import silhouette_score
    return float(silhouette_score(Z, lab, sample_size=min(len(Z), 4000), random_state=0))


def construir() -> dict:
    from sklearn.cluster import KMeans
    from atlas_spain.stats.panel import cargar, exportar
    P = cargar()
    N = P.nivel("municipio")
    pob = P.serie("municipio", "poblacion", "2025")
    cols = {}
    for v, per, log, k in VARS:
        x = P.serie("municipio", v, per)
        cols[k] = np.where(x > 0, np.log(x), np.nan) if log else x
    X = np.column_stack([cols[k] for _, _, _, k in VARS])
    codigo = np.full(len(pob), -1, int)
    perfiles, idx_global = [], 0
    for clave, etiqueta, lo, hi in ESTRATOS:
        m = np.isfinite(X).all(1) & np.isfinite(pob) & (pob >= lo) & (pob < hi)
        Xs = X[m]
        Z = np.clip(Xs, np.percentile(Xs, 1, 0), np.percentile(Xs, 99, 0))
        mu, sd = Z.mean(0), Z.std(0)
        Z = (Z - mu) / sd
        mejor = None
        for k in (2, 3, 4):
            lab = KMeans(k, n_init=20, random_state=0).fit_predict(Z)
            if np.bincount(lab).min() < 0.05 * len(Z):
                continue
            s = _silueta(Z, lab)
            if mejor is None or s > mejor[0]:
                mejor = (s, k, lab)
        s, k, lab = mejor
        med_estrato = np.median(Xs, 0)
        orden = np.argsort([-np.median(Xs[lab == c][:, 1]) for c in range(k)])  # por renta, de mayor a menor
        for c in orden:
            sel = lab == c
            cent = Z[sel].mean(0)
            desc = sorted(((abs(z), k_, z) for z, (_, _, _, k_) in zip(cent, VARS)), reverse=True)[:2]
            adjetivos = [DESCRIPTORES[k_][0 if z > 0 else 1] for _, k_, z in desc if abs(z) >= 0.35]
            nombre = etiqueta + (" · " + ", ".join(adjetivos) if adjetivos else " · perfil medio")
            ids = np.where(m)[0][sel]
            codigo[ids] = idx_global
            raw = {k_: Xs[sel][:, j] for j, (_, _, _, k_) in enumerate(VARS)}
            perfiles.append({
                "id": idx_global, "nombre": nombre, "estrato": clave, "color": COLORES[idx_global % len(COLORES)],
                "n_municipios": int(sel.sum()), "poblacion": float(np.nansum(pob[ids])),
                "pct_poblacion": float(np.nansum(pob[ids]) / np.nansum(pob)),
                "mediana": {"poblacion": float(np.median(pob[ids])), "densidad": float(np.exp(np.median(raw["densidad"]))),
                            "renta": float(np.median(raw["renta"])), "pct_65": float(np.median(raw["edad"])),
                            "crecimiento": float(np.median(raw["crecimiento"]))},
                "centroide_z": {k_: float(z) for z, (_, _, _, k_) in zip(cent, VARS)},
                "ejemplos": [N["nombres"][i] for i in ids[np.argsort(-pob[ids])][:6]],
            })
            idx_global += 1
        for p in perfiles[-k:]:
            p["silueta_estrato"] = s
            p["k_estrato"] = k
            p["mediana_estrato"] = {"densidad": float(np.exp(med_estrato[0])), "renta": float(med_estrato[1]),
                                    "pct_65": float(med_estrato[2]), "crecimiento": float(med_estrato[3])}
    sin = int((codigo < 0).sum())
    out = {"version": "1.0", "fecha": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "metodo": "k-medias estratificado por tamaño (k por silueta, semilla 0, n_init 20) sobre log densidad, renta 2024, % 65+ 2024 y variación 2015–2025, estandarizadas y recortadas P1–P99",
           "variables": [{"variable": v, "periodo": p, "log": l} for v, p, l, _ in VARS],
           "sin_perfil": sin, "perfiles": perfiles,
           "asignacion": {N["ids"][i]: int(c) for i, c in enumerate(codigo) if c >= 0},
           "limitaciones": ["Tipología de territorios, no de personas: no describe a los votantes individuales.",
                            "Renta y edad de un solo año (2024); los perfiles no recogen cambios anteriores en esas variables.",
                            f"{sin} municipios sin renta publicada quedan sin perfil.",
                            "Silueta moderada: los municipios forman un continuo; los límites entre perfiles son graduales."]}
    destino = paths.DATA / "gold" / "perfiles_territoriales.json"
    destino.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"{len(perfiles)} perfiles · {len(out['asignacion'])} municipios asignados · {sin} sin perfil")
    for p in perfiles:
        print(f"  {p['id']}: {p['nombre']:<60} n={p['n_municipios']:5d} pob={p['pct_poblacion'] * 100:5.1f}%  sil={p['silueta_estrato']:.2f}  {', '.join(p['ejemplos'][:3])}")
    exportar()  # el panel incluye la asignación como variable «perfil»
    cargar.cache_clear()
    return out


if __name__ == "__main__":
    construir()
