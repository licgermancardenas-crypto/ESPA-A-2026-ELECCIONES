# DATA DICTIONARY — ATLAS SPAIN

Generado automáticamente desde el warehouse (`python -m atlas_spain.dictionary`). No editar a mano: las descripciones viven en `src/atlas_spain/dictionary.py`.

Columnas de linaje presentes en bronze/silver: `_source_id`, `_execution_id`, `_ingested_at`.

## `gold.dim_data_source`

Catálogo de fuentes con estado verificado en vivo.

Filas (estimadas): 62

| Columna | Tipo | Descripción |
|---|---|---|
| `source_id` | VARCHAR | Fuente en DATA_SOURCE_REGISTRY. |
| `organismo` | VARCHAR |  |
| `dataset` | VARCHAR |  |
| `categoria` | VARCHAR |  |
| `url` | VARCHAR |  |
| `api` | VARCHAR |  |
| `formato` | VARCHAR |  |
| `cobertura_territorial` | VARCHAR |  |
| `cobertura_historica` | VARCHAR |  |
| `frecuencia` | VARCHAR |  |
| `granularidad` | VARCHAR |  |
| `licencia` | VARCHAR |  |
| `restricciones` | VARCHAR |  |
| `metodo_extraccion` | VARCHAR |  |
| `connector` | VARCHAR |  |
| `estado` | VARCHAR |  |
| `http_status` | VARCHAR |  |
| `content_type` | VARCHAR |  |
| `ultima_verificacion` | VARCHAR |  |
| `ultima_extraccion` | VARCHAR |  |
| `ultima_extraccion_estado` | VARCHAR |  |
| `probe_url` | VARCHAR |  |

## `gold.dim_election`

Convocatorias electorales cargadas.

Filas (estimadas): 9

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `tipo_eleccion` | VARCHAR |  |
| `election_type` | VARCHAR |  |
| `anno` | INTEGER |  |
| `mes` | INTEGER |  |
| `fecha` | DATE |  |
| `source_id` | VARCHAR | Fuente en DATA_SOURCE_REGISTRY. |

## `gold.dim_geography`

Registro geográfico maestro: país, CCAA, provincias, municipios, distritos y secciones.

Filas (estimadas): 55.141

| Columna | Tipo | Descripción |
|---|---|---|
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `geo_type` | VARCHAR | pais | ccaa | provincia | municipio | distrito | seccion. |
| `geo_name` | VARCHAR |  |
| `parent_geo_id` | VARCHAR | geo_id del nivel superior. |
| `official_code` | VARCHAR | Código oficial INE del territorio. |
| `valid_from` | DATE | Inicio de vigencia observado; nulo = anterior a la cobertura descargada. |
| `valid_to` | TIMESTAMP_NS | Fin de vigencia; nulo = vigente en el último dato. |
| `source_id` | VARCHAR | Fuente en DATA_SOURCE_REGISTRY. |

## `gold.election_indices`

ENEP, ENPP, Gallagher, margen, competitividad y dominio por convocatoria y territorio.

Filas (estimadas): 68.115

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `geo_level` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `n_candidaturas` | BIGINT |  |
| `votos_candidaturas` | HUGEINT |  |
| `escanos` | HUGEINT |  |
| `enep` | DOUBLE | Número efectivo de partidos electorales (Laakso–Taagepera). |
| `enpp` | DOUBLE | Número efectivo de partidos parlamentarios. |
| `gallagher` | DOUBLE | Índice de desproporcionalidad de Gallagher (puntos %). |
| `dominio` | DOUBLE |  |
| `margen` | DOUBLE |  |
| `competitividad` | DOUBLE |  |
| `ganador_siglas` | VARCHAR |  |
| `votos_sin_escano` | HUGEINT |  |

## `gold.fact_economy_province`

PIB y PIB per cápita (Contabilidad Regional del INE) por provincia, CCAA y total.

Filas (estimadas): 10.907

| Columna | Tipo | Descripción |
|---|---|---|
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `anyo` | BIGINT | Año de referencia (Padrón: población a 1 de enero de ese año). |
| `indicador` | VARCHAR |  |
| `tipo` | VARCHAR |  |
| `precios` | VARCHAR |  |
| `unidad` | VARCHAR |  |
| `escala` | VARCHAR |  |
| `estado_dato` | VARCHAR |  |
| `valor` | DOUBLE |  |
| `tabla_ine` | BIGINT |  |
| `_execution_id` | VARCHAR | Ejecución de ingesta que produjo la fila (linaje). |
| `derivado_uniprovincial` | BOOLEAN | Fila provincial derivada de la CCAA uniprovincial (el INE solo publica la CCAA). |

