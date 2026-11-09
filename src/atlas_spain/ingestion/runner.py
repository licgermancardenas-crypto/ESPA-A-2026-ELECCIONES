"""Motor de ejecución de conectores con trazabilidad completa.

Cada ejecución registra: execution_id, source_id, timestamp, dataset, registros
descargados/procesados, errores, duración, estado y versión (hash del contenido).
El registro va a ops.executions (DuckDB) y a data/ops/executions.jsonl.
Nunca se marca como exitosa una descarga que no ocurrió.
"""

from __future__ import annotations

import hashlib
import json
import time
import traceback
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from atlas_spain import paths
from atlas_spain.http import BlockedByChallenge
from atlas_spain.warehouse import connect

EXECUTIONS_DDL = """
CREATE TABLE IF NOT EXISTS ops.executions (
    execution_id      VARCHAR PRIMARY KEY,
    source_id         VARCHAR NOT NULL,
    dataset           VARCHAR NOT NULL,
    started_at        TIMESTAMPTZ NOT NULL,
    finished_at       TIMESTAMPTZ,
    duration_s        DOUBLE,
    status            VARCHAR NOT NULL,   -- success | partial | failed | blocked | skipped_unchanged | no_input
    records_downloaded BIGINT,
    records_processed BIGINT,
    errors            BIGINT,
    error_detail      VARCHAR,
    version           VARCHAR,            -- sha256 del contenido descargado
    artifacts         VARCHAR             -- JSON con rutas escritas
)
"""

ARTIFACTS_DDL = """
CREATE TABLE IF NOT EXISTS ops.artifacts (
    execution_id VARCHAR,
    source_id    VARCHAR,
    kind         VARCHAR,     -- raw | parquet
    path         VARCHAR,
    sha256       VARCHAR,
    bytes        BIGINT,
    rows         BIGINT,
    created_at   TIMESTAMPTZ
)
"""


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class Execution:
    source_id: str
    dataset: str
    execution_id: str = field(default_factory=lambda: uuid.uuid4().hex[:16])
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    finished_at: datetime | None = None
    duration_s: float | None = None
    status: str = "running"
    records_downloaded: int = 0
    records_processed: int = 0
    errors: int = 0
    error_detail: str | None = None
    version: str | None = None
    artifacts: list[dict] = field(default_factory=list)

    # ── escritura de artefactos ──
    def bronze_dir(self) -> Path:
        d = paths.BRONZE / self.source_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_raw(self, name: str, content: bytes) -> Path:
        digest = sha256_bytes(content)
        d = self.bronze_dir() / "raw" / digest[:12]
        d.mkdir(parents=True, exist_ok=True)
        p = d / name
        if not p.exists():
            p.write_bytes(content)
        self.artifacts.append({"kind": "raw", "path": str(p), "sha256": digest,
                               "bytes": len(content), "rows": None})
        return p

    def save_parquet(self, name: str, df: pd.DataFrame) -> Path:
        """Escribe parquet bronze. Añade columnas de linaje a cada fila."""
        df = df.copy()
        df["_source_id"] = self.source_id
        df["_execution_id"] = self.execution_id
        df["_ingested_at"] = self.started_at
        d = self.bronze_dir() / "parquet" / name
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{self.execution_id}.parquet"
        df.to_parquet(p, index=False)
        self.records_processed += len(df)
        self.artifacts.append({"kind": "parquet", "path": str(p), "sha256": sha256_file(p),
                               "bytes": p.stat().st_size, "rows": len(df)})
        return p


def _persist(ex: Execution) -> None:
    rec = asdict(ex)
    rec["started_at"] = ex.started_at.isoformat()
    rec["finished_at"] = ex.finished_at.isoformat() if ex.finished_at else None
    paths.ensure_dirs()
    with open(paths.OPS / "executions.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    con = connect()
    try:
        con.execute(EXECUTIONS_DDL)
        con.execute(ARTIFACTS_DDL)
        con.execute(
            "INSERT OR REPLACE INTO ops.executions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [ex.execution_id, ex.source_id, ex.dataset, ex.started_at, ex.finished_at, ex.duration_s,
             ex.status, ex.records_downloaded, ex.records_processed, ex.errors, ex.error_detail,
             ex.version, json.dumps(ex.artifacts, ensure_ascii=False)],
        )
        for a in ex.artifacts:
            con.execute("INSERT INTO ops.artifacts VALUES (?,?,?,?,?,?,?,?)",
                        [ex.execution_id, ex.source_id, a["kind"], a["path"], a["sha256"],
                         a["bytes"], a["rows"], ex.finished_at])
    finally:
        con.close()


def run(source_id: str, dataset: str, fn, **kwargs) -> Execution:
    """Ejecuta `fn(execution, **kwargs)` registrando el resultado.

    `fn` debe actualizar records_downloaded / errors y escribir artefactos.
    Puede devolver un estado explícito ('partial', 'no_input', 'skipped_unchanged').
    """
    ex = Execution(source_id=source_id, dataset=dataset)
    t0 = time.perf_counter()
    try:
        result = fn(ex, **kwargs)
        if isinstance(result, str):
            ex.status = result
        else:
            ex.status = "partial" if ex.errors else "success"
        raws = sorted(a["sha256"] for a in ex.artifacts if a["kind"] == "raw")
        if raws:
            ex.version = sha256_bytes("".join(raws).encode())[:16]
    except BlockedByChallenge as exc:
        ex.status = "blocked"
        ex.errors += 1
        ex.error_detail = str(exc)
    except Exception as exc:  # noqa: BLE001 — se registra cualquier fallo
        ex.status = "failed"
        ex.errors += 1
        ex.error_detail = f"{type(exc).__name__}: {exc}\n{traceback.format_exc(limit=4)}"
    ex.finished_at = datetime.now(timezone.utc)
    ex.duration_s = round(time.perf_counter() - t0, 3)
    _persist(ex)
    return ex
