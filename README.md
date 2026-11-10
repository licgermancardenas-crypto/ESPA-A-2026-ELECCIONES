# ATLAS SPAIN

Plataforma de inteligencia política, electoral, demográfica, económica y territorial de España.

**RAW DATA → DATA ENGINEERING → DATA INTELLIGENCE → ANALYTICS → DECISION SUPPORT**

Estado real de lo implementado, datos descargados y bloqueos: **[PROJECT_STATUS.md](PROJECT_STATUS.md)**.

## Documentos

| Documento | Contenido |
|---|---|
| [DATA_SOURCE_REGISTRY.csv](DATA_SOURCE_REGISTRY.csv) | Catálogo de fuentes con estado verificado en vivo (`atlas registry verify`) |
| [DATA_DISCOVERY_REPORT.md](DATA_DISCOVERY_REPORT.md) | Investigación de fuentes: qué hay, qué falta, qué está bloqueado |
| [DATA_DICTIONARY.md](DATA_DICTIONARY.md) | Tablas y columnas del warehouse (generado desde la base real) |
| [docs/METHODOLOGY.md](docs/METHODOLOGY.md) | Identificadores, definiciones electorales, sistemas electorales e índices |
| [config/sources.yaml](config/sources.yaml) | Fuente de verdad del registro de fuentes |

## Arquitectura

```
fuentes públicas ──► conectores (src/atlas_spain/ingestion) ──► BRONZE  data/bronze/<fuente>/{raw,parquet}
                        │  log: ops.executions + data/ops/executions.jsonl
                        ▼
                     dbt (dbt/models) ──► SILVER (normalizado)  ──► GOLD (analítica)
                        │                                             │
                     geo (src/atlas_spain/geo) ──► gold.geo_boundaries + GeoJSON para MapLibre
                        ▼
                     calidad (src/atlas_spain/quality) ──► ops.quality_results
                        ▼
                     API FastAPI (src/atlas_spain/api) ──► frontend (pendiente)
```

- **Warehouse:** DuckDB (`data/warehouse/atlas.duckdb`) + Parquet. Elegido por volumen real
  (decenas de millones de filas como máximo) y por la máquina de trabajo (3,4 GB de RAM).
  PostgreSQL/PostGIS queda como destino de despliegue multiusuario (`docker compose --profile postgis`).
- **Bronze inmutable:** cada fichero original se guarda con su SHA-256; cada fila lleva
  `_source_id`, `_execution_id`, `_ingested_at`. Silver toma siempre la última ejecución de cada dataset.
- **Sin datos inventados:** los modelos electorales solo se activan si existen ficheros oficiales.

## Uso

```bash
pip install -e ".[dev]"

atlas registry verify                 # verifica las 60+ fuentes y regenera el CSV
atlas ingest --all                    # todos los conectores implementados
atlas ingest INE-SECCIONADO           # cartografía de secciones censales
atlas ingest MIR-IE-CONG --convocatorias 202307 201911 --niveles MUNI MESA
atlas build                           # geo + dbt seed/run/test + controles de calidad
atlas quality                         # solo controles de calidad
atlas status                          # Data Operations Center en consola
python -m atlas_spain.dictionary      # regenera DATA_DICTIONARY.md
uvicorn atlas_spain.api.main:app      # API en http://localhost:8000/docs
atlas powerbi                         # tablero Power BI -> reports/powerbi/ATLAS_Espana.pbip
pytest                                # tests (los de red se omiten por defecto)
```

### Dashboard web interactivo

```bash
atlas web --exportar     # regenera web/data desde el warehouse y abre http://127.0.0.1:8080
atlas web                # solo servir (si web/data ya existe)
```

- **Portada**: mapa de España por provincia con el partido más votado en las últimas generales, principales ciudades y recuadro de Canarias.
- **Mapa**: elecciones (generales, municipales, europeas 1977–2024; ganador, participación, competitividad),
  demografía (población, variación, densidad) y renta; niveles comunidad / provincia / municipio.
  Línea de tiempo con ▶ para recorrer todas las convocatorias.
- **Clic en un territorio**: el mapa se acerca y se "expande" al nivel inferior (comunidad → provincias →
  municipios → secciones censales). La ficha muestra resumen con frases calculadas, demografía 1996–2025,
  historial electoral completo, secciones (renta, densidad, 65+) y elecciones autonómicas.