## `gold.fact_election_results`

Votos, escaños y cuotas por candidatura, convocatoria y territorio.

Filas (estimadas): 1.060.644

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `geo_level` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `candidacy_id` | VARCHAR | Candidatura dentro de una convocatoria ({election_id}-{código}). No es un partido. |
| `votos` | BIGINT |  |
| `escanos` | BIGINT |  |
| `siglas` | VARCHAR |  |
| `denominacion` | VARCHAR |  |
| `vote_share` | DOUBLE | Votos / votos a candidaturas. |
| `share_valid` | DOUBLE | Votos / votos válidos. |
| `rank_votos` | BIGINT |  |

## `gold.fact_electoral_census`

Censo electoral de votación (INE-OCE) del último proceso publicado, hasta municipio.

Filas (estimadas): 4.770

| Columna | Tipo | Descripción |
|---|---|---|
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `geo_level` | VARCHAR |  |
| `tipo_eleccion` | VARCHAR |  |
| `tipo_elector` | VARCHAR | CER residentes en España, CERA residentes en el extranjero, CERE extranjeros residentes. |
| `dato` | VARCHAR |  |
| `periodo` | VARCHAR |  |
| `electores` | BIGINT | Personas inscritas en el censo electoral de votación. |
| `_execution_id` | VARCHAR | Ejecución de ingesta que produjo la fila (linaje). |

## `gold.fact_population`

Cifras oficiales de población del Padrón (1 de enero) por territorio, año y sexo.

Filas (estimadas): 712.392

| Columna | Tipo | Descripción |
|---|---|---|
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `geo_level` | VARCHAR |  |
| `anyo` | BIGINT | Año de referencia (Padrón: población a 1 de enero de ese año). |
| `sexo` | VARCHAR | T total, H hombres, M mujeres. |
| `poblacion` | HUGEINT | Personas empadronadas (cifra oficial). |
| `tipo_dato` | VARCHAR | Estado del dato según el INE (Definitivo, Provisional, Avance…). |
| `origen` | VARCHAR |  |
| `tabla_ine` | BIGINT |  |
| `_execution_id` | VARCHAR | Ejecución de ingesta que produjo la fila (linaje). |
| `geo_name` | VARCHAR |  |
| `parent_geo_id` | VARCHAR | geo_id del nivel superior. |

## `gold.fact_regional_results`

_Sin descripción._

Filas (estimadas): 540.079

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `tipo` | VARCHAR |  |
| `anyo` | INTEGER | Año de referencia (Padrón: población a 1 de enero de ese año). |
| `nivel` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `seccion_geo_id` | VARCHAR |  |
| `provincia_ine` | VARCHAR |  |
| `municipio_ine` | VARCHAR |  |
| `candidatura` | VARCHAR |  |
| `votos` | BIGINT |  |
| `escanos` | INTEGER |  |
| `censo` | BIGINT | Censo electoral de escrutinio (incluye CERA en ámbitos supramunicipales). |
| `votantes` | BIGINT | Blancos + nulos + votos a candidaturas. |
| `nulos` | BIGINT |  |
| `blancos` | BIGINT |  |
| `validos` | BIGINT |  |
| `votos_candidaturas` | BIGINT |  |
| `_execution_id` | VARCHAR | Ejecución de ingesta que produjo la fila (linaje). |

## `gold.fact_turnout`

Censo, votantes, blancos, nulos y participación por convocatoria y territorio.

Filas (estimadas): 68.115

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `geo_level` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `censo` | BIGINT | Censo electoral de escrutinio (incluye CERA en ámbitos supramunicipales). |
| `votantes` | BIGINT | Blancos + nulos + votos a candidaturas. |
| `votos_validos` | BIGINT | Blancos + votos a candidaturas. |
| `votos_blancos` | BIGINT |  |
| `votos_nulos` | BIGINT |  |
| `votos_candidaturas` | BIGINT |  |
| `numero_escanos` | BIGINT |  |
| `numero_mesas` | BIGINT |  |
| `incluye_cera` | BOOLEAN | Si el ámbito incluye el voto de residentes ausentes. |
| `_source_id` | VARCHAR |  |
| `turnout` | DOUBLE | Votantes / censo. |
| `blank_share` | DOUBLE |  |
| `null_share` | DOUBLE |  |

