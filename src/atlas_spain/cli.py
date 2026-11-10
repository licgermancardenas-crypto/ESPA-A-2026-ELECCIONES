"""CLI de ATLAS SPAIN.

    atlas registry verify            verifica todas las fuentes y regenera DATA_SOURCE_REGISTRY.csv
    atlas ingest <SOURCE_ID> [...]   ejecuta el conector de una o varias fuentes
    atlas ingest --all               ejecuta todos los conectores implementados
    atlas ingest MIR-IE-CONG --convocatorias 202307 201911 --niveles MUNI MESA
    atlas build                      construye silver/gold (dbt) y calcula índices
    atlas quality                    ejecuta los controles de calidad
    atlas status                     resumen de ejecuciones (Data Operations Center)
    atlas powerbi                    exporta datos y genera el tablero de Power BI (PBIP)
    atlas web [--exportar]           dashboard web interactivo (http://127.0.0.1:8080)
"""

from __future__ import annotations

import argparse
import sys

from atlas_spain import registry
from atlas_spain.ingestion import runner
from atlas_spain.ingestion.connectors import cmadrid, congreso, euskadi, eurostat, ine_files, ine_tempus, infoelectoral


def _infoelectoral_runner(tipo: str):
    def go(source_id, convocatorias=None, niveles=("MUNI",)):
        return runner.run(source_id, f"infoelectoral_{tipo}",
                          infoelectoral.extract, tipo=tipo, convocatorias=convocatorias,
                          niveles=tuple(niveles))
    return go


def connectors() -> dict:
    reg = {}
    for sid in ine_tempus.TABLES:
        reg[sid] = lambda s, tables=None, **_: runner.run(s, "ine_tempus", ine_tempus.extract, tables=tables)
    for sid in ine_tempus.CSV_TABLES:
        reg[sid] = lambda s, **_: runner.run(s, "ine_csv", ine_tempus.extract_csv)
    for sid in eurostat.DATASETS:
        reg[sid] = lambda s, **_: runner.run(s, "eurostat", eurostat.extract)
    reg["INE-CODMUN"] = lambda s, **_: runner.run(s, "diccionario_municipios", ine_files.extract_codmun)
    reg["INE-SECCIONADO"] = lambda s, **_: runner.run(s, "seccionado", ine_files.extract_seccionado)
    reg["EUSKADI-ELEC"] = lambda s, convocatorias=None, **_: runner.run(s, "euskadi", euskadi.extract,
                                                                        convocatorias=convocatorias)
    reg["CMADRID-ELEC"] = lambda s, **_: runner.run(s, "asamblea_madrid", cmadrid.extract)
    reg["CONGRESO-DIP"] = lambda s, **_: runner.run(s, "diputados", congreso.extract)
    for tipo, cfg in infoelectoral.catalog().items():
        reg[cfg["source_id"]] = _infoelectoral_runner(tipo)
    return reg


def cmd_ingest(args) -> int:
    reg = connectors()
    targets = list(reg) if args.all else args.sources
    unknown = [t for t in targets if t not in reg]
    if unknown:
        print(f"Sin conector implementado: {unknown}. Disponibles: {sorted(reg)}")
        return 2
    rc = 0
    for sid in targets:
        kw = {}
        if args.convocatorias:
            kw["convocatorias"] = args.convocatorias
        if args.niveles:
            kw["niveles"] = args.niveles
        if args.tablas:
            kw["tables"] = [int(t) for t in args.tablas]
        ex = reg[sid](sid, **kw)
        print(f"[{ex.status:>17}] {sid:<22} desc={ex.records_downloaded:>9} proc={ex.records_processed:>9} "
              f"err={ex.errors} {ex.duration_s}s  id={ex.execution_id}")
        if ex.error_detail:
            print("    " + ex.error_detail.strip().splitlines()[0][:300])
        if ex.status in ("failed",):
            rc = 1
    registry.refresh_extraction_columns()
    return rc


def cmd_registry(args) -> int:
    rows = registry.verify()
    registry.write_csv(rows)
    from collections import Counter
    c = Counter(r["estado"] for r in rows)
    print(f"{len(rows)} fuentes verificadas -> {registry.CSV_PATH.name}: {dict(c)}")
    return 0


def cmd_build(args) -> int:
    from atlas_spain.warehouse import build
    return build.main(skip_geo=args.skip_geo)


def cmd_quality(args) -> int:
    from atlas_spain.quality import checks
    return checks.main()


def cmd_powerbi(args) -> int:
    from atlas_spain.viz.powerbi_proyecto import generar
    generar(con_datos=not args.sin_datos)
    return 0


def cmd_web(args) -> int:
    if args.exportar:
        from atlas_spain.web.exportar import exportar
        print(exportar())
    from atlas_spain.web.server import main as serve
    print(f"ATLAS SPAIN en http://127.0.0.1:{args.port}")
    serve(port=args.port)
    return 0


def cmd_status(args) -> int:
    from atlas_spain.warehouse import connect
    con = connect(read_only=True)
    try:
        print(con.execute("""
            SELECT source_id, status, records_processed, errors, duration_s,
                   strftime(started_at, '%Y-%m-%d %H:%M') AS started
            FROM ops.executions QUALIFY row_number() OVER (PARTITION BY source_id ORDER BY started_at DESC) = 1
            ORDER BY source_id""").df().to_string(index=False))
    finally:
        con.close()
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="atlas")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("registry")
    r.add_argument("action", choices=["verify"])
    i = sub.add_parser("ingest")
    i.add_argument("sources", nargs="*")
    i.add_argument("--all", action="store_true")
    i.add_argument("--convocatorias", nargs="*")
    i.add_argument("--niveles", nargs="*", choices=["MUNI", "MESA"])
    i.add_argument("--tablas", nargs="*", help="INE: limitar a estas tablas (re-ingesta parcial)")
    b = sub.add_parser("build")
    b.add_argument("--skip-geo", action="store_true", help="no recalcular geometrías")
    sub.add_parser("quality")
    w = sub.add_parser("web", help="dashboard web interactivo en http://127.0.0.1:8080")
    w.add_argument("--port", type=int, default=8080)
    w.add_argument("--exportar", action="store_true", help="regenerar web/data antes de servir")
    pb = sub.add_parser("powerbi", help="genera reports/powerbi/ATLAS_Espana.pbip")
    pb.add_argument("--sin-datos", action="store_true")
    sub.add_parser("status")
    args = p.parse_args(argv)
    return {"registry": cmd_registry, "ingest": cmd_ingest, "build": cmd_build,
            "quality": cmd_quality, "status": cmd_status, "powerbi": cmd_powerbi, "web": cmd_web}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