- **Comparador histórico**, **Hallazgos** (generados desde los datos) y **Datos y calidad**.
- **Estadística** (Statistical Intelligence): descriptiva, distribuciones, correlación, regresión, contrastes,
  anomalías, autocorrelación espacial, probabilidad condicional y evaluación de encuestas sobre el warehouse.
  El cálculo lo hace `atlas_spain.stats` (local: `/api/stats`; publicado: función de Vercel). Ver
  [docs/STATISTICAL_INTELLIGENCE.md](docs/STATISTICAL_INTELLIGENCE.md).
- **Perfiles territoriales** (tipología de municipios y cómo vota cada tipo) y **Votantes (CIS)**: perfiles de votantes
  con microdatos de las encuestas postelectorales del CIS 2015–2023 (`python -m atlas_spain.encuestas.cis` lee los
  `MDxxxx.zip` dejados en `data/landing/cis/`).
- **Mapa base** a elegir: oscuro, **satélite** (ortofotos PNOA del Instituto Geográfico Nacional, CC BY 4.0) o
  **relieve 3D** (satélite sobre el modelo de elevación de AWS Terrain Tiles; arrastrar con clic derecho para girar).
- Enlaces directos a una vista: `http://127.0.0.1:8080/#fondo=satelite&sel=ES-MU-28079`.
- Sin claves de API: librerías (MapLibre, ECharts) y tipografías por CDN; teselas del IGN y de AWS.

#### Publicación (Vercel)

Versión pública: **https://atlas-spain-elecciones.vercel.app**

La web publicada es estática: no necesita Python ni el warehouse. Para actualizarla:

```bash
atlas web --exportar                     # o solo regenerar web/data si cambió el warehouse
python -m atlas_spain.stats.panel        # panel estadístico (data/gold/stat_panel.npz)
python -m atlas_spain.stats.hallazgos    # hallazgos estadísticos trazables
python -m atlas_spain.web.estatico       # fichas, secciones, datos de calidad y copia del motor (web/_lib)
cd web && vercel deploy --prod --yes --archive=tgz
```

`web/js/datos.js` lee primero esos archivos y, si faltan, usa la API local (`atlas web`).

### Tablero de Power BI

`atlas powerbi` exporta los CSV (`reports/powerbi/datos/`) y genera un proyecto PBIP con 8 páginas:
resumen, mapa provincial, mapa municipal, demografía, economía, censo electoral, datos y calidad, y
metodología. Los mapas los dibuja DAX en SVG (sin visuales personalizados). Al abrir el `.pbip` en
Power BI Desktop, pulsá **Actualizar** para cargar los datos (o `powershell -File
src/atlas_spain/viz/powerbi_refrescar.ps1`). Validación por DAX: `src/atlas_spain/viz/powerbi_consultar.ps1`.
Los mapas de España tienen un selector **Mapa base** (Mapa / Satélite): en modo satélite la ortofoto PNOA del
IGN (CC BY 4.0) va debajo y los colores se vuelven semitransparentes. La imagen la descarga
`python -m atlas_spain.viz.powerbi_fondo` (WMS del IGN, mismo encuadre UTM 30N que el lienzo, Canarias en su recuadro)
y viaja troceada en `datos/fondo_satelite.csv`. Es una imagen fija: para zoom satelital usar el dashboard web.

### Resultados electorales oficiales (Infoelectoral)

`infoelectoral.interior.gob.es` responde con un desafío anti-bot. ATLAS no lo elude.
Descargá los ZIP desde el navegador en el
[área de descargas](https://infoelectoral.interior.gob.es/es/elecciones-celebradas/area-de-descargas/)
y dejalos, con su nombre original (p. ej. `02202307_MUNI.zip`), en `data/landing/infoelectoral/`.
El conector los toma de ahí y registra el origen como `landing`.

## Estructura

```
config/            sources.yaml · elections.yaml · electoral_systems.yaml
src/atlas_spain/   http · registry · ingestion/ · parsers/ · electoral/ · geo/ · warehouse/ · quality/ · api/ · cli
dbt/               models/{staging,silver,gold} · macros · seeds
tests/             unitarios (motor electoral, parser, conectores, API)
docs/              METHODOLOGY.md
data/              (no versionado) landing · bronze · warehouse · ops · gold/geo
```

## Licencias de datos

Cada fuente conserva su licencia (ver `licencia` y `restricciones` en el registro). Citar siempre
el organismo de origen. ATLAS trabaja con información pública y agregada: no almacena DNI ni
fechas de nacimiento de candidatos, ni ningún dato personal de votantes.
