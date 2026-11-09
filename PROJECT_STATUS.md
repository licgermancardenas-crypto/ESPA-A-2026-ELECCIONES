# PROJECT STATUS — ATLAS SPAIN

Actualizado: 9 de noviembre de 2026 · Fase: **cimientos de datos (pasos 1–6 del roadmap, parciales)**.
Frontend web y Atlas AI todavía no están construidos; hay un tablero de Power BI sobre los datos reales.

## 1. Resumen en una línea

El motor de datos funciona de punta a punta con datos reales del INE, Eurostat y Congreso (≈ 1 millón de
filas, cartografía completa hasta sección censal, 30 controles de calidad), pero **no hay resultados
electorales cargados**: la fuente oficial (Infoelectoral) bloquea la descarga automatizada y requiere
bajar los ZIP a mano.

## 2. Qué está implementado

| Componente | Estado | Dónde |
|---|---|---|
| Registro de fuentes (62) con verificación en vivo | ✅ | `config/sources.yaml` → `DATA_SOURCE_REGISTRY.csv` |
| Motor de ingesta: log por ejecución, SHA-256 de cada fichero, linaje por fila, reintentos, detección de anti-bot | ✅ | `src/atlas_spain/ingestion/` |
| Conectores: INE Tempus (API), INE CSV, INE ficheros, Eurostat, Congreso, Infoelectoral | ✅ (21 fuentes) | `ingestion/connectors/` |
| Parser de ficheros DAT de Infoelectoral (03–12), sin DNI ni fecha de nacimiento | ✅ probado con fixtures; **sin probar con ficheros reales** | `parsers/infoelectoral_dat.py` |
| Warehouse DuckDB + dbt (staging/silver/gold), 9 modelos activos + 6 electorales en espera | ✅ | `dbt/` |
| Registro geográfico maestro (país → CCAA → provincia → municipio → distrito → sección) | ✅ | `gold.dim_geography` |
| Motor geoespacial: geometrías por nivel, áreas, centroides, GeoJSON para MapLibre | ✅ | `geo/build_geo.py`, `data/gold/geo/` |
| Motor electoral: D'Hondt (barrera + desempate LOREG), reparto de escaños del Congreso, concejales por población, régimen municipal, Senado, europeas | ✅ probado | `electoral/systems.py`, `electoral/dhondt.py` |
| Índices: ENP, Rae, Gallagher, Pedersen, Butler, margen, competitividad, dominio, eficiencia, votos sin escaño | ✅ (Python + SQL) | `electoral/indices.py`, `gold.election_indices` |
| Data Quality Center (completitud, validez, consistencia, frescura, cobertura, fiabilidad) + reconciliación D'Hondt vs escaños oficiales | ✅ | `quality/checks.py`, `ops.quality_results` |
| API FastAPI de solo lectura (fuentes, operaciones, calidad, territorios, SQL Explorer con bloqueo de escrituras) | ✅ | `api/main.py` |
| Tablero Power BI (PBIP generado por código, 8 páginas, mapas SVG por DAX), validado en Power BI Desktop | ✅ | `viz/powerbi_*.py`, `reports/powerbi/ATLAS_Espana.pbip` |
| Docker Compose (etl, api, postgis opcional) | ✅ escrito, **no probado** (no hay Docker en la máquina) | `docker-compose.yml` |
| Tests automatizados | ✅ 42 tests unitarios + 15 tests dbt | `tests/`, `dbt/models/schema.yml` |
| Documentación | ✅ | README, DATA_DISCOVERY_REPORT, DATA_DICTIONARY, docs/METHODOLOGY |

## 3. Datos descargados efectivamente (9-nov-2026)

| Fuente | Filas | Cobertura real |
|---|---|---|
| INE-DPOP-MUN — padrón por municipio y sexo | 710.652 | 8.136 municipios, **1996–2025** (52 tablas) |
| INE-DPOP-PROV / CCAA — padrón provincial y autonómico | 5.475 | 1996–**2021** (el INE congeló esas tablas; 2022–2025 se derivan sumando municipios) |
| INE-OCE — censo electoral | 196.896 | Solo el último proceso publicado: **autonómicas de Andalucía, mayo 2026**, 785 municipios, 6.510.832 electores CER |
| INE-SECCIONADO — cartografía censal | 36.477 secciones | 1-ene-2024 (10.460 distritos, 8.132 municipios) |
| INE-CODMUN — diccionarios de municipios | 40.657 | 2021–2025 (2020 no está en la URL esperada) |
| INE-CRE-PIB — PIB y PIB per cápita | 9.521 | 2000–2025 (provincias hasta 2024) |
| INE-EPA-PARO-CCAA — tasas de paro | 23.760 | CCAA, trimestral |
| INE-IPVA-MUN — índice de alquiler | 21.028 | municipios > 10.000 hab. |
| INE-DIRCE — empresas | 4.134 | provincia |
| INE-EJEC-HIPOT — ejecuciones hipotecarias | 1.908 | provincia |
| Eurostat (población NUTS3, PIB NUTS3, paro NUTS2) | 12.496 | España |
| CONGRESO-DIP — diputados activos y de baja | 412 | legislatura vigente |
| **Infoelectoral (Congreso, Senado, municipales, europeas, referéndums)** | **0** | **bloqueado** |

