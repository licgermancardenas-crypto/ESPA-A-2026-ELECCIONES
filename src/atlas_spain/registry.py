"""DATA_SOURCE_REGISTRY: carga, verificación en vivo y exportación a CSV / warehouse."""

from __future__ import annotations

import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import yaml

from atlas_spain import paths
from atlas_spain.http import probe

FIELDS = [
    "source_id", "organismo", "dataset", "categoria", "url", "api", "formato",
    "cobertura_territorial", "cobertura_historica", "frecuencia", "granularidad",
    "licencia", "restricciones", "metodo_extraccion", "connector",
    "estado", "http_status", "content_type", "ultima_verificacion", "ultima_extraccion",
    "ultima_extraccion_estado", "probe_url",
]

CSV_PATH = paths.ROOT / "DATA_SOURCE_REGISTRY.csv"


def load_sources() -> list[dict]:
    with open(paths.CONFIG / "sources.yaml", encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    sources = doc["sources"]
    ids = [s["source_id"] for s in sources]
    dup = {i for i in ids if ids.count(i) > 1}
    if dup:
        raise ValueError(f"source_id duplicados: {dup}")
    return sources


def get_source(source_id: str) -> dict:
    for s in load_sources():
        if s["source_id"] == source_id:
            return s
    raise KeyError(source_id)


def _last_extractions() -> dict[str, tuple[str, str]]:
    """Última ejecución por fuente, leída del log JSONL (no bloquea el warehouse)."""
    import json
    out: dict[str, tuple[str, str]] = {}
    log = paths.OPS / "executions.jsonl"
    if not log.exists():
        return out
    for line in log.read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        prev = out.get(r["source_id"])
        if prev is None or r["started_at"] > prev[0]:
            out[r["source_id"]] = (r["started_at"], r["status"])
    return out


def verify(workers: int = 6) -> list[dict]:
    """Consulta cada probe_url y devuelve las filas del registro con estado real."""
    sources = load_sources()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(lambda s: probe(s["probe_url"], headers=s.get("probe_headers")), sources))
    last = _last_extractions()
    rows = []
    for s, r in zip(sources, results):
        row = {k: s.get(k, "") for k in FIELDS}
        row.update({"estado": r["estado"], "http_status": r["http_status"],
                    "content_type": r["content_type"], "ultima_verificacion": now})
        le = last.get(s["source_id"])
        row["ultima_extraccion"], row["ultima_extraccion_estado"] = le if le else ("", "")
        row["connector"] = s.get("connector") or ""
        rows.append(row)
    return rows


def write_csv(rows: list[dict]) -> None:
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)


def refresh_extraction_columns() -> None:
    """Actualiza en el CSV solo las columnas de última extracción (sin re-verificar URLs)."""
    if not CSV_PATH.exists():
        return
    with open(CSV_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    last = _last_extractions()
    for row in rows:
        le = last.get(row["source_id"])
        row["ultima_extraccion"], row["ultima_extraccion_estado"] = le if le else ("", "")
    write_csv(rows)