## `gold.geo_boundaries`

Geometrías simplificadas (WKB, EPSG:4326) por geo_id y año del seccionado.

Filas (estimadas): 55.140

| Columna | Tipo | Descripción |
|---|---|---|
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `geo_type` | VARCHAR | pais | ccaa | provincia | municipio | distrito | seccion. |
| `anyo_geometria` | BIGINT |  |
| `area_km2` | DOUBLE | Área calculada en EPSG:3035 sobre la geometría completa. |
| `lon` | DOUBLE |  |
| `lat` | DOUBLE |  |
| `geometry_wkb` | BLOB | Geometría simplificada en WKB (EPSG:4326). |

## `gold.regional_turnout`

_Sin descripción._

Filas (estimadas): 40.615

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `tipo` | VARCHAR |  |
| `anyo` | INTEGER | Año de referencia (Padrón: población a 1 de enero de ese año). |
| `nivel` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `seccion_geo_id` | VARCHAR |  |
| `provincia_ine` | VARCHAR |  |
| `municipio_ine` | VARCHAR |  |
| `censo` | BIGINT | Censo electoral de escrutinio (incluye CERA en ámbitos supramunicipales). |
| `votantes` | BIGINT | Blancos + nulos + votos a candidaturas. |
| `nulos` | BIGINT |  |
| `blancos` | BIGINT |  |
| `validos` | BIGINT |  |
| `votos_candidaturas` | BIGINT |  |
| `turnout` | DOUBLE | Votantes / censo. |
| `suma_votos_partidos` | HUGEINT |  |
| `ganador` | VARCHAR |  |
| `cuota_ganador` | DOUBLE |  |

## `gold.results_by_family`

_Sin descripción._

Filas (estimadas): 532.171

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `geo_level` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `familia` | VARCHAR |  |
| `votos` | HUGEINT |  |
| `escanos` | HUGEINT |  |
| `vote_share` | DOUBLE | Votos / votos a candidaturas. |

## `gold.results_by_group`

_Sin descripción._

Filas (estimadas): 1.060.581

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `geo_level` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `agrupacion_id` | VARCHAR |  |
| `agrupacion_siglas` | VARCHAR |  |
| `agrupacion_denominacion` | VARCHAR |  |
| `votos` | HUGEINT |  |
| `escanos` | HUGEINT |  |
| `n_candidaturas` | BIGINT |  |
| `vote_share` | DOUBLE | Votos / votos a candidaturas. |

## `gold.volatility`

_Sin descripción._

Filas (estimadas): 32.806

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `election_id_anterior` | VARCHAR |  |
| `geo_level` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `volatilidad_pedersen` | DOUBLE |  |

## `silver.dim_municipality`

Municipios con vigencia observada en diccionarios anuales.

Filas (estimadas): 8.132

| Columna | Tipo | Descripción |
|---|---|---|
| `municipio_ine` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `nombre` | VARCHAR |  |
| `provincia_ine` | VARCHAR |  |
| `parent_geo_id` | VARCHAR | geo_id del nivel superior. |
| `ccaa_ine` | VARCHAR |  |
| `digito_control` | VARCHAR |  |
| `valid_from_observado` | DATE |  |
| `valid_to` | DATE | Fin de vigencia; nulo = vigente en el último dato. |
| `existia_antes_de_cobertura` | BOOLEAN |  |
| `n_denominaciones` | BIGINT |  |

## `silver.geo_census_units`

Distritos y secciones censales con jerarquía.

Filas (estimadas): 46.937

| Columna | Tipo | Descripción |
|---|---|---|
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `geo_type` | VARCHAR | pais | ccaa | provincia | municipio | distrito | seccion. |
| `geo_name` | VARCHAR |  |
| `parent_geo_id` | VARCHAR | geo_id del nivel superior. |
| `official_code` | VARCHAR | Código oficial INE del territorio. |
| `valid_from` | DATE | Inicio de vigencia observado; nulo = anterior a la cobertura descargada. |
| `valid_to` | TIMESTAMP_NS | Fin de vigencia; nulo = vigente en el último dato. |
| `source_id` | VARCHAR | Fuente en DATA_SOURCE_REGISTRY. |
| `anyo_seccionado` | BIGINT |  |

## `silver.ie_agrupaciones`

_Sin descripción._

Filas (estimadas): 13.153