Bronze: 317 MB · warehouse: 151 MB · capas geo: 157 MB (todo en `data/`, fuera de git).

En gold hoy: `dim_geography` (55.141 unidades), `geo_boundaries` (55.140 geometrías), `fact_population`
(712.392), `fact_economy_province` (10.907), `fact_electoral_census` (4.770), `dim_data_source` (62).
EPA, DIRCE, alquiler, ejecuciones, Eurostat y diputados están en bronze **sin modelo gold todavía**.

## 4. Calidad (último run)

30 controles: 28 OK, 1 aviso, 1 fallo.
- ✅ 19 CCAA, 52 provincias, 8.132 municipios vigentes, 0 huérfanos, 0 municipios sin geometría.
- ✅ Total = hombres + mujeres en todas las filas; 29 años de padrón municipal.
- ⚠️ Suma de municipios vs cifra provincial publicada: coincide en 1.299 de 1.300 pares (1996–2021).
  Única diferencia: **Almería 1996, −76 habitantes** (probable municipio ausente en la tabla actual). Sin corregir.
- ❌ Infoelectoral: extracción bloqueada.

## 5. Fuentes pendientes y bloqueos

| Bloqueo | Qué hace falta |
|---|---|
| Infoelectoral (anti-bot Cloudflare) | Descargar ZIP con navegador → `data/landing/infoelectoral/`. Prioridad: `02202307_MUNI.zip`, `02201911_MUNI.zip`, `02201904_MUNI.zip`, `02201606_MUNI.zip`, `02201512_MUNI.zip`, `04202305_MUNI.zip`, `04201905_MUNI.zip`, `07202406_MUNI.zip`, `07201905_MUNI.zip`; después los `_MESA`. Luego `atlas ingest MIR-IE-CONG MIR-IE-MUN MIR-IE-EUR` y `atlas build`. |
| Balance de Criminalidad (interior.gob.es, anti-bot) | Descarga manual |
| MIVAU, Senado (403) | Descarga manual o contacto con el organismo |
| CNIG líneas límite (formulario) | Descarga manual |
| CIS (registro), YouTube (API key), Reddit (OAuth), Google Trends (sin API pública) | Credenciales / acceso autorizado |
| Autonómicas | Conectores por comunidad; fuentes verificadas: País Vasco, Navarra, Canarias, Madrid, Baleares, CLM. Resto sin investigar. |

## 6. Limitaciones conocidas

- **Sin resultados electorales** no hay participación, voto por partido, escaños ni índices calculados con datos.
  Los modelos existen y se activan solos cuando aparecen los ficheros.
- El parser de Infoelectoral se probó con líneas sintéticas construidas desde el diseño de registro, no con
  ficheros reales. Al cargar el primer ZIP hay que revisar: totales que cuadran, reconciliación D'Hondt
  (control automático) y la equivalencia de códigos CCAA Interior→INE.
- **Continuidad de partidos** (AP→PP, CiU→Junts, Podemos/IU→Sumar…): no implementada. Sin ella no se calculan
  volatilidad ni swing entre convocatorias.
- **Sistemas autonómicos**: parámetros cargados pero **ninguno verificado** contra la ley vigente.
- Límites municipales = disolución de secciones del INE, no líneas límite jurídicas del IGN.
- Secciones de un solo año (2024): no hay equivalencias entre años.
- Censo electoral del INE: solo el último proceso publicado.
- Índices compuestos (Political Transformation, Economic/Housing Pressure, Territorial Score) y modelos de ML
  (pronóstico, clustering, anomalías): no iniciados.
- Máquina de trabajo con 3,4 GB de RAM: la ingesta del padrón municipal tarda ~1 h 50 min (API del INE lenta).

## 7. Próximos pasos

1. Cargar los ZIP de Infoelectoral y validar el pipeline electoral con datos reales.
2. Tabla de continuidad de partidos (versionada, con reglas documentadas).
3. Modelos gold para EPA, DIRCE, alquiler, ejecuciones, Eurostat y diputados; renta ADRH por sección.
4. Frontend Next.js + MapLibre (Overview, Data Center, Political Map, Data Operations) sobre la API.
5. Autonómicas: conectores País Vasco, Navarra, Canarias y Madrid; verificar `electoral_systems.yaml`.
6. Atlas AI: agente con SQL controlado sobre la API (`/sql` ya valida y limita).
