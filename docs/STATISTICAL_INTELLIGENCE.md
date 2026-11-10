# ATLAS SPAIN — Statistical Intelligence

Documento de trabajo de la evolución "Statistical Intelligence". Se actualiza al cerrar cada fase.

## Fase 1 — Auditoría del producto (estado real, 10/11/2026)

### Arquitectura existente

| Pieza | Implementación real | Se reutiliza |
|---|---|---|
| Warehouse | DuckDB `data/warehouse/atlas.duckdb`, medallion bronze (Parquet con linaje) → silver/gold (dbt-duckdb) | Sí: única fuente de datos de la capa estadística |
| Geografía | `gold.dim_geography` (1 país, 19 CCAA, 52 provincias, 8.132 municipios, 10.460 distritos, 36.477 secciones), `gold.geo_boundaries`, GeoParquet de secciones INE 2024 | Sí: unidad de análisis y pesos espaciales |
| Motor electoral | `atlas_spain.electoral` (D'Hondt + reglas LOREG por tipo), `gold.election_indices` (ENEP, ENPP, Gallagher, margen, competitividad), `gold.volatility` (Pedersen por familias) | Sí: no se recalculan; se leen |
| Familias políticas | seed documentado `dbt/seeds/party_families.csv` (2.690 reglas) | Sí |
| API | FastAPI de solo lectura (`/sources`, `/operations/executions`, `/quality`, `/geo/{id}`, `/sql` validado) + servidor web (`/api/ficha`, `/api/secciones`) | Sí: se añade un router `/stats` |
| Web | HTML + módulos JS sin build, MapLibre 4.7.1, ECharts 5.5.1; publicada estática en Vercel (`atlas-spain-elecciones.vercel.app`) | Sí: se añade una vista y una pestaña en la ficha |
| Hallazgos | `atlas_spain.web.exportar` genera 6 hallazgos calculados (texto + lista de territorios) | Sí: se amplía con hallazgos estadísticos trazables |
| Operaciones | `ops.executions` (ingestas), `ops.quality_results` (63 controles), `ops.artifacts` | Sí: se añade `ops.stat_runs` para ejecuciones estadísticas |
| Librerías | numpy, pandas, scipy 1.17, statsmodels 0.14, scikit-learn 1.8, PySAL (libpysal + esda) instaladas | Sí |

### Cobertura real de variables (lo que se puede analizar)

| Variable | Nivel | Período | Origen |
|---|---|---|---|
| Participación, abstención, votos válidos, blancos, nulos, censo | municipio, provincia, CCAA, nacional | 37 convocatorias: 16 generales (1977–2023), 12 municipales (1979–2023), 9 europeas (1987–2024) | Ministerio del Interior (Infoelectoral) |
| Voto y escaños por familia política | ídem | ídem | Interior + tabla de familias |
| ENEP, ENPP, Gallagher, margen, competitividad | ídem | ídem | `gold.election_indices` |
| Volatilidad de Pedersen | ídem | entre convocatorias del mismo tipo | `gold.volatility` |
| Población (total, hombres, mujeres) | municipio, provincia, CCAA | 1996–2025 (Padrón) | INE |
| Superficie y densidad | municipio y superiores | geometría 2024 | INE (seccionado) |
| Renta neta media por persona | municipio, distrito, sección | **solo 2024** | INE (ADRH) |
| % de población de 65 y más | municipio, distrito, sección | **solo 2024** | INE (ADRH) |
| Población ADRH | municipio, distrito, sección | **solo 2024** | INE (ADRH) |
| Autonómicas | País Vasco y Asamblea de Madrid | 1980–2024 / 1983–2023 | Gobierno Vasco, Comunidad de Madrid |
| PIB per cápita, paro EPA | provincia / CCAA | series | Eurostat / INE |

### Limitaciones comprobadas

- **Senado no está cargado**: no se ofrecen análisis del Senado.
- **Autonómicas solo en dos comunidades.**
- **Renta y edad tienen un solo año (2024)**: no hay series ni variaciones de renta.
- **No hay resultados electorales por sección censal** en el warehouse (solo cartografía y ADRH). A nivel de sección solo se analizan variables demográficas y económicas.
- **379 códigos municipales con resultados electorales no existen en la geografía 2024** (fusiones, segregaciones y altas/bajas desde 1977). La capa estadística trabaja con la geografía vigente y los excluye de forma explícita (se informa cuántos en cada análisis); no se reasignan sin una tabla de correspondencias documentada.
- Municipios de menos de 250 habitantes en municipales (listas abiertas, ficheros 11/12) no están modelados.
- No hay datos de encuestas en el warehouse.
- Atlas AI no existe todavía.

## Fase 2 — Diseño de integración

### Principios

1. Un único origen: el warehouse. La capa estadística no copia datos: construye una vista analítica derivada (`gold.stat_panel`) con dbt y lee de ella.
2. El cálculo vive en el backend (Python). El navegador solo pinta resultados estructurados.
3. Todo análisis es reproducible: se registra método, versión del código, parámetros, filtros, huella del dataset, n y faltantes.
4. Métodos validados con tests contra implementaciones de referencia (SciPy / statsmodels / scikit-learn).

### Componentes

```
warehouse (gold)
  └─ gold.stat_panel            [dbt, NUEVO] formato largo: territorio × variable × período → valor (+ pesos)
  └─ seed stat_variables        [NUEVO] catálogo: definición, fórmula, unidad, fuente, denominador, cobertura
src/atlas_spain/stats/          [NUEVO] motor estadístico (numpy + scipy)
  ├─ descriptive.py             media (simple/ponderada), mediana, cuantiles, varianza (poblacional/muestral), DE, IQR, asimetría
  ├─ distributions.py           histograma (reglas de intervalos), densidad (KDE), ECDF, boxplot
  ├─ outliers.py                z, z modificado (MAD), IQR, Isolation Forest (opcional)
  ├─ correlation.py             Pearson / Spearman / Kendall, IC (Fisher z), p, matriz, parcial
  ├─ inference.py               t de Welch, proporciones, chi-cuadrado, ANOVA, Mann-Whitney, Kruskal, tamaños de efecto, Holm / BH, IC, bootstrap
  ├─ regression.py              MCO (errores robustos HC3), logística, Poisson (IRLS), ridge / lasso, diagnósticos
  ├─ spatial.py                 I de Moran global y local (LISA) con pesos de contigüidad
  ├─ surveys.py                 error estándar, margen, efecto de diseño, n efectivo de Kish
  ├─ data.py                    acceso al panel y filtros territoriales/temporales
  └─ runs.py                    registro de ejecuciones (ops.stat_runs)
API
  ├─ local: router /stats en atlas_spain.api (FastAPI existente)
  └─ publicada: función Python de Vercel (web/api/stats.py) con el mismo motor y el panel exportado
web
  ├─ vista "Estadística" en la barra lateral: Overview, Descriptiva, Distribuciones, Correlación, Contrastes, Regresión, Anomalías, Espacial, Encuestas, Constructor
  ├─ pestaña "Análisis estadístico" en la ficha territorial (posición en la distribución provincial/nacional)
  └─ Hallazgos: tarjetas estadísticas trazables (método, n, parámetros, enlace al análisis)
ops.stat_runs [NUEVO]          registro de cada ejecución; visible en Datos y calidad
```

### Por qué una función de Vercel y no cálculo en el navegador

La web publicada es estática. Los laboratorios (correlación, regresión, contrastes, constructor) necesitan cálculo bajo demanda. Se publica el mismo motor Python como función serverless con solo numpy y scipy (las dependencias pesadas de referencia —statsmodels, scikit-learn, PySAL— se usan en local para validar y para precalcular lo espacial). El panel se exporta comprimido junto a la función.

### Pendiente de decisión del usuario

- **Atlas AI** necesita un proveedor de modelo de lenguaje y una clave de API con coste por uso. Se diseña para que responda solo con resultados del motor (herramientas sobre `/stats`), pero no se activa sin esa decisión.
- **Encuestas**: el módulo se construye para registrar fichas técnicas publicadas; los datos se cargan desde un fichero revisado a mano (`config/encuestas.yaml`) con la fuente original de cada campo.

## Fases 3 a 7 — Implementación y validación (10/11/2026)

### Correcciones verificadas en la lógica existente

| Elemento | Problema comprobado | Corrección |
|---|---|---|
| `gold.volatility` (Pedersen) | Descartaba las familias que desaparecían entre convocatorias (generales 2023: 17,8 % en vez de lo correcto) y trataba refundaciones como cambio de voto (AP→PP en 1989 daba 32 %) | Suma sobre la unión de familias; seed `family_lineage` con continuidades documentadas; también municipales y europeas. Generales: 1982 42,5 %, 1989 6,3 %, 2015 37,2 %, 2023 16,7 % |
| Hallazgo "terremotos electorales" | Al haber volatilidad de todos los tipos mezclaba municipales | Solo generales |
| Servicio | Un método inexistente lanzaba excepción (500 en Vercel) | Error de petición controlado y registrado |

### Componentes entregados

| Componente | Ubicación | Estado |
|---|---|---|
| Panel analítico | `dbt/models/gold/stat_panel.sql` + seed `stat_variables` (19 variables con definición, fórmula, unidad, fuente, peso natural y limitaciones) | ✅ |
| Panel de servicio | `atlas_spain.stats.panel` → `data/gold/stat_panel.npz` (970 series × 8.132 municipios, vecinos de contigüidad; huella SHA-256) | ✅ |
| Motor | `atlas_spain.stats` (descriptiva, distribuciones, atípicos, correlación, inferencia, regresión, encuestas, espacial, electoral) | ✅ 40 tests contra statsmodels / scikit-learn / SciPy / PySAL |
| Servicio | `atlas_spain.stats.service` (14 métodos, ámbitos, pesos, cambios entre períodos, filtro de tamaño, registro) | ✅ 12 tests de integración (panel sintético + panel real) |
| API local | `GET/POST /api/stats` en `atlas web` | ✅ |
| API publicada | Función Python de Vercel `web/api/stats.py` (numpy + scipy, ≤ 60 s) | ✅ verificada en producción |
| Interfaz | Vista **Estadística**: Resumen, Descriptiva, Correlación (+ matriz y parcial), Regresión, Contrastes, Anomalías, Espacial, Probabilidad, Encuestas, Constructor | ✅ |
| Mapa | Pestaña **Estadística** en la ficha (España, comunidad, provincia, municipio); clusters LISA pintados sobre el mapa | ✅ |
| Hallazgos | 6 hallazgos estadísticos trazables (`atlas_spain.stats.hallazgos`) con método, parámetros, ejecución y "Ver análisis" | ✅ |
| Operaciones | Ejecuciones en `data/ops/stat_runs.jsonl` (local) y `web/data/core/stat_runs.json`; estado del motor en Datos y calidad | ✅ |
| Móvil | Barra lateral como menú, ficha como hoja inferior, portada adaptada | ✅ |

### Reproducibilidad

Cada respuesta incluye `ejecucion`: id, método, versión del motor, huella del panel, parámetros, n, faltantes, duración y fecha. Se puede exportar en JSON o como informe Markdown, y guardar en el navegador.

### Pendiente

- **Atlas AI**: requiere decidir proveedor de modelo y clave de API (coste por uso). Diseño previsto: el asistente solo responde llamando a `/api/stats` (herramientas), nunca con cifras propias.
- **Encuestas**: el registro (`config/encuestas.yaml`) está vacío; se cargarán fichas técnicas publicadas y revisadas.
- **Modelos de efectos mixtos**: no implementados; con un solo año de renta y edad, la estructura de datos aún no lo justifica.
- **Power BI**: `nac_indices.csv` contiene la volatilidad anterior hasta regenerar `atlas powerbi`.
- Senado, autonómicas de 15 comunidades y resultados por sección censal siguen sin datos en el warehouse.

## Perfiles territoriales (10/11/2026)

**Qué es:** tipología de los 8.132 municipios para analizar cómo vota cada tipo de territorio. **No son perfiles de votantes:** los resultados oficiales son agregados y no permiten saber qué vota cada persona. Para perfiles individuales hacen falta encuestas (p. ej., microdatos del CIS).

**Método** (`atlas_spain.stats.perfiles`): k-medias estratificado por tamaño (< 5.000, 5.000–50.000 y ≥ 50.000 habitantes) sobre log densidad, renta neta por persona 2024, % de 65+ 2024 y variación de población 2015–2025, estandarizadas y recortadas P1–P99; k ∈ {2, 3, 4} por silueta (grupos ≥ 5 %), semilla 0. Sin estratificar, el 80–90 % de la población caía en un único grupo urbano. Los nombres se generan por reglas a partir de los centroides (diferencias respecto a la mediana del estrato).

**Resultado:** 8 perfiles, 8.037 municipios (95 sin renta publicada quedan fuera). Silueta 0,27–0,30: los municipios forman un continuo y los límites son graduales.

**Voto por perfil:** Σ votos de cada familia / Σ votos a candidaturas; participación = Σ votantes / Σ censo. Validación: la suma de todos los perfiles reproduce el resultado nacional (generales 2023: PP 33,3 %, PSOE 32,0 %).

**Dónde se ve:** Estadística → Perfiles (tarjetas, voto por perfil, evolución 1977–2023, participación, mapa); perfil en la pestaña Estadística de cada municipio; variable «perfil» en Probabilidad; hallazgo «Cómo vota cada tipo de municipio».

**Siguiente paso para perfiles de votantes reales:** integrar microdatos de encuestas del CIS (barómetros y postelectorales). La descarga suele requerir registro, que debe hacer el usuario.

## Votantes: microdatos de encuestas del CIS (10/11/2026)

**Qué añade:** perfiles de **personas** (no de territorios): quién vota a cada partido por edad, sexo, estudios, situación laboral, ideología, tamaño de municipio y comunidad; qué vota cada grupo; ideología media por partido; trasvases declarados entre elecciones; evolución de cada electorado 2015–2023.

**Fuente:** encuestas postelectorales de generales del CIS — estudios 3126 (2015), 3145 (2016), 3248 (abril 2019), 3269 (noviembre 2019) y 3420 (2023); 33.265 entrevistas. Descargadas desde www.cis.es mediante el formulario de solicitud del CIS (autorizado por el usuario), guardadas sin modificar en `data/landing/cis/` con su SHA-256 (`data/gold/cis_estudios.json`). Registradas como `CIS-POSTELECTORALES` en `config/sources.yaml`.

**Armonización** (`atlas_spain.encuestas.cis`): recuerdo de voto (variable recodificada del CIS) traducido a las familias de Atlas; voto en la elección anterior; categorías comunes de sexo, edad (tramos), estudios, situación laboral, ideología (1–10), tamaño de municipio y comunidad. El estudio de 2015 se lee del fichero ASCII con su sintaxis SPSS (lector propio, con decimales con coma). Pesos: PESO del CIS en 2015, nov. 2019 y 2023; 1 en 2016 y abril 2019 (afijación proporcional, «ponderación: no procede» según sus fichas técnicas).

**Calidad comprobada:** el voto declarado se desvía del oficial 1,5–2,5 puntos por partido de media y la participación declarada (81–88 %) supera la real (66–72 %). Por eso, por defecto, los pesos se **calibran al resultado oficial** por familia (la abstención no se ajusta); el test `test_ajuste_reproduce_resultado_oficial` lo verifica. Intervalos de Wilson sobre el tamaño efectivo de Kish (no incluyen el efecto de conglomerados). 2023 es telefónica (CATI); las demás, presenciales.

**Privacidad:** los microdatos están anonimizados por el CIS y viajan solo dentro de la función de Vercel (`web/api/_lib`, no servida como estático: verificado 404). La web solo recibe resultados agregados.

**Dónde se ve:** Estadística → Votantes (CIS): quién vota a cada partido, qué vota cada grupo, ideología, trasvases (Sankey), evolución, calidad de la encuesta; hallazgo «Quién vota a cada partido: la edad».

### Votantes por comunidad autónoma (10/11/2026)

- Todos los análisis de votantes admiten un **ámbito autonómico**; los pesos se calibran al resultado oficial de esa comunidad (test `test_ajuste_regional_reproduce_resultado_de_la_comunidad`).
- Nueva vista **Comparar comunidades**: un rasgo del electorado de un partido (p. ej. % de 65+ entre votantes del PP) en cada comunidad, con IC 95 %, fiabilidad y pintado en el mapa.
- **Fiabilidad:** alta ≥ 150 votantes del partido en la muestra, media 50–149, baja < 50. En la evolución no se estiman puntos con menos de 50 votantes.
- **Provincias: no.** Muestras por provincia demasiado pequeñas (2023: mediana de 135 entrevistas; solo 6 de 52 superan 300). Para estimar perfiles provinciales haría falta un modelo (regresión multinivel con postestratificación, MRP) con tablas censales de edad × sexo × estudios por provincia (INE, Censo 2021).

### Votantes por provincia: MRP (10/11/2026)

Módulo `atlas_spain.encuestas.mrp` → `data/gold/mrp/*.json` y `web/data/mrp/*.json` (solo agregados; los microdatos no se publican).

1. **Marco:** Censo anual del INE, tabla 66601 (españoles de 18+ por provincia × sexo × edad × estudios). Año 2021 para 2015–2019 y 2023 para 2023. El grupo 18–24 toma 2/5 del grupo censal 15–19.
2. **Modelo:** logística multinomial con penalización L2 (sexo, edad, estudios, edad×sexo, edad×estudios, comunidad, provincia, comunidad×edad). C elegido por validación cruzada (0,15 en las cinco elecciones). Partidos con < 30 votantes en la encuesta van a «Otros».
3. **Postestratificación y calibración:** raking por provincia hasta reproducir exactamente abstención y voto oficial (blanco y nulo dentro de «Otros»).
4. **Incertidumbre:** bootstrap de entrevistas (40 réplicas), IC 95 % por percentiles.

**Validación (provincia fuera, provincias con ≥ 300 entrevistas):** error medio absoluto de la composición por edad de cada electorado frente a la estimación directa de la propia provincia (ajustada a censo y resultado oficial). Referencia: perfil nacional del partido calculado sin esa provincia.

| Elección | MRP | Perfil nacional | MRP mejor en |
|---|---|---|---|
| Abril 2019 (Madrid, Barcelona) | 3,5 pp | 3,5 pp | 4/11 |
| Noviembre 2019 | 4,2 pp | 4,6 pp | 7/10 |
| 2023 (Madrid, Barcelona, Sevilla, Valencia) | 4,3 pp | 4,7 pp | 14/22 |

Mejora modesta, concentrada en partidos regionales. Errores dominados por el ruido de la propia estimación directa (100–300 votantes por partido). La encuesta telefónica de 2023 sobrerrepresenta universitarios (46 % frente al 25 % del censo); el MRP lo corrige por construcción. Una primera versión de la validación filtraba la provincia evaluada en la referencia nacional y no ajustaba la estimación directa al censo: daba resultados engañosos y se corrigió.

#### Ampliación: situación laboral y tamaño de municipio (10/11/2026)

- El marco pasa a provincia × sexo × edad × estudios × situación laboral (5) × tamaño de municipio (4): 54.282 celdas.
- El INE no publica ese cruce. Se reconstruye por IPF en cada provincia y sexo con los márgenes edad × estudios (66601),
  edad × situación laboral (67128, españoles) y edad × tamaño (67078, municipios ≥ 500 hab.; el resto a «Hasta 10.000»;
  todas las nacionalidades). La asociación estudios–situación laboral (67131) se conserva como semilla del ajuste.
  Supuesto: tamaño independiente de estudios y situación laboral dentro de provincia × sexo × edad.
- El modelo añade situación laboral, tamaño, comunidad × tamaño y edad × situación laboral.
- Validación (misma metodología): abril 2019 3,6 frente a 3,5 pp; noviembre 2019 4,1 frente a 4,6 pp; 2023 4,4 frente a 4,7 pp (13/22).
