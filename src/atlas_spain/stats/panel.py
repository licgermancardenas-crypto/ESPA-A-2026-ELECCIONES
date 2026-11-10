"""Panel de servicio: exporta gold.stat_panel a un archivo compacto y lo carga para el motor.

    python -m atlas_spain.stats.panel        → data/gold/stat_panel.npz

El archivo contiene, por nivel (municipio, provincia, ccaa, pais):
- ids, nombres y padres (provincia / comunidad) en la geografía vigente;
- una matriz float32 series × territorios (NaN = sin dato) con las claves "variable|categoría|período";
- el catálogo de variables (seed stat_variables) y los vecinos por contigüidad (municipios y provincias).

No sustituye al warehouse: es un derivado de solo lectura, regenerable, identificado por su huella
(SHA-256), que queda registrada en cada ejecución estadística.
"""

from __future__ import annotations

import hashlib
import io
import json
from functools import lru_cache
from pathlib import Path

import numpy as np

NIVELES = ("municipio", "provincia", "ccaa", "pais")


def exportar(destino: Path | None = None) -> Path:
    import duckdb
    import geopandas as gpd
    from libpysal.weights import Queen

    from atlas_spain import paths
    destino = destino or paths.DATA / "gold" / "stat_panel.npz"
    con = duckdb.connect(str(paths.WAREHOUSE), read_only=True)
    con.execute("SET memory_limit='900MB'; SET threads=2")
    geo = con.execute("""select g.geo_id, g.geo_type nivel, g.geo_name nombre, g.parent_geo_id padre, p.parent_geo_id abuelo
                         from gold.dim_geography g left join gold.dim_geography p on p.geo_id = g.parent_geo_id
                         where g.geo_type in ('municipio','provincia','ccaa','pais') order by g.geo_id""").df()
    cat = con.execute("select * from main.stat_variables").df()
    arrays, meta = {}, {"niveles": {}, "catalogo": json.loads(cat.to_json(orient="records", force_ascii=False))}
    for nivel in NIVELES:
        g = geo[geo.nivel == nivel].reset_index(drop=True)
        ids = g.geo_id.tolist()
        pos = {k: i for i, k in enumerate(ids)}
        df = con.execute("""select geo_id, variable, coalesce(categoria, '') categoria, periodo, valor
                            from gold.stat_panel where nivel = ? order by variable, categoria, periodo""", [nivel]).df()
        df["clave"] = df.variable + "|" + df.categoria + "|" + df.periodo
        claves = df.clave.drop_duplicates().tolist()
        kpos = {k: i for i, k in enumerate(claves)}
        M = np.full((len(claves), len(ids)), np.nan, dtype=np.float32)
        M[df.clave.map(kpos).to_numpy(), df.geo_id.map(pos).to_numpy()] = df.valor.to_numpy(np.float32)
        arrays[f"{nivel}__M"] = M
        if nivel == "municipio":
            prov, cc = g.padre.tolist(), g.abuelo.tolist()
        elif nivel == "provincia":
            prov, cc = ids, g.padre.tolist()
        else:
            prov, cc = [None] * len(ids), ids if nivel == "ccaa" else [None]
        meta["niveles"][nivel] = {"ids": ids, "nombres": g.nombre.tolist(), "provincia": prov, "ccaa": cc, "claves": claves}
        del df
    # vecinos por contigüidad (reina) sobre la cartografía publicada en la web (misma geografía 2024)
    for nivel, fichero in (("municipio", "municipios"), ("provincia", "provincias")):
        gj = paths.ROOT / "web" / "data" / "geo" / f"{fichero}.geojson"
        if not gj.exists():
            continue
        gdf = gpd.read_file(gj)
        w = Queen.from_dataframe(gdf, use_index=False, silence_warnings=True)
        orden = {k: i for i, k in enumerate(meta["niveles"][nivel]["ids"])}
        idx_gdf = gdf["id"].map(orden).to_numpy()
        vec = [[] for _ in orden]
        for i, vs in w.neighbors.items():
            if np.isfinite(idx_gdf[i]):
                vec[int(idx_gdf[i])] = [int(idx_gdf[j]) for j in vs if np.isfinite(idx_gdf[j])]
        lon = np.array([len(v) for v in vec], np.int32)
        arrays[f"{nivel}__vec_n"] = lon
        arrays[f"{nivel}__vec"] = np.array([j for v in vec for j in v], np.int32)
    con.close()
    # perfiles territoriales (atlas_spain.stats.perfiles): asignación como serie "perfil||2025" y definiciones en meta
    fp = paths.DATA / "gold" / "perfiles_territoriales.json"
    if fp.exists():
        pf = json.loads(fp.read_text(encoding="utf-8"))
        ids = meta["niveles"]["municipio"]["ids"]
        fila = np.array([pf["asignacion"].get(i, np.nan) for i in ids], np.float32)
        arrays["municipio__M"] = np.vstack([arrays["municipio__M"], fila[None, :]])
        meta["niveles"]["municipio"]["claves"].append("perfil||2025")
        meta["perfiles"] = {k: v for k, v in pf.items() if k != "asignacion"}
    buf = io.BytesIO()
    np.savez_compressed(buf, meta=np.frombuffer(json.dumps(meta, ensure_ascii=False).encode("utf-8"), np.uint8), **arrays)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(buf.getvalue())
    print(f"panel: {destino} ({destino.stat().st_size / 2**20:.1f} MB)")
    return destino


class Panel:
    """Acceso de solo lectura al panel exportado."""

    def __init__(self, ruta: Path):
        raw = Path(ruta).read_bytes()
        self.huella = hashlib.sha256(raw).hexdigest()[:16]
        z = np.load(io.BytesIO(raw), allow_pickle=False)
        self.meta = json.loads(bytes(z["meta"]).decode("utf-8"))
        self.M = {n: z[f"{n}__M"] for n in NIVELES}
        self.vecinos = {}
        for n in ("municipio", "provincia"):
            if f"{n}__vec" in z:
                lon, flat = z[f"{n}__vec_n"], z[f"{n}__vec"]
                cortes = np.r_[0, np.cumsum(lon)]
                self.vecinos[n] = [flat[cortes[i]:cortes[i + 1]].tolist() for i in range(len(lon))]
        self.claves = {n: {k: i for i, k in enumerate(self.meta["niveles"][n]["claves"])} for n in NIVELES}
        self.catalogo = {v["variable"]: v for v in self.meta["catalogo"]}

    def nivel(self, n):
        return self.meta["niveles"][n]

    def serie(self, nivel: str, variable: str, periodo: str, categoria: str | None = None) -> np.ndarray | None:
        i = self.claves[nivel].get(f"{variable}|{categoria or ''}|{periodo}")
        return None if i is None else self.M[nivel][i].astype(float)

    def periodos(self, nivel: str, variable: str, categoria: str | None = None) -> list[str]:
        pref = f"{variable}|{categoria or ''}|"
        return sorted(k[len(pref):] for k in self.claves[nivel] if k.startswith(pref))

    def categorias(self, nivel: str, variable: str, periodo: str | None = None) -> list[str]:
        out = set()
        for k in self.claves[nivel]:
            v, c, p = k.split("|")
            if v == variable and c and (periodo is None or p == periodo):
                out.add(c)
        return sorted(out)


@lru_cache(maxsize=2)
def cargar(ruta: str | None = None) -> Panel:
    if ruta is None:
        from atlas_spain import paths
        ruta = str(paths.DATA / "gold" / "stat_panel.npz")
    return Panel(Path(ruta))


if __name__ == "__main__":
    exportar()