| Columna | Tipo | Descripción |
|---|---|---|
| `candidacy_id` | VARCHAR | Candidatura dentro de una convocatoria ({election_id}-{código}). No es un partido. |
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `siglas` | VARCHAR |  |
| `denominacion` | VARCHAR |  |
| `agrupacion_cod` | VARCHAR |  |
| `agrupacion_id` | VARCHAR |  |

## `silver.population_normalized`

Población normalizada (antes de enriquecer con nombres).

Filas (estimadas): 712.392

| Columna | Tipo | Descripción |
|---|---|---|
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `geo_level` | VARCHAR |  |
| `anyo` | BIGINT | Año de referencia (Padrón: población a 1 de enero de ese año). |
| `sexo` | VARCHAR | T total, H hombres, M mujeres. |
| `poblacion` | HUGEINT | Personas empadronadas (cifra oficial). |
| `tipo_dato` | VARCHAR | Estado del dato según el INE (Definitivo, Provisional, Avance…). |
| `origen` | VARCHAR |  |
| `tabla_ine` | BIGINT |  |
| `_execution_id` | VARCHAR | Ejecución de ingesta que produjo la fila (linaje). |

## `silver.ref_ccaa`

Comunidades y ciudades autónomas (código INE).

Filas (estimadas): 19

| Columna | Tipo | Descripción |
|---|---|---|
| `ccaa_ine` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `nombre` | VARCHAR |  |

## `silver.ref_provincia`

Provincias con su comunidad autónoma.

Filas (estimadas): 52

| Columna | Tipo | Descripción |
|---|---|---|
| `provincia_ine` | VARCHAR |  |
| `geo_id` | VARCHAR | Identificador canónico ATLAS (ver docs/METHODOLOGY.md §1). |
| `nombre` | VARCHAR |  |
| `ccaa_ine` | VARCHAR |  |
| `parent_geo_id` | VARCHAR | geo_id del nivel superior. |

## `silver.xw_ccaa_mir_ine`

Equivalencia de códigos de CCAA Ministerio del Interior → INE (derivada de datos).

Filas (estimadas): 171

| Columna | Tipo | Descripción |
|---|---|---|
| `election_id` | VARCHAR | {tipo}-{AAAAMM}; tipo 02 Congreso, 03 Senado, 04 municipales, 07 europeas. |
| `codigo_ccaa_mir` | VARCHAR |  |
| `ccaa_ine` | VARCHAR |  |

## `ops.artifacts`

Ficheros escritos por cada ejecución, con hash SHA-256.

Filas (estimadas): 639

| Columna | Tipo | Descripción |
|---|---|---|
| `execution_id` | VARCHAR |  |
| `source_id` | VARCHAR | Fuente en DATA_SOURCE_REGISTRY. |
| `kind` | VARCHAR |  |
| `path` | VARCHAR |  |
| `sha256` | VARCHAR |  |
| `bytes` | BIGINT |  |
| `rows` | BIGINT |  |
| `created_at` | TIMESTAMP WITH TIME ZONE |  |

## `ops.executions`

Log de ejecuciones de ingesta (Data Operations Center).

Filas (estimadas): 25

| Columna | Tipo | Descripción |
|---|---|---|
| `execution_id` | VARCHAR |  |
| `source_id` | VARCHAR | Fuente en DATA_SOURCE_REGISTRY. |
| `dataset` | VARCHAR |  |
| `started_at` | TIMESTAMP WITH TIME ZONE |  |
| `finished_at` | TIMESTAMP WITH TIME ZONE |  |
| `duration_s` | DOUBLE |  |
| `status` | VARCHAR |  |
| `records_downloaded` | BIGINT |  |
| `records_processed` | BIGINT |  |
| `errors` | BIGINT |  |
| `error_detail` | VARCHAR |  |
| `version` | VARCHAR |  |
| `artifacts` | VARCHAR |  |

## `ops.quality_results`

Resultados de los controles de calidad por run.

Filas (estimadas): 549

| Columna | Tipo | Descripción |
|---|---|---|
| `run_id` | VARCHAR |  |
| `run_at` | TIMESTAMP WITH TIME ZONE |  |
| `check_name` | VARCHAR |  |
| `dimension` | VARCHAR |  |
| `dataset` | VARCHAR |  |
| `value` | DOUBLE |  |
| `threshold` | VARCHAR |  |
| `status` | VARCHAR |  |
| `detail` | VARCHAR |  |
